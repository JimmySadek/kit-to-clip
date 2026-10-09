#!/usr/bin/env python3
"""Kit to Clip cards: reusable scenes for brief videos, composed into one HyperFrames project.

  cards.py list [--purpose stat] [--tier takeover] [--json]
  cards.py compose --brand <id> --spec <spec.json> --out <project-dir> [--canvas 1080x1920] [--platform tiktok]

spec.json: {"bpm": 120, "words": "transcript.json", "cards": [{"card": "headline", "slots": {...}, "dur": 3,
            "anchor": "beat:0"}, ...]}. Without an anchor a card starts when the one before it ends; with one it starts
on that beat (bpm), word (the transcript, from `hyperframes transcribe`) or second ("t:4.5"), and the anchor is written
as data-anchor so `finish.py anchors` can check it after later edits. Slots are checked against cards.json before
anything is built. Exit codes: 0 built or listed, 2 bad spec, no usable brand or missing engine files.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]             # the kit-to-clip skill
CARDS_DIR = ROOT / "formats" / "cards"
REGISTRY = json.loads((CARDS_DIR / "cards.json").read_text())
BY_ID = {c["id"]: c for c in REGISTRY["cards"]}


def fail(msg, lines=()):
    print(f"cards: {msg}", file=sys.stderr)
    for line in lines:
        print(f"  - {line}", file=sys.stderr)
    sys.exit(2)


def check(spec):
    errors = []
    if not isinstance(spec.get("cards"), list) or not spec["cards"]:
        return ["spec needs a non-empty \"cards\" list"]
    for i, c in enumerate(spec["cards"], 1):
        card = BY_ID.get(c.get("card"))
        if not card:
            errors.append(f"card {i}: unknown card '{c.get('card')}' (cards: {', '.join(BY_ID)})")
            continue
        slots, known = c.get("slots") or {}, {s["name"]: s for s in card["slots"]}
        for name in slots:
            if name not in known:
                errors.append(f"card {i} ({card['id']}): unknown slot '{name}' (slots: {', '.join(known)})")
        for s in card["slots"]:
            v = slots.get(s["name"])
            if v in (None, "", []):
                if s.get("required"):
                    errors.append(f"card {i} ({card['id']}): {s['name']} is missing ({s['hint']})")
                continue
            items = v if s.get("type") == "list" else [v]
            if s.get("type") == "list" and not (isinstance(v, list) and s["min"] <= len(v) <= s["max"]):
                errors.append(f"card {i} ({card['id']}): {s['name']} needs {s['min']} to {s['max']} items")
                continue
            for item in items:
                plain = re.sub(r"[*|]", "", item) if isinstance(item, str) else ""
                if not plain.strip():
                    errors.append(f"card {i} ({card['id']}): {s['name']} must be text")
                elif len(plain) > s["maxChars"]:
                    errors.append(f"card {i} ({card['id']}): {s['name']} is {len(plain)} characters, the limit is {s['maxChars']}: \"{plain}\"")
        dur = c.get("dur", card["dur"][0])
        if not (isinstance(dur, (int, float)) and card["dur"][0] <= dur <= card["dur"][1]):
            errors.append(f"card {i} ({card['id']}): dur must be {card['dur'][0]} to {card['dur'][1]} s")
    return errors


def anchor_time(anchor, bpm, words):
    kind, _, val = anchor.partition(":")
    if kind == "t":
        return float(val)
    if kind == "beat":
        if not bpm:
            fail(f"anchor {anchor} needs \"bpm\" in the spec")
        return int(val) * 60 / bpm
    if kind == "word":
        if words is None:
            fail(f"anchor {anchor} needs \"words\" (a transcript from hyperframes transcribe) in the spec")
        text, _, k = val.partition("#")
        norm = lambda w: re.sub(r"[^\w']", "", w.lower())
        hits = [w for w in words if norm(w.get("text", "")) == norm(text)]
        idx = int(k or 1) - 1
        if not 0 <= idx < len(hits):
            fail(f"anchor {anchor}: that word is not in the transcript")
        return hits[idx]["start"]
    fail(f"unknown anchor '{anchor}' (beat:N, word:text, t:seconds)")


def words_html(text):
    """One span per word; *focal* words take the accent; punctuation stays on the word before it (no stray space)."""
    lines = []
    for ln in text.split("|"):
        words = []                                   # [text, focal]
        for part in re.split(r"(\*[^*]+\*)", ln.strip()):
            if not part:
                continue
            focal = part.startswith("*")
            for w in part.strip("*").split():
                if words and re.fullmatch(r"[.,;:!?%)\u2019\u201d]+", w):
                    words[-1][0] += w                # "." after "*One platform*" joins "platform"
                else:
                    words.append([w, focal])
        lines.append('<span class="ln">' + " ".join(f'<span class="w{" accent" if f else ""}">{html.escape(w)}</span>'
                                                  for w, f in words) + "</span>")
    return "".join(lines)


def card_html(i, c, at, dur):
    s = c.get("slots") or {}
    e = lambda k: html.escape(s.get(k, ""))
    body = {
        "headline": lambda: f'<div class="hl display">{words_html(s["text"])}</div>',
        "stat": lambda: (f'<div class="stat-value display">{e("value")}</div><div class="rule"></div>'
                         f'<div class="stat-label label">{e("label")}</div>'
                         + (f'<div class="stat-source body">{e("source")}</div>' if s.get("source") else "")),
        "list": lambda: ((f'<div class="list-title display">{e("title")}</div>' if s.get("title") else "")
                         + '<ul class="list-items body">' + "".join(f"<li>{html.escape(x)}</li>" for x in s["items"]) + "</ul>"),
        "quote": lambda: f'<div class="quote-text display">“{e("quote")}”</div><div class="quote-by body">{e("by")}</div>',
        "lower-third": lambda: (f'<div class="lt"><span class="name display">{e("name")}</span>'
                                + (f'<span class="role body">{e("role")}</span>' if s.get("role") else "") + "</div>"),
        "lockup": lambda: ('<img alt="logo"><div class="rule"></div>'
                           + (f'<div class="tagline body">{e("tagline").replace("|", "<br>")}</div>' if s.get("tagline") else "")
                           + (f'<div class="cta label accent">{e("cta")}</div>' if s.get("cta") else "")),
    }[c["card"]]()
    anchor = f' data-anchor="{html.escape(c["anchor"])}"' if c.get("anchor") else ""
    return (f'<section id="card-{i}" class="card card-{c["card"]}" data-card="{c["card"]}" data-at="{at:g}" data-dur="{dur:g}"{anchor}>'
            f"{body}</section>")


def find_node_file(rel, start):
    roots = [start, *start.parents]
    for s in (os.environ.get("REEL_STUDIO"), os.environ.get("REEL_STUDIO_HOME"), str(ROOT.parents[2]), str(Path.home() / ".kit-to-clip")):
        if s:
            roots.append(Path(s))
    for d in roots:
        if (d / "node_modules" / rel).is_file():
            return d / "node_modules" / rel
    return None


def cmd_list(a):
    rows = [c for c in REGISTRY["cards"] if (not a.purpose or c["purpose"] == a.purpose) and (not a.tier or c["tier"] == a.tier)]
    if a.json:
        print(json.dumps(rows, indent=1))
        return
    for c in rows:
        slots = ", ".join(f"{s['name']}{'' if s.get('required') else '?'} <= {s['maxChars']}" for s in c["slots"])
        print(f"{c['id']:<12} {c['tier']:<9} {c['purpose']:<12} {c['dur'][0]:g}-{c['dur'][1]:g} s  {slots}")


def cmd_compose(a):
    spec_path = Path(a.spec).resolve()
    spec = json.loads(spec_path.read_text())
    errors = check(spec)
    if errors:
        fail(f"{len(errors)} spec problem(s); nothing was built", errors)
    words = json.loads((spec_path.parent / spec["words"]).read_text()) if spec.get("words") else None
    W, H = (int(v) for v in a.canvas.split("x"))
    safe = {"top": 0.08, "bottom": 0.08, "left": 0.08, "right": 0.08}
    if a.platform:
        prof = json.loads((ROOT / "finish" / "profiles.json").read_text())["profiles"].get(a.platform)
        if not prof:
            fail(f"no finish profile '{a.platform}'")
        safe = {k: max(v + 0.02, 0.06) for k, v in prof["safe"].items()}
    safe_px = {k: round(v * (H if k in ("top", "bottom") else W)) for k, v in safe.items()}
    placed, t = [], 0.0
    for c in spec["cards"]:
        dur = float(c.get("dur", BY_ID[c["card"]]["dur"][0]))
        at = anchor_time(c["anchor"], spec.get("bpm"), words) if c.get("anchor") else t
        placed.append((c, round(at, 3), dur))
        t = at + dur
    duration = round(max(at + d for _, at, d in placed), 3)
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(ROOT / "brand" / "scripts" / "bridge.py"), "--brand", a.brand, "--project", str(out),
                        "--canvas", a.canvas, "--force"])
    if r.returncode:
        sys.exit(r.returncode)
    pack = json.loads((out / ".reel-brand.json").read_text()).get("pack", {})
    if pack.get("contract") != 1:
        fail(f"the {a.brand} pack has no token contract, so cards cannot style it (Kit to Clip brand/brand-pack.md)")
    (out / "vendor").mkdir(exist_ok=True)
    for rel in ("gsap/dist/gsap.min.js", "gsap/dist/CustomEase.min.js"):
        src = find_node_file(rel, out)
        if not src:
            fail(f"{rel} not found in a node_modules above the project or in the engine folder")
        shutil.copy2(src, out / "vendor" / Path(rel).name)
    music = ""
    if spec.get("music"):
        src = spec_path.parent / spec["music"]
        (out / "assets" / "audio").mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out / "assets" / "audio" / ("music" + src.suffix.lower()))
        music = (f'<audio id="music" src="assets/audio/music{src.suffix.lower()}" data-start="0" data-duration="{duration}" '
                 'data-track-index="10" data-timeline-role="music"></audio>')
    page = (CARDS_DIR / "template" / "index.html").read_text()
    for k, v in {"__W__": str(W), "__H__": str(H), "__DUR__": str(duration), "__MUSIC__": music,
                 "__CARDS__": "\n      ".join(card_html(i, c, at, d) for i, (c, at, d) in enumerate(placed))}.items():
        page = page.replace(k, v)
    (out / "index.html").write_text(page)
    cfg = {"canvas": [W, H], "safe": safe_px, "duration": duration,
           "cards": [{"card": c["card"], "at": at, "dur": d} for c, at, d in placed]}
    (out / "cards-config.js").write_text("window.CARDS = " + json.dumps(cfg) + ";\n")
    (out / ".reel-format.json").write_text(json.dumps({"format": "cards", "brand": a.brand, "pack": pack, "canvas": [W, H],
                                                       "platform": a.platform, "duration": duration, "spec": spec}, indent=1))
    print(f"cards: built {out} ({W}x{H}, {duration} s, {len(placed)} cards: " + ", ".join(f"{c['card']}@{at:g}s" for c, at, _ in placed) + ")")
    print("  next: npx hyperframes lint, finish.py check, finish.py hook, finish.py safe" + (f" --platform {a.platform}" if a.platform else "")
          + (", finish.py anchors" if any(c.get("anchor") for c in spec["cards"]) else "") + ", then look at stills (npx hyperframes snapshot --describe false)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--purpose"); p.add_argument("--tier"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("compose"); p.add_argument("--brand", required=True); p.add_argument("--spec", required=True)
    p.add_argument("--out", required=True); p.add_argument("--canvas", default="1080x1920"); p.add_argument("--platform")
    a = ap.parse_args()
    {"list": cmd_list, "compose": cmd_compose}[a.cmd](a)


if __name__ == "__main__":
    main()
