#!/usr/bin/env python3
"""Reference videos for Kit to Clip: "make it like this video".

  reference.py helper [--json]          is the media fetcher skill installed (and new enough)?
  reference.py tools [--install]        are its tools there (yt-dlp, Whisper)? --install puts them in the engine
  reference.py cuts <video> [--json]    where the shots change, and the pace that gives
  reference.py beats <video> [--json]   the music's hits (the engine's own detector) and how many cuts land on one

The media fetcher is a separate, free skill (JimmySadek/video-fetcher-to-markdown). It reads a video link from
YouTube, Instagram, TikTok, X and other sites: transcript, frames and the file itself. Kit to Clip uses it as a
helper and only installs it after the person says yes (references/reference-video.md).
Source scripts/env.sh first so the engine's Python and ffmpeg are on the PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HELPER_SKILL = "youtube-fetcher"
HELPER_REPO = "JimmySadek/video-fetcher-to-markdown"
INSTALL_COMMAND = f"npx -y skills add {HELPER_REPO} --skill {HELPER_SKILL} -g -a claude-code -y"
SKILL_DIR = Path(__file__).resolve().parents[1]


# ── The helper skill ──────────────────────────────────────────────────────
def helper_candidates(cwd: Path | None = None, home: Path | None = None) -> list[Path]:
    """Places a skills installer puts the helper, nearest first."""
    cwd = cwd or Path.cwd()
    home = home or Path.home()
    places = []
    if os.environ.get("KIT_TO_CLIP_FETCHER"):
        places.append(Path(os.environ["KIT_TO_CLIP_FETCHER"]).expanduser())
    places.append(SKILL_DIR.parent / HELPER_SKILL)  # next to this skill (same skills folder)
    for folder in [cwd, *cwd.parents]:
        places += [folder / ".claude" / "skills" / HELPER_SKILL, folder / ".agents" / "skills" / HELPER_SKILL]
    places += [
        home / ".claude" / "skills" / HELPER_SKILL,
        home / ".agents" / "skills" / HELPER_SKILL,
        home / ".codex" / "skills" / HELPER_SKILL,
    ]
    seen, unique = set(), []
    for place in places:
        if place not in seen:
            seen.add(place)
            unique.append(place)
    return unique


def find_helper(cwd: Path | None = None, home: Path | None = None) -> dict:
    """ready: has fetch_media.py; outdated: an older copy (YouTube captions only); missing: not installed."""
    outdated = None
    for place in helper_candidates(cwd, home):
        if not (place / "SKILL.md").is_file():
            continue
        if (place / "scripts" / "fetch_media.py").is_file():
            return {"state": "ready", "path": str(place.resolve()), "fetch_media": str((place / "scripts" / "fetch_media.py").resolve())}
        outdated = outdated or place
    if outdated:
        return {
            "state": "outdated",
            "path": str(outdated.resolve()),
            "update": f"{INSTALL_COMMAND}   (or, for a git checkout: git -C {outdated.resolve()} pull)",
        }
    return {"state": "missing", "install": INSTALL_COMMAND}


# ── Its tools ─────────────────────────────────────────────────────────────
def whisper_package() -> str:
    return "mlx-whisper" if sys.platform == "darwin" and platform.machine() == "arm64" else "openai-whisper"


def engine_python() -> Path | None:
    studio = os.environ.get("REEL_STUDIO")
    if not studio:
        return None
    python = Path(studio) / ".reel-kit" / "env" / "bin" / "python"
    return python if python.is_file() else None


def tool_status() -> dict:
    whisper = shutil.which("mlx_whisper") or shutil.which("whisper")
    return {
        "ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
        "yt-dlp": bool(shutil.which("yt-dlp")),
        "whisper": bool(whisper),
        "engine_python": str(engine_python() or ""),
        "whisper_package": whisper_package(),
    }


def install_tools(dry_run: bool = False) -> int:
    """Install yt-dlp and Whisper into the engine's own Python: no password, nothing else on the machine changes."""
    python = engine_python()
    if python is None:
        print("❌ The video engine's Python was not found. Source scripts/env.sh first (and finish setup).", file=sys.stderr)
        return 2
    command = [str(python), "-m", "pip", "install", "--upgrade", "--quiet", "yt-dlp", whisper_package()]
    if dry_run:
        print(" ".join(command))
        return 0
    print(f"Installing yt-dlp and {whisper_package()} into the video engine (a few minutes)…", file=sys.stderr)
    result = subprocess.run(command)
    if result.returncode != 0:
        print("❌ The install failed; the lines above say why.", file=sys.stderr)
        return 1
    print("✅ Video reader tools installed in the engine. The first transcription also downloads a speech model (about 1.5 GB).")
    return 0


