"""The ✋ stops in film.json `approvals`: what Claude asks, what the person clicked or said, and what a change reopens.

  approvals.<stop> = {"asked": "storyboard v2", "since": 30}                 Claude asks (studio.py ask); no yes yet
  approvals.<stop> = {"asked": …, "yes": "…", "at": "…", "via": "studio", "event": 31}    after the yes is recorded

The page never writes `approvals`. A click in the Studio only adds an `approve` line to the event log, written and
stamped by the server: a sequence number of its own and a keyed check (HMAC) over the line, with a key kept in
`.studio/approve.key`. A line typed into the log by hand, a copied stamp or a replayed line counts for nothing.
A click counts only for the version Claude asks about now, and only once.

What a yes covered is kept next to it in `.studio/approved/<stop>.json` (not in film.json, which stays plain): the
script, the parts, the style map, the joins, the brand and the voice files the person judged. When any of them
changes, wherever the change came from, the stop is reopened and needs a new yes.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path

from board import read_board
from compose import ensure_studio_dir, film_brand, write_atomic


def _read_finish_version(video):
    try:
        f = json.loads((Path(video) / '.studio' / 'results' / 'finish' / 'finish.json').read_text(encoding='utf-8'))
        return f.get('version') if isinstance(f, dict) else None
    except (OSError, ValueError):
        return None


def _read_music_takes(video):
    """Snapshot of the actual audition takes in .studio/results/music/music.json (excludes assembled track)."""
    try:
        m = json.loads((Path(video) / '.studio' / 'results' / 'music' / 'music.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(m, dict) or not isinstance(m.get('cues'), dict) or not m['cues']:
        return None
    out = {}
    for cid in sorted(m['cues']):
        cm = m['cues'][cid]
        if not isinstance(cm, dict):
            continue
        takes = []
        for t in cm.get('takes') or []:
            if not isinstance(t, dict):
                continue
            audio = t.get('audio')
            mark = _file_mark(video, f'.studio/results/music/{audio}') if isinstance(audio, str) else None
            takes.append([t.get('n'), t.get('round'), t.get('seed'), t.get('engine'), mark])
        out[cid] = {'round': cm.get('round'), 'made': cm.get('made'), 'takes': takes}
    return out or None


def asked_snapshot_path(video, stop):
    return Path(video) / '.studio' / 'asked' / f'{stop}.json'


def _write_asked_snapshot(video, stop):
    path = asked_snapshot_path(video, stop)
    if stop == 'music':
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, json.dumps({'takes': _read_music_takes(video)}, indent=1, ensure_ascii=False) + '\n')
    else:
        path.unlink(missing_ok=True)


def music_moved(video, stop):
    """True when new music audition takes were made after Claude asked for the music yes."""
    if stop != 'music':
        return False
    try:
        snap = json.loads(asked_snapshot_path(video, stop).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return False
    return _canon(_read_music_takes(video)) != _canon(snap.get('takes'))

STOPS = ('script', 'storyboard', 'music', 'final')
NAMES = {'script': '✋ Script', 'storyboard': '✋ Storyboard', 'music': '✋ Music pick', 'final': '✋ Final film'}
# What each stop's yes covers. A change to any of these reopens it.
_PICTURE = ('script', 'parts', 'map', 'joins', 'brand', 'voice')
COVERS = {'script': ('script', 'words'), 'storyboard': _PICTURE + ('board',), 'music': _PICTURE + ('music',),
          'final': _PICTURE + ('music', 'finish')}
INPUT_NAMES = {'script': 'the script', 'words': "the parts' words", 'parts': 'the story parts', 'map': 'the style map',
               'joins': 'the joins', 'brand': 'the brand', 'voice': 'the voice files', 'music': 'the music',
               'finish': 'the finish choices', 'board': 'the storyboard panels'}
STUDIO_YES = 'Clicked ✋ Yes in the Studio'


# --- the server's key and stamp ----------------------------------------------------------------------------------

def signing_key(video, create=False):
    """The Studio's approve key (32 random bytes, hex, mode 0600), made once per video folder."""
    path = ensure_studio_dir(video) / 'approve.key'
    try:
        key = path.read_text().strip()
        if len(key) == 64:
            return bytes.fromhex(key)
    except (OSError, ValueError):
        pass
    if not create:
        return None
    key = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(key + '\n')
    return bytes.fromhex(key)


