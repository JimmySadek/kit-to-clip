#!/usr/bin/env python3
"""Explainer (neutral format, trial): a narrated explainer where the voice comes first. Every scene starts on the
first word of its sentence (anchored, so finish.py anchors can prove it), captions are burned in word by word, and the
look comes from one of five illustration styles over the brand's tokens. Works with any brand whose video pack has
token contract v1 (brand/brand-pack.md in Kit to Clip).

  build.py --brand <name> --voice voice.wav --transcript transcript.json --scenes scenes.json --out <project-dir>
           [--style clean|cut-paper|risograph|sketchbook|isometric] [--canvas 1080x1920] [--platform tiktok]
           [--music bed.wav] [--no-captions]

voice.wav: the narration (the voice-over power, or a recording). transcript.json: word timings from
`hyperframes transcribe voice.wav` ([{"text", "start", "end"}, ...]). scenes.json: one scene per sentence,
[{"say": "the sentence's first words as spoken", "headline": "...", "sub": "...", "visual": "path/to/image.svg"}].
Exit codes: 0 built, 2 bad input, no usable brand or missing engine files.
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]             # the kit-to-clip skill
FORMAT = json.loads((HERE / "format.json").read_text())
sys.path.insert(0, str(HERE.parent / "brand-reel"))
from build import find_node_file   # noqa: E402  (shared helper: gsap from the project or the engine)

HEADLINE_MAX, SUB_MAX = 34, 60
TAIL = 1.4                         # seconds after the voice for the end card
norm = lambda w: re.sub(r"[^\w']", "", w.lower())       # the same normalisation finish.py anchors uses


def fail(msg, lines=()):
    print(f"explainer: {msg}", file=sys.stderr)
    for line in lines:
        print(f"  - {line}", file=sys.stderr)
    sys.exit(2)


def locate(scenes, words):
    """Each scene's first word index in the transcript, in order, or errors."""
    starts, errors, cursor = [], [], 0
    for n, s in enumerate(scenes, 1):
        want = [norm(w) for w in s["say"].split() if norm(w)][:3]
        if not want:
            errors.append(f"scene {n}: 'say' has no words")
            starts.append(None)
            continue
        found = None
        for i in range(cursor, len(words) - len(want) + 1):
            if [norm(words[i + k]["text"]) for k in range(len(want))] == want:
                found = i
                break
        if found is None:
            errors.append(f"scene {n}: \"{' '.join(want)}\" was not found in the transcript after scene {n - 1}"
                          " (use the words exactly as spoken, and keep scenes in script order)")
        else:
            cursor = found + 1
        starts.append(found)
    return starts, errors