# ── Cuts ──────────────────────────────────────────────────────────────────
def detect_cuts(video: Path, threshold: float = 0.3) -> dict:
    """Shot changes from ffmpeg's scene score, plus duration and the pace they give."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True,
    )
    duration = float(json.loads(probe.stdout or "{}").get("format", {}).get("duration") or 0)
    scan = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-an", "-vf",
         f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if scan.returncode != 0:
        raise RuntimeError(scan.stderr.strip().splitlines()[-1] if scan.stderr.strip() else "ffmpeg failed")
    times = [round(float(t), 2) for t in re.findall(r"pts_time:([0-9.]+)", scan.stderr)]
    shots = [b - a for a, b in zip([0.0, *times], [*times, duration]) if b > a]
    return {
        "duration": round(duration, 2),
        "cuts": times,
        "shots": len(shots),
        "average_shot": round(sum(shots) / len(shots), 2) if shots else round(duration, 2),
        "cuts_per_10s": round(len(times) / duration * 10, 1) if duration else 0,
        "threshold": threshold,
    }


# ── Beats ─────────────────────────────────────────────────────────────────
ON_BEAT_WINDOW = 0.1  # a cut within 0.1 s of a hit counts as on the beat (about 3 frames at 30 fps)


def detect_beats(video: Path, duration: float) -> list[dict]:
    """Run `hyperframes beats` on a throwaway project whose only track is this video's sound."""
    studio = os.environ.get("REEL_STUDIO")
    if not studio:
        raise RuntimeError("the video engine was not found: source scripts/env.sh first")
    with tempfile.TemporaryDirectory(prefix="reference-beats-") as tmp:
        project = Path(tmp)
        audio = project / "sound.m4a"
        extract = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-c:a", "aac", "-b:a", "128k", str(audio)],
            capture_output=True, text=True,
        )
        if extract.returncode != 0 or not audio.exists():
            raise RuntimeError("this video has no sound to find beats in")
        (project / "index.html").write_text(
            '<!doctype html><html><body><div id="root" data-composition-id="reference" data-width="1080" '
            f'data-height="1920" data-duration="{duration:.3f}"><audio id="music" src="sound.m4a" '
            'data-start="0" data-track-index="0"></audio></div></body></html>\n',
            encoding="utf-8",
        )
        run = subprocess.run(["npx", "hyperframes", "beats", str(project), "--json"], cwd=studio, capture_output=True, text=True)
        result = project / "beats" / "sound.m4a.json"
        if run.returncode != 0 or not result.exists():
            raise RuntimeError("the engine could not find beats: " + (run.stderr or run.stdout).strip()[-300:])
        return json.loads(result.read_text(encoding="utf-8")).get("beats") or []


