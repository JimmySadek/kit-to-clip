#!/usr/bin/env python3
"""Brand reel (neutral format, draft): one brand motif transformed through a headline, a stat, three points and a
lockup, cut on a beat grid. Works with any brand whose video pack has token contract v1 (brand/brand-pack.md in
Kit to Clip).

  build.py --brand <name> --slots <slots.json> --out <project-dir> [--canvas 1080x1920] [--platform tiktok]
           [--bpm 120] [--variant auto|1-18] [--music <file cut to the bpm>]

slots.json holds the slots in format.json (headline, stat_value, stat_label, points, tagline); each is checked
against its limits before anything is built. --variant picks the devices (motif entrance, headline style, flurry);
auto (the default) picks a set that differs from the last three brand reels for the same brand in the same folder,
and the choice is recorded in .reel-format.json.
Exit codes: 0 built, 2 bad slots, no usable brand or missing engine files.
"""
import argparse
import html
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]             # the kit-to-clip skill
FORMAT = json.loads((HERE / "format.json").read_text())


def fail(msg, lines=()):
    print(f"brand-reel: {msg}", file=sys.stderr)
    for line in lines:
        print(f"  - {line}", file=sys.stderr)
    sys.exit(2)


def check_slots(values):
    known, errors = {s["name"]: s for s in FORMAT["slots"]}, []
    for name in values:
        if name not in known:
            errors.append(f"unknown slot '{name}' (slots: {', '.join(known)})")
    for s in FORMAT["slots"]:
        v = values.get(s["name"])
        if v is None or v == "" or v == []:
            if s.get("required"):
                errors.append(f"{s['name']} is missing ({s['hint']})")
            continue
        items = v if s["type"] == "list" else [v]
        if s["type"] == "list" and (not isinstance(v, list) or len(v) != s["items"]):
            errors.append(f"{s['name']} needs exactly {s['items']} items")
            continue
        for item in items:
            if not isinstance(item, str) or not item.strip():
                errors.append(f"{s['name']} must be text")
            elif len(item) > s["maxChars"]:
                errors.append(f"{s['name']} is {len(item)} characters, the limit is {s['maxChars']}: \"{item}\"")
    return errors


def find_node_file(rel, start):
    """A file under node_modules, looking up from the project, then in the engine studio."""
    roots = [start, *start.parents]
    own = str(ROOT.parents[2])         # <studio>/.claude/skills/kit-to-clip -> <studio> in an installed studio
    for s in (os.environ.get("REEL_STUDIO"), os.environ.get("REEL_STUDIO_HOME"), own, str(Path.home() / ".kit-to-clip")):
        if s:
            roots.append(Path(s))
    for d in roots:
        p = d / "node_modules" / rel
        if p.is_file():
            return p
    return None