def caption_lines(words, max_chars=24, max_words=4):
    """Short caption lines: break on punctuation, on length and on a pause."""
    lines, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        text = " ".join(words[j]["text"] for j in cur)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = nxt is not None and nxt["start"] - w["end"] > 0.35
        if re.search(r"[.!?,;:]$", w["text"]) or len(cur) >= max_words or len(text) >= max_chars or pause or nxt is None:
            lines.append(cur)
            cur = []
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--scenes", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--style", default="clean", choices=FORMAT["styles"])
    ap.add_argument("--canvas", default="1080x1920", choices=FORMAT["canvases"])
    ap.add_argument("--platform", help="finish profile whose safe area the layout keeps clear (e.g. tiktok)")
    ap.add_argument("--music", help="a music bed; it plays under the voice at a low level")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--brand-skill", help="the brand kit folder holding kit-to-clip/pack.json (skips the search)")
    ap.add_argument("--script", help="the approved script (text): captions use its spelling, the voice's timings stay")
    a = ap.parse_args()

    voice, transcript = Path(a.voice), Path(a.transcript)
    for p in (voice, transcript, Path(a.scenes)):
        if not p.is_file():
            fail(f"{p} not found")
    try:
        words = json.loads(transcript.read_text())
        scenes = json.loads(Path(a.scenes).read_text())
    except ValueError as e:
        fail(f"unreadable JSON: {e}")
    if isinstance(words, dict):
        words = words.get("words") or []
    words = [w for w in words if str(w.get("text", "")).strip()]
    if not words:
        fail(f"{transcript} has no words (transcribe the voice first: hyperframes transcribe)")
    if a.script:
        # speech recognition misspells names ("Padle" for "Padel"); the approved script is the truth for the words
        said = [t for t in Path(a.script).read_text(encoding="utf-8").split() if norm(t)]
        if len(said) == len(words):
            fixed = [(w["text"], t) for w, t in zip(words, said) if norm(w["text"]) != norm(t)]
            words = [{**w, "text": t} for w, t in zip(words, said)]
            if fixed:
                print("explainer: captions follow the script: " + ", ".join(f"{a_!r} -> {b_!r}" for a_, b_ in fixed))
        else:
            print(f"explainer: ⚠ the script has {len(said)} words and the voice {len(words)}, so the captions keep the "
                  "transcript's words; read them and fix transcript.json by hand if a name is misheard")
    errors = []
    if not isinstance(scenes, list) or not 2 <= len(scenes) <= 8:
        fail("scenes.json must be a list of 2 to 8 scenes")
    for n, s in enumerate(scenes, 1):
        if not str(s.get("say", "")).strip():
            errors.append(f"scene {n}: 'say' is missing (the first words of its sentence, as spoken)")
        if not str(s.get("headline", "")).strip():
            errors.append(f"scene {n}: 'headline' is missing")
        elif len(s["headline"]) > HEADLINE_MAX:
            errors.append(f"scene {n}: headline is {len(s['headline'])} characters, the limit is {HEADLINE_MAX}: \"{s['headline']}\"")
        if len(s.get("sub", "")) > SUB_MAX:
            errors.append(f"scene {n}: sub is {len(s['sub'])} characters, the limit is {SUB_MAX}")
        if s.get("visual") and not Path(s["visual"]).is_file():
            errors.append(f"scene {n}: visual {s['visual']} not found")
    if errors:
        fail(f"{len(errors)} problem(s); nothing was built", errors)
    starts, errors = locate(scenes, words)
    if errors:
        fail(f"{len(errors)} scene(s) not found in the voice; nothing was built", errors)

    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(voice)],
                           capture_output=True, text=True)
    try:
        voice_s = float(probe.stdout.strip())
    except ValueError:
        fail(f"{voice} is not an audio file ffprobe can read")
    duration = round(max(voice_s, words[-1]["end"]) + TAIL, 3)
    W, H = (int(v) for v in a.canvas.split("x"))
    safe = {"top": 0.08, "bottom": 0.08, "left": 0.08, "right": 0.08}
    if a.platform:
        prof = json.loads((ROOT / "finish" / "profiles.json").read_text())["profiles"].get(a.platform)
        if not prof:
            fail(f"no finish profile '{a.platform}'")
        safe = {k: max(v + 0.02, 0.06) for k, v in prof["safe"].items()}
    safe_px = {k: round(v * (H if k in ("top", "bottom") else W)) for k, v in safe.items()}

    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(ROOT / "brand" / "scripts" / "bridge.py"), "--brand", a.brand, "--project", str(out),
                        "--canvas", a.canvas, "--force", *(["--brand-skill", a.brand_skill] if a.brand_skill else [])])
    if r.returncode:
        sys.exit(r.returncode)
    pack = json.loads((out / ".reel-brand.json").read_text()).get("pack", {})
    if pack.get("contract") != 1:
        fail(f"the {a.brand} pack has no token contract, so this neutral format cannot style it (brand/brand-pack.md)")
    vendor = out / "vendor"
    vendor.mkdir(exist_ok=True)
    for rel in ("gsap/dist/gsap.min.js", "gsap/dist/CustomEase.min.js"):
        src = find_node_file(rel, out)
        if not src:
            fail(f"{rel} not found in a node_modules above the project or in the engine folder")
        shutil.copy2(src, vendor / Path(rel).name)
    style_dir = HERE / "styles" / a.style
    for f in ("style.css", "style.js"):
        shutil.copy2(style_dir / f, out / f)
    audio_dir = out / "assets" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(voice, audio_dir / ("voice" + voice.suffix.lower()))
    (out / "transcript.json").write_text(json.dumps(words, indent=1))      # the corrected words, for finish.py anchors
    audio = (f'<audio id="voice" src="assets/audio/voice{voice.suffix.lower()}" data-start="0" data-duration="{duration}" '
             'data-track-index="10"></audio>')
    if a.music:
        m = Path(a.music)
        if not m.is_file():
            fail(f"music file {m} not found")
        shutil.copy2(m, audio_dir / ("music" + m.suffix.lower()))
        audio += (f'\n<audio id="music" src="assets/audio/music{m.suffix.lower()}" data-start="0" data-duration="{duration}" '
                  'data-track-index="11" data-volume="0.22"></audio>')

    scene_html, scene_cfg = [], []
    for n, (s, i) in enumerate(zip(scenes, starts)):
        first = norm(words[i]["text"])
        occurrence = sum(1 for w in words[:i + 1] if norm(w["text"]) == first)
        t0 = round(words[i]["start"], 3)
        t1 = round(words[starts[n + 1]]["start"], 3) if n + 1 < len(scenes) else round(max(voice_s, words[-1]["end"]), 3)
        visual = ""
        if s.get("visual"):
            src = Path(s["visual"])
            dst = Path("assets") / f"scene-{n + 1}{src.suffix.lower()}"
            (out / dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out / dst)
            visual = f'<img class="scene-visual" src="{dst.as_posix()}" alt="">'
        sub = f'<p class="scene-sub">{html.escape(s["sub"])}</p>' if s.get("sub") else ""
        anchor = f"word:{first}" + (f"#{occurrence}" if occurrence > 1 else "")
        scene_html.append(
            f'<section class="scene" id="scene-{n + 1}" data-scene="{n + 1}">'
            f'<div class="scene-art" data-seed="{n + 1}">{visual}</div>'
            f'<h1 class="scene-headline" data-anchor="{anchor}" data-at="{t0}">{html.escape(s["headline"])}</h1>{sub}</section>')
        scene_cfg.append({"n": n + 1, "start": t0, "end": t1, "anchor": anchor, "has_visual": bool(visual)})

    lines = [] if a.no_captions else caption_lines(words)
    cap_html = "".join(
        f'<div class="cap-line" id="cap-{k}">' + " ".join(f'<span class="cap-word" id="w-{j}">{html.escape(words[j]["text"])}</span>'
                                                           for j in line) + "</div>" for k, line in enumerate(lines))
    cap_cfg = []
    for k, line in enumerate(lines):          # one line on screen at a time: a line ends when the next begins
        nxt = words[lines[k + 1][0]]["start"] if k + 1 < len(lines) else float("inf")
        cap_cfg.append({"id": f"cap-{k}", "start": round(words[line[0]]["start"], 3),
                        "end": round(min(words[line[-1]]["end"] + 0.12, nxt), 3),
                        "words": [{"id": f"w-{j}", "start": round(words[j]["start"], 3)} for j in line]})

    page = (HERE / "template" / "index.html").read_text()
    for k, v in {"__W__": str(W), "__H__": str(H), "__DUR__": str(duration), "__AUDIO__": audio, "__STYLE__": a.style,
                 "__SCENES__": "\n".join(scene_html), "__CAPTIONS__": cap_html}.items():
        page = page.replace(k, v)
    (out / "index.html").write_text(page)
    config = {"canvas": [W, H], "duration": duration, "voice_end": round(max(voice_s, words[-1]["end"]), 3), "safe": safe_px,
              "style": a.style, "scenes": scene_cfg, "captions": cap_cfg}
    (out / "format-config.js").write_text("window.REEL_FORMAT = " + json.dumps(config) + ";\n")
    record = {"format": FORMAT["id"], "format_version": FORMAT["version"], "format_status": FORMAT["status"], "brand": a.brand,
              "pack": pack, "canvas": [W, H], "platform": a.platform, "style": a.style, "duration": duration,
              "scenes": scenes, "captions": not a.no_captions, "music": bool(a.music)}
    (out / ".reel-format.json").write_text(json.dumps(record, indent=1))
    print(f"explainer: built {out} ({W}x{H}, {duration} s, {len(scenes)} scenes on their words, style {a.style}"
          + (", captions" if lines else "") + (", music bed" if a.music else "") + ")")
    print("  next: npx hyperframes lint, finish.py check, finish.py safe" + (f" --platform {a.platform}" if a.platform else "")
          + ", finish.py anchors --project <dir> (words from transcript.json), then look at the stills (npx hyperframes snapshot --describe false) before rendering")


if __name__ == "__main__":
    main()