def mac(key, n, at, stop, asked, seq):
    msg = json.dumps([n, at, stop, asked, seq], ensure_ascii=False).encode('utf-8')
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def stamp(key, n, at, stop, asked, seq):
    return {'origin': 'studio', 'key_ok': True, 'seq': seq, 'mac': mac(key, n, at, stop, asked, seq)}


def read_log(video):
    lines = []
    try:
        with open(Path(video) / '.studio' / 'events.jsonl', encoding='utf-8') as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:                        # a line cut short: skip it
                    continue
                if isinstance(e, dict):
                    lines.append(e)
    except OSError:
        pass
    return lines


def clicks(video, events=None):
    """Every `approve` line in the log, each with ok (a real Studio click) or why it does not count."""
    key = signing_key(video)
    out, seq = [], 0
    for e in read_log(video) if events is None else events:
        if e.get('kind') != 'approve':
            continue
        d = e.get('detail') if isinstance(e.get('detail'), dict) else {}
        s = e.get('stamp') if isinstance(e.get('stamp'), dict) else {}
        row = {'n': e.get('n'), 'at': e.get('at'), 'stop': d.get('stop'), 'asked': d.get('asked'), 'ok': False}
        if not s:
            row['why'] = 'not stamped by the Studio server (written by hand?)'
        elif key is None:
            row['why'] = 'this folder has no Studio key, so no stamp can be checked'
        elif not (s.get('origin') == 'studio' and s.get('key_ok') is True and isinstance(s.get('seq'), int)
                  and isinstance(s.get('mac'), str)
                  and hmac.compare_digest(s['mac'], mac(key, e.get('n'), e.get('at'), d.get('stop'), d.get('asked'),
                                                        s['seq']))):
            row['why'] = 'the stamp does not check out (copied or edited by hand?)'
        elif s['seq'] != seq + 1:
            row['why'] = f'out of order (sequence {s["seq"]} after {seq})'
        else:
            seq = s['seq']
            row['ok'] = True
        out.append(row)
    return out


def last_seq(video):
    return sum(1 for c in clicks(video) if c['ok'])


# --- what a yes covers -------------------------------------------------------------------------------------------

def _file_mark(video, path):
    p = Path(os.path.expanduser(path))
    p = p if p.is_absolute() else Path(video) / p
    try:
        st = p.stat()
        return [path, st.st_size, st.st_mtime_ns]
    except OSError:
        return [path, None, None]


def inputs(film, video):
    """The inputs a stop can cover, as plain JSON values (names in INPUT_NAMES)."""
    parts = [p for p in film.get('parts') or [] if isinstance(p, dict)]
    styles = film.get('styles') if isinstance(film.get('styles'), dict) else {}
    smap = styles.get('map') if isinstance(styles.get('map'), dict) else {}
    picks = styles.get('joins') if isinstance(styles.get('joins'), dict) else {}
    branded = bool(film_brand(film))
    rows = []
    for p in parts:
        m = smap.get(p.get('id')) if isinstance(smap.get(p.get('id')), dict) else {}
        rows.append([p.get('id'), m.get('style'), (m.get('brand') or 'as-is') if branded else 'as-is'])
    joins = [[b[0], (picks.get(b[0]) or {}).get('type') if isinstance(picks.get(b[0]), dict) else None]
             for a, b in zip(rows, rows[1:]) if a[1] != b[1]]
    voice = film.get('voice') if isinstance(film.get('voice'), dict) else {}
    takes = voice.get('takes') if isinstance(voice.get('takes'), dict) else {}
    files = sorted({i['path'] for i in film.get('inputs') or [] if isinstance(i, dict) and i.get('kind') == 'voice'
                    and isinstance(i.get('path'), str)}
                   | {t['file'] for t in takes.values() if isinstance(t, dict) and isinstance(t.get('file'), str)})
    fin_ver = _read_finish_version(video)
    fin_val = {'choices': film.get('finish'), 'build': fin_ver} if fin_ver is not None else film.get('finish')
    mtakes = _read_music_takes(video)
    music_val = {'film': film.get('music'), 'takes': mtakes} if mtakes is not None else film.get('music')
    return {
        'script': film.get('script'),
        'words': [[p.get('id'), p.get('words')] for p in parts],
        'parts': [{k: p.get(k) for k in ('id', 'from', 'to', 'words', 'picture', 'sound')} for p in parts],
        'map': rows,
        'joins': joins,
        'brand': film_brand(film),
        'voice': [_file_mark(video, f) for f in files],
        'music': music_val,
        'finish': fin_val,
        'board': (read_board(video) or {}).get('version'),     # a panel drawn again changes what the yes judged
    }


