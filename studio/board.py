#!/usr/bin/env python3
"""④ Storyboard: one rough panel per story part and one per style join, each drawn with the style's own code.

    python3 board.py <video folder> [--film film.json]     draw every panel; the board version goes up by one
    python3 board.py <video folder> --panel p3             draw one panel again; only it and the board version go up

Panels land in <video>/.studio/results/board/ (git-ignored: they are drawn with the private style code). board.json
lists them in time order with what each was drawn from (`basis`), so the room can tell when one is out of date.
Needs Node, puppeteer-core and the bundled browser: source <kit-to-clip>/scripts/env.sh first.
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

WORKER = HERE / 'board.js'
PROFILES = HERE.parent / 'finish' / 'profiles.json'
PANEL_W, PANEL_H = 640, 360


def board_dir(video):
    return ensure_studio_dir(Path(video)) / 'results' / 'board'


def read_board(video):
    """board.json, or None before the first drawing. Reads only: no folder is made."""
    try:
        b = json.loads((Path(video) / '.studio' / 'results' / 'board' / 'board.json').read_text(encoding='utf-8'))
        return b if isinstance(b, dict) else None
    except (OSError, ValueError):
        return None


def comments(events, b):
    """The person's comments on panels, oldest first. A comment is open until its panel is drawn again."""
    now = {p['id']: p.get('version') for p in (b or {}).get('panels') or [] if isinstance(p, dict)}
    out = []
    for e in events:
        d = e.get('detail') if isinstance(e.get('detail'), dict) else {}
        if e.get('kind') == 'comment' and isinstance(d.get('panel'), str) and isinstance(d.get('text'), str):
            out.append({'n': e.get('n'), 'at': e.get('at'), 'panel': d['panel'], 'text': d['text'], 'board': d.get('board'),
                        'panel_version': d.get('panel_version'),
                        'open': d['panel'] in now and d.get('panel_version') == now[d['panel']]})
    return out


def style_time(style_run, at):
    """Where in a style's own animation a film time falls, from 0 to 1: its run of parts plays the explainer once."""
    span = max(style_run['to'] - style_run['from'], 0.001)
    return round(min(max((at - style_run['from']) / span, 0.02), 0.98), 4)


def layout(film):
    """The canvas and, for each platform with the same shape, its safe box in the film's pixels (finish/profiles.json)."""
    frame = film.get('frame') or {}
    w, h = int(frame.get('width') or 1920), int(frame.get('height') or 1080)
    safe = {}
    try:
        profiles = json.loads(PROFILES.read_text())['profiles']
    except (OSError, ValueError, KeyError):
        profiles = {}
    for name, p in profiles.items():
        c = p.get('canvas')
        if c and abs(c[0] / c[1] - w / h) < 0.01 and any(p['safe'].values()):
            s = p['safe']
            safe[name] = {'left': round(w * s['left']), 'right': w - round(w * s['right']),
                          'top': round(h * s['top']), 'bottom': h - round(h * s['bottom'])}
    return {'canvas': [w, h], 'safe': safe,
            'note': 'Rough panels: no brand yet, and text positions are only checked against the canvas and safe box.'}


def specs(film):
    """Every panel the film needs now, in time order: a join comes just before the part where the new style starts."""
    rows = compose.mapped_parts(film)
    runs = compose.runs_of(rows)
    run_of = {p['id']: r for r in runs for p, _ in r['parts']}
    joins = {j['part']: j for j in compose.joins_of(film, rows)}
    out = []
    for p, style, mode in rows:
        j = joins.get(p['id'])
        if j:                                          # the old style's last moment meets the new one's first
            out.append({'id': f'join-{p["id"]}', 'kind': 'join', 'part': p['id'], 'at': j['at'], 'type': j['type'],
                        'from_style': j['from'], 'to_style': j['to'],
                        'draw': {'a': {'style': j['from'], 't': 0.98}, 'b': {'style': j['to'], 't': 0.02}},
                        'basis': {'at': j['at'], 'from': j['from'], 'to': j['to'], 'type': j['type']}})
        mid = (p['from'] + p['to']) / 2
        out.append({'id': p['id'], 'kind': 'part', 'part': p['id'], 'name': p.get('name', ''), 'at': p['from'],
                    'from': p['from'], 'to': p['to'], 'style': style, 'brand': mode,
                    'picture': p.get('picture', ''), 'words': p.get('words', ''),
                    'draw': {'style': style, 't': style_time(run_of[p['id']], mid)},
                    'basis': {'from': p['from'], 'to': p['to'], 'style': style, 'brand': mode,
                              'picture': p.get('picture', ''), 'words': p.get('words', '')}})
    return out


