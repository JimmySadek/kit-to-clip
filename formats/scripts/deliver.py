#!/usr/bin/env python3
"""Kit to Clip deliver: finish one render for each destination into clear per-platform folders.

  python3 deliver.py <render.mp4> --slug perfect-rally --format fold-cut --platforms tiktok --out <deliveries>

Works for any format (neutral or from a brand's pack). Each platform has its own safe-zone layout, so deliver each
platform's own render (built with that platform's layout).

Result:
  <deliveries>/<slug>/<format>/<platform>/<slug>-<format>-<platform>-master.mp4   full quality, -14 LUFS, <= -1 dBTP
                                          ...-share.mp4       <= 30 MB for phones and chat
                                          ...-cover.png       cover frame
                                          ...-contact.png     1 frame per second of the finished file
                                          ...-safe-check.png  cover with that platform's interface zones tinted red
                                          report.json         every measured number
A video with sound is refused unless --cues <cue-sheet.json> (the sound was made for the picture: the sync check runs)
or --no-sync "reason" (for example "footage's own sound") is given: see finish/README.md.
Today Instagram and TikTok are both 9:16 (Instagram = Reels profile). Platform names map to finish profiles below.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLATFORMS = {"tiktok": "tiktok", "instagram": "instagram-reels", "youtube-shorts": "youtube-shorts",
             "instagram-feed": "instagram-feed", "youtube": "youtube"}


def find_finish():
    p = HERE.parents[1] / "finish" / "scripts" / "finish.py"     # <kit-to-clip>/finish/scripts/finish.py
    if p.exists():
        return p
    sys.exit("deliver: finish/scripts/finish.py is missing from this Kit to Clip install")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("render")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--format", required=True, help="the format id, e.g. brand-reel (formats.py list shows them)")
    ap.add_argument("--platforms", required=True, help="the platform(s) this render was built for, e.g. tiktok")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cover-at", type=float)
    ap.add_argument("--cues", help="cue sheet for a video whose sound was made for its picture: the sync check runs first")
    ap.add_argument("--no-sync", metavar="REASON", help="a video with sound needs a sync check or a reason: e.g. \"footage's own sound\"")
    a = ap.parse_args()
    finish = find_finish()
    summary = {}
    ok_all = True
    for plat in [p.strip() for p in a.platforms.split(",") if p.strip()]:
        if plat not in PLATFORMS:
            sys.exit(f"deliver: unknown platform '{plat}'. Known: {', '.join(PLATFORMS)}")
        dest = Path(a.out) / a.slug / a.format / plat
        dest.mkdir(parents=True, exist_ok=True)
        name = f"{a.slug}-{a.format}"
        cmd = [sys.executable, str(finish), "finish", a.render, "--profile", PLATFORMS[plat], "--out", str(dest), "--name", name]
        if a.cover_at is not None:
            cmd += ["--cover-at", str(a.cover_at)]
        if a.cues:
            cmd += ["--cues", a.cues]
        if a.no_sync:
            cmd += ["--no-sync", a.no_sync]
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(f"[{plat}] " + (r.stdout.strip() + ("\n" + r.stderr.strip() if r.returncode and r.stderr.strip() else "") or r.stderr.strip()))
        ok_all &= r.returncode == 0
        # tidy names: <slug>-<format>-<platform>-master.mp4 etc.; one report.json per folder
        prof = PLATFORMS[plat]
        for f in dest.glob(f"{name}-{prof}*"):
            if f.name.endswith(".report.json"):
                f.replace(dest / "report.json")
            else:
                f.replace(dest / f.name.replace(f"-{prof}", f"-{plat}"))
        summary[plat] = sorted(p.name for p in dest.iterdir())
    print(json.dumps(summary, indent=1))
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