def _canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def covered(stop, film, video):
    now = inputs(film, video)
    return {k: now[k] for k in COVERS[stop]}


def snapshot_path(video, stop):
    return Path(video) / '.studio' / 'approved' / f'{stop}.json'


def write_snapshot(video, stop, entry, film):
    path = snapshot_path(video, stop)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps({'asked': entry.get('asked'), 'event': entry.get('event'), 'via': entry.get('via'),
                                   'inputs': covered(stop, film, video)}, indent=1, ensure_ascii=False) + '\n')


def changed_since_yes(video, stop, film):
    """The input names that changed since the yes, [] when none, None when the yes left no record to compare."""
    try:
        snap = json.loads(snapshot_path(video, stop).read_text(encoding='utf-8'))['inputs']
    except (OSError, ValueError, KeyError, TypeError):
        return None
    now = covered(stop, film, video)
    return [k for k in COVERS[stop] if _canon(now.get(k)) != _canon(snap.get(k))]


# --- each stop's state -------------------------------------------------------------------------------------------

def entry_of(film, stop):
    raw = film.get('approvals') if isinstance(film.get('approvals'), dict) else {}
    e = raw.get(stop)
    return e if isinstance(e, dict) else None


def has_yes(entry):
    return bool(entry and isinstance(entry.get('yes'), str) and entry['yes'].strip())


def board_moved(video, stop, asked):
    """The board version now, when the storyboard ask names another one (panels drawn again after the ask), else None."""
    if stop != 'storyboard' or not isinstance(asked, str):
        return None
    now = (read_board(video) or {}).get('version')
    named = re.search(r'\bv(\d+)\b', asked)
    return now if now and (not named or int(named.group(1)) != now) else None


def status(video, film, events=None):
    """Per stop: {state: none | asked | outdated | clicked | approved | reopened, asked, …}. The page and Claude read
    this. `outdated`: the storyboard was drawn again after Claude asked, so a click on the old version cannot count."""
    all_clicks = clicks(video, events)
    out = {}
    for stop in STOPS:
        e = entry_of(film, stop)
        row = {'stop': stop, 'name': NAMES[stop], 'state': 'none', 'covers': [INPUT_NAMES[k] for k in COVERS[stop]]}
        if e is None:
            out[stop] = row
            continue
        asked = e.get('asked') if isinstance(e.get('asked'), str) else None
        row['asked'] = asked
        if has_yes(e):
            row.update(state='approved', yes=e['yes'], at=e.get('at'), via=e.get('via') or 'chat', event=e.get('event'))
            changed = changed_since_yes(video, stop, film)
            if changed:
                row.update(state='reopened', changed=[INPUT_NAMES[k] for k in changed], changed_keys=changed)
            elif changed is None:
                row['unchecked'] = True                   # a yes recorded without the Studio: nothing to compare with
        elif asked and board_moved(video, stop, asked):
            row.update(state='outdated', board=board_moved(video, stop, asked))
        elif asked and music_moved(video, stop):
            row.update(state='outdated', music_outdated=True)
        elif asked:
            row['state'] = 'asked'
            since = e.get('since') if isinstance(e.get('since'), int) else 0
            hit = next((c for c in all_clicks if c['ok'] and c['stop'] == stop and c['asked'] == asked
                        and isinstance(c['n'], int) and c['n'] > since), None)
            if hit:
                row.update(state='clicked', event=hit['n'], clicked_at=hit['at'])
        out[stop] = row
    return out


