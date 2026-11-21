#!/usr/bin/env python3
"""Kit to Clip Studio: a small local server for one video folder's film.json, its rooms and its event log.

  python3 studio.py open <video-folder> [--film film.json] [--room styles]   start (or reuse) and print the URL
  python3 studio.py stop <video-folder>                                    stop that folder's server
  python3 studio.py events <video-folder> [--since N]                      print the clicks logged after line N
  python3 studio.py wait <video-folder> --since N [--timeout S]            block until a click Claude must answer
  python3 studio.py ask <video-folder> <stop> "<version>"                  ask for a ✋ yes on one version
  python3 studio.py approvals <video-folder> [--record]                    each stop's state; --record writes clicked yeses
  python3 studio.py yes <video-folder> <stop> --words "…"                  record a yes the person said in chat

Safety: binds 127.0.0.1 only on a random port; a secret key in the first URL only, swapped for an HttpOnly,
SameSite=Strict cookie; the Host header must name this server (no DNS rebinding); writes must come from the Studio's own
origin; no referrer leaves the page. Style previews run in a sandboxed frame with an opaque origin and a content policy
that blocks every request except Google Fonts. Standard library only. The server stops after 4 hours with no request.
"""
import argparse
import datetime as dt
import hmac
import html
import importlib.util
import json
import mimetypes
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import approvals  # noqa: E402  (the Studio's own folder)
import board  # noqa: E402
import mix  # noqa: E402
import music  # noqa: E402
import render  # noqa: E402
import voice  # noqa: E402
import compose  # noqa: E402
from compose import StudioError, ensure_studio_dir, write_atomic  # noqa: E402

PAGE = HERE / 'page'
ROOMS = ('start', 'story', 'styles', 'voice', 'board', 'music', 'finish')
PAGE_SECTIONS = ('start', 'styles', 'rooms', 'brand', 'parts', 'story', 'script', 'music', 'finish')   # sections the page may replace
EVENT_KINDS = ('open', 'paste', 'upload', 'map', 'brand', 'brand-pick', 'join', 'preset', 'shortlist', 'copy-prompt',
               'copy-build-prompt', 'ask', 'not-yet', 'parts', 'story', 'script', 'comment', 'music', 'finish')
# A click Claude has to answer: `wait` returns on these. `approve` and `reopen` lines are written by the server only.
WAKE_KINDS = ('ask', 'approve', 'not-yet', 'comment')
VOICE_ROUTES = ('ai-studio', 'own', 'kokoro', 'none')
STOP_ROOMS = {'script': 'story', 'storyboard': 'board', 'music': 'music', 'final': 'finish'}
BRAND_PY = HERE.parent / 'scripts' / 'brand.py'
IDLE_SECONDS = float(os.environ.get('KIT_TO_CLIP_STUDIO_IDLE') or 4 * 3600)   # tests set a short one
CLOSE_GRACE = float(os.environ.get('KIT_TO_CLIP_STUDIO_GRACE') or 2.5)   # a planned stop keeps answering this
                                                                            # long, so an open page says "closed" calmly
MAX_JSON_BYTES = 2_000_000
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
CHUNK = 1024 * 1024
INPUT_KINDS = (('voice', ('.wav', '.mp3', '.m4a', '.aif', '.aiff', '.flac')), ('footage', ('.mp4', '.mov', '.mkv', '.webm')),
               ('inspiration', ('.png', '.jpg', '.jpeg', '.gif', '.webp')), ('script', ('.txt', '.md', '.doc', '.docx', '.rtf', '.pdf')))
STUDIO_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
              "font-src https://fonts.gstatic.com; img-src 'self' data:; frame-src 'self'; connect-src 'self'; "
              "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
PREVIEW_CSP = ("default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
               "font-src https://fonts.gstatic.com; img-src data: blob:; connect-src 'none'; "
               "sandbox allow-scripts; frame-ancestors 'self'; form-action 'none'; base-uri 'none'")

# Our loop for a style's hero frame inside the sandboxed preview. The parent page sends {k2c: 'play'|'pause'}.
PREVIEW_LOOP = r"""
(function () {
  const style = (window.STYLES || [])[0], canvas = document.querySelector('canvas');
  if (!style || !window.H) { document.body.dataset.state = 'empty'; return; }
  const q = new URLSearchParams(location.search), demo = q.get('demo') === '1';
  const length = demo ? (style.explainerDuration || 15) : (style.duration || 6);
  const shown = demo ? Object.assign(Object.create(style), { draw: style.explainer }) : style;
  if (!demo) { canvas.width = 480; canvas.height = 270; }      // a card is small: fewer pixels keep the page quick
  // Styles are written for frame-by-frame renders and a frame can take 100+ ms, so a card spaces its frames to use
  // at most about a third of the time. The demo draws as fast as the style allows.
  let playing = demo, from = parseFloat(q.get('t0')) || 0, started = performance.now(), last = 0, cost = 0;
  const at = () => (from + (performance.now() - started) / 1000) % length;
  const frame = () => {
    const t0 = performance.now();
    try { H.render(shown, canvas, demo ? at() : (style.frameT || 0) + at()); } catch (e) { document.body.dataset.state = 'error'; }
    cost = cost ? cost * 0.7 + (performance.now() - t0) * 0.3 : performance.now() - t0;
  };
  const tick = (now) => {
    if (!playing) return;
    if (!now || now - last >= (demo ? 0 : Math.max(1000 / 24, cost * 3))) { last = now || 0; frame(); }
    requestAnimationFrame(tick);
  };
  window.addEventListener('message', (e) => {
    const k = e.data && e.data.k2c;
    if (k === 'play' && !playing) { playing = true; started = performance.now(); tick(); }
    if (k === 'pause' && playing) { playing = false; from = at(); }
  });
  Promise.resolve(H.loadFonts ? H.loadFonts(style) : 0).catch(() => 0).then(() => {
    frame(); document.body.dataset.state = 'drawn'; if (playing) tick();
    parent.postMessage({ k2c: 'ready' }, '*');
  });
})();
"""

NO_PREVIEW = ('<!doctype html><html><head><meta charset="utf-8"><title>No preview</title><style>html,body{margin:0;height:100%;'
              'background:#1f2624;color:#c9d3cf;font:13px/1.4 system-ui,sans-serif}body{display:grid;place-content:center;'
              'padding:12px;text-align:center}small{display:block;margin-top:4px;color:#8c9a95;font-size:11px}</style></head>'
              '<body><div>No live preview for this style<small>{why}</small></div></body></html>')


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def count_lines(path):
    try:
        with open(path, 'rb') as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def read_server(video):
    try:
        return json.loads((Path(video) / '.studio' / 'server.json').read_text())
    except (OSError, ValueError):
        return None


def write_private(path, text):
    """Write a file only its owner can read (mode 0600)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(text)


def safe_name(raw):
    """A dropped file's base name only: no folders, no '..', no hidden names."""
    name = os.path.basename(urllib.parse.unquote(raw or '').replace('\\', '/')).strip()
    name = ''.join(c for c in name if c.isprintable() and c not in '/\\:')
    name = name.lstrip('.')
    stem, ext = os.path.splitext(name)
    if len(name) > 120:                                   # file systems refuse long names; keep the extension
        name = stem[:120 - len(ext[:16])] + ext[:16]
    return name or None


