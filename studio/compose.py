#!/usr/bin/env python3
"""Kit to Clip Studio: write the build prompt for one film from its film.json and the private style library.

  python3 compose.py <video-folder> [--film film.json] [--out .studio/prompt.txt] [--template PATH] [--outline]

The style library is private and never in git. Its folder comes from $KIT_TO_CLIP_ATLAS, else from one line in
~/.config/kit-to-clip/config.json: {"atlas_dir": "/path/to/the/folder"}. The prompt holds library code, so it is
written only into the video folder's .studio/ (which ignores itself) and the clipboard, never next to the skill.
Exit 0 when written, 2 when film.json, the template or the library has a problem (nothing is written then).
"""
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
CATALOGUE = SKILL_ROOT / 'catalogue' / 'index.json'
TEMPLATE = HERE / 'prompt-template.md'
JOINS = HERE / 'joins.json'
CONFIG = Path('~/.config/kit-to-clip/config.json').expanduser()
MAX_PACKAGE_BYTES = 2_000_000
WARN_BYTES = 250_000
NO_FONT = 'no font'
FENCE_RE = re.compile(r'```js\n(.*?)\n```', re.S)
FONT_RE = re.compile(r'href="(https://fonts\.googleapis\.com/[^"]+)"')
CARD_RE = re.compile(r'^STYLE CARD\n(.*?)(?:\n[ \t]*\n|\Z)', re.S | re.M)
SLOT_RE = re.compile(r'\{\{(\w+)\}\}')
REQUIRED_SLOTS = ('parts_table', 'style_map', 'shared_code', 'style_sources')
BRAND_MODES = {'brand': 'brand skill', 'palette': 'brand colours only', 'as-is': 'as is'}
TIMED_RE = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)\s*\|\s*(.+?)\s*$')


class StudioError(Exception):
    """A clear problem for the person; nothing was written."""


def inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([path, root]) == root


def ensure_studio_dir(video):
    """<video>/.studio/ with its own .gitignore ("*"), written before anything else goes in."""
    studio = Path(video) / '.studio'
    studio.mkdir(parents=True, exist_ok=True)
    ignore = studio / '.gitignore'
    if not ignore.is_file():
        ignore.write_text('*\n')
    return studio