def verdicts(video, film, events=None):
    """Every approve line with whether it counts now, for Claude to read before saying anything in chat."""
    st = status(video, film, events)
    out = []
    for c in clicks(video, events):
        v = dict(c)
        if c['ok']:
            row = st.get(c['stop']) or {}
            e = entry_of(film, c['stop']) or {}
            since = e.get('since') if isinstance(e.get('since'), int) else 0
            if c['stop'] not in STOPS:
                v.update(ok=False, why='not a stop')
            elif not row.get('asked'):
                v.update(ok=False, why='Claude is not asking about this stop now')
            elif row['state'] == 'outdated':
                if row.get('music_outdated'):
                    v.update(ok=False, why='new music takes were made after Claude asked')
                else:
                    v.update(ok=False, why=f'the storyboard was drawn again (v{row["board"]}) after Claude asked')
            elif c['asked'] != row['asked']:
                v.update(ok=False, why=f'a click on "{c["asked"]}", but Claude now asks about "{row["asked"]}"')
            elif isinstance(c['n'], int) and c['n'] <= since:
                v.update(ok=False, why='clicked before Claude asked this time')
            elif row['state'] in ('approved', 'reopened') and row.get('event') != c['n']:
                v.update(ok=False, why='this version already has its yes')
            elif row['state'] == 'clicked' and row.get('event') != c['n']:
                v.update(ok=False, why='a second click on the same version')
        out.append(v)
    return out


# --- what Claude writes ------------------------------------------------------------------------------------------

def load(video, film_name='film.json'):
    return json.loads((Path(video) / film_name).read_text(encoding='utf-8'))


def save(video, film, film_name='film.json'):
    write_atomic(Path(video) / film_name, json.dumps(film, indent=2, ensure_ascii=False) + '\n')


def ask(video, stop, label, since, film_name='film.json'):
    """Claude asks for a stop's yes on one version (e.g. "storyboard v2"). Any older yes for the stop goes."""
    if stop not in STOPS:
        raise ValueError(f'{stop} is not a stop ({", ".join(STOPS)})')
    if not isinstance(label, str) or not label.strip():
        raise ValueError('the ask needs a version label, e.g. "storyboard v2"')
    b = read_board(video) if stop == 'storyboard' else None
    if b and b.get('version'):                       # the yes is for the panels on screen now, so the label names them
        named = re.search(r'\bv(\d+)\b', label)
        if not named or int(named.group(1)) != b['version']:
            raise ValueError(f'the storyboard is at v{b["version"]} now: ask for "storyboard v{b["version"]}"')
    film = load(video, film_name)
    film.setdefault('approvals', {})
    film['approvals'][stop] = {'asked': label.strip(), 'since': since}
    snapshot_path(video, stop).unlink(missing_ok=True)
    _write_asked_snapshot(video, stop)
    save(video, film, film_name)
    return film['approvals'][stop]


def chat_yes(video, stop, words, at, film_name='film.json'):
    """A yes the person said in chat: recorded with their words, and what it covered."""
    if stop not in STOPS:
        raise ValueError(f'{stop} is not a stop ({", ".join(STOPS)})')
    if not isinstance(words, str) or not words.strip():
        raise ValueError("a chat yes needs the person's own words")
    film = load(video, film_name)
    film.setdefault('approvals', {})
    old = entry_of(film, stop) or {}
    entry = {**({'asked': old['asked']} if isinstance(old.get('asked'), str) else {}), 'yes': words.strip(), 'at': at,
             'via': 'chat'}
    film['approvals'][stop] = entry
    write_snapshot(video, stop, entry, film)
    asked_snapshot_path(video, stop).unlink(missing_ok=True)
    save(video, film, film_name)
    return entry


def record(video, film_name='film.json'):
    """Write each counting Studio click as its stop's yes, and remove each yes whose inputs changed since.
    Returns what it did, one line per stop, for Claude to say back in chat."""
    film = load(video, film_name)
    done = []
    for stop, row in status(video, film).items():
        if row['state'] == 'clicked':
            entry = {'asked': row['asked'], 'yes': STUDIO_YES, 'at': row['clicked_at'], 'via': 'studio',
                     'event': row['event']}
            film['approvals'][stop] = entry
            write_snapshot(video, stop, entry, film)
            asked_snapshot_path(video, stop).unlink(missing_ok=True)
            done.append({'stop': stop, 'did': 'recorded', 'asked': row['asked'], 'event': row['event'],
                         'say': f'You approved {row["asked"]} in the Studio.'})
        elif row['state'] == 'reopened':
            del film['approvals'][stop]
            snapshot_path(video, stop).unlink(missing_ok=True)
            asked_snapshot_path(video, stop).unlink(missing_ok=True)
            done.append({'stop': stop, 'did': 'reopened', 'asked': row.get('asked'), 'changed': row['changed'],
                         'say': f'{NAMES[stop]} is open again: {", ".join(row["changed"])} changed after your yes.'})
    if done:
        save(video, film, film_name)
    return done
