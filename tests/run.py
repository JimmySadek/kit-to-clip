#!/usr/bin/env python3
"""Negative-control tests for the Kit to Clip engine: every check must fail on a fixture built to break it, and pass on
its control. Fixtures are generated into a temporary folder (compositions, videos made with ffmpeg, brand packs,
slots), so nothing binary is committed.

  python3 tests/run.py            all cases (source scripts/env.sh of the skill first; needs node, ffmpeg, Chrome)
  python3 tests/run.py safe gif   only cases whose name contains one of the words

Exit 0 when every case behaves as expected, 1 otherwise. Do not loosen a check to make a case pass: fix the check.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO if (REPO / "SKILL.md").is_file() else REPO / "addons" / "kit-to-clip"   # public repo = the skill / workshop
FINISH = SKILL / "finish" / "scripts" / "finish.py"
BRIDGE = SKILL / "brand" / "scripts" / "bridge.py"
BRAND_REEL = SKILL / "formats" / "neutral" / "brand-reel" / "build.py"
FORMATS = SKILL / "formats" / "scripts" / "formats.py"
DETECT = SKILL / "scripts" / "brand.py"
PACK_GUIDE = SKILL / "brand" / "brand-pack.md"
TEASER = SKILL / "formats" / "neutral" / "teaser-loop" / "build.py"
EXPLAINER = SKILL / "formats" / "neutral" / "explainer" / "build.py"
ASSETS = SKILL / "brand" / "scripts" / "assets.py"
PACK = "kit-to-clip"                   # the video pack folder inside a brand kit
DELIVER = SKILL / "formats" / "scripts" / "deliver.py"
EFFECTS = SKILL / "sound" / "scripts" / "effects.py"
PITCH = SKILL / "sound" / "scripts" / "pitch.py"
SCORE = SKILL / "sound" / "scripts" / "score.py"
REFERENCE = SKILL / "scripts" / "reference.py"
STYLES = SKILL / "scripts" / "styles.py"
EXPORT = REPO / "packaging" / "export-engine.sh"     # workshop only: the public repo has no packaging/
TOOLBOX_PY = SKILL / "scripts" / "toolbox.py"
MEMORY_PY = SKILL / "scripts" / "memory.py"
LEAKSCAN = REPO / "packaging" / "leakscan.py"       # workshop only
INSTALLER = SKILL / "setup" / "install.sh"


def find_engine():
    """A folder whose node_modules has HyperFrames' packages: the engine studio, the repo, or a folder in the repo."""
    tries = [os.environ.get("REEL_STUDIO"), os.environ.get("REEL_STUDIO_HOME"), str(Path.home() / ".kit-to-clip"), str(REPO),
             *sorted(str(d) for d in REPO.iterdir() if d.is_dir())]
    for s in tries:
        if s and all((Path(s) / "node_modules" / f).is_file() for f in ("gsap/dist/gsap.min.js", "puppeteer-core/package.json")):
            return Path(s).resolve()
    sys.exit("tests: no engine found (node_modules with gsap and puppeteer-core); run the engine setup or set REEL_STUDIO_HOME")


# ---------------------------------------------------------------- fixtures
ROOT = """<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><script src="vendor/gsap.min.js"></script>{head}
<style>html, body {{ width: 1080px; height: 1920px; margin: 0; overflow: hidden; background: #111; }}
#root {{ position: relative; width: 100%; height: 100%; }}</style></head>
<body><div id="root" data-composition-id="t" data-start="0" data-width="1080" data-height="1920"{dur}>
{body}
</div><script>{root_js}</script></body></html>
"""
HOST = ('<div id="el-scene" data-composition-id="scene" data-composition-src="compositions/{src}" data-start="1" '
        'data-duration="3" data-track-index="1" data-width="1080" data-height="1920"></div>')
SUB = """<!doctype html><html lang="en"><head><meta charset="UTF-8"></head><body><template id="scene-template">
<style>#root {{ position: absolute; inset: 0; }} .cap {{ position: absolute; left: 160px; top: {top}px;
font: 64px Helvetica, sans-serif; color: #fff; }}</style>
<div id="root" data-composition-id="scene" data-width="1080" data-height="1920" data-duration="3">
<div class="cap" id="cap">Tap to pay</div></div>
<script>{js}</script></template></body></html>
"""
OK_JS = ('(function () { const tl = gsap.timeline({ paused: true }); tl.from("#cap", { opacity: 0, duration: 0.5 })'
         '.to("#cap", { x: 10, duration: 2.5 }); window.__timelines["scene"] = tl; })();')
REGISTER = 'window.__timelines["t"] = gsap.timeline({ paused: true });'
COMPOSITIONS = {
    "inside": {},
    "bottom-band": {"top": 1400},
    "no-root-timeline": {"root_js": "// the root timeline is never registered"},
    "no-text": {"body": '<div style="position:absolute;left:200px;top:600px;width:300px;height:300px;background:#e33"></div>'},
    "zero-duration": {"dur": "", "body": '<div style="position:absolute;left:200px;top:600px;color:#fff;font-size:64px">Hello</div>'},
    "missing-sub": {"src": "nowhere.html"},
    "sub-throws": {"js": OK_JS + " applyBrandHelpers();"},
    "seek-throws": {"js": '(function () { const tl = gsap.timeline({ paused: true }); tl.to("#cap", { x: 10, duration: 3, '
                          'onUpdate() { if (tl.time() > 2) throw new Error("bad frame"); } }); window.__timelines["scene"] = tl; })();'},
    "remote-font": {"head": '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">'},
    # first-three-seconds fixtures: a title on screen and moving from 0 s, and one broken opening per rule
    "hook-good": {"body": '<div id="t" style="position:absolute;left:100px;top:700px;font:bold 96px Helvetica;color:#fff">Launch day</div>',
                  "root_js": 'window.__timelines["t"] = gsap.timeline({ paused: true }).to("#t", { x: 60, duration: 4 });'},
    "hook-late-text": {"body": '<div id="b" style="position:absolute;left:100px;top:500px;width:400px;height:400px;background:#e33"></div>'
                               '<div id="t" style="position:absolute;left:100px;top:1000px;font:bold 96px Helvetica;color:#fff;opacity:0">Launch day</div>',
                       "root_js": 'window.__timelines["t"] = gsap.timeline({ paused: true }).to("#b", { x: 200, duration: 4 }).to("#t", { opacity: 1, duration: 0.3 }, 3.5);'},
    "snippet-no-timeline": {"body": '<div style="position:absolute;left:100px;top:700px;font:bold 96px Helvetica;color:#fff">Still</div>',
                            "root_js": "// no timeline registered"},
    # motion trace fixtures: a headline that jumps between two hidden positions inside a mask, then is revealed; a box that moves
    "trace": {"body": '<div style="position:absolute;left:100px;top:600px;width:500px;height:100px;overflow:hidden">'
                      '<div id="hid" data-track="headline" style="position:absolute;top:110px;font:bold 80px Helvetica;color:#fff">Hi</div></div>'
                      '<div id="box" data-track="box" style="position:absolute;left:100px;top:1000px;width:120px;height:120px;background:#e33"></div>',
              "root_js": 'window.__timelines["t"] = gsap.timeline({ paused: true }).set("#hid", { y: -500 }, 0.5).set("#hid", { y: 0 }, 1.0)'
                         '.to("#hid", { y: -110, duration: 0.4 }, 2.5).to("#box", { x: 300, duration: 1, ease: "power2.inOut" }, 1.0);'},
    "trace-dup": {"body": '<div id="a" data-track="same" style="position:absolute;left:100px;top:600px;width:80px;height:80px;background:#e33"></div>'
                          '<div id="b" data-track="same" style="position:absolute;left:300px;top:600px;width:80px;height:80px;background:#33e"></div>',
                  "root_js": 'window.__timelines["t"] = gsap.timeline({ paused: true }).to("#a", { x: 50, duration: 1 });'},
    "hook-static": {"body": '<div id="t" style="position:absolute;left:100px;top:700px;font:bold 96px Helvetica;color:#fff">Launch day</div>',
                    "root_js": 'window.__timelines["t"] = gsap.timeline({ paused: true }).to("#t", { x: 60, duration: 2 }, 1.5);'},
}


def make_composition(base, name, gsap):
    o = COMPOSITIONS[name]
    d = base / "comp" / name
    if d.exists():                       # a fixture is shared by the safe and console cases
        return d
    (d / "vendor").mkdir(parents=True)
    (d / "compositions").mkdir()
    shutil.copy2(gsap, d / "vendor" / "gsap.min.js")
    (d / "index.html").write_text(ROOT.format(head=o.get("head", ""), dur=o.get("dur", ' data-duration="4"'),
                                              body=o.get("body", HOST.format(src=o.get("src", "scene.html"))),
                                              root_js=o.get("root_js", REGISTER)))
    (d / "compositions" / "scene.html").write_text(SUB.format(top=o.get("top", 900), js=o.get("js", OK_JS)))
    return d