def input_kind(name):
    ext = os.path.splitext(name)[1].lower()
    return next((k for k, exts in INPUT_KINDS if ext in exts), 'other')


class Studio:
    """The state one server keeps: its folder, its secret, its locks and its event counter."""

    def __init__(self, video, film='film.json'):
        self.video = Path(video).resolve()
        self.film_name = film
        self.studio = ensure_studio_dir(self.video)
        self.key = secrets.token_urlsafe(24)
        self.session = secrets.token_urlsafe(24)
        self.write_lock = threading.Lock()      # one page write to film.json at a time
        self.event_lock = threading.Lock()      # one appended line at a time
        self.last_request = time.monotonic()
        self.port = None
        self.closing = None                     # 'stop' or 'idle' once a planned stop has begun
        self.events_path = self.studio / 'events.jsonl'
        self.next_n = 1 + self.count_events()
        self.approve_key = approvals.signing_key(self.video, create=True)
        self.approve_seq = approvals.last_seq(self.video)

    @property
    def film_path(self):
        return self.video / self.film_name

    def count_events(self):
        return count_lines(self.events_path)

    def read_film(self):
        return json.loads(self.film_path.read_text(encoding='utf-8'))

    def replace_sections(self, sections, base=None):
        """Replace whole top-level sections; every other field, known or not, stays as it is on disk.
        Returns the new stamp and whether the file had changed since `base`, the stamp the page last loaded."""
        with self.write_lock:
            before = self.film_path.stat().st_mtime_ns
            film = self.read_film()
            film.update(sections)
            write_atomic(self.film_path, json.dumps(film, indent=2, ensure_ascii=False) + '\n')
            return self.film_path.stat().st_mtime_ns, base is not None and before != base

    def _write_line(self, line):
        with open(self.events_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(line, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        self.next_n = line['n'] + 1
        return line

    def _next(self):
        """A line's n is its place in the log, counted again each time: a line someone added by hand cannot make a
        later click look older than Claude's ask."""
        self.next_n = 1 + self.count_events()
        return self.next_n

    def append_event(self, room, kind, detail):
        with self.event_lock:
            return self._write_line({'n': self._next(), 'at': now_iso(), 'room': room, 'kind': kind, 'detail': detail})

    def approve(self, stop, asked, room):
        """A ✋ Yes click: one stamped `approve` line, only for the version Claude asks about now and only once.
        Returns (line, None), or (None, why) when the click cannot count."""
        with self.event_lock:
            film = self.read_film()
            row = approvals.status(self.video, film).get(stop)
            if row is None:
                return None, f'{stop} is not a stop'
            why = {'none': 'Claude has not asked for this yes yet',
                   'clicked': 'your yes is already logged; Claude records it next',
                   'approved': 'this version already has its yes',
                   'reopened': 'something changed after your yes; Claude asks again first',
                   'outdated': ('new music takes were made after Claude asked; listen to the new takes and Claude asks again first'
                                if row.get('music_outdated')
                                else 'the panels were drawn again after Claude asked; Claude asks again first')}.get(row['state'])
            if why:
                return None, why
            if stop == 'music':
                cues = music.cues_for_film(film)
                if cues:
                    mres = music.read_music_results(self.video)
                    res_cues = mres.get('cues') if isinstance(mres, dict) and isinstance(mres.get('cues'), dict) else {}
                    if not res_cues:
                        return None, 'make and listen to takes for every cue before approving the music'
                    for cue in cues:
                        cm = res_cues.get(cue['id'])
                        takes = cm.get('takes') if isinstance(cm, dict) else None
                        if not takes:
                            return None, 'listen and pick a take for every cue before approving the music'
                        cur_round = int(cm.get('round') or 1)
                        pick = cue.get('pick')
                        pick_round = cue.get('pick_round')
                        if pick is None or pick_round is None or int(pick_round) != cur_round:
                            return None, 'listen and pick a take for every cue before approving the music'
                        if not any(int(t.get('n', -1)) == int(pick) for t in takes if isinstance(t, dict)):
                            return None, 'listen and pick a take for every cue before approving the music'
            if asked != row['asked']:
                return None, f'Claude now asks about "{row["asked"]}"; reload to see it'
            n, at, seq = self._next(), now_iso(), self.approve_seq + 1
            line = self._write_line({'n': n, 'at': at, 'room': room, 'kind': 'approve',
                                     'detail': {'stop': stop, 'asked': asked},
                                     'stamp': approvals.stamp(self.approve_key, n, at, stop, asked, seq)})
            self.approve_seq = seq
            return line, None

    def stamp(self):
        def mtime(p):
            try:
                return p.stat().st_mtime_ns
            except OSError:
                return 0
        results = self.studio / 'results'
        newest = max([mtime(results)] + [mtime(p) for p in results.rglob('*')] if results.is_dir() else [0])
        watching = read_watch(self.video)
        return {'film': str(mtime(self.film_path)), 'results': newest, 'watching': bool(watching),   # film as text: ns overflow JS numbers
                'closing': self.closing}

    def update_film(self, change):
        """Change film.json in place under the write lock; `change` edits the dict and may return a value."""
        with self.write_lock:
            film = self.read_film()
            out = change(film)
            write_atomic(self.film_path, json.dumps(film, indent=2, ensure_ascii=False) + '\n')
            return out

    def set_take(self, seg, fields, token=None):
        """Update one voice take. With a token, only the drop that started this run may finish it."""
        def change(film):
            v = film.get('voice') if isinstance(film.get('voice'), dict) else {}
            takes = v.get('takes') if isinstance(v.get('takes'), dict) else {}
            if token is not None and (takes.get(seg) or {}).get('token') != token:
                return False
            takes[seg] = dict(takes.get(seg) or {}, **fields) if token is not None else fields
            v['takes'] = takes
            film['voice'] = v
            rooms = film.get('rooms') if isinstance(film.get('rooms'), dict) else {}
            if rooms.get('voice', 'empty') == 'empty':
                film['rooms'] = dict(rooms, voice='draft')
            return True
        return self.update_film(change)

    def time_take(self, seg, text, rel, token):
        """In a thread: hear the take, match it to the clean copy, record the result."""
        try:
            fields = voice.time_take(self.video, seg, text, rel)
        except Exception as e:                    # noqa: BLE001  a failed take says why in the room
            fields = {'state': 'failed', 'error': str(e)[:400]}
        if self.set_take(seg, fields, token):
            self.append_event('voice', 'voice', {'segment': seg, 'action': fields['state'],
                                                 **({'flagged': fields['flagged']} if 'flagged' in fields else {})})

    def add_input(self, rel, kind, note):
        with self.write_lock:
            film = self.read_film()
            film.setdefault('inputs', []).append({'kind': kind, 'path': rel, 'note': note})
            write_atomic(self.film_path, json.dumps(film, indent=2, ensure_ascii=False) + '\n')


def installed_brands(video):
    """The brand skills found by scripts/brand.py: video packs and brand kits on this computer and in the video's repo.
    Returns [{"skill": folder name, "name": shown name, "pack": has a video pack}], sorted by name; [] when none."""
    try:
        spec = importlib.util.spec_from_file_location('k2c_brand', BRAND_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        top = subprocess.run(['git', '-C', str(video), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        found = mod.detect(Path(top.stdout.strip() or video).resolve())
    except (Exception, SystemExit):            # a missing bridge or an unreadable kit: the picker still offers the rest
        return []
    out = {}
    for p in found.get('packs', []) + found.get('installed', []):
        out.setdefault(Path(p['kit']).name, {'name': p.get('name') or Path(p['kit']).name, 'pack': True})
    repo_kits = [Path(k) for k in found.get('kits', [])]
    repo_kits = [k for k in repo_kits if re.search(r'-(brand|design|identity)$', k.name) and mod.has_logo(k)]   # not helper skills
    for k in [Path(k['path']) for k in found.get('installed_kits', [])] + repo_kits:
        words = re.sub(r'-(brand|design|identity)$', '', k.name).split('-')
        out.setdefault(k.name, {'name': ' '.join(w.upper() if len(w) <= 3 else w.capitalize() for w in words), 'pack': False})
    return sorted(({'skill': k, **v} for k, v in out.items()), key=lambda b: b['name'].lower())


def check_brand(brand, allowed):
    """film.brand from the page: null, an installed brand skill {name, skill}, or another brand {name, skill: null,
    other: true} that Claude asks the guide for."""
    if brand is None:
        return None
    if not isinstance(brand, dict) or set(brand) - {'name', 'skill', 'other'}:
        raise ValueError('a brand is null or {name, skill, other}')
    name, skill = brand.get('name'), brand.get('skill')
    if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError('a brand needs a short name')
    if skill is None:
        if brand.get('other') is not True:
            raise ValueError('a brand without a skill is "another brand" (other: true)')
        return {'name': name.strip(), 'skill': None, 'other': True}
    if not isinstance(skill, str) or skill not in allowed:
        raise ValueError(f'"{skill}" is not a brand skill installed on this computer')
    return {'name': name.strip(), 'skill': skill}


PART_ID = re.compile(r'[A-Za-z0-9_-]{1,40}')
PART_TEXT = ('name', 'words', 'picture', 'sound')


def check_parts(parts, styles):
    """Story parts from the Story room, always sent with styles: unique ids, each part ends after it starts, back to
    back with no gap, and a map and joins that name only these parts. Anything wrong refuses the whole request."""
    if not isinstance(parts, list) or not parts:
        raise ValueError('parts is a list of at least one part')
    if len(parts) > 400:
        raise ValueError('at most 400 parts')
    ids = []
    for i, p in enumerate(parts):
        if not isinstance(p, dict):
            raise ValueError(f'part {i + 1} is not an object')
        pid = p.get('id')
        if not isinstance(pid, str) or not PART_ID.fullmatch(pid):
            raise ValueError(f'part {i + 1} needs a short id (letters, digits, - or _)')
        if pid in ids:
            raise ValueError(f'two parts are called {pid}')
        ids.append(pid)
        a, b = p.get('from'), p.get('to')
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (a, b)) or not 0 <= a < b:
            raise ValueError(f'{pid} needs a start and an end in seconds, the end after the start')
        if i and abs(parts[i - 1]['to'] - a) > 1e-6:
            raise ValueError(f'{pid} must start where {parts[i - 1]["id"]} ends ({parts[i - 1]["to"]} s)')
        for k in PART_TEXT:
            if k in p and (not isinstance(p[k], str) or len(p[k]) > 20000):
                raise ValueError(f'{pid}: {k} is text of up to 20000 characters')
    if not isinstance(styles, dict):
        raise ValueError('styles is an object')
    for field in ('map', 'joins'):
        extra = sorted(set(styles.get(field) or {}) - set(ids)) if isinstance(styles.get(field) or {}, dict) else ['?']
        if extra:
            raise ValueError(f'styles.{field} names parts that do not exist: {", ".join(extra)}')
    return parts


def _text(v, what, most=2000):
    if not isinstance(v, str) or len(v) > most:
        raise ValueError(f'{what} is text of up to {most} characters')
    return v


def check_story(story):
    """film.story: {ideas: [{id, title, line, why}], picked: an idea id or null, beats: [{id, text}]}."""
    if not isinstance(story, dict) or set(story) - {'ideas', 'picked', 'beats'}:
        raise ValueError('story is {ideas, picked, beats}')
    ideas, beats = story.get('ideas') or [], story.get('beats') or []
    if not isinstance(ideas, list) or len(ideas) > 6 or not isinstance(beats, list) or len(beats) > 60:
        raise ValueError('a story has up to 6 ideas and 60 beats')
    ids = set()
    for i in ideas:
        if not isinstance(i, dict) or not isinstance(i.get('id'), str) or not PART_ID.fullmatch(i['id']):
            raise ValueError('each idea needs a short id')
        ids.add(i['id'])
        for k in ('title', 'line', 'why'):
            if k in i:
                _text(i[k], f'idea {k}')
    if story.get('picked') is not None and story['picked'] not in ids:
        raise ValueError('the picked idea is not in the list')
    for b in beats:
        if not isinstance(b, dict) or not isinstance(b.get('id'), str) or not PART_ID.fullmatch(b['id']):
            raise ValueError('each beat needs a short id')
        _text(b.get('text', ''), 'a beat')
    return story


def check_script(script):
    """film.script: {model, voice, segments: [{id, style, text}]}, in the form Gemini TTS reads. Square brackets can be
    read aloud, so none is ever saved (the page turns them into tags first)."""
    if not isinstance(script, dict) or set(script) - {'model', 'voice', 'segments'}:
        raise ValueError('script is {model, voice, segments}')
    for k in ('model', 'voice'):
        if k in script:
            _text(script[k], f'the {k}', 200)
    segs = script.get('segments') or []
    if not isinstance(segs, list) or len(segs) > 100:
        raise ValueError('a script has up to 100 segments')
    seen = set()
    for g in segs:
        if not isinstance(g, dict) or not isinstance(g.get('id'), str) or not PART_ID.fullmatch(g['id']) or g['id'] in seen:
            raise ValueError('each segment needs its own short id')
        seen.add(g['id'])
        style, text = _text(g.get('style', ''), 'a Style line', 300), _text(g.get('text', ''), 'a segment', 5000)
        if re.search(r'[\[\]]', style + text):
            raise ValueError(f'{g["id"]}: never square brackets, they can be read aloud. Use a tag like <short pause>')
    return script


def check_music(m):
    """film.music: {cues: {<id>: {name, style, bpm, key, hits, spans, layers, pick, wrong}}, avoid: [[word, reason]]}."""
    if not isinstance(m, dict) or set(m) - {'cues', 'avoid'}:
        raise ValueError('music is {cues, avoid}')
    cues = m.get('cues')
    if cues is not None:
        if not isinstance(cues, dict) or len(cues) > 40:
            raise ValueError('music.cues is an object of up to 40 cues')
        for cid, c in cues.items():
            if not isinstance(cid, str) or not PART_ID.fullmatch(cid) or not isinstance(c, dict):
                raise ValueError('each music cue needs a short id and an object')
            for k in ('name', 'key', 'hits', 'wrong'):
                if k in c and c[k] is not None:
                    _text(c[k], f'cue {cid} {k}', 1000)
            if 'style' in c and c['style'] is not None:
                _text(c['style'], f'cue {cid} style', 120)
            if 'bpm' in c and c['bpm'] is not None:
                bpm = c['bpm']
                if not isinstance(bpm, (int, float)) or isinstance(bpm, bool) or not 40 <= bpm <= 240:
                    raise ValueError(f'cue {cid}: bpm must be between 40 and 240')
            if 'pick' in c and c['pick'] is not None:
                if not isinstance(c['pick'], int) or isinstance(c['pick'], bool) or not 1 <= c['pick'] <= 20:
                    raise ValueError(f'cue {cid}: pick must be a take number (1..20) or null')
            if 'pick_round' in c and c['pick_round'] is not None:
                if not isinstance(c['pick_round'], int) or isinstance(c['pick_round'], bool) or not 1 <= c['pick_round'] <= 1000:
                    raise ValueError(f'cue {cid}: pick_round must be a positive round number or null')
            if 'layers' in c and c['layers'] is not None:
                if not isinstance(c['layers'], list) or len(c['layers']) > 10:
                    raise ValueError(f'cue {cid}: layers is a list of up to 10 layers')
                for lay in c['layers']:
                    if not isinstance(lay, dict):
                        raise ValueError(f'cue {cid}: each layer is an object')
                    _text(lay.get('layer', ''), 'layer name', 120)
                    chips = lay.get('chips') or []
                    if not isinstance(chips, list) or len(chips) > 30:
                        raise ValueError(f'cue {cid}: each layer has up to 30 keyword chips')
                    for ch in chips:
                        if not isinstance(ch, list) or len(ch) < 1 or len(ch) > 2:
                            raise ValueError(f'cue {cid}: each chip is [keyword, reason]')
                        _text(ch[0], 'keyword', 200)
                        if len(ch) == 2:
                            _text(ch[1], 'keyword reason', 500)
            if 'spans' in c and c['spans'] is not None:
                if not isinstance(c['spans'], list) or len(c['spans']) > 40:
                    raise ValueError(f'cue {cid}: spans is a list of [from, to] pairs')
                for sp in c['spans']:
                    if (not isinstance(sp, list) or len(sp) != 2
                            or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in sp)
                            or not 0 <= sp[0] < sp[1]):
                        raise ValueError(f'cue {cid}: each span is [from, to] in seconds')
    avoid = m.get('avoid')
    if avoid is not None:
        if not isinstance(avoid, list) or len(avoid) > 60:
            raise ValueError('music.avoid is a list of up to 60 [word, reason] pairs')
        for item in avoid:
            if not isinstance(item, list) or len(item) < 1 or len(item) > 2:
                raise ValueError('each avoided word is [word, reason]')
            _text(item[0], 'avoided word', 120)
            if len(item) == 2:
                _text(item[1], 'avoided word reason', 500)
    return m


def check_finish(f):
    """film.finish: {formats: {wide, tall, square}, captions: burned|srt|off, lufs: -24..-8}."""
    if not isinstance(f, dict) or set(f) - {'formats', 'captions', 'lufs'}:
        raise ValueError('finish is {formats, captions, lufs}')
    if 'formats' in f and f['formats'] is not None:
        fmts = f['formats']
        if not isinstance(fmts, dict) or set(fmts) - {'wide', 'tall', 'square'} or not all(isinstance(v, bool) for v in fmts.values()):
            raise ValueError('finish.formats is booleans for wide, tall, square')
    if 'captions' in f and f['captions'] is not None:
        if f['captions'] not in ('burned', 'srt', 'off'):
            raise ValueError('finish.captions must be burned, srt or off')
    if 'lufs' in f and f['lufs'] is not None:
        v = f['lufs']
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not -24 <= v <= -8:
            raise ValueError('finish.lufs must be between -24 and -8')
    return f


def read_watch(video):
    """The running `wait` process, if any (its pid in .studio/watching)."""
    try:
        pid = int((Path(video) / '.studio' / 'watching').read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if pid_alive(pid) else None


def styles_payload(atlas_set):
    keep = ('id', 'order', 'name', 'family', 'ground', 'look', 'motion', 'explains', 'fit', 'comparison_labels')
    families = list(json.loads(compose.CATALOGUE.read_text()).get('families', []))
    styles = [{k: s[k] for k in keep if k in s} for s in compose.catalogue().values()]
    return {'atlas': atlas_set, 'families': families, 'joins': compose.joins_config(), 'styles': styles}


def preview_page(style_id, nonce):
    s = compose.read_style(style_id)
    font = (f'<link rel="stylesheet" href="{html.escape(s["font"])}">' if s['font'] != compose.NO_FONT else '')
    safe = lambda code: code.replace('</script', '<\\/script')   # noqa: E731
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(s["name"])}</title>{font}'
            '<style>html,body{margin:0;height:100%;background:#1f2624;overflow:hidden}'
            'canvas{display:block;width:100%;height:100%;object-fit:contain}</style></head>'
            '<body><canvas width="1280" height="720"></canvas>'
            f'<script nonce="{nonce}">{safe(s["h"])}</script>'
            f'<script nonce="{nonce}">{safe(s["sound"])}</script>'
            f'<script nonce="{nonce}">{safe(s["source"])}</script>'
            f'<script nonce="{nonce}">{PREVIEW_LOOP}</script></body></html>')


def make_handler(st):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'KitToClipStudio'
        sys_version = ''

        def log_message(self, fmt, *args):     # quiet: no request lines in the server log
            pass

        # -- answers --
        def send(self, code, body=b'', ctype='text/plain; charset=utf-8', headers=None):
            if isinstance(body, str):
                body = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def json(self, code, data):
            self.send(code, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')

        def refuse(self, why='forbidden'):
            self.send(403, why)

        # -- checks --
        def host_ok(self):
            return self.headers.get('Host') == f'127.0.0.1:{st.port}'

        def cookie_ok(self):
            for part in (self.headers.get('Cookie') or '').split(';'):
                name, _, value = part.strip().partition('=')
                if name == f'studio_{st.port}' and hmac.compare_digest(value, st.session):
                    return True
            return False

        def origin_ok(self):
            return self.headers.get('Origin') == f'http://127.0.0.1:{st.port}'

        def body_json(self):
            n = int(self.headers.get('Content-Length') or 0)
            if n <= 0 or n > MAX_JSON_BYTES:
                raise ValueError('a JSON body of up to 2 MB is needed')
            data = json.loads(self.rfile.read(n))
            if not isinstance(data, dict):
                raise ValueError('the body must be a JSON object')
            return data

        def gate(self):
            """Every request: the right Host. Then the key (entry URL only) or the cookie."""
            st.last_request = time.monotonic()
            if not self.host_ok():
                self.refuse('wrong host')
                return None
            url = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(url.query)
            if 'key' in query:
                if self.command == 'GET' and url.path == '/' and hmac.compare_digest(query['key'][0], st.key):
                    room = query.get('room', [''])[0]
                    target = '/' + ('#' + room if room in ROOMS else '')
                    nonce = secrets.token_urlsafe(12)
                    self.send(200, f'<!doctype html><meta charset="utf-8"><title>Kit to Clip Studio</title>'
                                   f'<script nonce="{nonce}">location.replace({json.dumps(target)})</script>',
                              'text/html; charset=utf-8',
                              {'Set-Cookie': f'studio_{st.port}={st.session}; HttpOnly; SameSite=Strict; Path=/',
                               'Content-Security-Policy': f"default-src 'none'; script-src 'nonce-{nonce}'"})
                else:
                    self.refuse('the key works only on the Studio entry URL')
                return None
            if not self.cookie_ok():
                self.refuse('open the Studio from the URL that studio.py open printed')
                return None
            return url

        # -- routes --
        def do_GET(self):
            url = self.gate()
            if url is None:
                return
            path = url.path
            if path == '/' or path == '/index.html':
                return self.page_file('index.html')
            if path.startswith('/page/'):
                return self.page_file(path[len('/page/'):])
            if path == '/api/film':
                try:                              # the stamp is taken first: if Claude writes in between, it is older
                    stamp = st.film_path.stat().st_mtime_ns
                    return self.send(200, st.film_path.read_bytes(), 'application/json; charset=utf-8',
                                     {'X-Film-Stamp': str(stamp)})
                except OSError:
                    return self.json(404, {'error': f'no {st.film_name} in the video folder yet'})
            if path == '/api/stamp':
                return self.json(200, st.stamp())
            if path == '/api/info':
                return self.json(200, {'folder': str(st.video), 'inputs': str(st.video / 'inputs'), 'film': st.film_name,
                                       'max_upload': MAX_UPLOAD_BYTES, 'events': st.next_n - 1, 'idle': IDLE_SECONDS})
            if path == '/api/approvals':
                try:
                    film = st.read_film()
                except (OSError, ValueError):
                    return self.json(404, {'error': f'no readable {st.film_name}'})
                return self.json(200, {'stops': list(approvals.status(st.video, film).values())})
            if path == '/api/brands':
                return self.json(200, {'brands': installed_brands(st.video)})
            if path == '/api/styles':
                try:
                    atlas = compose.atlas_dir() is not None
                except StudioError:
                    atlas = False
                return self.json(200, styles_payload(atlas))
            if path.startswith('/preview/'):
                return self.preview(path[len('/preview/'):])
            if path.startswith('/voice/'):
                return self.voice_file(path[len('/voice/'):])
            if path == '/api/board':
                b = board.read_board(st.video) or {'version': 0, 'panels': []}
                return self.json(200, {**b, 'comments': board.comments(approvals.read_log(st.video), b)})
            if path.startswith('/board/'):
                return self.board_file(path[len('/board/'):])
            if path == '/api/music':
                m = music.read_music_results(st.video) or {'version': 0, 'cues': {}}
                return self.json(200, m)
            if path.startswith('/music/'):
                return self.result_file('music', path[len('/music/'):], ('.wav', '.mp4', '.json'))
            if path == '/api/finish':
                return self.json(200, {'finish': mix.read_finish(st.video), 'render': render.read_render(st.video)})
            if path.startswith('/finish/'):
                return self.result_file('finish', path[len('/finish/'):], ('.mp4', '.m4a', '.wav', '.srt', '.json'))
            if path.startswith('/render/'):
                return self.result_file('render', path[len('/render/'):], ('.mp4', '.wav', '.json'))
            self.send(404, 'not found')

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            url = self.gate()
            if url is None:
                return
            if not self.origin_ok():
                return self.refuse('writes must come from the Studio page')
            try:
                if url.path == '/api/film':
                    return self.post_film()
                if url.path == '/api/event':
                    return self.post_event()
                if url.path == '/api/approve':
                    return self.post_approve()
                if url.path == '/api/prompt':
                    return self.post_prompt()
                if url.path == '/api/upload':
                    return self.post_upload()
                if url.path == '/api/voice':
                    return self.post_voice(urllib.parse.parse_qs(url.query).get('seg', [''])[0])
                if url.path == '/api/voice-route':
                    return self.post_voice_route()
            except ValueError as e:
                return self.json(400, {'error': str(e)})
            self.send(404, 'not found')

        def page_file(self, name):
            if not PAGE.is_dir() or name not in os.listdir(PAGE) or name.startswith('.'):
                return self.send(404, 'not found')
            ctype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
            if ctype.startswith('text/') or ctype.endswith('javascript'):
                ctype += '; charset=utf-8'
            self.send(200, (PAGE / name).read_bytes(), ctype, {'Content-Security-Policy': STUDIO_CSP})

        def preview(self, style_id):
            if style_id not in compose.catalogue():
                return self.send(404, 'not a catalogue style')
            try:
                if compose.atlas_dir() is None:
                    return self.send(404, 'no private style folder is set')
                nonce = secrets.token_urlsafe(16)
                body = preview_page(style_id, nonce)
            except StudioError as e:              # a sealed note inside the frame instead of a blank box
                return self.send(404, NO_PREVIEW.replace("{why}", html.escape(str(e))), 'text/html; charset=utf-8',
                                 {'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'"})
            self.send(200, body, 'text/html; charset=utf-8',
                      {'Content-Security-Policy': PREVIEW_CSP.format(nonce=nonce)})

        def post_film(self):
            data = self.body_json()
            bad = [k for k in data if k not in PAGE_SECTIONS]
            if not data or bad:
                raise ValueError('the page may replace only these sections: ' + ', '.join(PAGE_SECTIONS))
            if 'parts' in data:                   # never new parts with an old map: both in one write, or nothing
                if 'styles' not in data:
                    raise ValueError('parts and styles are saved together, in one request')
                check_parts(data['parts'], data['styles'])
            if 'story' in data:
                check_story(data['story'])
            if 'script' in data:
                check_script(data['script'])
            if 'music' in data:
                check_music(data['music'])
            if 'finish' in data:
                check_finish(data['finish'])
            if 'brand' in data:
                try:
                    current = ((st.read_film().get('brand') or {}).get('skill'))
                except (OSError, ValueError, AttributeError):
                    current = None
                if not isinstance(current, str):
                    current = None
                data['brand'] = check_brand(data['brand'], {b['skill'] for b in installed_brands(st.video)} | {current} - {None})
            if isinstance(data.get('styles'), dict) and isinstance(data['styles'].get('map'), dict):
                try:
                    brand = data['brand'] if 'brand' in data else st.read_film().get('brand')
                except (OSError, ValueError):
                    brand = None
                if not compose.film_brand({'brand': brand}):   # no brand: every part as is, whatever the page sent
                    data['styles'] = dict(data['styles'], map={k: dict(m, brand='as-is') if isinstance(m, dict) else m
                                                               for k, m in data['styles']['map'].items()})
            base = self.headers.get('X-Film-Base', '')
            try:
                before = approvals.status(st.video, st.read_film())
            except (OSError, ValueError):
                before = {}
            try:
                mtime, changed = st.replace_sections(data, int(base) if base.isdigit() else None)
            except (OSError, ValueError) as e:
                return self.json(409, {'error': f'film.json could not be updated ({e})'})
            reopened = []
            for stop, row in approvals.status(st.video, st.read_film()).items():
                if row['state'] == 'reopened' and (before.get(stop) or {}).get('state') == 'approved':
                    st.append_event(STOP_ROOMS[stop], 'reopen', {'stop': stop, 'asked': row.get('asked'),
                                                                 'because': row['changed'], 'via': 'studio'})
                    reopened.append({'stop': stop, 'name': row['name'], 'changed': row['changed']})
            self.json(200, {'ok': True, 'film': str(mtime), 'changed': changed, 'reopened': reopened})

        def post_event(self):
            data = self.body_json()
            kind, room, detail = data.get('kind'), data.get('room'), data.get('detail', {})
            if kind not in EVENT_KINDS or room not in ROOMS or not isinstance(detail, dict):
                raise ValueError('an event needs a known kind, a room and a detail object')
            if kind == 'not-yet':
                note = detail.get('note', '')
                if detail.get('stop') not in approvals.STOPS or not isinstance(note, str) or len(note) > 4000:
                    raise ValueError('"not yet" needs a stop and a note of up to 4000 characters')
            if kind == 'comment':                    # the server, not the page, says which drawing it was about
                text, b = detail.get('text'), board.read_board(st.video) or {}
                panel = next((p for p in b.get('panels') or [] if p.get('id') == detail.get('panel')), None)
                if not panel or not isinstance(text, str) or not text.strip() or len(text) > 4000:
                    raise ValueError('a comment needs a panel on the storyboard now and 1 to 4000 characters')
                detail = {'panel': panel['id'], 'text': text.strip(), 'board': b.get('version'),
                          'panel_version': panel.get('version')}
            self.json(200, st.append_event(room, kind, detail))

        def post_approve(self):
            data = self.body_json()
            stop, asked = data.get('stop'), data.get('asked')
            if stop not in approvals.STOPS or not isinstance(asked, str):
                raise ValueError('a yes needs a stop and the version it answers')
            room = data.get('room') if data.get('room') in ROOMS else STOP_ROOMS[stop]
            try:
                line, why = st.approve(stop, asked, room)
            except (OSError, ValueError) as e:
                return self.json(409, {'error': f'{st.film_name} could not be read ({e})'})
            if why:
                return self.json(409, {'error': why})
            self.json(200, {'ok': True, 'n': line['n'], 'at': line['at'], 'stop': stop, 'asked': asked})

        def post_prompt(self):
            try:
                text, facts = compose.compose(st.video, st.film_name)
            except StudioError as e:
                return self.json(400, {'error': str(e)})
            write_atomic(st.studio / 'prompt.txt', text)
            self.json(200, {'text': text, **facts})

        def receive(self, folder):
            """Read the request body into a temporary file in `folder`; returns its path (the caller moves or removes it)."""
            n = int(self.headers.get('Content-Length') or -1)
            if n < 0:
                raise ValueError('the upload needs a Content-Length')
            if n > MAX_UPLOAD_BYTES:
                raise ValueError('over 500 MB: copy it into the video folder by hand')
            folder.mkdir(exist_ok=True)
            fd, part = tempfile.mkstemp(prefix='.upload-', suffix='.part', dir=folder)
            part, left = Path(part), n
            try:
                with os.fdopen(fd, 'wb') as f:
                    while left:
                        chunk = self.rfile.read(min(CHUNK, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                if left:
                    raise ValueError('the upload stopped before the end')
                os.chmod(part, 0o644)
                return part, n
            except BaseException:
                part.unlink(missing_ok=True)
                raise

        def post_voice(self, seg):
            """A voice take for one script segment: saved as voice/<seg>.<ext>, then timed in the background."""
            name = safe_name(self.headers.get('X-File-Name')) or ''
            ext = os.path.splitext(name)[1].lower()
            if ext not in voice.AUDIO:
                raise ValueError('a voice take is ' + ', '.join(voice.AUDIO) + ' audio')
            film = st.read_film()
            segs = {g.get('id'): g for g in ((film.get('script') or {}).get('segments') or []) if isinstance(g, dict)}
            if seg not in segs or not PART_ID.fullmatch(seg):
                raise ValueError(f'the script has no segment "{seg[:40]}"')
            folder = st.video / 'voice'
            part, n = self.receive(folder)
            rel = f'voice/{seg}{ext}'
            try:
                for old in folder.glob(f'{seg}.*'):         # one take per segment: the new one replaces the old
                    if old.suffix.lower() in voice.AUDIO and old.name != f'{seg}{ext}':
                        old.unlink()
                os.replace(part, st.video / rel)
            finally:
                part.unlink(missing_ok=True)
            token = secrets.token_hex(8)
            st.set_take(seg, {'file': rel, 'state': 'timing', 'name': name, 'bytes': n, 'token': token, 'at': now_iso(),
                              'clean': voice.clean(segs[seg].get('text'))})
            st.append_event('voice', 'voice', {'segment': seg, 'action': 'drop', 'file': rel, 'bytes': n})
            threading.Thread(target=st.time_take, args=(seg, segs[seg].get('text') or '', rel, token), daemon=True).start()
            self.json(200, {'ok': True, 'segment': seg, 'file': rel, 'state': 'timing'})

        def post_voice_route(self):
            route = self.body_json().get('route')
            if route not in VOICE_ROUTES:
                raise ValueError('the voice route is one of ' + ', '.join(VOICE_ROUTES))
            def change(film):
                film['voice'] = dict(film.get('voice') if isinstance(film.get('voice'), dict) else {}, route=route)
            st.update_film(change)
            st.append_event('voice', 'voice', {'action': 'route', 'route': route})
            self.json(200, {'ok': True, 'route': route})

        def send_media(self, path, ctype):
            """Serve a local media file with HTTP Range support so <video> and <audio> seeking works smoothly."""
            size = path.stat().st_size
            rng = self.headers.get('Range')
            if rng and rng.startswith('bytes='):
                m = re.match(r'^bytes=(\d*)-(\d*)$', rng.strip())
                if m and (m.group(1) != '' or m.group(2) != ''):
                    s_raw, e_raw = m.groups()
                    if s_raw == '' and e_raw:
                        n = int(e_raw)
                        start, end = max(0, size - n), size - 1
                    else:
                        start = int(s_raw) if s_raw else 0
                        end = int(e_raw) if e_raw else size - 1
                    if start >= size or start > end:
                        return self.send(416, b'', headers={'Content-Range': f'bytes */{size}'})
                    end = min(end, size - 1)
                    length = end - start + 1
                    self.send_response(206)
                    self.send_header('Content-Type', ctype)
                    self.send_header('Content-Length', str(length))
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    if self.command != 'HEAD':
                        with open(path, 'rb') as f:
                            f.seek(start)
                            left = length
                            while left > 0:
                                buf = f.read(min(CHUNK, left))
                                if not buf:
                                    break
                                self.wfile.write(buf)
                                left -= len(buf)
                    return
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(size))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if self.command != 'HEAD':
                with open(path, 'rb') as f:
                    while True:
                        buf = f.read(CHUNK)
                        if not buf:
                            break
                        self.wfile.write(buf)

        def voice_file(self, name):
            """A take or its words file, from the video's voice/ folder only."""
            folder = st.video / 'voice'
            if not folder.is_dir() or '/' in name or name.startswith('.') or name not in os.listdir(folder):
                return self.send(404, 'not found')
            ctype = 'application/json; charset=utf-8' if name.endswith('.json') else (mimetypes.guess_type(name)[0] or 'application/octet-stream')
            return self.send_media(folder / name, ctype)

        def result_file(self, sub, name, exts):
            """One result file from .studio/results/<sub>/ only."""
            folder = st.studio / 'results' / sub
            if '/' in name or '\\' in name or name.startswith('.') or not any(name.endswith(e) for e in exts) \
                    or not folder.is_dir() or name not in os.listdir(folder):
                return self.send(404, 'not found')
            if name.endswith('.json'):
                ctype = 'application/json; charset=utf-8'
            elif name.endswith('.srt'):
                ctype = 'text/plain; charset=utf-8'
            elif name.endswith('.mp4'):
                ctype = 'video/mp4'
            elif name.endswith('.m4a'):
                ctype = 'audio/mp4'
            elif name.endswith('.wav'):
                ctype = 'audio/wav'
            else:
                ctype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
            return self.send_media(folder / name, ctype)

        def board_file(self, name):
            """One storyboard panel, from .studio/results/board/ only."""
            folder = st.studio / 'results' / 'board'
            if not name.endswith('.png') or '/' in name or name.startswith('.') or not folder.is_dir() \
                    or name not in os.listdir(folder):
                return self.send(404, 'not found')
            return self.send(200, (folder / name).read_bytes(), 'image/png')

        def post_upload(self):
            name = safe_name(self.headers.get('X-File-Name'))
            n = int(self.headers.get('Content-Length') or -1)
            if not name:
                raise ValueError('the file needs a name')
            if n < 0:
                raise ValueError('the upload needs a Content-Length')
            if n > MAX_UPLOAD_BYTES:
                return self.json(413, {'error': 'over 500 MB: copy it into the inputs folder by hand',
                                       'folder': str(st.video / 'inputs')})
            inputs = st.video / 'inputs'
            inputs.mkdir(exist_ok=True)
            stem, ext = os.path.splitext(name)
            fd, part = tempfile.mkstemp(prefix='.upload-', suffix='.part', dir=inputs)   # one per upload
            part, left = Path(part), n
            try:
                with os.fdopen(fd, 'wb') as f:
                    while left:
                        chunk = self.rfile.read(min(CHUNK, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                if left:
                    raise ValueError('the upload stopped before the end')
                os.chmod(part, 0o644)
                dest, i = inputs / name, 2
                while True:                               # link fails if the name exists: two drops never share one
                    try:
                        os.link(part, dest)
                        break
                    except FileExistsError:
                        dest, i = inputs / f'{stem} ({i}){ext}', i + 1
            except OSError as e:
                return self.json(400, {'error': f'the file could not be saved ({e.strerror or e})'})
            finally:
                part.unlink(missing_ok=True)
            rel = f'inputs/{dest.name}'
            kind = input_kind(dest.name)
            st.add_input(rel, kind, 'Dropped in the Studio')
            st.append_event('start', 'upload', {'path': rel, 'bytes': n, 'kind': kind})
            self.json(200, {'ok': True, 'path': rel, 'kind': kind, 'bytes': n})

    return Handler


# --- commands -----------------------------------------------------------------------------------------------------

class _StudioServer(ThreadingHTTPServer):
    request_queue_size = 64


def serve(video, film):
    st = Studio(video, film)
    httpd = _StudioServer(('127.0.0.1', 0), make_handler(st))
    httpd.daemon_threads = True
    st.port = httpd.server_address[1]
    info = {'port': st.port, 'pid': os.getpid(), 'started': now_iso(), 'key': st.key, 'film': film}
    write_private(st.studio / 'server.json', json.dumps(info, indent=2) + '\n')

    def close(why):
        """A planned stop: the stamp says so for a moment, so the open page shows a calm "closed", not a warning."""
        if st.closing:
            return
        st.closing = why
        time.sleep(CLOSE_GRACE)
        httpd.shutdown()

    def idle():
        while True:
            time.sleep(min(30, IDLE_SECONDS / 4))
            if time.monotonic() - st.last_request > IDLE_SECONDS:
                return close('idle')
    threading.Thread(target=idle, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=close, args=('stop',), daemon=True).start())
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        cur = read_server(st.video)
        if cur and cur.get('pid') == os.getpid():
            (st.studio / 'server.json').unlink(missing_ok=True)


def entry_url(info, room=None):
    url = f'http://127.0.0.1:{info["port"]}/?key={info["key"]}'
    return url + (f'&room={room}' if room else '')


def running(video):
    info = read_server(video)
    if info and pid_alive(info.get('pid')) and port_open(info.get('port')):
        return info
    return None


def cmd_open(a):
    video = Path(a.video).expanduser().resolve()
    if not video.is_dir():
        print(f'studio: {video} is not a folder', file=sys.stderr)
        return 2
    studio = ensure_studio_dir(video)                 # .gitignore first, before anything else is written
    if not (video / a.film).is_file():
        print(f'studio: no {a.film} in {video}. Write it first (see studio/README.md)', file=sys.stderr)
        return 2
    info = running(video)
    if info and info.get('film', 'film.json') != a.film:
        print(f'studio: a Studio for {video} is already open on {info.get("film")}; stop it first', file=sys.stderr)
        return 2
    if not info:
        log = open(studio / 'server.log', 'a')
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'serve', str(video), '--film', a.film],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, close_fds=True)
        for _ in range(100):
            info = read_server(video)
            if info and info.get('pid') == proc.pid and port_open(info['port']):
                break
            if proc.poll() is not None:
                print(f'studio: the server stopped at once; see {studio / "server.log"}', file=sys.stderr)
                return 1
            time.sleep(0.05)
        else:
            print('studio: the server did not start in 5 s', file=sys.stderr)
            return 1
    print(entry_url(info, a.room))
    return 0


def cmd_stop(a):
    video = Path(a.video).expanduser().resolve()
    info = read_server(video)
    if not info or not pid_alive(info.get('pid')):
        (video / '.studio' / 'server.json').unlink(missing_ok=True)
        print(f'studio: no Studio running for {video}')
        return 0
    os.kill(int(info['pid']), signal.SIGTERM)
    for _ in range(int((CLOSE_GRACE + 5) / 0.05)):
        if not pid_alive(info['pid']):
            break
        time.sleep(0.05)
    print(f'studio: stopped the Studio for {video}')
    return 0


def read_events(video, since):
    lines = []
    try:
        with open(Path(video) / '.studio' / 'events.jsonl', encoding='utf-8') as f:
            for line in f:
                try:
                    lines.append(json.loads(line))
                except ValueError:                        # a line cut short (server killed mid-write): skip it
                    pass
    except OSError:
        return []
    return [e for e in lines if isinstance(e, dict) and e.get('n', 0) > since]


def cmd_events(a):
    for e in read_events(Path(a.video).expanduser(), a.since):
        print(json.dumps(e, ensure_ascii=False))
    return 0


def cmd_wait(a):
    video = Path(a.video).expanduser().resolve()
    watch = ensure_studio_dir(video) / 'watching'
    watch.write_text(str(os.getpid()))

    def leave(*_):
        if watch.is_file() and watch.read_text().strip() == str(os.getpid()):
            watch.unlink(missing_ok=True)
        sys.exit(130)
    signal.signal(signal.SIGTERM, leave)
    signal.signal(signal.SIGINT, leave)
    end = time.monotonic() + a.timeout if a.timeout else None
    try:
        while end is None or time.monotonic() < end:
            asks = [e for e in read_events(video, a.since) if e.get('kind') in WAKE_KINDS]
            if asks:
                for e in asks:
                    print(json.dumps(e, ensure_ascii=False))
                return 0
            time.sleep(0.5)
        print('studio: no click to answer before the timeout', file=sys.stderr)
        return 3
    finally:
        if watch.is_file() and watch.read_text().strip() == str(os.getpid()):
            watch.unlink(missing_ok=True)


def cmd_voice(a):
    """Time a take Claude made (Kokoro, or a file the person sent in chat): copied to voice/<seg>, heard, matched."""
    video = Path(a.video).resolve()
    film = json.loads((video / a.film).read_text(encoding='utf-8'))
    segs = {g.get('id'): g for g in ((film.get('script') or {}).get('segments') or []) if isinstance(g, dict)}
    src = Path(a.file).resolve()
    if a.seg not in segs:
        raise SystemExit(f'❌ the script has no segment "{a.seg}"')
    if src.suffix.lower() not in voice.AUDIO or not src.is_file():
        raise SystemExit('❌ give an audio file: ' + ', '.join(voice.AUDIO))
    (video / 'voice').mkdir(exist_ok=True)
    rel = f'voice/{a.seg}{src.suffix.lower()}'
    if src != (video / rel).resolve():
        for old in (video / 'voice').glob(f'{a.seg}.*'):
            if old.suffix.lower() in voice.AUDIO:
                old.unlink()
        shutil.copyfile(src, video / rel)
    st = Studio(video, a.film)
    token = secrets.token_hex(8)
    st.set_take(a.seg, {'file': rel, 'state': 'timing', 'name': src.name, 'bytes': src.stat().st_size, 'token': token,
                        'at': now_iso(), 'clean': voice.clean(segs[a.seg].get('text'))})
    st.time_take(a.seg, segs[a.seg].get('text') or '', rel, token)
    take = st.read_film()['voice']['takes'][a.seg]
    print(json.dumps({k: take.get(k) for k in ('file', 'state', 'words', 'flagged', 'words_file', 'error') if k in take}))
    return 0 if take.get('state') == 'timed' else 1


def cmd_ask(a):
    video = Path(a.video).expanduser().resolve()
    try:
        entry = approvals.ask(video, a.stop, a.label, count_lines(video / '.studio' / 'events.jsonl'), a.film)
    except (OSError, ValueError) as e:
        print(f'studio: {e}', file=sys.stderr)
        return 2
    print(json.dumps({'stop': a.stop, **entry}, ensure_ascii=False))
    return 0


def cmd_approvals(a):
    video = Path(a.video).expanduser().resolve()
    try:
        film = approvals.load(video, a.film)
        report = {'stops': list(approvals.status(video, film).values()), 'clicks': approvals.verdicts(video, film)}
        if a.record:
            report['did'] = approvals.record(video, a.film)
    except (OSError, ValueError) as e:
        print(f'studio: {e}', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


def cmd_yes(a):
    video = Path(a.video).expanduser().resolve()
    try:
        entry = approvals.chat_yes(video, a.stop, a.words, now_iso(), a.film)
    except (OSError, ValueError) as e:
        print(f'studio: {e}', file=sys.stderr)
        return 2
    print(json.dumps({'stop': a.stop, **entry}, ensure_ascii=False))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='Kit to Clip Studio, the local page for one film.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('open', help='start or reuse the Studio for a video folder and print its URL')
    p.add_argument('video')
    p.add_argument('--film', default='film.json')
    p.add_argument('--room', choices=ROOMS)
    p = sub.add_parser('stop', help="stop a video folder's Studio")
    p.add_argument('video')
    p = sub.add_parser('events', help='print the clicks logged after line N')
    p.add_argument('video')
    p.add_argument('--since', type=int, default=0)
    p = sub.add_parser('wait', help='block until a click Claude must answer (ask, ✋ yes, not yet, comment) after line N')
    p.add_argument('video')
    p.add_argument('--since', type=int, required=True)
    p.add_argument('--timeout', type=float)
    p = sub.add_parser('ask', help='ask for a ✋ yes on one version of a stop')
    p.add_argument('video')
    p.add_argument('stop', choices=approvals.STOPS)
    p.add_argument('label', help='the version the yes is for, e.g. "storyboard v2"')
    p.add_argument('--film', default='film.json')
    p = sub.add_parser('approvals', help="each stop's state and every ✋ Yes click with whether it counts")
    p.add_argument('video')
    p.add_argument('--film', default='film.json')
    p.add_argument('--record', action='store_true', help='write counting clicks as yeses; drop yeses whose inputs changed')
    p = sub.add_parser('yes', help='record a yes the person said in chat, in their words')
    p.add_argument('video')
    p.add_argument('stop', choices=approvals.STOPS)
    p.add_argument('--words', required=True)
    p.add_argument('--film', default='film.json')
    p = sub.add_parser('voice', help='time a voice take for one script segment (copied to voice/<seg>)')
    p.add_argument('video')
    p.add_argument('--seg', required=True, help='the script segment, e.g. seg-01')
    p.add_argument('--file', required=True, help='the audio file')
    p.add_argument('--film', default='film.json')
    p = sub.add_parser('serve', help=argparse.SUPPRESS)
    p.add_argument('video')
    p.add_argument('--film', default='film.json')
    a = ap.parse_args(argv)
    if a.cmd == 'serve':
        serve(a.video, a.film)
        return 0
    return {'open': cmd_open, 'stop': cmd_stop, 'events': cmd_events, 'wait': cmd_wait, 'ask': cmd_ask,
            'approvals': cmd_approvals, 'yes': cmd_yes, 'voice': cmd_voice}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