def style_page(style_id):
    """One style's code on a bare page, for the worker. The code stays in memory and in the git-ignored panels."""
    s = compose.read_style(style_id)
    font = f'<link rel="stylesheet" href="{s["font"]}">' if s['font'] != compose.NO_FONT else ''
    safe = lambda code: code.replace('</script', '<\\/script')   # noqa: E731
    return (f'<!doctype html><html><head><meta charset="utf-8">{font}</head><body>'
            f'<canvas width="{PANEL_W}" height="{PANEL_H}"></canvas>'
            f'<script>{safe(s["h"])}</script><script>{safe(s["sound"])}</script><script>{safe(s["source"])}</script>'
            '</body></html>')


def tools():
    node = shutil.which('node')
    studio = os.environ.get('REEL_STUDIO', '')
    browser = os.environ.get('HYPERFRAMES_BROWSER_PATH', '')
    if not node or not (Path(studio) / 'node_modules' / 'puppeteer-core').is_dir() or not Path(browser).is_file():
        raise StudioError('drawing panels needs Node, puppeteer-core and the bundled browser: '
                          'source <kit-to-clip>/scripts/env.sh first')
    return node


def draw(video, todo):
    """Run the worker on the panels in `todo`; it writes <id>.png next to board.json."""
    node = tools()
    out = board_dir(video)
    out.mkdir(parents=True, exist_ok=True)
    styles = sorted({d['style'] for t in todo for d in ([t['draw']['a'], t['draw']['b']] if t['kind'] == 'join'
                                                         else [t['draw']])})
    with tempfile.TemporaryDirectory(prefix='k2c-board-') as tmp:
        job = {'width': PANEL_W, 'height': PANEL_H, 'out': str(out),
               'pages': {s: style_page(s) for s in styles},
               'panels': [{'id': t['id'], 'kind': t['kind'], 'draw': t['draw']} for t in todo]}
        path = Path(tmp) / 'job.json'
        path.write_text(json.dumps(job))
        r = subprocess.run([node, str(WORKER), str(path)], text=True, capture_output=True, timeout=600)
        if r.returncode:
            raise StudioError('the panels could not be drawn: ' + (r.stderr.strip().splitlines() or ['no output'])[-1][:400])
        return json.loads(r.stdout or '{}')


def build(video, film_name='film.json', panel=None):
    video = Path(video).resolve()
    film = compose.load_film(video, film_name)
    want = specs(film)
    old = read_board(video) or {'version': 0, 'panels': []}
    olds = {p['id']: p for p in old.get('panels') or []}
    if panel is not None:
        if not olds:
            raise StudioError('there is no storyboard yet: draw all panels first')
        if panel not in {w['id'] for w in want}:
            raise StudioError(f'the film has no panel "{panel}" now. Panels: ' + ', '.join(w['id'] for w in want))
        todo = [w for w in want if w['id'] == panel]
    else:
        todo = want
    report = draw(video, todo)
    drawn = {t['id'] for t in todo}
    version = int(old.get('version') or 0) + 1
    made = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    panels = []
    for w in want:
        if w['id'] in drawn:
            panels.append(dict({k: v for k, v in w.items() if k != 'draw'}, file=f'{w["id"]}.png',
                               version=int((olds.get(w['id']) or {}).get('version') or 0) + 1, drawn=made,
                               **({'note': report['notes'][w['id']]} if w['id'] in (report.get('notes') or {}) else {})))
        elif w['id'] in olds:
            panels.append(olds[w['id']])               # kept as drawn; the room shows when its basis no longer matches
    for p in board_dir(video).glob('*.png'):          # a panel the film no longer has goes
        if p.stem not in {q['id'] for q in panels}:
            p.unlink()
    board = {'version': version, 'made': made, 'film': film_name, 'redrawn': sorted(drawn) if panel else 'all',
             'layout': layout(film), 'panels': panels}
    write_atomic(board_dir(video) / 'board.json', json.dumps(board, indent=2, ensure_ascii=False) + '\n')
    return board


def main(argv=None):
    ap = argparse.ArgumentParser(description='Draw the storyboard panels for a Kit to Clip film.')
    ap.add_argument('video')
    ap.add_argument('--film', default='film.json')
    ap.add_argument('--panel', help='draw only this panel again (a part id like p3, or join-p5)')
    a = ap.parse_args(argv)
    try:
        board = build(a.video, a.film, a.panel)
    except StudioError as e:
        print(f'❌ {e}', file=sys.stderr)
        return 1
    parts = sum(1 for p in board['panels'] if p['kind'] == 'part')
    print(json.dumps({'version': board['version'], 'panels': len(board['panels']), 'parts': parts,
                      'joins': len(board['panels']) - parts, 'redrawn': board['redrawn'],
                      'folder': str(board_dir(Path(a.video).resolve()))}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