def beat_report(beats: list[dict], cuts: list[float], duration: float) -> dict:
    times = [b["time"] for b in beats]
    gaps = sorted(b - a for a, b in zip(times, times[1:]) if b > a)
    bpm = round(60 / gaps[len(gaps) // 2], 1) if gaps else 0  # median gap: robust to missed hits
    on_beat = [c for c in cuts if any(abs(c - t) <= ON_BEAT_WINDOW for t in times)]
    strongest = sorted(beats, key=lambda b: -b.get("strength", 0))[:8]
    # Share of the timeline within the window of some hit: what random cuts would score. Dense hits make it high.
    covered, end = 0.0, 0.0
    for t in times:
        lo, hi = max(t - ON_BEAT_WINDOW, end, 0.0), min(t + ON_BEAT_WINDOW, duration)
        covered += max(0.0, hi - lo)
        end = max(end, hi)
    chance = covered / duration if duration else 0
    return {
        "duration": round(duration, 2),
        "hits": len(times),
        "bpm": bpm,
        "bpm_note": "may be double time; half is %.1f" % (bpm / 2) if bpm > 170 else "",
        "strongest_hits": sorted(round(b["time"], 2) for b in strongest),
        "cuts": len(cuts),
        "cuts_on_a_hit": len(on_beat),
        "by_chance": round(chance * len(cuts), 1),
        "window_s": ON_BEAT_WINDOW,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    helper = sub.add_parser("helper", help="Is the media fetcher skill installed?")
    helper.add_argument("--json", action="store_true")
    tools = sub.add_parser("tools", help="Are yt-dlp and Whisper available?")
    tools.add_argument("--install", action="store_true", help="Install them into the engine (ask the person first)")
    tools.add_argument("--dry-run", action="store_true", help="With --install: print the command only")
    cuts = sub.add_parser("cuts", help="Shot changes and pace of a video")
    cuts.add_argument("video")
    cuts.add_argument("--threshold", type=float, default=0.3, help="Scene score for a cut (0-1, default 0.3)")
    cuts.add_argument("--json", action="store_true")
    beats = sub.add_parser("beats", help="Music hits, tempo, and how many cuts land on a hit")
    beats.add_argument("video")
    beats.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "helper":
        report = find_helper()
        if args.json:
            print(json.dumps(report, indent=2))
        elif report["state"] == "ready":
            print(f"✅ media fetcher ready: {report['path']}")
        elif report["state"] == "outdated":
            print(f"⚠️ media fetcher is an older copy (YouTube captions only): {report['path']}\n   update: {report['update']}")
        else:
            print(f"media fetcher not installed.\n   install: {report['install']}")
        return 0 if report["state"] == "ready" else 3

    if args.command == "tools":
        if args.install:
            return install_tools(args.dry_run)
        status = tool_status()
        missing = [name for name in ("ffmpeg", "yt-dlp", "whisper") if not status[name]]
        print(json.dumps({**status, "missing": missing}, indent=2))
        return 0 if not missing else 3

    video = Path(args.video).expanduser()
    if not video.is_file():
        print(f"❌ Not a file: {video}", file=sys.stderr)
        return 2
    try:
        if args.command == "beats":
            cut_report = detect_cuts(video)
            report = beat_report(detect_beats(video, cut_report["duration"]), cut_report["cuts"], cut_report["duration"])
        else:
            report = detect_cuts(video, args.threshold)
    except (RuntimeError, ValueError, OSError) as error:
        print(f"❌ {error}", file=sys.stderr)
        return 1
    if args.command == "beats":
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            note = f" ({report['bpm_note']})" if report["bpm_note"] else ""
            print(f"about {report['bpm']} bpm{note}, {report['hits']} hits; "
                  f"{report['cuts_on_a_hit']} of {report['cuts']} cuts land within {ON_BEAT_WINDOW} s of a hit "
                  f"(random cuts would score about {report['by_chance']})")
            print("strongest hits at: " + ", ".join(f"{t:.2f}" for t in report["strongest_hits"]))
        return 0
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['duration']} s, {report['shots']} shots, average {report['average_shot']} s, "
              f"{report['cuts_per_10s']} cuts per 10 s")
        print("cuts at: " + (", ".join(f"{t:.2f}" for t in report["cuts"]) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