VIDEOS = {  # ffmpeg recipes (540x960, 30 fps)
    "clean": ["-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=4"],
    "three-colors": ["-f", "lavfi", "-i", "color=c=red:s=540x960:r=30:d=1", "-f", "lavfi", "-i", "color=c=blue:s=540x960:r=30:d=1",
                     "-f", "lavfi", "-i", "color=c=green:s=540x960:r=30:d=1", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0"],
    "still": ["-f", "lavfi", "-i", "color=c=0x0F3D2E:s=540x960:r=30:d=3"],
    "flash": ["-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=4", "-vf",
              "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(n,60,61)'"],
    "flat-first": ["-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=4", "-vf",
                   "drawbox=x=0:y=0:w=iw:h=ih:color=0x0F3D2E:t=fill:enable='lt(n,1)'"],
    "freeze": ["-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=4", "-vf", "loop=loop=90:size=1:start=45"],
    "box-oneway": ["-f", "lavfi", "-i", "color=c=0x0F3D2E:s=540x960:r=30:d=4", "-f", "lavfi", "-i",
                   "color=c=0xFFB000:s=120x120:r=30:d=4", "-filter_complex", "[0:v][1:v]overlay=x='(t/4)*(W-w)':y=420"],
    "box-circle": ["-f", "lavfi", "-i", "color=c=0x0F3D2E:s=540x960:r=30:d=4", "-f", "lavfi", "-i",
                   "color=c=0xFFB000:s=120x120:r=30:d=4", "-filter_complex",
                   "[0:v][1:v]overlay=x='210+150*cos(2*PI*t/4)':y='420+150*sin(2*PI*t/4)'"],
    "box-circle-20s": ["-f", "lavfi", "-i", "color=c=0x0F3D2E:s=540x676:r=30:d=20", "-f", "lavfi", "-i",
                       "color=c=0xFFB000:s=120x120:r=30:d=20", "-filter_complex",
                       "[0:v][1:v]overlay=x='210+150*cos(2*PI*t/4)':y='280+150*sin(2*PI*t/4)'"],
}
ALPHA_LOOP = ["-f", "lavfi", "-i", "color=c=black@0.0:s=320x320:r=30:d=4,format=rgba", "-f", "lavfi", "-i",
              "color=c=0xFFB000:s=80x80:r=30:d=4,format=rgba", "-filter_complex",
              "[0:v][1:v]overlay=x='120+80*cos(2*PI*t/4)':y='120+80*sin(2*PI*t/4)',format=yuva444p10le",
              "-c:v", "prores_ks", "-profile:v", "4444"]


def make_video(base, name):
    d = base / "video"
    d.mkdir(exist_ok=True)
    if name == "alpha-loop":                          # a transparent loop, as `hyperframes render --format mov` makes
        out = d / "alpha-loop.mov"
        if not out.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", *ALPHA_LOOP, str(out)], check=True)
        return out
    out = d / f"{name}.mp4"
    if out.exists():
        return out
    subprocess.run(["ffmpeg", "-v", "error", "-y", *VIDEOS[name], "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


SOUND_CUES = [1.0, 2.0, 3.0, 4.0, 5.0]        # the seconds where the picture flashes and a click is meant to sound


def make_sound_video(base, name, shift_ms=0, silent=()):
    """A 6 s clip: the picture flashes white at each cue time; a click sounds at each cue time moved by shift_ms
    (positive = sound early), except at the cues in `silent`. Made with ffmpeg and the stdlib, nothing binary is committed."""
    import math
    import struct
    import wave
    out = base / "video" / f"{name}.mp4"
    if out.exists():
        return out
    out.parent.mkdir(exist_ok=True)
    sr = 48000
    buf = [0.0] * (sr * 6)
    for i, cue in enumerate(SOUND_CUES):
        if i in silent:
            continue
        s = round((cue - shift_ms / 1000) * sr)
        for k in range(int(0.08 * sr)):
            buf[s + k] += 0.6 * min(1.0, k / (0.003 * sr)) * math.exp(-k / (0.02 * sr)) * math.sin(2 * math.pi * 1200 * k / sr)
    wav = out.with_suffix(".wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, x)) * 32767)) for x in buf))
    flash = "+".join(f"between(n,{round(c * 30)},{round(c * 30) + 2})" for c in SOUND_CUES)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=6", "-i", str(wav),
                    "-vf", f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='{flash}'", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)], check=True)
    wav.unlink()
    return out


def make_spiky_video(base, name, gain_db):
    """A 6 s clip whose sound is a quiet tone with short loud spikes (peak about 19 dB over its loudness): the kind of mix
    a loudness step that cannot add gain past the peak ceiling leaves too quiet. gain_db moves the whole mix."""
    out = base / "video" / f"{name}.mp4"
    if out.exists():
        return out
    out.parent.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=6", "-f", "lavfi", "-i",
                    "aevalsrc='0.12*sin(2*PI*220*t)+0.9*sin(2*PI*1500*t)*lt(mod(t,0.5),0.008)':s=48000:d=6", "-af", f"volume={gain_db}dB",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", str(out)], check=True)
    return out


def make_brand_repo(base):
    """A test brand repo: a provisional pack with the token contract, a broken pack, and a pack missing tokens."""
    r = base / "brand-repo"
    kit = r / ".agents" / "skills" / "test-brand"
    (kit / PACK / "templates").mkdir(parents=True)
    (kit / "assets").mkdir()
    (kit / "SKILL.md").write_text("---\nname: test-brand\ndescription: test-only brand for the Kit to Clip tests\n---\n")
    for bg, name in (("#0F3D2E", "on-light"), ("#FFFFFF", "on-dark")):
        (kit / "assets" / f"logo-{name}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 100"><rect x="0" y="20" width="60" height="60" '
            f'fill="#FFB000"/><text x="80" y="78" font-family="Helvetica, sans-serif" font-weight="700" font-size="72" '
            f'fill="{bg}">test</text></svg>')
    (kit / PACK / "pack.json").write_text(json.dumps({
        "schema": 1, "brand": "test", "name": "test brand", "version": "0.1", "status": "provisional", "contract": 1,
        "copy": {"assets/brand/logo/test-logo-on-light.svg": "assets/logo-on-light.svg",
                 "assets/brand/logo/test-logo-on-dark.svg": "assets/logo-on-dark.svg"},
        "templates": {"brand.css": "templates/brand.css", "brand-snippets.js": "templates/brand-snippets.js"}}))
    (kit / PACK / "templates" / "brand.css").write_text(""":root {
  --reel-bg: #0F3D2E; --reel-fg: #FFFFFF; --reel-accent: #FFB000; --reel-on-accent: #0F3D2E;
  --reel-muted: rgba(255, 255, 255, .7); --reel-surface: #0A2A20;
  --reel-font-display: "Helvetica Neue", Arial, sans-serif; --reel-weight-display: 800;
  --reel-font-body: "Helvetica Neue", Arial, sans-serif; --reel-weight-body: 500;
  --reel-font-label: "Helvetica Neue", Arial, sans-serif; --reel-weight-label: 700;
  --reel-ease-enter: cubic-bezier(0.22, 1, 0.36, 1); --reel-ease-exit: cubic-bezier(0.64, 0, 0.78, 0);
  --reel-ease-move: cubic-bezier(0.65, 0, 0.35, 1); --reel-dur-enter: 0.5; --reel-dur-exit: 0.35; --reel-dur-move: 0.7;
  --reel-energy: steady; --reel-radius: 8px; --reel-line: 8px;
}
""")
    (kit / PACK / "templates" / "brand-snippets.js").write_text(
        'window.REEL_BRAND = { name: "test", logo: { onDark: "assets/brand/logo/test-logo-on-dark.svg", '
        'onLight: "assets/brand/logo/test-logo-on-light.svg" }, motif: { kind: "shape", svg: \'<svg viewBox="0 0 100 100">'
        '<rect x="20" y="20" width="60" height="60" fill="currentColor"/></svg>\' } };\n')
    broken = r / ".agents" / "skills" / "broken-brand" / PACK
    broken.mkdir(parents=True)
    (broken / "pack.json").write_text('{"brand": ')
    thin = r / ".agents" / "skills" / "thin-brand" / PACK
    (thin / "templates").mkdir(parents=True)
    (thin / "pack.json").write_text(json.dumps({"schema": 1, "brand": "thin", "name": "thin", "contract": 1,
                                                 "templates": {"brand.css": "templates/brand.css"}}))
    (thin / "templates" / "brand.css").write_text(":root { --reel-bg: #000; }\n")
    (r / "reels" / "videos").mkdir(parents=True)
    return r


def make_detect_repos(base):
    """One repo per brand-detection state, and a pack with its own formats (good, draft, broken)."""
    d = base / "detect"
    kit = d / "one" / ".agents" / "skills" / "one-brand"
    (kit / PACK / "formats").mkdir(parents=True)
    (kit / "SKILL.md").write_text("---\nname: one-brand\ndescription: test brand kit\n---\n")
    (kit / PACK / "pack.json").write_text(json.dumps({"schema": 1, "brand": "one", "name": "One", "version": "1",
                                                        "status": "approved", "formats": "formats"}))
    (kit / PACK / "formats" / "README.md").write_text("# One's formats\n")
    for fid, row in {"good": {"name": "Good", "status": "approved"}, "wip": {"name": "Work in progress", "status": "draft"},
                     "bad": {"status": "approved"}}.items():
        (kit / PACK / "formats" / fid).mkdir()
        (kit / PACK / "formats" / fid / "format.json").write_text(json.dumps(
            {"schema": 1, "id": fid, "made_for": "clip", "journey": "../README.md", **row}))
    (d / "pointer" / "reels").mkdir(parents=True)
    (d / "pointer" / "reels" / "brand.json").write_text(json.dumps({"kit": str(kit)}))
    (d / "kit" / ".agents" / "skills" / "acme-brand").mkdir(parents=True)
    (d / "kit" / ".agents" / "skills" / "acme-brand" / "SKILL.md").write_text("---\nname: acme-brand\ndescription: Acme colours, fonts and logos\n---\n")
    (d / "unchosen" / "docs" / "brand" / "direction-a").mkdir(parents=True)
    (d / "none").mkdir()
    (d / "chosen").mkdir()
    home = d / "home"                                  # a stand-in home folder with one installed brand kit
    zeta = home / ".claude" / "skills" / "zeta-brand"
    (zeta / "assets" / "logo").mkdir(parents=True)
    (zeta / "SKILL.md").write_text("---\nname: zeta-brand\ndescription: Zeta colours, fonts and logos\n---\n")
    (zeta / "assets" / "logo" / "zeta-logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (home / ".claude" / "skills" / "zeta-icons" / "assets").mkdir(parents=True)   # not a brand kit: no logo, no -brand name
    (home / ".claude" / "skills" / "zeta-icons" / "SKILL.md").write_text("---\nname: zeta-icons\ndescription: brand icons\n---\n")
    return d


def make_guide_kit(base):
    """The example pack in brand-pack.md, written out as a kit: keeps the public guide honest."""
    import re
    text = PACK_GUIDE.read_text()
    block = lambda lang, after: re.search(rf"{re.escape(after)}.*?```{lang}\n(.*?)```", text, re.S).group(1)
    kit = base / "guide-kit" / "acme-brand"
    (kit / PACK / "templates").mkdir(parents=True)
    pack = json.loads(block("json", "`kit-to-clip/pack.json`"))
    (kit / PACK / "pack.json").write_text(json.dumps(pack))
    (kit / PACK / "templates" / "brand.css").write_text(block("css", "`kit-to-clip/templates/brand.css`"))
    (kit / PACK / "templates" / "brand-snippets.js").write_text(block("js", "window.REEL_BRAND"))
    (kit / PACK / "guide.md").write_text("# Acme\n")
    for src in pack["copy"].values():
        (kit / src).parent.mkdir(parents=True, exist_ok=True)
        (kit / src).write_text("<svg xmlns='http://www.w3.org/2000/svg'/>" if src.endswith(".svg") else "placeholder")
    return kit


def make_anchor_projects(base, gsap):
    """Scenes anchored to beats, words and seconds, with real GSAP timelines: one project in time, one per way to drift or
    fail. bpm 120, so beat 4 is 2.0 s. The check reads when the timeline really starts each element, not data-at."""
    d = base / "anchors"
    words = [{"text": "Meet", "start": 0.4, "end": 0.7}, {"text": "the", "start": 0.7, "end": 0.8},
             {"text": "launch", "start": 1.2, "end": 1.6}, {"text": "launch.", "start": 5.0, "end": 5.4}]
    box = lambda i, extra="": (f'<div id="{i}" style="position:absolute;left:100px;top:{300 + 150 * (len(i) % 5)}px;width:160px;height:90px;'
                               f'background:#e33;{extra}" ')
    tw = lambda js: f'window.__timelines["t"] = gsap.timeline({{ paused: true }}){js};'
    projects = {
        # declared times are deliberately a little off: only the timeline counts, so these still pass
        "ok": (box("s1") + 'data-anchor="beat:4" data-start="2.1"></div>' + box("s2", "opacity:0;") + 'data-anchor="word:launch" data-start="1.3"></div>'
               + box("s3") + 'data-anchor="word:launch#2" data-at="5.2"></div>'
               + '<div id="host" data-composition-id="end" data-composition-src="compositions/end.html" data-start="3" data-duration="3" '
                 'data-track-index="1" data-width="1080" data-height="1920"></div>',
               tw('.to("#s1", { x: 200, duration: 0.5 }, 2.0).to("#s2", { opacity: 1, duration: 0.3 }, 1.2).to("#s3", { x: 200, duration: 0.5 }, 5.0)')),
        # the tween starts 0.2 s after its declared data-at: the declaration says 2.0, the timeline plays 2.2
        "drift": (box("s1") + 'data-anchor="beat:4" data-at="2.0"></div>', tw('.to("#s1", { x: 200, duration: 0.5 }, 2.2)')),
        # a hit that lands on the beat: the move ends at 2.0 s
        "lands": (box("s1") + 'data-anchor="beat:4"></div>', tw('.to("#s1", { x: 300, duration: 0.8, ease: "power3.out" }, 1.2)')),
        "late-scene": (box("s1") + 'data-anchor="beat:4" data-anchor-scope="scene"></div>', tw('.to("#s1", { x: 200, duration: 0.5 }, 3.0)')),
        "late-hit": (box("s1") + 'data-anchor="beat:4"></div>', tw('.to("#s1", { x: 200, duration: 0.5 }, 3.0)')),
        "never-moves": (box("s1") + 'data-anchor="beat:4" data-start="2.0"></div>', tw("")),
        # text parked in a mask jumps while hidden: that is not motion, so this never "starts" at 0.5 s
        "hidden-jump": ('<div id="m" style="position:absolute;left:100px;top:600px;width:500px;height:100px;overflow:hidden">'
                        '<div id="s1" data-anchor="beat:4" style="position:absolute;top:110px;font:bold 80px Helvetica;color:#fff">Hi</div></div>',
                        tw('.set("#s1", { y: -500 }, 0.5).set("#s1", { y: 0 }, 1.0).to("#s1", { y: -110, duration: 0.4 }, 2.0)')),
        "no-word": (box("s1") + 'data-anchor="word:rocket" data-start="1.0"></div>', tw('.to("#s1", { x: 200, duration: 0.5 }, 1.0)')),
        "none": (box("s1") + 'data-start="1.0"></div>', tw('.to("#s1", { x: 200, duration: 0.5 }, 1.0)')),
    }
    for name, (body, js) in projects.items():
        (d / name / "vendor").mkdir(parents=True)
        (d / name / "compositions").mkdir()
        shutil.copy2(gsap, d / name / "vendor" / "gsap.min.js")
        (d / name / "index.html").write_text(ROOT.format(head="", dur=' data-duration="8"', body=body, root_js=js))
        (d / name / "transcript.json").write_text(json.dumps(words))
    (d / "ok" / "compositions" / "end.html").write_text(
        '<!doctype html><html><head><meta charset="UTF-8"></head><body><template id="end-template">'
        '<div data-composition-id="end" data-width="1080" data-height="1920" data-duration="3">'
        '<div id="card" data-anchor="t:3.5" style="position:absolute;left:200px;top:1400px;width:200px;height:100px;background:#36e"></div></div>'
        '<script>(function () { const tl = gsap.timeline({ paused: true }); tl.to("#card", { x: 80, duration: 0.5 }, 0.5); '
        'window.__timelines["end"] = tl; })();</script></template></body></html>')
    return d


def make_asset_kit(base):
    """A brand kit whose device picture hides under a misleading name in source-assets/ and inside a slide deck."""
    import zipfile
    kit = base / "asset-kit"
    (kit / "source-assets" / "shots").mkdir(parents=True)
    (kit / "templates").mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x333333:s=320x200:d=1", "-frames:v", "1",
                    str(kit / "source-assets" / "shots" / "upload.png")], check=True)
    (kit / "manifest.json").write_text(json.dumps({"assets": [{"path": "source-assets/shots/upload.png", "use": "tablet mockup with the product"}]}))
    with zipfile.ZipFile(kit / "templates" / "deck.pptx", "w") as z:
        z.write(kit / "source-assets" / "shots" / "upload.png", "ppt/media/image7.png")
    return kit


def make_capture(base):
    """A minimal website capture (hyperframes capture's extracted/ files): a cookie banner button that must be ignored,
    the brand's own button, one accent, and a kit whose pack disagrees on the display face."""
    cap = base / "capture"
    (cap / "extracted").mkdir(parents=True)
    (cap / "assets").mkdir()
    (cap / "assets" / "logo-abc123.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (cap / "meta.json").write_text(json.dumps({"id": "example.test-video", "name": "Example"}))
    (cap / "extracted" / "tokens.json").write_text(json.dumps({
        "title": "Example Co", "description": "An example company.", "cssVariables": {"--brand": "#0f7b6c", "--grey": "#8a8f94"},
        "sections": [{"backgroundColor": "#101418"}, {"backgroundColor": "#101418"}],
        "colorStats": [{"hex": "#FFFFFF", "textCount": 300, "bgCount": 2, "interactiveBg": 0},
                       {"hex": "#0F7B6C", "textCount": 4, "bgCount": 9, "interactiveBg": 9},
                       {"hex": "#8A8F94", "textCount": 40, "bgCount": 0, "interactiveBg": 0},
                       {"hex": "#1B2127", "textCount": 0, "bgCount": 6, "interactiveBg": 0},
                       {"hex": "#101418", "textCount": 0, "bgCount": 1, "interactiveBg": 0}]}))
    (cap / "extracted" / "design-styles.json").write_text(json.dumps({
        "typography": [{"role": "display", "fontFamily": "Inter", "fontSize": "64px", "fontWeight": "700", "sampleText": "Hello"},
                       {"role": "body", "fontFamily": "Inter", "fontSize": "18px", "fontWeight": "400", "sampleText": "Body"}],
        "radius": ["6px", "40px"], "shadows": [],
        "buttons": [{"label": "Accept all cookies", "background": "#0F7B6C", "color": "#000000", "borderRadius": "40px", "fontWeight": "700"},
                    {"label": "Book a demo", "background": "#0F7B6C", "color": "#FFFFFF", "borderRadius": "6px", "fontWeight": "600"}]}))
    kit = base / "capture-kit"
    (kit / "kit-to-clip" / "templates").mkdir(parents=True)
    (kit / "kit-to-clip" / "templates" / "brand.css").write_text(':root { --reel-accent: #0f7b6c; --reel-font-display: "Brand Serif", serif; --reel-radius: 6px; }')
    (base / "capture-empty").mkdir()
    return cap, kit


SLOTS_OK = {"headline": "Built to be seen", "stat_value": "12", "stat_label": "seconds in this reel",
            "points": ["One brand motif", "Cut on the beat", "Ends on the logo"], "tagline": "A test brand, not a real one."}
SLOTS_BAD = {"headline": "A headline that is far too long for this format", "stat_value": "12", "stat_label": "x",
             "points": ["one", "two"], "tagline": "ok"}


# ---------------------------------------------------------------- cases: (name, argv builder, exit, text in output)
def make_toolbox(base):
    """Card folders for the toolbox: a blocked licence, a missing checksum, an empty box, and a local 'release' (a zip
    served by file://) with a right and a wrong checksum, plus a fake installed browser library to vendor."""
    import hashlib, zipfile
    tb = base / "toolbox"
    card = lambda **kw: {"schema": 1, "name": kw.get("id"), "about": "test power", "maturity": "stable",
                         "capabilities": ["voice-over"], "fallback": "text", "upstream": {"github": "x/y"}, **kw}
    def write(folder, c):
        (tb / folder).mkdir(parents=True, exist_ok=True)
        (tb / folder / f"{c['id']}.json").write_text(json.dumps(c))
    write("nc", card(id="ncvoice", kind="pip", pinned="1", install={"packages": ["x"]}, licence={"spdx": "CC-BY-NC-4.0"}))
    write("nosum", card(id="nosum", kind="release", pinned="1", install={"repo": "x/y", "tag": "v1", "asset": "a.zip"}, licence={"spdx": "MIT"}))
    (tb / "empty").mkdir(parents=True)
    zpath = tb / "localtool.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        info = zipfile.ZipInfo("localtool/run.sh")
        info.external_attr = 0o755 << 16
        z.writestr(info, '#!/bin/bash\necho "hello from the tool" > "$1"\n')
    good = hashlib.sha256(zpath.read_bytes()).hexdigest()
    release = lambda cid, sha: card(id=cid, kind="release", pinned="1.0", licence={"spdx": "MIT"},
                                    install={"url": zpath.as_uri(), "asset": "localtool.zip", "sha256": {"1.0": sha},
                                             "extract": "zip", "entries": {"cli": "localtool/run.sh"}},
                                    smoke={"steps": [["{cli}", "{scratch}/out.txt"]], "expect": [{"file": "{scratch}/out.txt", "contains": "hello"}]})
    write("local", release("localtool", good))
    write("local", release("badsum", "0" * 64))
    lib = card(id="fakelib", kind="npm", pinned="1.0.0", licence={"spdx": "MIT"}, install={"packages": ["fakelib@{version}"]},
               vendor={"files": {"node_modules/fakelib/dist/fake.js": "fake.js"}}, homepage="https://example.org")
    write("local", lib)
    dist = tb / "tools" / "fakelib" / "1.0.0" / "node_modules" / "fakelib" / "dist"
    dist.mkdir(parents=True)
    (dist / "fake.js").write_text("window.fake = 1;\n")
    (tb / "tools" / "fakelib" / "installed.json").write_text(json.dumps({"version": "1.0.0", "kind": "npm", "entries": {"fake.js": str(dist / "fake.js")}}))
    (tb / "project").mkdir()
    (tb / "state").mkdir()
    (tb / "state" / "updates.json").write_text(json.dumps({"checked": __import__("datetime").datetime.now().isoformat(timespec="seconds"), "results": []}))
    return tb


# sha256 of sfx.wav for one plain note hit with the room off, made by the engine before the room existed (kept so the
# room-off layer is checked to stay bit-identical to the old dry layer)
DRY_SHA256 = "43a8f26ac205ba4fc1d4c51a170025d951df293ef586abe4a0badacfffb8e36b"


def cases(base, gsap):
    comp = lambda n: str(make_composition(base, n, gsap))
    vid = lambda n: str(make_video(base, n))
    repo = make_brand_repo(base)
    (base / "slots-ok.json").write_text(json.dumps(SLOTS_OK))
    (base / "slots-bad.json").write_text(json.dumps(SLOTS_BAD))
    py = sys.executable
    fin = lambda *a: [py, str(FINISH), *a]
    finish = lambda v, prof, *extra: fin("finish", vid(v), "--profile", prof, "--out", str(base / "out" / v), "--name", v, *extra)
    reel = str(repo / "reels" / "videos" / PACK)
    det = make_detect_repos(base)
    detect = lambda name: [py, str(DETECT), "detect", "--repo", str(det / name)]
    in_home = lambda *argv: ["env", f"HOME={det / 'home'}", *argv]
    fmts = lambda *a: [py, str(FORMATS), "list", "--project", str(det / "one"), *a]
    guide_kit = make_guide_kit(base)
    leaky = base / "leaky"
    (leaky / "notes").mkdir(parents=True)
    (leaky / "notes" / "a.md").write_text("made on " + "/Us" + "ers/someone/Desktop\n")   # split: this file is scanned too
    helper_homes = base / "helper"
    old_fetcher = helper_homes / "old" / ".claude" / "skills" / "youtube-fetcher"
    (old_fetcher).mkdir(parents=True)
    (old_fetcher / "SKILL.md").write_text("---\nname: youtube-fetcher\n---\n")
    new_fetcher = helper_homes / "new" / "youtube-fetcher"
    (new_fetcher / "scripts").mkdir(parents=True)
    (new_fetcher / "SKILL.md").write_text("---\nname: youtube-fetcher\n---\n")
    (new_fetcher / "scripts" / "fetch_media.py").write_text("")
    (helper_homes / "empty").mkdir()
    helper = lambda home, *extra: ["env", f"HOME={helper_homes / home}", "KIT_TO_CLIP_FETCHER=", *extra, py, str(REFERENCE), "helper"]
    ref = lambda *a: [py, str(REFERENCE), *a]
    (base / "ref-still.png").write_bytes(b"png")
    refs = lambda f: ["bash", "-c", f'"{py}" "{STYLES}" --root "{base / "ref-styles"}" init --title "Ref" --author T >/dev/null 2>&1; '
                                    f'"{py}" "{STYLES}" --root "{base / "ref-styles"}" refs --style ref "{f}"']
    anc = make_anchor_projects(base, gsap)
    anchors = lambda name, *extra: fin("anchors", "--project", str(anc / name), "--bpm", "120", *extra)
    TRACE = SKILL / "finish" / "scripts" / "trace.mjs"
    (base / "trace_check.py").write_text('''import json, math, sys
m = json.load(open(sys.argv[1])); F = m["frames"]; fps = m["fps"]
def series(name, weighted):
    v = [0.0]
    for a, b in zip(F, F[1:]):
        d = math.hypot(math.hypot(b[name]["x"] - a[name]["x"], b[name]["y"] - a[name]["y"]), b[name]["w"] - a[name]["w"]) * fps
        v.append(d * (min(a[name]["vis"], b[name]["vis"]) if weighted else 1))
    return v
raw, vis = series("headline", False), series("headline", True)
j = max(range(len(raw)), key=lambda i: raw[i])
print(f"hidden jump at {F[j]['t']:.2f} s: raw {'over 1000' if raw[j] > 1000 else raw[j]} px/s, visible {vis[j]:.0f} px/s")
v = series("box", True); a, b = round(1.0 * fps), round(2.0 * fps)
pk = max(range(a, b + 1), key=lambda i: v[i])
print(f"box peaks at {100 * (pk - a) / (b - a):.0f}% of its move")
still = next(i for i in range(pk, len(v)) if v[i] < 0.03 * v[pk])
print(f"box comes to rest within one frame of its end: {'yes' if abs(still - b) <= 1 else 'NO, ' + str(still - b) + ' frames'}")
''')
    trace = lambda name, *extra: ["node", str(TRACE), comp(name), "--out", str(base / f"motion-{name}.json"), *extra]
    trace_read = lambda: ["bash", "-c", f'node "{TRACE}" "{comp("trace")}" --out "{base}/motion-read.json" >/dev/null && "{py}" "{base}/trace_check.py" "{base}/motion-read.json"']
    def plan(name, **over):
        f = base / f"plan-{name}.json"
        f.write_text(json.dumps({"key": "A minor", "whoosh": [{"ids": ["box"], "gain": 0.2}],
                                 "hits": [{"id": "box", "at": 2.0, "kind": "note", "note": 69, "cue": "box lands"}], **over}))
        return str(f)
    fx = lambda name, plan_file: [py, str(EFFECTS), str(base / "motion-read.json"), plan_file, "--out", str(base / f"fx-{name}")]
    # a 4 s trace written by hand (no node): "box" moves from 0.5 s to 1.6 s and rests; "still" never moves
    frames = []
    for k in range(120):
        u = min(1.0, max(0.0, (k / 30 - 0.5) / 1.1))
        frames.append({"t": round(k / 30, 4),
                       "box": {"x": 100 + 700 * (3 * u * u - 2 * u ** 3), "y": 300.0, "w": 200.0, "h": 200.0, "vis": 1.0},
                       "still": {"x": 500.0, "y": 600.0, "w": 100.0, "h": 100.0, "vis": 1.0}})
    (base / "synth-motion.json").write_text(json.dumps({"fps": 30, "duration": 4.0, "width": 1080, "ids": ["box", "still"], "frames": frames}))
    synth = str(base / "synth-motion.json")
    def fxplan(name, hits, **over):
        f = base / f"plan-{name}.json"
        f.write_text(json.dumps({"key": "A minor", "hits": hits, **over}))
        return str(f)
    fxs = lambda name, plan_file: [py, str(EFFECTS), synth, plan_file, "--out", str(base / f"fx-{name}")]
    (base / "sha.py").write_text("import hashlib, sys\nprint('dry layer sha256', hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())\n")
    (base / "peak.py").write_text('''import sys, wave
import numpy as np
w = wave.open(sys.argv[1]); x = np.abs(np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32767)
ok = 0.1 < x.max() <= 0.951
print("never clips" if ok else f"CLIPS or silent: peak {x.max():.3f}")
sys.exit(0 if ok else 1)
''')
    (base / "riser_check.py").write_text('''import json, sys, wave
import numpy as np
d = sys.argv[1]
cue = json.load(open(d + "/cue-sheet.json"))[0]
w = wave.open(d + "/sfx.wav"); sr = w.getframerate()
x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float).reshape(-1, 2) / 32767
end, land = cue["sound_t"], cue["picture_t"]
def rms(a, b):
    s = x[int(a * sr):int(b * sr)]
    return float(np.sqrt((s ** 2).mean())) if len(s) else 0.0
before, after = rms(end - 0.5, end - 0.05), rms(end + 0.1, end + 0.5)
ok = before > 0.01 and after < 1e-5 and abs(land - end - 0.01) < 0.001
print(f"riser: loud before its end {before:.3f}, silent after {after:.6f}, lands {land} s, ends {end} s: "
      + ("ends on the landing" if ok else "does NOT end on the landing"))
sys.exit(0 if ok else 1)
''')
    riser_end = lambda kind: ["bash", "-c", f'"{py}" "{EFFECTS}" "{synth}" "{fxplan("end-" + kind, [{"id": "box", "at": 1.6, "kind": kind, "length": 1.0, "cue": "box lands"}], room=False)}" '
                                            f'--out "{base}/fx-end-{kind}" >/dev/null && "{py}" "{base}/riser_check.py" "{base}/fx-end-{kind}"']
    sha_of = lambda name: ["bash", "-c", f'"{py}" "{EFFECTS}" "{synth}" "{fxplan(name, [{"id": "box", "at": 1.6, "kind": "note", "note": 69, "gain": 0.55, "cue": "box lands"}], **({"room": False} if name == "room-off" else {}))}" '
                                          f'--out "{base}/fx-{name}" >/dev/null && "{py}" "{base}/sha.py" "{base}/fx-{name}/sfx.wav"']
    # trace -> effects -> put the sound on a dummy picture -> sync, all on the box that moves from 1 s to 2 s
    fx_sync = lambda delay_ms: ["bash", "-c", f'node "{TRACE}" "{comp("trace")}" --out "{base}/motion-read.json" >/dev/null && '
                                f'"{py}" "{EFFECTS}" "{base}/motion-read.json" "{plan("ok")}" --out "{base}/fx-sync{delay_ms}" >/dev/null && '
                                f'ffmpeg -v error -y -f lavfi -i testsrc2=s=180x320:r=30:d=4 -i "{base}/fx-sync{delay_ms}/sfx.wav" -af "adelay={delay_ms}|{delay_ms}" '
                                f'-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{base}/fx-sync{delay_ms}/dummy.mp4" && '
                                f'"{py}" "{FINISH}" sync "{base}/fx-sync{delay_ms}/dummy.mp4" --cues "{base}/fx-sync{delay_ms}/cue-sheet.json" --out "{base}/fx-sync{delay_ms}/sync.json"']
    tone = lambda name, hz: ["bash", "-c", f'ffmpeg -v error -y -f lavfi -i "sine=frequency={hz}:duration=0.6" "{base}/{name}.wav" && '
                             f'"{py}" "{PITCH}" check --key "A minor" "{base}/{name}.wav"']
    noise = ["bash", "-c", f'ffmpeg -v error -y -f lavfi -i "anoisesrc=d=0.6:c=white:r=48000:a=0.3" "{base}/noise.wav" && '
             f'"{py}" "{PITCH}" check --key "A minor" "{base}/noise.wav"']
    def loud(gain_db):
        name = f"spiky{gain_db:+d}".replace("+", "p").replace("-", "m")
        v = make_spiky_video(base, name, gain_db)
        rep = base / "out" / name / f"{name}-tiktok.report.json"
        check = ('import json,sys; a=json.load(open(sys.argv[1]))["audio"]; ok=abs(a["after_lufs"]+14)<=0.5 and a["after_tp"]<=-1.0; '
                 'print("loudness", a["after_lufs"], "LUFS", a["after_tp"], "dBTP, range", a["after_lra"], "LU:", "IN" if ok else "OUT")')
        return ["bash", "-c", f'"{py}" "{FINISH}" finish "{v}" --profile tiktok --out "{base}/out/{name}" --name {name} --no-sync "test clip" '
                              f'>/dev/null; "{py}" -c \'{check}\' "{rep}"']
    (base / "score_check.py").write_text('''import json, re, sys
sys.path.insert(0, sys.argv[1])
import score
NAMES = "C C# D D# E F F# G G# A A# B".split()
def load(d):
    return json.load(open(d + "/score.json")), score.analyze(d + "/music.wav")
if sys.argv[2] == "one":
    spec, r = load(sys.argv[3])
    bad = []
    if abs(r["seconds"] - spec["bars"] * 4 * 60 / spec["bpm"]) > 0.03: bad.append(f"not whole bars ({r['seconds']} s)")
    if abs(r["lufs"] + 18) > 0.5: bad.append(f"level {r['lufs']} LUFS")
    if r["true_peak"] > -2.9: bad.append(f"true peak {r['true_peak']}")
    out = [n for n in spec["notes_used"] if NAMES.index(re.match(r"[A-G]#?", n).group()) not in set(spec["scale_pc"])]
    if out: bad.append(f"notes out of key {out}")
    print(f"{spec['style']} {spec['bpm']} bpm {spec['key']}:", "OK whole bars, level, peak and key" if not bad else "NOT OK: " + "; ".join(bad))
else:
    (sa, ra), (sb, rb) = load(sys.argv[3]), load(sys.argv[4])
    ok = rb["onsets_per_second"] >= 2 * ra["onsets_per_second"] and ra["centroid_hz"] < 0.7 * rb["centroid_hz"]
    print(f"{sa['style']} {ra['onsets_per_second']}/s {ra['centroid_hz']} Hz vs {sb['style']} {rb['onsets_per_second']}/s {rb['centroid_hz']} Hz:",
          "DIFFERENT (the second is busier and brighter)" if ok else "TOO ALIKE")
''')
    sc = lambda *a: [py, str(SCORE), *a]
    def made(name, *extra):
        return sc("make", "--out", str(base / f"music-{name}"), "--bars", "4", *extra)
    def music(name, *extra):
        d = base / f"music-{name}"
        return ["bash", "-c", f'"{py}" "{SCORE}" make --out "{d}" --bars 4 {" ".join(extra)} >/dev/null && "{py}" "{base}/score_check.py" "{SCORE.parent}" one "{d}"']
    both = lambda: ["bash", "-c", f'"{py}" "{base}/score_check.py" "{SCORE.parent}" two "{base}/music-calm" "{base}/music-pulse"']
    full_chain = lambda: ["bash", "-c", (
        f'node "{TRACE}" "{comp("trace")}" --out "{base}/motion-read.json" >/dev/null && '
        f'"{py}" "{EFFECTS}" "{base}/motion-read.json" "{plan("chain")}" --out "{base}/fx-chain" >/dev/null && '
        f'"{py}" "{SCORE}" make --style calm --bpm 200 --bars 4 --out "{base}/music-chain" >/dev/null && '
        f'"{py}" "{SCORE}" mix "{base}/music-chain/music.wav" "{base}/fx-chain/sfx.wav" --out "{base}/chain-mix.wav" && '
        f'"{py}" "{FINISH}" audio "{base}/chain-mix.wav"')]
    # the installer's pinned files: all present next to install.sh, and a missing one is named plainly (no network needed)
    incomplete = lambda: ["bash", "-c", f'rm -rf "{base}/setup-copy" && mkdir -p "{base}/setup-copy" && cp -R "{SKILL}/setup" "{base}/setup-copy/setup" '
                          f'&& cp "{SKILL}/SKILL.md" "{base}/setup-copy/SKILL.md" && rm "{base}/setup-copy/setup/package.json" '
                          f'&& bash "{base}/setup-copy/setup/install.sh" "{base}/setup-copy/engine"']
    tbox = make_toolbox(base)
    tbx = lambda folder, *a: ["env", f"KIT_TO_CLIP_CARDS={tbox / folder}", f"KIT_TO_CLIP_TOOLS={tbox / 'tools'}",
                              f"KIT_TO_CLIP_STATE={tbox / 'state'}", py, str(TOOLBOX_PY), *a]
    lic = lambda expr, usage: [py, "-c", f"import sys; sys.path.insert(0, {str(TOOLBOX_PY.parent)!r}); import toolbox; "
                                         f"print(toolbox.classify({expr!r}, {usage!r})['verdict'])"]
    def legacy(case):
        """Run install.sh's legacy-cleanup block alone, against a fake studio and home."""
        root = base / f"legacy-{case}"
        for name in ("reel-studio", "reel-brand", "reel-formats", "reel-finish", "hyperframes"):
            (root / "studio" / ".claude" / "skills" / name).mkdir(parents=True, exist_ok=True)
        (root / "setup").mkdir(parents=True, exist_ok=True)
        if case == "user":
            (root / "home" / ".claude" / "skills" / "kit-to-clip").mkdir(parents=True, exist_ok=True)
            (root / "home" / ".claude" / "skills" / "kit-to-clip" / "SKILL.md").write_text("---\nname: kit-to-clip\n---\n")
        script = (f'BLOCK=$(awk \'/^ONE_SKILL=""/{{f=1}} f{{print}} f && /^fi$/{{exit}}\' "{INSTALLER}"); '
                  f'STUDIO="{root}/studio"; HOME="{root}/home"; SETUP="{root}/setup"; LOG="{root}/log"; eval "$BLOCK"; '
                  f'echo "left: $(ls "{root}/studio/.claude/skills" | tr "\\n" ";")"')
        return ["bash", "-c", script]
    FLASH_CLIPS = {
        "strobe5": ["-f", "lavfi", "-i", "color=black:s=320x180:r=30:d=3", "-vf", "format=gray,geq=lum='if(mod(floor(N/3),2),235,16)'"],
        "blink1": ["-f", "lavfi", "-i", "color=black:s=320x180:r=30:d=3", "-vf", "format=gray,geq=lum='if(mod(floor(N/15),2),235,16)'"],
        "smallbox": ["-f", "lavfi", "-i", "color=0x101010:s=1080x1920:r=30:d=3", "-vf", "drawbox=x=1000:y=60:w=40:h=40:color=white:t=fill:enable='mod(floor(n/3),2)'"],
        "red5": ["-f", "lavfi", "-i", "color=black:s=320x180:r=30:d=3", "-vf", "format=gbrp,geq=r='if(mod(floor(N/3),2),230,0)':g=0:b=0"],
        "fade": ["-f", "lavfi", "-i", "color=black:s=320x180:r=30:d=3", "-vf", "format=gray,geq=lum='16+219*N/90'"],
        "moving": ["-f", "lavfi", "-i", "color=0x1d4ed8:s=320x320:r=30:d=6", "-f", "lavfi", "-i", "color=white:s=80x80:r=30:d=6",
                   "-filter_complex", "[0][1]overlay=x='120+60*sin(2*PI*t/6)':y=120"],
    }
    def clip(name):
        f = base / "flash" / f"{name}.mp4"
        if not f.exists():
            f.parent.mkdir(exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", *FLASH_CLIPS[name], "-pix_fmt", "yuv420p", str(f)], check=True)
        return str(f)
    mem = lambda name, *a: ["env", f"KIT_TO_CLIP_MEMORY={base / 'mem' / name}", py, str(MEMORY_PY), *a]
    memsh = lambda name: f'KIT_TO_CLIP_MEMORY="{base / "mem" / name}" "{py}" "{MEMORY_PY}"'
    two_sessions = lambda: ["bash", "-c", (
        f'rm -rf "{base}/mem/two"; {memsh("two")} record --brand acme --brand-name Acme --format brand-reel --platforms tiktok --repo "{base}/repo-a" >/dev/null && '
        f'{memsh("two")} prefer --dislike "slow fades" --reason "felt sleepy" --topic motion >/dev/null && '
        f'{memsh("two")} recall --repo "{base}/repo-b"')]
    leak_mem = base / "leak-mem"
    (leak_mem / "memory").mkdir(parents=True)
    (leak_mem / "memory" / "profile.json").write_text("{}")
    # offline: env.sh removes every key that makes the video engine send frames to an online vision service, and every
    # stills or capture command in the skill carries its local-only flag
    (base / "offline_check.py").write_text('''import os, re, subprocess, sys
from pathlib import Path
KEYS = ["GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "HYPERFRAMES_VERTEX_PROJECT_ID", "HYPERFRAMES_VERTEX_SERVICE_ACCOUNT"]
if sys.argv[1] == "env":
    env = {**os.environ, **{k: "fake-key" for k in KEYS}}
    shown = subprocess.run(["bash", "-c", 'source "$1" >/dev/null 2>&1; env', "_", sys.argv[2]], env=env,
                           capture_output=True, text=True).stdout
    left = [k for k in KEYS if re.search(rf"^{k}=", shown, re.M)]
    print("still set after env.sh: " + ", ".join(left) if left else "no online vision key left after env.sh")
    sys.exit(1 if left else 0)
RULES = [(r"npx\\s+hyperframes\\s+snapshot\\b", "--describe false"), (r"npx\\s+hyperframes\\s+capture\\b", "--skip-vision")]
bad = []
for f in sorted(Path(sys.argv[2]).rglob("*")):
    if not f.is_file() or f.suffix not in {".md", ".py", ".sh", ".mjs", ".js", ".json", ".html"} or "node_modules" in f.parts:
        continue
    for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
        for cmd, flag in RULES:
            for m in re.finditer(cmd, line):
                if flag not in line[m.end():]:
                    bad.append(f"{f.name}:{n} lacks {flag}")
print("\\n".join(bad) if bad else "every stills and capture command stays local")
sys.exit(1 if bad else 0)
''')
    offline = lambda *a: [py, str(base / "offline_check.py"), *a]
    leaky_env = base / "env-keeps-keys.sh"
    leaky_env.write_text("".join(l for l in (SKILL / "scripts" / "env.sh").read_text().splitlines(True) if not l.startswith("unset GEMINI")))
    skillck = SKILL / "setup" / "check_skill_licences.py"
    unlisted = base / "licences-unlisted.json"                      # a pinned skill with no licence record
    unlisted.write_text(json.dumps({"sources": {}, "skills": {}}))
    noncomm = base / "licences-noncommercial.json"                  # every source recorded, one with a non-commercial licence
    rec = json.loads((SKILL / "setup" / "skills-licences.json").read_text())
    rec["sources"]["pbakaus/impeccable"] = {"licence": "CC-BY-NC-4.0", "evidence": "fixture"}
    noncomm.write_text(json.dumps(rec))
    (base / "online-guide").mkdir()
    (base / "online-guide" / "README.md").write_text("Stills: `npx hyperframes " + "snapshot --at 2`.\n")   # split: the skill is scanned too
    exd = base / "explainer-in"
    exd.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=4", str(exd / "voice.wav")], check=True)
    said = [("Padle", 0.10, 0.45), ("moves", 0.50, 0.80), ("fast.", 0.85, 1.20), ("Read", 1.40, 1.60), ("the", 1.62, 1.70),
            ("rally", 1.72, 2.10), ("now.", 2.15, 2.40), ("That", 2.70, 2.90), ("is", 2.92, 3.00), ("how.", 3.02, 3.40)]
    (exd / "transcript.json").write_text(json.dumps([{"text": t, "start": a, "end": b} for t, a, b in said]))
    (exd / "script.txt").write_text("Padel moves fast. Read the rally now. That is how.")
    (exd / "scenes.json").write_text(json.dumps([{"say": "Padel moves fast", "headline": "Padel moves fast.", "sub": "Every rally tells a story."},
                                                 {"say": "Read the rally", "headline": "Read the rally"}, {"say": "That is how", "headline": "That is how."}]))
    (exd / "scenes-lost.json").write_text(json.dumps([{"say": "Padel moves fast", "headline": "A"}, {"say": "Serve and volley", "headline": "B"}]))
    (exd / "scenes-long.json").write_text(json.dumps([{"say": "Padel moves", "headline": "A headline that is far too long for one scene"}, {"say": "That is", "headline": "B"}]))
    ex_out = repo / "reels" / "videos" / "explainer"
    explainer = lambda scenes="scenes.json", out=ex_out, *extra: [py, str(EXPLAINER), "--brand", "test", "--voice", str(exd / "voice.wav"),
                                                                  "--transcript", str(exd / "transcript.json"), "--scenes", str(exd / scenes),
                                                                  "--script", str(exd / "script.txt"), "--out", str(out), "--platform", "tiktok", *extra]
    snd = lambda n, **kw: str(make_sound_video(base, n, **kw))
    cues = base / "cues.json"
    cues.write_text(json.dumps([{"cue": f"flash {i + 1}", "picture_t": t} for i, t in enumerate(SOUND_CUES)]))
    (base / "not-a-cue-sheet.json").write_text('{"cue": "one"}')
    (base / "sync").mkdir()
    syn = lambda video, cue_file=None: fin("sync", video, "--cues", str(cue_file or cues), "--out", str(base / "sync" / (Path(video).stem + ".json")))
    sound = lambda extra: fin("finish", snd("sound-on"), "--profile", "tiktok", "--out", str(base / "out" / "sound"), "--name", "s", *extra)
    stale = lambda: ["bash", "-c", f'"{py}" "{FINISH}" sync "{snd("sound-on")}" --cues "{cues}" >/dev/null && '
                     f'cp "{base}/video/sound-on.sync.json" "{base}/video/sound-late.sync.json" && '
                     f'"{py}" "{FINISH}" finish "{snd("sound-late", shift_ms=-90)}" --profile tiktok --out "{base}/out/stale" --name st']
    kit = make_asset_kit(base)
    (base / "teaser-ok.json").write_text(json.dumps({"headline": "Launch *day*.|See you there.", "duration": 6}))
    (base / "teaser-bad.json").write_text(json.dumps({"headline": "A *headline far too long to ever fit a teaser loop format at all today", "media": "nowhere.png"}))
    teaser = str(repo / "reels" / "videos" / "teaser")
    CARDS = SKILL / "formats" / "scripts" / "cards.py"
    (base / "cards-ok.json").write_text(json.dumps({"bpm": 120, "cards": [
        {"card": "headline", "slots": {"text": "Launch *day*."}, "dur": 2.5, "anchor": "beat:0"},
        {"card": "stat", "slots": {"value": "12", "label": "test value, not a real number"}, "dur": 3, "anchor": "beat:6"},
        {"card": "lockup", "slots": {"tagline": "A test brand.|Not a real one."}, "dur": 2.5, "anchor": "beat:12"}]}))
    (base / "cards-bad.json").write_text(json.dumps({"cards": [{"card": "headline", "slots": {"text": "x" * 60}}, {"card": "banner"}]}))
    cards_out = str(repo / "reels" / "videos" / "cards")
    cap, cap_kit = make_capture(base)
    SHEET = SKILL / "brand" / "scripts" / "brandsheet.py"
    sheet = lambda *extra: [py, str(SHEET), str(cap), "--out", str(base / "sheet.md"), "--json", str(base / "sheet.json"), *extra]
    workshop_only = [
        ("export: planted private path fails the leak scan", lambda: [py, str(REPO / "packaging" / "leakscan.py"), str(leaky)], 1, "notes/a.md:1: matches"),
        ("export: the public tree has no private details", lambda: ["bash", str(EXPORT), str(base / "export")], 0, "leakscan: clean"),
    ] if EXPORT.is_file() else []
    return workshop_only + [
        ("safe: caption inside the box passes", lambda: fin("safe", "--project", comp("inside"), "--platform", "tiktok"), 0, "stay inside"),
        ("safe: caption in the bottom band fails", lambda: fin("safe", "--project", comp("bottom-band"), "--platform", "tiktok"), 1, "bottom by"),
        ("safe: no root timeline fails", lambda: fin("safe", "--project", comp("no-root-timeline"), "--platform", "tiktok"), 1, "no timeline registered"),
        ("safe: nothing to measure fails", lambda: fin("safe", "--project", comp("no-text"), "--platform", "tiktok"), 1, "no visible text or logo"),
        ("safe: zero duration fails", lambda: fin("safe", "--project", comp("zero-duration"), "--platform", "tiktok"), 1, "zero duration"),
        ("safe: sub-composition that does not load fails", lambda: fin("safe", "--project", comp("missing-sub"), "--platform", "tiktok"), 1, "did not mount"),
        ("safe: sub-composition script error fails", lambda: fin("safe", "--project", comp("sub-throws"), "--platform", "tiktok"), 1, "script error"),
        ("console: healthy composition passes with its real duration", lambda: fin("check", "--project", comp("inside")), 0, "(4.00 s, 1 sub-composition(s) loaded)"),
        ("console: sub-composition script error fails", lambda: fin("check", "--project", comp("sub-throws")), 1, "composition script error"),
        ("console: missing sub-composition file fails", lambda: fin("check", "--project", comp("missing-sub")), 1, "missing file"),
        ("console: error hidden while seeking fails", lambda: fin("check", "--project", comp("seek-throws")), 1, "hidden by the HyperFrames runtime"),
        ("hook: a title on screen and moving from the start passes", lambda: fin("hook", "--project", comp("hook-good")), 0, "✓ hook check"),
        ("hook: an opening on background only fails", lambda: fin("hook", "--project", comp("inside")), 1, "only background"),
        ("hook: no readable text by 3 s fails", lambda: fin("hook", "--project", comp("hook-late-text")), 1, "no readable text or logo by 3"),
        ("hook: nothing moving in the first second fails", lambda: fin("hook", "--project", comp("hook-static")), 1, "nothing moves in the first second"),
        ("loop: a seamless loop exports mp4, webm, apng and gif", lambda: fin("loop", vid("box-circle"), "--out", str(base / "loops" / "a"), "--export", "mp4,webm,apng,gif"), 0, "export_apng"),
        ("loop: a loop that jumps back fails", lambda: fin("loop", vid("box-oneway"), "--out", str(base / "loops" / "b"), "--export", "mp4"), 1, "visibly jumps back"),
        ("loop: a LinkedIn GIF of 20 s stays under 250 frames", lambda: fin("loop", vid("box-circle-20s"), "--out", str(base / "loops" / "c"), "--export", "gif", "--gif-profile", "linkedin-gif"), 0, "frames (cap 250)"),
        ("loop: a transparent render keeps its alpha", lambda: fin("loop", vid("alpha-loop"), "--out", str(base / "loops" / "d"), "--export", "webm,mov,apng,gif"), 0, "(transparent)"),
        ("loop: animated WebP export", lambda: fin("loop", vid("box-circle"), "--out", str(base / "loops" / "e"), "--export", "webp"), 0, "export_webp"),
        ("snippet: a single-file loop plays live and holds for reduced motion", lambda: fin("snippet", "--project", comp("hook-good"), "--out", str(base / "snip")), 0, "holds still for reduced motion"),
        ("snippet: a composition with sub-compositions is refused", lambda: fin("snippet", "--project", comp("inside"), "--out", str(base / "snip")), 2, "single-file composition"),
        ("snippet: no timeline fails", lambda: fin("snippet", "--project", comp("snippet-no-timeline"), "--out", str(base / "snip")), 1, "no timeline registered"),
        ("console: remote font request fails", lambda: fin("check", "--project", comp("remote-font")), 1, "network request at load"),
        ("trace: records every element marked data-track", lambda: trace("trace"), 0, "2 element(s), 120 frames at 30 fps"),
        ("trace: a jump while hidden in a mask reads as zero visible speed", trace_read, 0, "raw over 1000 px/s, visible 0 px/s"),
        ("trace: a move peaks in the middle", trace_read, 0, "box peaks at 50% of its move"),
        ("trace: a move comes to rest within a frame of its end", trace_read, 0, "within one frame of its end: yes"),
        ("trace: nothing marked is an error, not an empty file", lambda: trace("inside"), 1, "no element to trace"),
        ("trace: two elements with one name are refused", lambda: trace("trace-dup"), 1, 'named "same"'),
        ("effects: hits and whooshes made from the trace pass the sync gate", lambda: fx_sync(0), 0, "1 of 1 cues have their sound"),
        ("effects: the same sound 100 ms late fails the sync gate", lambda: fx_sync(100), 1, "0 of 1 cues have their sound"),
        ("effects: a note outside the key is refused", lambda: fx("a", plan("bad-note", hits=[{"id": "box", "at": 2.0, "kind": "note", "note": 70}])), 2, "outside A minor"),
        ("effects: an element that is not in the trace is refused", lambda: fx("b", plan("no-el", hits=[{"id": "nope", "at": 2.0, "kind": "thump"}])), 2, "no element named 'nope'"),
        ("effects: a hit while the element is still moving warns", lambda: fx("c", plan("moving", hits=[{"id": "box", "at": 1.5, "kind": "tick"}])), 0, "is not at rest"),
        ("effects: a riser ends on the frame its element lands", lambda: riser_end("riser"), 0, "ends on the landing"),
        ("effects: a tick is not a riser and fails the riser end check", lambda: riser_end("tick"), 1, "does NOT end on the landing"),
        ("effects: a riser on an element that never moves is reported", lambda: fxs("riser-still", fxplan("riser-still", [{"id": "still", "at": 1.6, "kind": "riser"}])), 0, "never moved"),
        ("music: ace_takes recovers beat offsets, ranks takes, keeps endings and refuses mismatched takes (self-test)", lambda: [py, str(SKILL / "sound" / "scripts" / "ace_takes.py"), "--self-test"], 0, "self-test: 13/13 passed"),
        ("effects: a library sound from a power that is not installed is refused", lambda: fxs("lib-missing", fxplan("lib-missing", [{"id": "box", "at": 1.6, "kind": "file", "file": "kenney-nope:click_001.ogg"}], key=None)), 2, "the power 'kenney-nope' is not installed"),
        ("effects: a plain file path is used as it is (control)", lambda: fxs("lib-path", fxplan("lib-path", [{"id": "box", "at": 1.6, "kind": "file", "file": str(base / "no-such.wav")}], key=None)), 2, "no-such.wav' not found"),
        ("effects: a riser note outside the key is refused", lambda: fxs("riser-out", fxplan("riser-out", [{"id": "box", "at": 1.6, "kind": "riser", "note": 70}])), 2, "riser note A#4 is outside A minor"),
        ("effects: a chime in key passes", lambda: fxs("chime-ok", fxplan("chime-ok", [{"id": "box", "at": 1.6, "kind": "chime", "note": 69}])), 0, "1 hit(s)"),
        ("effects: a chime whose note is outside the key is refused", lambda: fxs("chime-out", fxplan("chime-out", [{"id": "box", "at": 1.6, "kind": "chime", "note": 70}])), 2, "outside A minor"),
        ("effects: a chime whose fifth is outside the key is refused", lambda: fxs("chime-fifth", fxplan("chime-fifth", [{"id": "box", "at": 1.6, "kind": "chime", "note": 71}])), 2, "the fifth above, F#5, is outside A minor"),
        ("effects: a slam in key passes", lambda: fxs("slam-ok", fxplan("slam-ok", [{"id": "box", "at": 1.6, "kind": "slam", "note": 57, "gain": 0.6}])), 0, "1 hit(s)"),
        ("effects: a slam outside the key is refused", lambda: fxs("slam-out", fxplan("slam-out", [{"id": "box", "at": 1.6, "kind": "slam", "note": 58}])), 2, "outside A minor"),
        ("effects: a room wet share above 1 is refused", lambda: fxs("room-bad", fxplan("room-bad", [{"id": "box", "at": 1.6, "kind": "note", "note": 69}], room={"wet": 2})), 2, "share of reverb, from 0 to 1"),
        ("room: a plain note with the room off is bit-identical to the old dry layer", lambda: sha_of("room-off"), 0, "dry layer sha256 " + DRY_SHA256),
        ("room: the default room changes the dry layer", lambda: sha_of("room-default"), 0, "!dry layer sha256 " + DRY_SHA256),
        ("room: a loud layer with the default room never clips", lambda: ["bash", "-c", f'"{py}" "{EFFECTS}" "{synth}" "{fxplan("room-loud", [{"id": "box", "at": 1.6, "kind": "slam", "note": 57, "gain": 3.0}, {"id": "box", "at": 1.6, "kind": "chime", "note": 69, "gain": 3.0}])}" --out "{base}/fx-room-loud" >/dev/null && "{py}" "{base}/peak.py" "{base}/fx-room-loud/sfx.wav"'], 0, "never clips"),
        ("pitch: a note in key passes the key check", lambda: tone("a440", 440), 0, "in A minor"),
        ("pitch: a note outside the key fails the key check", lambda: tone("as466", 466.16), 1, "A# (466"),
        ("pitch: noise is untuned and fits any key", lambda: noise, 0, "untuned, fits A minor"),
        ("score: the four styles are listed", lambda: sc("styles"), 0, "cinematic"),
        ("score: pulse is whole bars, at level, under -3 dBTP and in key", lambda: music("pulse", "--style pulse"), 0, "OK whole bars, level, peak and key"),
        ("score: calm is whole bars, at level, under -3 dBTP and in key", lambda: music("calm", "--style calm"), 0, "OK whole bars, level, peak and key"),
        ("score: uplift is whole bars, at level, under -3 dBTP and in key", lambda: music("uplift", "--style uplift"), 0, "OK whole bars, level, peak and key"),
        ("score: cinematic is whole bars, at level, under -3 dBTP and in key", lambda: music("cinematic", "--style cinematic"), 0, "OK whole bars, level, peak and key"),
        ("score: any key and tempo (F# minor, 100 bpm) stays in key", lambda: music("fsharp", "--style pulse", "--bpm 100", '--key "F# minor"'), 0, "pulse 100.0 bpm F# minor: OK"),
        ("score: a major key with its own chords stays in key", lambda: music("eb", "--style uplift", '--key "Eb major"', "--progression 1,4,5,1"), 0, "uplift 118 bpm D# major: OK"),
        ("score: two styles really differ (calm against pulse)", both, 0, "DIFFERENT"),
        ("score: an unknown style is refused", lambda: made("x", "--style", "disco"), 2, "no style"),
        ("score: fewer than 4 bars is refused", lambda: sc("make", "--style", "pulse", "--bars", "3", "--out", str(base / "music-x")), 2, "at least 4 bars"),
        ("score: a key it cannot read is refused", lambda: made("x", "--style", "pulse", "--key", "H minor"), 2, "not understood"),
        ("score: sections that do not add up are refused", lambda: made("x", "--style", "pulse", "--sections", "hook:1,build:1,drop:1,end:2"), 2, "add up"),
        ("score: music and effects mix under -3 dBTP and the render leaves the level alone", full_chain, 0, "leave this level alone"),
        ("setup: the installer's pinned files are all present next to install.sh", lambda: [py, "-c", "import pathlib, sys; d = pathlib.Path(sys.argv[1]); m = [f for f in ('environment.yml', 'package.json', 'package-lock.json', 'skills-lock.json', 'install.sh') if not (d / f).is_file()]; print('setup files present' if not m else 'MISSING ' + ', '.join(m))", str(SKILL / "setup")], 0, "setup files present"),
        ("setup: a missing pinned file is named plainly, not a bare cp error", incomplete, 1, "package.json is missing"),
        ("finish: clean video passes the motion gate", lambda: finish("clean", "website-loop"), None, "black_flash: none"),
        ("finish: 2-frame black flash fails", lambda: finish("flash", "website-loop"), 1, "ms black at"),
        ("finish: flat first frame fails", lambda: finish("flat-first", "website-loop"), 1, "opens on nothing"),
        ("finish: flat first frame allowed when intended", lambda: finish("flat-first", "gif", "--allow-flat-open"), None, "allowed by --allow-flat-open"),
        ("finish: 3 s freeze mid-video is a warning", lambda: finish("freeze", "website-loop"), None, "frozen 3.0 s"),
        ("sync: sound on its picture passes", lambda: syn(snd("sound-on")), 0, "5 of 5 cues have their sound"),
        ("sync: sound 30 ms early is inside the window", lambda: syn(snd("sound-early30", shift_ms=30)), 0, "5 of 5 cues have their sound"),
        ("sync: sound 90 ms late fails", lambda: syn(snd("sound-late", shift_ms=-90)), 1, "0 of 5 cues have their sound"),
        ("sync: sound 80 ms early fails", lambda: syn(snd("sound-early80", shift_ms=80)), 1, "0 of 5 cues have their sound"),
        ("sync: a picture moment with no sound at all fails", lambda: syn(snd("sound-gaps", silent=(1, 3))), 1, "no sound onset near it"),
        ("sync: a silent video is a usage error", lambda: syn(vid("clean")), 2, "has no sound"),
        ("sync: a file that is not a cue sheet is a usage error", lambda: syn(snd("sound-on"), base / "not-a-cue-sheet.json"), 2, "is not a cue sheet"),
        ("finish: a video with sound and no sync report is refused", lambda: sound([]), 1, "nothing shows the sound follows the picture"),
        ("finish: a video whose sound is off the picture is refused", lambda: fin("finish", snd("sound-late", shift_ms=-90), "--profile", "tiktok", "--out", str(base / "out" / "late"), "--name", "l", "--cues", str(cues)), 1, "the sound does not follow the picture"),
        ("finish: sound that follows the picture passes and is recorded", lambda: sound(["--cues", str(cues)]), None, "sync: 5 of 5 cues inside"),
        ("finish: the saved sync report is used next time", lambda: sound([]), None, "sync: 5 of 5 cues inside"),
        ("finish: a sync report for another version of the render is refused", stale, 1, "earlier version of this render"),
        ("deliver: a video with sound is refused without a sync check or a reason", lambda: [py, str(DELIVER), snd("sound-deliver"), "--slug", "d", "--format", "clip", "--platforms", "tiktok", "--out", str(base / "out" / "deliver-a")], 1, "nothing shows the sound follows the picture"),
        ("deliver: --no-sync passes the reason on to finish", lambda: [py, str(DELIVER), snd("sound-deliver"), "--slug", "d", "--format", "clip", "--platforms", "tiktok", "--out", str(base / "out" / "deliver-b"), "--no-sync", "footage's own sound"], None, "skipped: footage's own sound"),
        ("finish: --no-sync passes and prints its reason", lambda: sound(["--no-sync", "footage's own sound"]), None, "skipped: footage's own sound"),
        ("finish: --cues with --no-sync is a usage error", lambda: sound(["--cues", str(cues), "--no-sync", "x"]), 2, "either --cues or --no-sync"),
        ("finish: a profile that drops the sound needs no sync check", lambda: fin("finish", snd("sound-on"), "--profile", "gif", "--out", str(base / "out" / "gifsound"), "--name", "g"), None, "no audio track (by profile or source)"),
        ("loudness: a spiky mix lands on -14 LUFS and under -1 dBTP", lambda: loud(0), 0, "IN"),
        ("loudness: the same mix 6 dB quieter lands there too", lambda: loud(-6), 0, "IN"),
        ("loudness: the same mix 6 dB hotter lands there too", lambda: loud(6), 0, "IN"),
        ("audio preflight: a mix with hot peaks is flagged as one the render turns down", lambda: fin("audio", str(make_spiky_video(base, "spikyp6", 6))), 0, "the render will turn this down"),
        ("audio preflight: a mix with headroom is left alone by the render", lambda: fin("audio", str(make_spiky_video(base, "spikym12", -12))), 0, "leave this level alone"),
        ("audio preflight: a silent video is a usage error", lambda: fin("audio", vid("clean")), 2, "has no sound"),
        ("loudness: the report states the loudness range", lambda: loud(0), 0, "range"),
        ("gif: a loop that jumps back fails", lambda: finish("box-oneway", "gif"), 1, "visibly jumps back"),
        ("gif: a seamless loop passes and loops forever", lambda: finish("box-circle", "gif"), 0, "loops forever"),
        ("bridge: the repo's own provisional pack is used", lambda: [py, str(BRIDGE), "--brand", "test", "--project", reel + "-bridge"], 0, "provisional brand"),
        ("bridge: unknown brand stops", lambda: [py, str(BRIDGE), "--brand", "nobody", "--project", reel + "-x"], 2, "no video pack"),
        ("bridge: contract with missing tokens stops", lambda: [py, str(BRIDGE), "--brand", "thin", "--project", reel + "-thin"], 2, "does not define"),
        ("bridge: --list reports a broken pack", lambda: [py, str(BRIDGE), "--list", "--project", reel], 0, "(broken)"),
        ("brand reel: slots over their limits stop the build", lambda: [py, str(BRAND_REEL), "--brand", "test", "--slots", str(base / "slots-bad.json"), "--out", reel + "-bad"], 2, "the limit is"),
        ("brand reel: builds for the test brand", lambda: [py, str(BRAND_REEL), "--brand", "test", "--slots", str(base / "slots-ok.json"), "--out", reel, "--platform", "tiktok"], 0, "brand-reel: built"),
        ("brand reel: passes the console check", lambda: fin("check", "--project", reel), 0, "(12.00 s)"),
        ("brand reel: passes the safe check", lambda: fin("safe", "--project", reel, "--platform", "tiktok"), 0, "stay inside"),
        ("detect: the repo's own pack is used", lambda: detect("one"), 0, "brand: pack"),
        ("detect: two brands in one repo asks which", lambda: [py, str(DETECT), "detect", "--repo", str(repo)], 0, "next: ask which brand"),
        ("detect: a pointer to a kit elsewhere is followed", lambda: detect("pointer"), 0, "brand: pointer"),
        ("detect: a kit without a pack goes to onboarding", lambda: detect("kit"), 0, "brand onboarding"),
        ("detect: brand work without an identity is flagged", lambda: detect("unchosen"), 0, "brand: unchosen"),
        ("detect: no brand is flagged, never guessed", lambda: detect("none"), 0, "brand: none"),
        ("detect: an installed brand kit without a pack is offered", lambda: in_home(*detect("none")), 0, "installed kit without a video pack\tzeta-brand"),
        ("detect: a skill without logos is not a brand kit", lambda: in_home(*detect("none")), 0, "!zeta-icons"),
        ("detect: choosing an installed kit leads to onboarding", lambda: in_home("bash", "-c", f'"{py}" "{DETECT}" use --kit zeta-brand --repo "{det / "chosen"}" && "{py}" "{DETECT}" detect --repo "{det / "chosen"}"'), 0, "brand onboarding"),
        ("detect: an unknown kit is refused", lambda: in_home(py, str(DETECT), "use", "--kit", "nobody-brand", "--repo", str(det / "chosen")), 2, "no installed brand kit"),
        ("formats: a pack's approved format is listed", lambda: fmts(), 0, "good\tGood\tapproved\tclip\tone"),
        ("formats: a pack's draft is hidden by default", lambda: fmts(), 0, "!wip"),
        ("formats: a pack's draft shows with --all", lambda: fmts("--all"), 0, "wip\tWork in progress\tdraft"),
        ("formats: a broken format file is reported", lambda: fmts(), 0, 'needs "name"'),
        ("anchors: scenes that start on their beat, word and second pass, whatever data-start says", lambda: anchors("ok"), 0, "4 anchored element(s) start or come to rest"),
        ("anchors: a tween that starts 0.2 s after its declared data-at fails", lambda: anchors("drift"), 1, "drifted outside"),
        ("anchors: the failure shows what the timeline plays and what was declared", lambda: anchors("drift"), 1, "starts 2.200 s, declared 2.00 s"),
        ("anchors: a hit whose move comes to rest on the beat passes", lambda: anchors("lands"), 0, "lands"),
        ("anchors: a scene marked data-anchor-scope=scene may follow its beat", lambda: anchors("late-scene"), 0, "1 anchored element(s)"),
        ("anchors: the same delay on a hit fails", lambda: anchors("late-hit"), 1, "drifted outside -0.034..+0.045"),
        ("anchors: an anchored element that never moves fails", lambda: anchors("never-moves"), 1, "nothing on it ever moves"),
        ("anchors: motion while hidden in a mask is not counted", lambda: anchors("hidden-jump"), 0, "starts 2.000 s"),
        ("anchors: a word that is not in the transcript fails", lambda: anchors("no-word"), 1, "is not in the transcript"),
        ("anchors: nothing anchored fails, never passes", lambda: anchors("none"), 1, "no element has data-anchor"),
        ("assets: search finds an original by its manifest note", lambda: [py, str(ASSETS), "search", str(kit), "tablet", "--no-remote"], 0, "[manifest]"),
        ("assets: an absent asset lists where it looked", lambda: [py, str(ASSETS), "search", str(kit), "laptop", "--no-remote"], 1, "searched:"),
        ("assets: the sheet includes pictures inside office files", lambda: [py, str(ASSETS), "sheet", str(kit), "--out", str(base / "sheet")], 0, "2 pictures (2 thumbnailed)"),
        ("teaser loop: slots over their limits stop the build", lambda: [py, str(TEASER), "--brand", "test", "--slots", str(base / "teaser-bad.json"), "--out", teaser + "-bad"], 2, "the limit is"),
        ("teaser loop: builds for the test brand", lambda: [py, str(TEASER), "--brand", "test", "--slots", str(base / "teaser-ok.json"), "--out", teaser], 0, "teaser-loop: built"),
        ("teaser loop: passes the console check", lambda: fin("check", "--project", teaser), 0, "(6.00 s)"),
        ("teaser loop: passes the hook check", lambda: fin("hook", "--project", teaser), 0, "✓ hook check"),
        ("cards: over-long slots and unknown cards stop the build", lambda: [py, str(CARDS), "compose", "--brand", "test", "--spec", str(base / "cards-bad.json"), "--out", cards_out + "-bad"], 2, "unknown card 'banner'"),
        ("cards: a sequence builds for the test brand", lambda: [py, str(CARDS), "compose", "--brand", "test", "--spec", str(base / "cards-ok.json"), "--out", cards_out, "--platform", "tiktok"], 0, "headline@0s, stat@3s, lockup@6s"),
        ("cards: the sequence passes the console check", lambda: fin("check", "--project", cards_out), 0, "(8.50 s)"),
        ("cards: the first card is readable at once (hook)", lambda: fin("hook", "--project", cards_out), 0, "readable muted by 0.0 s"),
        ("cards: every card stays inside the TikTok safe box", lambda: fin("safe", "--project", cards_out, "--platform", "tiktok"), 0, "stay inside"),
        ("cards: every card sits on its beat (anchors)", lambda: fin("anchors", "--project", cards_out, "--bpm", "120"), 0, "3 anchored element(s) start or come to rest"),
        ("brand sheet: finds the accent and ignores the cookie banner", lambda: ["bash", "-c", " ".join(f'"{x}"' for x in sheet()) + f' && cat "{base / "sheet.json"}"'], 0, '"value": "6px"'),
        ("brand sheet: text on the accent is what the brand's buttons use", lambda: ["bash", "-c", " ".join(f'"{x}"' for x in sheet()) + f' && cat "{base / "sheet.json"}"'], 0, '"value": "#FFFFFF",\n   "from": "text on the site'),
        ("brand sheet: a face that differs from the kit is a conflict", lambda: sheet("--kit", str(cap_kit)), 0, "1 conflict(s) with the kit"),
        ("brand sheet: an incomplete capture stops", lambda: [py, str(SHEET), str(base / "capture-empty"), "--out", str(base / "x.md")], 2, "not a complete capture"),
        ("reference: no media fetcher installed is reported with the install command", lambda: helper("empty"), 3, "skills add JimmySadek/video-fetcher-to-markdown"),
        ("reference: an older fetcher (captions only) is reported as outdated", lambda: helper("old"), 3, "older copy"),
        ("reference: a fetcher with fetch_media.py is ready", lambda: helper("empty", f"KIT_TO_CLIP_FETCHER={new_fetcher}"), 0, "media fetcher ready"),
        ("reference: hard cuts are found where the colour changes", lambda: ref("cuts", vid("three-colors")), 0, "cuts at: 1.00, 2.00"),
        ("reference: a still shot has no cuts", lambda: ref("cuts", vid("still")), 0, "cuts at: none"),
        ("reference: clicks in a video are found as hits", lambda: ref("beats", str(make_sound_video(base, "ref-clicks"))), 0, "hits;"),
        ("reference: a video without sound has no beats", lambda: ref("beats", vid("still")), 1, "no sound"),
        ("styles: a picture is kept as a reference", lambda: refs(base / "ref-still.png"), 0, "1 reference(s)"),
        ("styles: a raw video is refused as a reference", lambda: refs(vid("still")), 1, "is a video"),
        ("toolbox: every shipped card and capability is valid", lambda: [py, str(TOOLBOX_PY), "lint"], 0, "all valid"),
        ("toolbox: a card with a non-commercial licence fails lint", lambda: tbx("nc", "lint"), 1, "blocked by policy"),
        ("toolbox: a downloaded power without a checksum fails lint", lambda: tbx("nosum", "lint"), 1, "needs sha256 or sums"),
        ("toolbox: install refuses a blocked licence", lambda: tbx("nc", "install", "ncvoice"), 4, "licence block"),
        ("toolbox: nothing to provide a capability prints its fallback", lambda: tbx("empty", "which", "voice-over"), 3, "fallback: on-screen text"),
        ("toolbox: an unknown capability is a usage error", lambda: tbx("empty", "which", "teleport"), 2, "unknown capability"),
        ("toolbox: a download whose checksum is wrong is refused", lambda: tbx("local", "install", "badsum"), 1, "checksum mismatch"),
        ("toolbox: a download with the right checksum installs", lambda: tbx("local", "install", "localtool"), 0, "localtool 1.0 installed"),
        ("toolbox: the installed power passes its smoke test", lambda: ["bash", "-c", " ".join(f'"{x}"' for x in tbx("local", "install", "localtool")) + " >/dev/null 2>&1 && " + " ".join(f'"{x}"' for x in tbx("local", "smoke", "localtool"))], 0, "✅ localtool: passed"),
        ("toolbox: a power that is not installed fails its smoke test", lambda: tbx("local", "smoke", "badsum"), 1, "not installed"),
        ("toolbox: vendor copies browser files into the project", lambda: tbx("local", "vendor", "fakelib", str(tbox / "project")), 0, "vendor/fake.js"),
        ("toolbox: vendor credits the library in CREDITS.md", lambda: ["bash", "-c", " ".join(f'"{x}"' for x in tbx("local", "vendor", "fakelib", str(tbox / "project"))) + f' >/dev/null && cat "{tbox}/project/CREDITS.md"'], 0, "fakelib 1.0.0 (MIT)"),
        ("toolbox: the update watch stays quiet when checked this week", lambda: tbx("empty", "updates", "--if-due"), 0, "last checked 0 day(s) ago"),
        ("licence: non-commercial is blocked", lambda: lic("CC-BY-NC-4.0", "library"), 0, "block"),
        ("licence: free text with a non-commercial clause is blocked", lambda: lic("Free for non-commercial or academic use", "library"), 0, "block"),
        ("licence: an unknown licence is reviewed, never allowed", lambda: lic("", "library"), 0, "review"),
        ("licence: GPL inside our code needs a review", lambda: lic("GPL-3.0", "library"), 0, "review"),
        ("licence: GPL as a separate program is fine", lambda: lic("GPL-3.0", "separate-program"), 0, "allow"),
        ("licence: MIT OR AGPL lets us choose MIT", lambda: lic("MIT OR AGPL-3.0", "library"), 0, "allow"),
        ("licence: MIT AND AGPL is blocked", lambda: lic("MIT AND AGPL-3.0", "library"), 0, "block"),
        ("installer: old reel-* skill folders go when kit-to-clip is in the user's skills", lambda: legacy("user"), 0, "left: hyperframes;"),
        ("installer: old reel-* skill folders stay when no kit-to-clip is found", lambda: legacy("none"), 0, "left: hyperframes;reel-brand;reel-finish;reel-formats;reel-studio;"),
        ("flash: a full-frame strobe at 5 flashes a second fails", lambda: fin("flash", clip("strobe5")), 1, "over the safe limit of 3"),
        ("flash: a blink once a second passes", lambda: fin("flash", clip("blink1")), 0, "at most 1 flash in any second"),
        ("flash: a tiny strobing corner box passes (small-area rule)", lambda: fin("flash", clip("smallbox")), 0, "at most 0 flashes"),
        ("flash: a red strobe fails", lambda: fin("flash", clip("red5")), 1, "over the safe limit"),
        ("flash: a slow fade passes", lambda: fin("flash", clip("fade")), 0, "at most 0 flashes"),
        ("loop: a still for reduced motion is written from the last frame", lambda: fin("loop", clip("moving"), "--out", str(base / "out" / "rm"), "--export", "mp4"), None, "still on the last frame"),
        ("loop: the embed shows the still to people who turn motion off", lambda: ["bash", "-c", " ".join(f'"{x}"' for x in fin("loop", clip("moving"), "--out", str(base / "out" / "rm2"), "--export", "mp4,webm")) + f' >/dev/null; cat "{base}/out/rm2/moving-loop.report.json"'], None, "prefers-reduced-motion: reduce"),
        ("loop: a loop over 5 s gets a pause button", lambda: ["bash", "-c", " ".join(f'"{x}"' for x in fin("loop", clip("moving"), "--out", str(base / "out" / "rm3"), "--export", "mp4")) + f' >/dev/null; cat "{base}/out/rm3/moving-loop.report.json"'], None, "k2c-pause"),
        ("explainer: builds for the test brand, scenes on their words", lambda: explainer(), 0, "3 scenes on their words"),
        ("explainer: captions follow the approved script's spelling", lambda: explainer(), 0, "'Padle' -> 'Padel'"),
        ("explainer: every scene starts on its spoken word (anchors)", lambda: fin("anchors", "--project", str(ex_out)), 0, "3 anchored element(s)"),
        ("explainer: passes the console check", lambda: fin("check", "--project", str(ex_out)), 0, "seeks cleanly"),
        ("explainer: opens on content, not empty background (hook)", lambda: fin("hook", "--project", str(ex_out)), 0, "first frame shows"),
        ("explainer: stays inside the TikTok safe box", lambda: fin("safe", "--project", str(ex_out), "--platform", "tiktok"), 0, "stay inside"),
        ("explainer: a scene whose words are not in the voice is refused", lambda: explainer("scenes-lost.json", ex_out.with_name("explainer-lost")), 2, "was not found in the transcript"),
        ("explainer: a headline over its limit is refused", lambda: explainer("scenes-long.json", ex_out.with_name("explainer-long")), 2, "the limit is 34"),
        ("explainer: every illustration style builds", lambda: ["bash", "-c", " && ".join(" ".join(f'"{x}"' for x in explainer("scenes.json", ex_out.with_name(f"explainer-{st}"), "--style", st)) + " >/dev/null" for st in ("cut-paper", "risograph", "sketchbook", "isometric")) + " && echo all styles built"], 0, "all styles built"),
        ("memory: an empty memory says so and exits 3", lambda: mem("fresh", "recall"), 3, "No memory yet"),
        ("memory: a brand used in one repo is offered first in another", lambda: two_sessions(), 0, "Offer first: the acme brand"),
        ("memory: likes and dislikes come back with their reasons", lambda: two_sessions(), 0, "Avoid: slow fades (felt sleepy)"),
        ("memory: the newest word on the same thing wins", lambda: ["bash", "-c", f'{memsh("flip")} prefer --dislike "hard cuts" >/dev/null && {memsh("flip")} prefer --like "hard cuts" --reason "changed my mind" >/dev/null && {memsh("flip")} show'], 0, "!avoids (general): hard cuts"),
        ("memory: forgetting a brand removes its jobs and preferences", lambda: ["bash", "-c", " ".join(f'"{x}"' for x in two_sessions()) + f' >/dev/null && {memsh("two")} forget --brand acme >/dev/null && {memsh("two")} recall'], 0, "!acme"),
        ("memory: it lives in the engine folder by default, never in the repo", lambda: ["env", "-u", "KIT_TO_CLIP_MEMORY", f"REEL_STUDIO={base / 'eng'}", py, "-c", f"import sys; sys.path.insert(0, {str(MEMORY_PY.parent)!r}); import memory; print(memory.memory_dir())"], 0, str(base / "eng" / "memory")),
        ("offline: env.sh removes the online vision keys", lambda: offline("env", str(SKILL / "scripts" / "env.sh")), 0, "no online vision key left"),
        ("offline: an env.sh that keeps the keys is caught", lambda: offline("env", str(leaky_env)), 1, "still set after env.sh: GEMINI_API_KEY"),
        ("offline: every stills and capture command in the skill stays local", lambda: offline("docs", str(SKILL)), 0, "stays local"),
        ("offline: a stills command without --describe false is caught", lambda: offline("docs", str(base / "online-guide")), 1, "README.md:1 lacks --describe false"),
        ("skills: every pinned skill has an allowed licence", lambda: [py, str(skillck)], 0, "pinned skills have an allowed licence"),
        ("skills: a pinned skill with no licence record is caught", lambda: [py, str(skillck), "--licences", str(unlisted)], 1, "no licence recorded"),
        ("skills: a non-commercial skill licence is caught", lambda: [py, str(skillck), "--licences", str(noncomm)], 1, "CC-BY-NC-4.0 is not allowed"),
        ("finish: plan prints the safe box without a project", lambda: fin("plan", "--profile", "youtube"), 0, "x 96-1824, y 54-972"),
        ("finish: safe refuses an unknown platform and lists the profiles", lambda: fin("safe", "--project", str(ex_out), "--platform", "nope"), 2, "unknown platform 'nope'"),
        ("guide: the brand-pack guide's example pack bridges", lambda: [py, str(BRIDGE), "--brand", "acme", "--brand-skill", str(guide_kit), "--project", str(base / "guide-project")], 0, "token contract: v1"),
    ] + ([
        ("leakscan: a person's memory in an export is caught", lambda: [py, str(LEAKSCAN), str(leak_mem)], 1, "local memory or toolbox state"),
    ] if LEAKSCAN.is_file() else [])


def main():
    only = [w.lower() for w in sys.argv[1:]]
    engine = find_engine()
    gsap = engine / "node_modules/gsap/dist/gsap.min.js"
    env = {**os.environ, "REEL_STUDIO": str(engine)}   # every check finds the same engine, whatever the machine's default
    base = Path(tempfile.mkdtemp(prefix="reel-tests-"))
    results = []
    try:
        for name, argv, want_exit, want_text in cases(base, gsap):
            if only and not any(w in name.lower() for w in only):
                continue
            r = subprocess.run(argv(), capture_output=True, text=True, cwd=base, env=env)
            text = r.stdout + r.stderr
            found = want_text[1:] not in text if want_text.startswith("!") else want_text in text   # "!x": x must not appear
            ok = (want_exit is None or r.returncode == want_exit) and found
            results.append((ok, name, r.returncode, want_exit, want_text, text))
            print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"  (exit {r.returncode}, wanted {want_exit}; wanted text: {want_text!r})"))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    bad = [x for x in results if not x[0]]
    for _, name, _, _, _, text in bad:
        print(f"\n--- {name}\n{text.strip()[-1500:]}")
    print(f"\n{len(results) - len(bad)}/{len(results)} cases behaved as expected")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