def write_atomic(path, text):
    """Write through a temporary file in the same folder and a rename, so a reader never sees half a file."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        if path.exists():                                 # keep the file's mode; a new file stays private (0600)
            os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --- the style library -------------------------------------------------------------------------------------------

def atlas_dir():
    """The private style folder from $KIT_TO_CLIP_ATLAS or the config line, or None when neither is set."""
    raw = os.environ.get('KIT_TO_CLIP_ATLAS')
    if not raw and CONFIG.is_file():
        try:
            raw = json.loads(CONFIG.read_text()).get('atlas_dir')
        except (OSError, ValueError, AttributeError) as e:
            raise StudioError(f'{CONFIG} is not readable JSON ({e})')
    if not raw:
        return None
    root = Path(raw).expanduser()
    if not root.is_dir():
        raise StudioError(f'the private style folder {root} is not a folder')
    if inside(root, SKILL_ROOT):
        raise StudioError('the private style folder is inside the Kit to Clip package, which is public; keep it in a '
                          'folder outside the package')
    return Path(os.path.realpath(root))


_catalogue = None


def catalogue():
    """{id: entry} for the 86 catalogue styles, in catalogue order."""
    global _catalogue
    if _catalogue is None:
        index = json.loads(CATALOGUE.read_text())
        _catalogue = {s['id']: s for s in index['styles']}
    return _catalogue


def parse_card(text):
    """'Key: value' lines of a style card into a dict, keeping the order."""
    card = {}
    for line in text.splitlines():
        key, sep, value = line.partition(':')
        if sep and key.strip():
            card[key.strip()] = value.strip()
    return card


def read_style(style_id, atlas=None):
    """One style's parts from its library file: helpers (h), sound kit, source, card and font link (or NO_FONT)."""
    entry = catalogue().get(style_id) if isinstance(style_id, str) else None
    if entry is None:
        raise StudioError(f'"{style_id}" is not a catalogue style id')
    root = Path(atlas) if atlas is not None else atlas_dir()
    if root is None:
        raise StudioError('no private style folder is set: add {"atlas_dir": "<folder>"} to '
                          '~/.config/kit-to-clip/config.json, or set KIT_TO_CLIP_ATLAS')
    if inside(root, SKILL_ROOT):
        raise StudioError('the private style folder is inside the Kit to Clip package, which is public')
    file = root / f'{style_id}.json'
    if not file.is_file() or not inside(file, root):
        raise StudioError(f'no {style_id}.json in the private style folder {root}')
    if file.stat().st_size > MAX_PACKAGE_BYTES:
        raise StudioError(f'{file} is larger than a style file should be')
    try:
        pkg = json.loads(file.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise StudioError(f'{file} is not readable JSON ({e})')
    prompt = pkg.get('prompt') if isinstance(pkg, dict) else None
    if not isinstance(prompt, str):
        raise StudioError(f'{file} has no text "prompt"')
    blocks = FENCE_RE.findall(prompt)
    if len(blocks) != 3:
        raise StudioError(f'{file}: expected 3 js code blocks (helpers, sound kit, style source), found {len(blocks)}. '
                          'The library format may have changed')
    card = CARD_RE.search(prompt)
    if not card:
        raise StudioError(f'{file}: no STYLE CARD section. The library format may have changed')
    font = FONT_RE.search(prompt)
    return {'id': style_id, 'name': entry['name'], 'family': entry['family'], 'h': blocks[0], 'sound': blocks[1],
            'source': blocks[2], 'card': parse_card(card.group(1)), 'font': font.group(1) if font else NO_FONT}


# --- the film -----------------------------------------------------------------------------------------------------

def load_film(video, film='film.json'):
    path = Path(video) / film
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise StudioError(f'no {film} in {video}')
    except (OSError, ValueError) as e:
        raise StudioError(f'{path} is not readable JSON ({e})')
    if not isinstance(data, dict) or not isinstance(data.get('parts'), list) or not data['parts']:
        raise StudioError(f'{path} has no story parts yet')
    return data


def joins_config():
    return json.loads(JOINS.read_text())


def suggest(from_id, to_id, cfg=None):
    """The join types to offer for a style change, best first (rules in joins.json)."""
    cfg = cfg or joins_config()
    cat = catalogue()
    facts = {'from_family': cat.get(from_id, {}).get('family'), 'to_family': cat.get(to_id, {}).get('family')}
    for rule in cfg['suggest']:
        if all(facts.get(k) == v for k, v in rule['when'].items()):
            return rule['order']
    return list(cfg['types'])


def film_brand(film):
    """The film's brand when it names one ({"name", ...}); None means no brand, so every part is as is."""
    b = film.get('brand')
    return b if isinstance(b, dict) and isinstance(b.get('name'), str) and b['name'].strip() else None


def mapped_parts(film):
    """[(part, style id, brand mode)] for every part; refuses parts with no style or an unknown one.
    With no brand every part is as is, whatever mode the map holds, so the prompt never invents a brand."""
    smap = (film.get('styles') or {}).get('map') or {}
    cat, rows, missing = catalogue(), [], []
    for p in film['parts']:
        m = smap.get(p['id']) or {}
        if not m.get('style'):
            missing.append(p['id'])
            continue
        if m['style'] not in cat:
            raise StudioError(f'part {p["id"]}: "{m["style"]}" is not a catalogue style id')
        mode = m.get('brand') or 'as-is'
        if mode not in BRAND_MODES:
            raise StudioError(f'part {p["id"]}: brand mode "{mode}" is not one of {", ".join(BRAND_MODES)}')
        if not film_brand(film):
            mode = 'as-is'
        rows.append((p, m['style'], mode))
    if missing:
        raise StudioError('these parts have no style yet: ' + ', '.join(missing) + '. Put a style on every part first')
    return rows


def runs_of(rows):
    """Neighbouring parts with the same style, as runs: {style, from, to, parts: [(part, mode)]}."""
    out = []
    for p, style, mode in rows:
        if out and out[-1]['style'] == style:
            out[-1]['to'] = p['to']
            out[-1]['parts'].append((p, mode))
        else:
            out.append({'style': style, 'from': p['from'], 'to': p['to'], 'parts': [(p, mode)]})
    return out


def joins_of(film, rows, cfg=None):
    """One join per style change, keyed by the part where the new style starts. A stored pick wins, else the first
    suggestion. Stored picks where the style no longer changes are ignored."""
    cfg = cfg or joins_config()
    picks = (film.get('styles') or {}).get('joins') or {}
    out = []
    for (a, sa, _), (b, sb, _) in zip(rows, rows[1:]):
        if sa == sb:
            continue
        pick = picks.get(b['id']) or {}
        kind = pick.get('type') if pick.get('type') in cfg['types'] else suggest(sa, sb, cfg)[0]
        out.append({'part': b['id'], 'at': b['from'], 'from': sa, 'to': sb, 'type': kind, 'note': pick.get('note', '')})
    return out


def t1(x):
    return f'{float(x):.1f}'


def cell(text):
    return ' '.join(str(text or '').split()).replace('|', '/')


def part_label(rows, ids):
    nums = [i + 1 for i, (p, _, _) in enumerate(rows) if p['id'] in ids]
    return f'part {nums[0]}' if len(nums) == 1 else f'parts {nums[0]}–{nums[-1]}'


def parts_table(film, rows):
    cat = catalogue()
    lines = ['| # | Part | From (s) | To (s) | Words | Picture | Sound | Style | Brand |',
             '|---|---|---|---|---|---|---|---|---|']
    for i, (p, style, mode) in enumerate(rows, 1):
        lines.append(f'| {i} | {cell(p.get("name"))} | {t1(p["from"])} | {t1(p["to"])} | {cell(p.get("words"))} | '
                     f'{cell(p.get("picture"))} | {cell(p.get("sound"))} | {cat[style]["name"]} | {BRAND_MODES[mode]} |')
    return '\n'.join(lines)


def expand(path, video=None):
    """An input path from film.json: ~ expanded, relative paths taken from the video folder."""
    if not path:
        return None
    p = Path(os.path.expanduser(path))
    return p if p.is_absolute() or video is None else Path(video) / p


def voice_timing(film, video=None):
    inputs = film.get('inputs') or []
    script = next((i for i in inputs if i.get('kind') == 'script' and i.get('path')), None)
    voice = next((i for i in inputs if i.get('kind') == 'voice' and i.get('path')), None)
    lines = []
    if script:
        f = expand(script['path'], video)
        try:
            lines = [m.groups() for m in map(TIMED_RE.match, f.read_text(encoding='utf-8').splitlines()) if m]
        except (OSError, UnicodeDecodeError):
            lines = []
    # Also collect timed segments from Room ③ Voice takes when no external timed script was supplied.
    vsec = film.get('voice') if isinstance(film.get('voice'), dict) else {}
    takes = vsec.get('takes') if isinstance(vsec.get('takes'), dict) else {}
    seg_lines = []
    if not lines and takes and video is not None:
        cursor = 0.0
        for g in ((film.get('script') or {}).get('segments') or []):
            if not isinstance(g, dict):
                continue
            t = takes.get(g.get('id'))
            if not isinstance(t, dict) or not t.get('words_file'):
                continue
            wf = Path(video) / t['words_file']
            try:
                wdoc = json.loads(wf.read_text(encoding='utf-8'))
                wlist = wdoc.get('words') or []
                if wlist:
                    slot = g.get('slot')
                    off = float(slot[0]) if isinstance(slot, (list, tuple)) and slot else cursor
                    a = off + float(wlist[0]['start'])
                    b = off + float(wlist[-1]['end'])
                    seg_lines.append((f'{a:.2f}', f'{b:.2f}', ' '.join(w['text'] for w in wlist)))
                    cursor = max(cursor, b + 0.35)
            except (OSError, ValueError, KeyError):
                continue
    length = film.get('length')
    if not length and (lines or seg_lines):
        src_lines = lines or seg_lines
        length = round(float(src_lines[-1][1]) + 1, 2)
    if not lines and not seg_lines and not voice and not takes:
        return (f'No voice in this film yet. `window.DURATION = {length}` (the film length).' if length else
                'No voice and no length in this film yet. Set `window.DURATION` to the end of the last part.')
    out = ['The audio is the clock. The voice take is fixed; the picture follows it, never the other way round. '
           'Every on-screen word, cut and hit lands on the time its line is spoken.']
    if voice:
        out.append(f'\nVoice take, already placed in film time: `{Path(voice["path"]).name}`. It is mixed in later, '
                   'outside the player: do not embed or play it in the HTML file.')
    elif takes:
        out.append(f'\nVoice takes ({len(takes)} segment(s)) in `voice/`. They are mixed in later, '
                   'outside the player: do not embed or play them in the HTML file.')
    if lines:
        out.append(f'\nThe spoken lines, in film seconds (start–end | words), from `{Path(script["path"]).name}`:\n')
        out.extend(f'- {float(a):6.2f}–{float(b):6.2f} | {w}' for a, b, w in lines)
    elif seg_lines:
        out.append('\nThe timed voice segments, in film seconds (start–end | words), from Room ③ Voice:\n')
        out.extend(f'- {float(a):6.2f}–{float(b):6.2f} | {w}' for a, b, w in seg_lines)
    elif script:
        out.append(f'\nA timed script was named (`{Path(script["path"]).name}`) but could not be read when this '
                   'prompt was written. Ask for it before you place any words.')
    out.append(f'\n`window.DURATION = {length}`' + (' (the film length).' if film.get('length') else
                                                       ' (the last spoken word plus 1 s).'))
    return '\n'.join(out)


def style_map_text(rows, runs, joins, cfg):
    cat = catalogue()
    out = ['The film in runs (neighbouring parts in the same style):\n']
    for n, r in enumerate(runs, 1):
        ids = [p['id'] for p, _ in r['parts']]
        modes = sorted({BRAND_MODES[m] for _, m in r['parts']})
        again = ' (returns)' if any(x['style'] == r['style'] for x in runs[:n - 1]) else ''
        out.append(f'{n}. {cat[r["style"]]["name"]}{again}: {t1(r["from"])}–{t1(r["to"])} s, '
                   f'{part_label(rows, ids)}, brand: {" and ".join(modes)}')
    if not joins:
        out.append('\nOne style on the whole film, so there is no join.')
        return '\n'.join(out)
    out.append(f'\nJoins ({len(joins)}), one at each style change:\n')
    for j in joins:
        jt = cfg['types'][j['type']]
        out.append(f'- At {t1(j["at"])} s, {cat[j["from"]]["name"]} to {cat[j["to"]]["name"]}: '
                   f'**{jt["name"]}**. {jt["line"]} How: {jt["build"]}' + (f' My note: {j["note"]}' if j['note'] else ''))
    return '\n'.join(out)


def brand_text(film, rows):
    brand = film_brand(film) or {}
    name, skill = brand.get('name', '').strip(), brand.get('skill')
    groups = []
    for i, (p, style, mode) in enumerate(rows):
        if mode == 'as-is':
            continue
        prev = rows[i - 1] if i else None
        if groups and prev and prev[2] == mode and prev[1] == style:
            groups[-1]['ids'].append(p['id'])
            groups[-1]['to'] = p['to']
        else:
            groups.append({'mode': mode, 'style': style, 'ids': [p['id']], 'from': p['from'], 'to': p['to']})
    if not groups:
        return 'No brand in this film. Every part keeps its style exactly as it is.'
    cat, skill_ref = catalogue(), f'`{skill}` brand skill' if skill else f'{name} brand guide (ask the person for it)'
    out = [f'The brand is {name}. It applies only where listed; every other part keeps its style as it is.\n']
    for g in groups:
        where = f'{part_label(rows, g["ids"]).capitalize()} ({t1(g["from"])}–{t1(g["to"])} s, {cat[g["style"]]["name"]})'
        if g['mode'] == 'brand':
            out.append(f'- {where}: read the {skill_ref} before the layout, and apply it to these parts only: its '
                       'colours, fonts, logo and rules, drawn in the style\'s own medium.')
        else:
            out.append(f'- {where}: brand colours only, taken from the {skill_ref}. The style keeps its own fonts, '
                       'lettering, textures and finishing.')
    return '\n'.join(out)


def code_block(text):
    return f'```js\n{text}\n```'


def shared_code(styles):
    first = styles[0]
    out = ['## The helper library (H)\n', code_block(first['h']), '\n## The sound kit (SOUND)\n',
           code_block(first['sound'])]
    for s in styles[1:]:
        for key, label in (('h', 'helper library'), ('sound', 'sound kit')):
            if s[key] != first[key]:
                out.append(f'\nNote: {s["name"]} carries a different {label} text. This prompt keeps the one from '
                           f'{first["name"]}; use it for every style.')
    return '\n'.join(out)


def style_sources(styles, runs, rows):
    out = []
    for n, s in enumerate(styles, 1):
        ids = [p['id'] for r in runs if r['style'] == s['id'] for p, _ in r['parts']]
        card = '\n'.join(f'- {k}: {v}' for k, v in s['card'].items() if k not in ('Name',))
        font = (f'Font link (load it before the first frame):\n<link rel="stylesheet" href="{s["font"]}">'
                if s['font'] != NO_FONT else 'No web font: use the fonts the source names, or system fonts.')
        out.append(f'## Style {n}: {s["name"]} (`{s["id"]}`)\n\nUsed in {part_label(rows, ids)}.\n\nStyle card:\n{card}'
                   f'\n\n{font}\n\nReference source (`draw` is its best single frame, `explainer` its demo film, '
                   f'`explainerSound` the demo\'s sound):\n\n{code_block(s["source"])}')
    return '\n\n'.join(out)


def compose(video, film_name='film.json', template=None, atlas=None):
    """(prompt text, facts) for one film. Raises StudioError with a clear reason when something is missing."""
    film = load_film(video, film_name)
    cfg = joins_config()
    rows = mapped_parts(film)
    runs = runs_of(rows)
    joins = joins_of(film, rows, cfg)
    order = list(dict.fromkeys(style for _, style, _ in rows))   # each style once, in order of first use
    styles = [read_style(s, atlas) for s in order]
    frame = film.get('frame') or {}
    values = {
        'title': film.get('title') or 'Untitled film', 'about': film.get('about') or '',
        'length': film.get('length') or '', 'width': frame.get('width', 1280), 'height': frame.get('height', 720),
        'fps': frame.get('fps', 30), 'parts_table': parts_table(film, rows), 'voice_timing': voice_timing(film, video),
        'style_map': style_map_text(rows, runs, joins, cfg), 'brand': brand_text(film, rows),
        'shared_code': shared_code(styles), 'style_sources': style_sources(styles, runs, rows),
    }
    tpl_path = Path(template) if template else TEMPLATE
    try:
        tpl = tpl_path.read_text(encoding='utf-8')
    except OSError as e:
        raise StudioError(f'cannot read the template {tpl_path} ({e})')
    used = set(SLOT_RE.findall(tpl))
    unknown = sorted(used - set(values))
    if unknown:
        raise StudioError(f'{tpl_path}: unknown slot(s) {", ".join(unknown)}')
    lacking = [s for s in REQUIRED_SLOTS if s not in used]
    if lacking:
        raise StudioError(f'{tpl_path}: the template lacks {", ".join(lacking)}')
    text = SLOT_RE.sub(lambda m: str(values[m.group(1)]), tpl)
    size = len(text.encode('utf-8'))
    warnings = ['the prompt is over 250 KB: 3 or more styles may need a trim'] if size > WARN_BYTES else []
    return text, {'bytes': size, 'styles': order, 'joins': len(joins), 'parts': len(rows), 'warnings': warnings}


def outline(text):
    """[(heading, bytes)] for the top-level '# ' headings outside code: the prompt's shape without its code."""
    marks, fence, pos = [], False, 0
    for line in text.splitlines(keepends=True):
        if line.startswith('```'):
            fence = not fence
        elif not fence and line.startswith('# '):
            marks.append((line[2:].strip(), pos))
        pos += len(line.encode('utf-8'))
    return [(h, (marks[i + 1][1] if i + 1 < len(marks) else pos) - start) for i, (h, start) in enumerate(marks)]


def main(argv=None):
    ap = argparse.ArgumentParser(description='Write the build prompt for one film.')
    ap.add_argument('video', help='the video folder holding film.json')
    ap.add_argument('--film', default='film.json')
    ap.add_argument('--out', help='where to write it (default <video>/.studio/prompt.txt)')
    ap.add_argument('--template', help='prompt template (default studio/prompt-template.md)')
    ap.add_argument('--outline', action='store_true', help='also print the headings and their sizes')
    a = ap.parse_args(argv)
    video = Path(a.video).expanduser()
    try:
        text, facts = compose(video, a.film, a.template)
    except StudioError as e:
        print(f'compose: {e}. Nothing was written.', file=sys.stderr)
        return 2
    if a.out:
        out = Path(a.out).expanduser()
        if not out.is_absolute():
            out = video / out
    else:
        out = ensure_studio_dir(video) / 'prompt.txt'
    if out.parent.name == '.studio':
        ensure_studio_dir(out.parent.parent)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(out, text)
    print(f'build prompt: {facts["bytes"] / 1000:.1f} KB, {len(facts["styles"])} style(s), {facts["joins"]} join(s), '
          f'{facts["parts"]} parts -> {out}')
    for w in facts['warnings']:
        print(f'⚠️ {w}')
    if a.outline:
        for heading, size in outline(text):
            print(f'  {size / 1000:7.1f} KB  {heading}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
