#!/usr/bin/env python3
"""Teaser loop (neutral format, trial): a still teaser brought to life as a seamless loop. It opens on the finished
layout, so the first frame (and the thumbnail) reads at once; the background breathes around its focus, an accent ring
pulses, the accent line draws under the focal word and sweeps away, the media floats, and every motion is periodic,
so the last frame flows into the first. Works with any brand whose video pack has token contract v1.

  build.py --brand <id> --slots <slots.json> --out <project-dir> [--canvas 1080x1080]

slots.json holds the slots in format.json. Pictures (background, media) are copied from the brand's own files into
assets/media/ with their source path and sha256 in .reel-format.json; they are placed, cropped, masked and moved,
never repainted. Exit codes: 0 built, 2 bad slots, no usable brand or missing engine files.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]             # the kit-to-clip skill
FORMAT = json.loads((HERE / "format.json").read_text())
DEFAULTS = {"background_crop": [0, 0, 1, 1], "focus": [0.85, 0.16], "media_box": [0.42, 0.6, 0.5], "media_edge": "none",
            "logo_box": [0.1, 0.1, 0.22], "headline_box": [0.11, 0.27, 0.66], "headline_size": 0.068, "field": "radial-dots",
            "duration": 8, "background_opacity": 1, "headline_leading": None,
            "background_motion": "wave", "background_feather": [0.07, 0.05, 0.07, 0.05]}


def fail(msg, lines=()):
    print(f"teaser-loop: {msg}", file=sys.stderr)
    for line in lines:
        print(f"  - {line}", file=sys.stderr)
    sys.exit(2)


def check_slots(values, base):
    known, errors = {s["name"]: s for s in FORMAT["slots"]}, []
    for name in values:
        if name not in known:
            errors.append(f"unknown slot '{name}' (slots: {', '.join(known)})")
    for s in FORMAT["slots"]:
        v = values.get(s["name"])
        if v is None:
            if s.get("required"):
                errors.append(f"{s['name']} is missing ({s['hint']})")
            continue
        t = s["type"]
        if t == "text":
            plain = re.sub(r"[*|]", "", v) if isinstance(v, str) else ""
            if not plain.strip():
                errors.append(f"{s['name']} must be text")
            elif len(plain) > s["maxChars"]:
                errors.append(f"{s['name']} is {len(plain)} characters, the limit is {s['maxChars']}: \"{plain}\"")
            elif v.count("*") % 2:
                errors.append(f"{s['name']}: the focal word needs a * on both sides")
        elif t == "image":
            p = Path(os.path.expanduser(v)) if isinstance(v, str) else None
            p = p if p is None or p.is_absolute() else base / p
            if not p or not p.is_file():
                errors.append(f"{s['name']}: picture not found: {v}")
        elif t == "box":
            if not (isinstance(v, list) and len(v) == s["size"] and all(isinstance(x, (int, float)) for x in v)):
                errors.append(f"{s['name']} needs {s['size']} numbers ({s['hint']})")
        elif t == "choice" and v not in s["choices"]:
            errors.append(f"{s['name']} must be one of {', '.join(s['choices'])}")
        elif t == "number" and not isinstance(v, (int, float)):
            errors.append(f"{s['name']} must be a number")
    o = values.get("background_opacity", 1)
    if isinstance(o, (int, float)) and not 0.3 <= o <= 1:
        errors.append("background_opacity must be 0.3 to 1")
    d = values.get("duration", DEFAULTS["duration"])
    if isinstance(d, (int, float)) and not 6 <= d <= 12:
        errors.append("duration must be 6 to 12 seconds")
    return errors


def headline_html(text):
    lines = []
    for ln in text.split("|"):
        parts = re.split(r"\*([^*]+)\*", ln.strip())
        # the accent line is a real underline on a transparent copy of the word, so it skips the descenders
        out = "".join(html.escape(p) if i % 2 == 0 else
                      f'<span class="focal">{html.escape(p)}<i class="uline" aria-hidden="true">{html.escape(p)}</i></span>'
                      for i, p in enumerate(parts))
        lines.append(f'<span class="ln">{out}</span>')
    return "".join(lines)


def find_node_file(rel, start):
    """A file under node_modules, looking up from the project, then in the engine studio."""
    roots = [start, *start.parents]
    for s in (os.environ.get("REEL_STUDIO"), os.environ.get("REEL_STUDIO_HOME"), str(ROOT.parents[2]), str(Path.home() / ".kit-to-clip")):
        if s:
            roots.append(Path(s))
    for d in roots:
        p = d / "node_modules" / rel
        if p.is_file():
            return p
    return None


def picture(src, out, name):
    dst = out / "assets" / "media" / (name + src.suffix.lower())
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(dst)], capture_output=True, text=True)
    w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
    return dst, [w, h], hashlib.sha256(src.read_bytes()).hexdigest()


def edge_colour(img):
    """Median colour of the picture's outer border (its outermost pixels at 64x36): the canvas takes it, and the
    template feathers the picture's edges into it, so a crop that runs past the picture never shows a seam."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(img), "-vf", "scale=64:36:flags=area,format=rgb24", "-f", "rawvideo", "-"],
                       capture_output=True)
    px = r.stdout
    if len(px) < 64 * 36 * 3:
        return None
    at = lambda x, y: px[(y * 64 + x) * 3:(y * 64 + x) * 3 + 3]
    border = [at(x, y) for x in range(64) for y in (0, 35)] + [at(x, y) for y in range(36) for x in (0, 63)]
    med = [sorted(c)[len(c) // 2] for c in zip(*border)]
    return "#%02x%02x%02x" % tuple(med)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--slots", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--canvas", default="1080x1080", choices=FORMAT["canvases"])
    a = ap.parse_args()

    slots_path = Path(a.slots).resolve()
    values = json.loads(slots_path.read_text())
    errors = check_slots(values, slots_path.parent)
    if errors:
        fail(f"{len(errors)} slot problem(s); nothing was built", errors)
    v = {**DEFAULTS, **values}
    W, H = (int(x) for x in a.canvas.split("x"))

    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(ROOT / "brand" / "scripts" / "bridge.py"), "--brand", a.brand, "--project", str(out),
                        "--canvas", a.canvas, "--force"])
    if r.returncode:
        sys.exit(r.returncode)
    pack = json.loads((out / ".reel-brand.json").read_text()).get("pack", {})
    if pack.get("contract") != 1:
        fail(f"the {a.brand} pack has no token contract, so this neutral format cannot style it (Kit to Clip brand/brand-pack.md)")
    (out / "vendor").mkdir(exist_ok=True)
    for rel in ("gsap/dist/gsap.min.js", "gsap/dist/CustomEase.min.js"):
        src = find_node_file(rel, out)
        if not src:
            fail(f"{rel} not found in a node_modules above the project or in the engine folder")
        shutil.copy2(src, out / "vendor" / Path(rel).name)

    resolve = lambda s: (Path(os.path.expanduser(s)) if Path(os.path.expanduser(s)).is_absolute() else slots_path.parent / s)
    sources, bg_html, media_html, cfg_extra = {}, "", "", {}
    if values.get("background"):
        dst, size, sha = picture(resolve(values["background"]), out, "background")
        sources["background"] = {"source": str(resolve(values["background"])), "sha256": sha, "size": size}
        # the wave layer paints the same file as a CSS background, so the picture is one media node, not two
        bg_html = (f'<div id="bg" data-safe-ignore><img src="assets/media/{dst.name}" alt="">'
                   f'<div class="wave" style="background-image: url(\'assets/media/{dst.name}\')"></div></div>')
        cfg_extra.update(background_crop=v["background_crop"], background_size=size, background_edge=edge_colour(dst))
    if values.get("media"):
        dst, size, sha = picture(resolve(values["media"]), out, "media")
        sources["media"] = {"source": str(resolve(values["media"])), "sha256": sha, "size": size}
        edge = v["media_edge"]
        media_html = f'<div id="media" class="{edge}" data-safe-ignore><img src="assets/media/{dst.name}" alt=""></div>'
        cfg_extra.update(media_box=v["media_box"], media_aspect=size[0] / size[1])

    page = (HERE / "template" / "index.html").read_text()
    for k, val in {"__W__": str(W), "__H__": str(H), "__DUR__": str(v["duration"]), "__BACKGROUND__": bg_html,
                   "__MEDIA__": media_html, "__SLOT_headline__": headline_html(values["headline"])}.items():
        page = page.replace(k, val)
    (out / "index.html").write_text(page)
    config = {"canvas": [W, H], "duration": v["duration"], "margin": round(min(W, H) * 0.1), "focus": v["focus"], "field": v["field"],
              "logo_box": v["logo_box"], "headline_box": v["headline_box"], "headline_size": v["headline_size"],
              "headline_leading": v["headline_leading"], "background_opacity": v["background_opacity"],
              "background_motion": v["background_motion"], "background_feather": v["background_feather"], **cfg_extra}
    (out / "format-config.js").write_text("window.REEL_FORMAT = " + json.dumps(config) + ";\n")
    record = {"format": FORMAT["id"], "format_version": FORMAT["version"], "format_status": FORMAT["status"], "brand": a.brand,
              "pack": pack, "canvas": [W, H], "duration": v["duration"], "slots": values, "pictures": sources}
    (out / ".reel-format.json").write_text(json.dumps(record, indent=1))
    print(f"teaser-loop: built {out} ({W}x{H}, {v['duration']} s loop, brand {a.brand}"
          + (f", {len(sources)} brand picture(s)" if sources else ", generated field") + ")")
    print("  next: npx hyperframes lint, finish.py check, finish.py hook, stills (npx hyperframes snapshot --describe false) side by side with the reference, "
          "then render and finish.py loop --gif-profile <profile>")


if __name__ == "__main__":
    main()