def recent_devices(out, brand, n=3):
    """Devices of the last n brand reels for this brand next to this project (newest first), for the variety audit."""
    found = []
    for f in out.parent.glob("*/.reel-format.json"):
        if f.parent == out:
            continue
        try:
            r = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if r.get("format") == FORMAT["id"] and r.get("brand") == brand and r.get("devices"):
            found.append((f.stat().st_mtime, r["devices"]))
    return [d for _, d in sorted(found, key=lambda x: x[0], reverse=True)[:n]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--slots", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--canvas", default="1080x1920", choices=FORMAT["canvases"])
    ap.add_argument("--platform", help="finish profile whose safe area the layout keeps clear (e.g. tiktok)")
    ap.add_argument("--bpm", type=float, default=FORMAT["default_bpm"])
    ap.add_argument("--variant", default="auto", help="1 to 18, or auto: differ from the last 3 brand reels for this brand")
    ap.add_argument("--music", help="an audio file already cut to --bpm, starting on the downbeat")
    a = ap.parse_args()

    values = json.loads(Path(a.slots).read_text())
    errors = check_slots(values)
    if errors:
        fail(f"{len(errors)} slot problem(s); nothing was built", errors)
    if not 60 <= a.bpm <= 180:
        fail("--bpm must be between 60 and 180")
    W, H = (int(v) for v in a.canvas.split("x"))
    safe = {"top": 0.08, "bottom": 0.08, "left": 0.08, "right": 0.08}
    if a.platform:
        prof = json.loads((ROOT / "finish" / "profiles.json").read_text())["profiles"].get(a.platform)
        if not prof:
            fail(f"no finish profile '{a.platform}'")
        safe = {k: max(v + 0.02, 0.06) for k, v in prof["safe"].items()}   # the platform's area plus a small margin
    safe_px = {k: round(v * (H if k in ("top", "bottom") else W)) for k, v in safe.items()}

    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = ROOT / "brand" / "scripts" / "bridge.py"
    r = subprocess.run([sys.executable, str(bridge), "--brand", a.brand, "--project", str(out), "--canvas", a.canvas, "--force"])
    if r.returncode:
        sys.exit(r.returncode)
    pack = json.loads((out / ".reel-brand.json").read_text()).get("pack", {})
    if pack.get("contract") != 1:
        fail(f"the {a.brand} pack has no token contract, so this neutral format cannot style it "
             "(add the --reel-* variables and REEL_BRAND to the pack: Kit to Clip brand/brand-pack.md)")

    vendor = out / "vendor"
    vendor.mkdir(exist_ok=True)
    for rel in ("gsap/dist/gsap.min.js", "gsap/dist/CustomEase.min.js"):
        src = find_node_file(rel, out)
        if not src:
            fail(f"{rel} not found in a node_modules above the project or in the engine folder")
        shutil.copy2(src, vendor / Path(rel).name)

    n = FORMAT["devices"]
    pick = lambda v: {"entrance": n["entrance"][(v - 1) % 3], "headline": n["headline"][((v - 1) // 3) % 3],
                      "flurry": n["flurry"][((v - 1) // 9) % 2]}
    recent = recent_devices(out, a.brand)
    if a.variant == "auto":
        # variety audit: share at most one device with each of the last three brand reels for this brand
        variant = next((v for v in range(1, 19) if all(sum(pick(v)[k] == r[k] for k in r) <= 1 for r in recent)), 1)
    else:
        variant = int(a.variant)
        if not 1 <= variant <= 18:
            fail("--variant must be 1 to 18, or auto")
    devices = pick(variant)
    repeats = [r for r in recent if r == devices]
    duration = round(FORMAT["beats"] * 60 / a.bpm, 3)
    music = ""
    if a.music:
        src = Path(a.music)
        if not src.is_file():
            fail(f"music file {src} not found")
        (out / "assets" / "audio").mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out / "assets" / "audio" / ("music" + src.suffix.lower()))
        music = (f'<audio id="music" src="assets/audio/music{src.suffix.lower()}" data-start="0" data-duration="{duration}" '
                 'data-track-index="10"></audio>')

    page = (HERE / "template" / "index.html").read_text()
    fills = {"__W__": str(W), "__H__": str(H), "__DUR__": str(duration), "__MUSIC__": music,
             "__SLOT_points__": "".join(f"<li>{html.escape(p)}</li>" for p in values["points"])}
    for s in FORMAT["slots"]:
        if s["type"] == "text":
            fills[f"__SLOT_{s['name']}__"] = html.escape(values[s["name"]])
    for k, val in fills.items():
        page = page.replace(k, val)
    (out / "index.html").write_text(page)
    config = {"canvas": [W, H], "bpm": a.bpm, "duration": duration, "safe": safe_px, "devices": devices}
    (out / "format-config.js").write_text("window.REEL_FORMAT = " + json.dumps(config) + ";\n")
    record = {"format": FORMAT["id"], "format_version": FORMAT["version"], "format_status": FORMAT["status"],
              "brand": a.brand, "pack": pack, "canvas": [W, H], "platform": a.platform, "bpm": a.bpm,
              "beats": FORMAT["beats"], "duration": duration, "variant": variant, "devices": devices, "slots": values,
              "music": bool(a.music)}
    (out / ".reel-format.json").write_text(json.dumps(record, indent=1))
    print(f"brand-reel: built {out} ({W}x{H}, {duration} s at {a.bpm:g} BPM, variant {variant}: "
          f"{devices['entrance']} / {devices['headline']} / {devices['flurry']})")
    if repeats:
        print("  ⚠ same devices as a recent brand reel for this brand; pass another --variant unless the repeat is a deliberate motif")
    print("  next: npx hyperframes lint, finish.py check, finish.py safe"
          + (f" --platform {a.platform}" if a.platform else "") + ", then look at snapshots before rendering")


if __name__ == "__main__":
    main()
