#!/usr/bin/env python3
"""Render a Studio player HTML frame-by-frame in Playwright's/HyperFrames' bundled Chromium -> ffmpeg,
and capture the offline SFX stem (window.SCORE_STEM = 'sfx' + SOUND.renderOffline / OfflineAudioContext).

  python3 render.py <video-folder> [--html player.html] [--fps 30] [--from 0] [--to S] [--no-sfx] [--film film.json]

Outputs land in <video>/.studio/results/render/ (git-ignored):
  picture.mp4     silent H.264 video at the film's exact frame size and fps
  sfx.wav         offline SFX stem (when the player scores sound effects)
  render.json     metadata for the Music and Finish rooms

Needs Node, puppeteer-core, ffmpeg and the bundled headless browser: source <kit-to-clip>/scripts/env.sh first.
There is no separate render yes: rendering is local and the person judges the result at ✋ Final film.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compose  # noqa: E402
from compose import StudioError, ensure_studio_dir, write_atomic  # noqa: E402

WORKER = HERE / 'render.js'


def render_dir(video):
    return ensure_studio_dir(Path(video)) / 'results' / 'render'


def read_render(video):
    """render.json, or None before the first render. Reads only: no folder is made."""
    try:
        r = json.loads((Path(video) / '.studio' / 'results' / 'render' / 'render.json').read_text(encoding='utf-8'))
        return r if isinstance(r, dict) else None
    except (OSError, ValueError):
        return None


def find_player(video, film, explicit=None):
    video = Path(video).resolve()
    if explicit:
        p = Path(explicit).expanduser()
        p = p if p.is_absolute() else video / p
        if not p.is_file():
            raise StudioError(f'player HTML not found: {p}')
        return p.resolve()
    if isinstance(film.get('player'), str) and film['player'].strip():
        p = Path(film['player']).expanduser()
        p = p if p.is_absolute() else video / p
        if p.is_file():
            return p.resolve()
    for inp in film.get('inputs') or []:
        if isinstance(inp, dict) and inp.get('kind') == 'player' and inp.get('path'):
            p = compose.expand(inp['path'], video)
            if p and p.is_file():
                return p.resolve()
    for name in ('player.html', 'film.html', 'index.html'):
        p = video / name
        if p.is_file():
            return p.resolve()
    raise StudioError('no player HTML found (pass --html <file.html>, set film.player, or save player.html in the video folder)')


def tools():
    node = shutil.which('node')
    ff = shutil.which('ffmpeg')
    studio = os.environ.get('REEL_STUDIO', '')
    browser = os.environ.get('HYPERFRAMES_BROWSER_PATH', '')
    if not node or not (Path(studio) / 'node_modules' / 'puppeteer-core').is_dir() or not Path(browser).is_file():
        raise StudioError('rendering needs Node, puppeteer-core and the bundled browser: source <kit-to-clip>/scripts/env.sh first')
    if not ff:
        raise StudioError('rendering needs ffmpeg on PATH: source <kit-to-clip>/scripts/env.sh first')
    return node


def render_film(video, film_name='film.json', html=None, fps=None, start_s=None, end_s=None,
                with_sfx=True, crf=16, preset='medium', dom_screenshot=False, out_video=None):
    video = Path(video).resolve()
    film = json.loads((video / film_name).read_text(encoding='utf-8')) if (video / film_name).is_file() else {}
    player = find_player(video, film, html)
    node = tools()
    frame = film.get('frame') or {}
    w = int(frame.get('width') or 1280)
    h = int(frame.get('height') or 720)
    use_fps = int(fps or frame.get('fps') or 30)
    out = render_dir(video)
    out.mkdir(parents=True, exist_ok=True)
    video_path = Path(out_video).resolve() if out_video else (out / 'picture.mp4')
    sfx_path = (out / 'sfx.wav') if with_sfx else None
    if sfx_path and sfx_path.exists():
        sfx_path.unlink()

    with tempfile.TemporaryDirectory(prefix='k2c-render-') as tmp:
        job = {
            'html': str(player),
            'width': w,
            'height': h,
            'fps': use_fps,
            'duration': film.get('length'),
            'from': start_s,
            'to': end_s,
            'crf': crf,
            'preset': preset,
            'dom_screenshot': bool(dom_screenshot),
            'out_video': str(video_path),
            'out_sfx': str(sfx_path) if sfx_path else None,
        }
        job_path = Path(tmp) / 'job.json'
        job_path.write_text(json.dumps(job), encoding='utf-8')
        r = subprocess.run([node, str(WORKER), str(job_path)], text=True, capture_output=True, timeout=3600)
        if r.returncode:
            err = (r.stderr.strip().splitlines() or ['render failed'])[-1][:400]
            raise StudioError(f'render failed: {err}')
        report = json.loads(r.stdout or '{}')

    old = read_render(video) or {'version': 0}
    made = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    try:
        player_rel = str(player.relative_to(video))
    except ValueError:
        player_rel = str(player)
    doc = {
        'version': int(old.get('version') or 0) + 1,
        'made': made,
        'film': film_name,
        'player': player_rel,
        'picture': video_path.name if video_path.parent == out else str(video_path),
        'sfx': 'sfx.wav' if report.get('sfx') else None,
        'sfx_note': report.get('sfx_note'),
        'width': report.get('width', w),
        'height': report.get('height', h),
        'fps': report.get('fps', use_fps),
        'frames': report.get('frames'),
        'duration': report.get('duration'),
    }
    write_atomic(out / 'render.json', json.dumps(doc, indent=2, ensure_ascii=False) + '\n')
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description='Render a Studio player HTML frame-by-frame to picture.mp4 and sfx.wav.')
    ap.add_argument('video')
    ap.add_argument('--film', default='film.json')
    ap.add_argument('--html', help='path to the player HTML (default film.player or player.html)')
    ap.add_argument('--fps', type=int, help='frames per second (default from film.json or 30)')
    ap.add_argument('--from', dest='start_s', type=float, help='render start time in seconds')
    ap.add_argument('--to', dest='end_s', type=float, help='render end time in seconds')
    ap.add_argument('--crf', type=int, default=16)
    ap.add_argument('--preset', default='medium')
    ap.add_argument('--no-sfx', action='store_true', help='skip offline SFX extraction')
    ap.add_argument('--dom', action='store_true', help='screenshot the full viewport instead of the canvas element')
    ap.add_argument('--out', help='override output video path')
    a = ap.parse_args(argv)
    try:
        doc = render_film(a.video, a.film, a.html, a.fps, a.start_s, a.end_s, not a.no_sfx, a.crf, a.preset, a.dom, a.out)
    except StudioError as e:
        print(f'❌ {e}', file=sys.stderr)
        return 1
    print(json.dumps(doc, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
