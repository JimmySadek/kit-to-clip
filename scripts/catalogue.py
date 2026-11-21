#!/usr/bin/env python3
"""Find a starting look in the style library catalogue and, optionally, your own saved styles.

The catalogue (catalogue/index.json) holds metadata only: names, family labels, descriptor tags, preview links and
source hashes for 86 published explainer styles. Their prompts and code are not bundled, and no entry has been
rendered or validated inside Kit to Clip. Search is keyword and tag matching with the reasons shown: a shortlist for
the director to judge, not a guarantee of fit or quality.

  catalogue.py list     [--family F] [--styles-root DIR] [--json]       browse everything
  catalogue.py search   TERMS... [--family F] [--limit N] [--styles-root DIR] [--json]
  catalogue.py families [--json]
  catalogue.py show     REF [--styles-root DIR] [--json]               REF is library:<id>, <id> or personal:<slug>
  catalogue.py load     ID --source-root DIR [--json]                  your own local copy of ONE library prompt

--styles-root is a saved-styles folder (<slug>/style.json, as written by styles.py). Approved styles join the
shortlist; drafts stay visible as drafts. Nothing is migrated, re-branded or written. Each saved row has a kind:
"reference" (styles.py capture: adaptable code, no slots, no brand) or "template" (a legacy record, also when kind
is missing). Search covers tags and a reference's reusable instructions (medium, motion, pacing, notes); its
original story and brand are shown (original_brand) but never searched or applied.

load reads exactly DIR/<id>.json, as exported and unchanged, in one of these shapes:
  {"info": {"id": <id>, ...}, "prompt": ...}   {"info": {"styleId": <id>, ...}, "prompt": ...}   {"id": <id>, "prompt": ...}
Every identifier present (id, info.id, info.styleId) must equal <id>; the filename alone never counts. The prompt is
returned only when its sha256 matches the catalogue. It never searches for or substitutes another copy, and a private
copy grants no publishing rights.
Browsing commands read only the index and style.json records; none of them write files or use the network.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent                      # the kit-to-clip skill; private sources must stay outside it
INDEX = SKILL_ROOT / 'catalogue' / 'index.json'
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')
DEFAULT_LIMIT = 8
MAX_RECORD_BYTES = 1_000_000
MAX_SOURCE_BYTES = 8_000_000
BROWSE = 'python3 <kit-to-clip>/scripts/catalogue.py list'
NOTICE = ('Keyword and tag shortlist for the director to judge, with the reasons shown. Not a guarantee of fit or '
          'quality. Library entries are metadata only and have not been validated in Kit to Clip.')
RIGHTS = ('Loaded from your own local copy for this job only. Kit to Clip does not include this source and grants no '
          'rights to use, publish or redistribute it; check the publisher\'s terms. Do not copy it into the Kit to '
          'Clip package or any public folder. It has not been validated in Kit to Clip.')
STOP = {'a', 'an', 'and', 'or', 'the', 'of', 'for', 'to', 'in', 'on', 'with', 'my', 'me', 'i', 'want', 'like',
        'something', 'some', 'style', 'styles', 'look', 'looks', 'video', 'videos', 'please', 'that', 'is'}
SPELLING = {'colour': 'color', 'colours': 'colors', 'coloured': 'colored', 'watercolour': 'watercolor',
            'grey': 'gray', 'centre': 'center', 'cosy': 'cozy', 'favourite': 'favorite', 'theatre': 'theater',
            'humour': 'humor', 'pencilled': 'penciled'}
PERSONAL_FIELDS = [('mood', 'mood'), ('made_for', 'made for'), ('platforms', 'platform'), ('signature', 'signature'),
                   ('type', 'type'), ('sound', 'sound'), ('structure', 'structure'), ('motion_rules', 'motion rule'),
                   ('dos', 'do'), ('remix_of', 'remix of'), ('tags', 'tag')]
# A saved reference's reusable instructions (styles.py capture). Its original_context (the first story and brand) is
# shown but never searched, so it does not pull the reference towards that brand or story.
INSTRUCTION_FIELDS = [('medium', 'medium'), ('motion', 'motion'), ('pacing', 'pacing'), ('notes', 'note'),
                      ('style_notes', 'style note')]
KINDS = ('template', 'reference')
LIBRARY_FIELDS = [('look', 'look tag', 'trait'), ('motion', 'motion tag', 'trait'),
                  ('explains', 'explanation tag', 'trait'), ('ground', 'background', 'trait'),
                  ('fit', 'inferred fit (guidance only)', 'fit')]


class CatalogueError(Exception):
    """A problem the person can fix: a bad id, folder, family or index."""


class SourceError(CatalogueError):
    """A selected source package could not be verified, so nothing was loaded."""


# --- text matching -------------------------------------------------------------------------------------------------
def tokens(text):
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
    return [SPELLING.get(t, t) for t in re.findall(r'[a-z0-9]+', text)]


def query_terms(query):
    raw = list(dict.fromkeys(tokens(query)))
    kept = [t for t in raw if t not in STOP]
    return kept or raw


def term_matches(term, toks):
    for k in toks:
        if k == term or (len(term) >= 4 and k.startswith(term)) or \
                (len(k) >= 4 and term.startswith(k) and len(term) - len(k) <= 3):
            return True
    return False


def strings(value, depth=0):
    """Text found in a style.json value (str, list or dict), for matching only."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if depth > 3:
        return []
    if isinstance(value, list):
        return [s for v in value for s in strings(v, depth + 1)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v, depth + 1)]
    return []


def slug(text):
    return '-'.join(tokens(text))


def inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([path, root]) == root


# --- library index ------------------------------------------------------------------------------------------------
def load_index(path=None):
    p = Path(path) if path else INDEX
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise CatalogueError(f'cannot read catalogue index {p}: {e}')
    styles = data.get('styles') if isinstance(data, dict) else None
    if not isinstance(styles, list) or not styles:
        raise CatalogueError(f'catalogue index {p} has no styles list')
    seen = set()
    for s in styles:
        ok = isinstance(s, dict) and isinstance(s.get('id'), str) and ID_RE.match(s['id']) and \
            isinstance(s.get('name'), str) and isinstance(s.get('family'), str) and \
            isinstance(s.get('order'), int) and isinstance(s.get('source'), dict) and \
            isinstance(s['source'].get('prompt_sha256'), str) and HEX64.match(s['source']['prompt_sha256'])
        if not ok:
            raise CatalogueError(f'catalogue index {p} has a malformed style entry: {str(s)[:80]}')
        if s['id'] in seen:
            raise CatalogueError(f'catalogue index {p} lists "{s["id"]}" twice')
        seen.add(s['id'])
    fams = list(dict.fromkeys(s['family'] for s in styles))
    if 'families' in data and set(data['families']) != set(fams):
        raise CatalogueError(f'catalogue index {p} families list does not match its styles')
    data['families'] = data.get('families') or fams
    return data


def families(index_path=None):
    index = load_index(index_path)
    counts = {}
    for s in index['styles']:
        counts[s['family']] = counts.get(s['family'], 0) + 1
    return [{'family': f, 'slug': slug(f), 'count': counts.get(f, 0)} for f in index['families']]


def resolve_family(index, family):
    if family is None:
        return None
    for f in index['families']:
        if family.strip().lower() == f.lower() or slug(family) == slug(f):
            return f
    raise CatalogueError(f'no family "{family}". Families: ' + ', '.join(index['families']))


def library_row(s):
    return {'ref': f'library:{s["id"]}', 'origin': 'library', 'id': s['id'], 'name': s['name'],
            'family': s['family'], 'ground': s.get('ground', 'unknown'), 'look': list(s.get('look') or []),
            'availability': 'metadata only; source not bundled; not validated in Kit to Clip',
            'ready_to_reuse': False}


def library_fields(s):
    """[(category, label, text)] searched for a library entry."""
    out = [('name', 'name', s['name']), ('name', 'id', s['id']), ('family', 'family', s['family'])]
    out += [('label', 'comparison label', v) for v in s.get('comparison_labels') or [] if isinstance(v, str)]
    for key, label, cat in LIBRARY_FIELDS:
        value = s.get(key)
        for v in ([value] if isinstance(value, str) else value or []):
            if isinstance(v, str) and v != 'unknown':
                out.append((cat, label, v))
    return out


# --- personal saved styles ----------------------------------------------------------------------------------------
def styles_dir(styles_root):
    root = Path(styles_root).expanduser()
    if not root.is_dir():
        raise CatalogueError(f'styles root {root} is not a folder')
    return Path(os.path.realpath(root))


def read_record(root, folder):
    """(row, problem) for one <root>/<folder>/style.json; exactly one is None."""
    rec = folder / 'style.json'
    where = str(rec)
    if not inside(rec, root):
        return None, {'path': where, 'problem': 'links outside the styles root; not read'}
    if not os.path.isfile(rec):
        return None, {'path': where, 'problem': 'style.json is not a regular file'}
    if os.path.getsize(rec) > MAX_RECORD_BYTES:
        return None, {'path': where, 'problem': 'style.json is too large to be a style record'}
    try:
        data = json.loads(rec.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        return None, {'path': where, 'problem': f'not valid JSON ({e.__class__.__name__}: {e})'}
    if not isinstance(data, dict):
        return None, {'path': where, 'problem': 'not a JSON object'}
    if not isinstance(data.get('title'), str) or not data['title'].strip():
        return None, {'path': where, 'problem': 'missing or non-text "title"'}
    if not isinstance(data.get('status'), str) or not data['status'].strip():
        return None, {'path': where, 'problem': 'missing or non-text "status"'}
    kind = data.get('kind', 'template')
    if kind not in KINDS:
        return None, {'path': where, 'problem': f'unknown "kind" {str(kind)[:40]!r} (expected template or reference; '
                                                'a record without kind is a legacy template)'}
    if kind == 'reference' and 'reference' in data and not isinstance(data['reference'], dict):
        return None, {'path': where, 'problem': 'a saved reference\'s "reference" source manifest must be an object'}
    status = data['status'].strip().lower()
    pick = lambda k, t, d=data: d.get(k) if isinstance(d.get(k), t) else None
    context = pick('original_context', dict) or {}
    first_brand = pick('brand', dict, context) or {}
    row = {'ref': f'personal:{folder.name}', 'origin': 'personal', 'id': folder.name, 'name': data['title'],
           'status': status, 'ready_to_reuse': status == 'approved', 'brand': pick('brand', str),
           'author': pick('author', str), 'version': pick('version', int), 'made_for': pick('made_for', str),
           'platforms': [p for p in pick('platforms', list) or [] if isinstance(p, str)],
           'mood': pick('mood', str), 'path': str(folder),
           'has_template': (folder / 'template' / 'index.html').is_file(),
           'kind': kind, 'tags': [t for t in pick('tags', list) or [] if isinstance(t, str) and t.strip()],
           'original_brand': pick('name', str, first_brand) or pick('id', str, first_brand),
           'reference_source': None}
    if kind == 'reference' and 'reference' in data:
        manifest = data['reference']
        entry = pick('entry', str, manifest)
        safe = entry and not os.path.isabs(entry) and '..' not in Path(entry).parts
        row['reference_source'] = {'path': str(folder / 'source'), 'entry': str(folder / entry) if safe else None,
                                   'portable': pick('portable', bool, manifest),
                                   'portability': pick('portability', str, manifest)}
    if status != 'approved':
        row['availability'] = f'{status}: visible for reference, not ready to reuse until approved'
    elif kind == 'reference':
        row['availability'] = ('approved saved reference: adapt its code in a fresh build; it has no slots and its '
                               'original brand is context only')
    else:
        row['availability'] = 'approved saved style'
    return row, data


def read_personal(styles_root):
    """(rows, records, problems) for every <slug>/style.json directly inside styles_root. Never raises per record."""
    root = styles_dir(styles_root)
    rows, records, problems = [], {}, []
    for folder in sorted(root.iterdir(), key=lambda p: p.name):
        if folder.name.startswith('.') or not folder.is_dir():
            continue
        if not (folder / 'style.json').exists() and not (folder / 'style.json').is_symlink():
            if folder.is_symlink() and not inside(folder, root):
                problems.append({'path': str(folder / 'style.json'), 'problem': 'links outside the styles root; not read'})
            continue
        row, data = read_record(root, folder)
        if row is None:
            problems.append(data)
        else:
            rows.append(row)
            records[row['ref']] = data
    return rows, records, problems


def personal_fields(row, data):
    out = [('name', 'title', row['name']), ('name', 'folder', row['id'])]
    for key, label in PERSONAL_FIELDS:
        out += [('trait', label, v) for v in strings(data.get(key))]
    instructions = data.get('instructions') if isinstance(data.get('instructions'), dict) else {}
    for key, label in INSTRUCTION_FIELDS:
        out += [('trait', label, v) for v in strings(instructions.get(key))]
    return out


# --- search -------------------------------------------------------------------------------------------------------
def match(fields, terms, phrase, exact_names):
    """Return None, or (sort key parts, matched term count, reasons) for one entry."""
    hits = {'name': set(), 'family': set(), 'label': set(), 'trait': set(), 'fit': set()}
    reasons = []
    exact = 2
    for cat, label, text in fields:
        toks = tokens(text)
        if phrase and ' '.join(toks) == phrase:
            if cat == 'name' and label in exact_names:
                exact = 0
                reasons.append(f'exact {label} match "{text}"')
            elif cat == 'label':
                exact = min(exact, 1)
                reasons.append(f'exact {label} match "{text}"')
        got = [t for t in terms if term_matches(t, toks)]
        if got:
            hits[cat].update(got)
            reasons.append(f'{label} "{text}" matches ' + ', '.join(f'"{t}"' for t in got))
    matched = set().union(*hits.values())
    if not matched:
        return None
    key = (exact, -len(matched), -len(hits['name']), -len(hits['trait'] | hits['family'] | hits['label']),
           -len(hits['fit']))
    return key, len(matched), reasons


def check_limit(limit):
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise CatalogueError(f'limit must be a whole number of at least 1, not {limit!r}')
    return limit


def search(query, family=None, limit=DEFAULT_LIMIT, styles_root=None, index_path=None):
    check_limit(limit)
    index = load_index(index_path)
    fam = resolve_family(index, family)
    terms = query_terms(query)
    if not terms:
        raise CatalogueError('give at least one search word, or use list to browse everything')
    phrase = ' '.join(tokens(query))
    found, drafts = [], []
    for s in index['styles']:
        if fam and s['family'] != fam:
            continue
        m = match(library_fields(s), terms, phrase, {'name', 'id'})
        if m:
            found.append((m[0] + (1, s['order'], s['id']), library_row(s), m))
    problems = []
    if styles_root is not None:
        rows, records, problems = read_personal(styles_root)
        if not fam:
            for row in rows:
                m = match(personal_fields(row, records[row['ref']]), terms, phrase, {'title', 'folder'})
                if not m:
                    continue
                if row['ready_to_reuse']:
                    found.append((m[0] + (0, 0, row['id']), row, m))
                else:
                    drafts.append((m[0] + (0, 0, row['id']), row, m))
    out = []
    for _, row, (_, n, reasons) in sorted(found, key=lambda x: x[0]):
        out.append(dict(row, matched_terms=f'{n} of {len(terms)} terms', reasons=reasons))
    draft_rows = [dict(row, matched_terms=f'{n} of {len(terms)} terms', reasons=reasons)
                  for _, row, (_, n, reasons) in sorted(drafts, key=lambda x: x[0])]
    browse = BROWSE + (f' --family "{fam}"' if fam else '') + (' --styles-root <folder>' if styles_root else '')
    result = {'query': query, 'terms': terms, 'family': fam, 'limit': limit, 'notice': NOTICE,
              'shortlist': out[:limit], 'total_matches': len(out), 'shown': min(limit, len(out)),
              'drafts': draft_rows, 'problems': problems, 'browse_all': browse,
              'library': index.get('availability', {})}
    if fam and styles_root is not None:
        result['personal_note'] = 'Saved styles have no family label, so a family filter leaves them out.'
    return result


def browse(family=None, styles_root=None, index_path=None):
    index = load_index(index_path)
    fam = resolve_family(index, family)
    items = []
    problems = []
    if styles_root is not None:
        rows, _, problems = read_personal(styles_root)
        if not fam:
            items += sorted(rows, key=lambda r: (not r['ready_to_reuse'], r['id']))
    items += [library_row(s) for s in index['styles'] if not fam or s['family'] == fam]
    return {'family': fam, 'items': items, 'total': len(items), 'problems': problems,
            'library': index.get('availability', {}), 'notice': NOTICE}


def parse_ref(ref):
    if not isinstance(ref, str) or not ref:
        raise CatalogueError('give a ref such as library:<id> or personal:<slug>')
    origin, _, ident = ref.partition(':') if ':' in ref else ('library', '', ref)
    if origin not in ('library', 'personal'):
        raise CatalogueError(f'"{ref}": refs start with library: or personal:')
    return origin, ident


def show(ref, styles_root=None, index_path=None):
    origin, ident = parse_ref(ref)
    if origin == 'library':
        index = load_index(index_path)
        entry = next((s for s in index['styles'] if s['id'] == ident), None)
        if entry is None:
            raise CatalogueError(f'"{ident}" is not in the catalogue; use list or search to find an id')
        return dict(library_row(entry), **{k: v for k, v in entry.items() if k not in ('id', 'name', 'family')},
                    collection=index.get('collection', {}), library=index.get('availability', {}),
                    fields=index.get('fields', {}))
    if styles_root is None:
        raise CatalogueError('personal refs need --styles-root <folder>; no saved styles are read otherwise')
    root = styles_dir(styles_root)
    if not ident or ident.startswith('.') or '/' in ident or '\\' in ident or ident != Path(ident).name:
        raise CatalogueError(f'"{ident}" is not a saved-style folder name')
    folder = root / ident
    if not (folder / 'style.json').exists():
        raise CatalogueError(f'no saved style "{ident}" in {root}')
    row, data = read_record(root, folder)
    if row is None:
        raise CatalogueError(f'{data["path"]}: {data["problem"]}')
    return dict(row, record=data)


# --- explicit private source --------------------------------------------------------------------------------------
def package_ids(pkg, cand):
    """[(field, value)] for every identifier present in a source package, valid or not."""
    found = [('id', pkg['id'])] if 'id' in pkg else []
    if 'info' in pkg:
        if not isinstance(pkg['info'], dict):
            raise SourceError(f'{cand}: "info" is not an object; nothing was loaded')
        found += [(f'info.{k}', pkg['info'][k]) for k in ('id', 'styleId') if k in pkg['info']]
    return found


def check_identity(pkg, style_id, cand):
    """The package must name style_id in every identifier it carries, and carry at least one."""
    ids = package_ids(pkg, cand)
    if not ids:
        raise SourceError(f'{cand} names no style (no id, info.id or info.styleId); identity is never taken from the '
                          'filename. Nothing was loaded')
    for field, value in ids:
        if not isinstance(value, str) or not ID_RE.match(value):
            raise SourceError(f'{cand}: {field} {repr(value)[:80]} is not a valid style id; nothing was loaded')
        if value != style_id:
            raise SourceError(f'{cand}: {field} is "{value}", not "{style_id}"; nothing was loaded')
    return [field for field, _ in ids]


def load_source(style_id, source_root, index_path=None):
    if not isinstance(style_id, str) or not ID_RE.match(style_id):
        raise SourceError(f'"{style_id}" is not a catalogue id; nothing was loaded')
    index = load_index(index_path)
    entry = next((s for s in index['styles'] if s['id'] == style_id), None)
    if entry is None:
        raise SourceError(f'"{style_id}" is not in the catalogue; nothing was loaded')
    if source_root is None:
        raise SourceError('pass --source-root <folder> holding your own copy; no folder is searched or guessed')
    given = Path(source_root).expanduser()
    if not given.is_dir():
        raise SourceError(f'source root {given} is not a folder; nothing was loaded')
    root = os.path.realpath(given)
    if inside(root, SKILL_ROOT):
        raise SourceError('the source root is inside the Kit to Clip package, which is distributed; keep private '
                          'sources in a folder outside it. Nothing was loaded')
    cand = os.path.join(root, f'{style_id}.json')
    if not os.path.lexists(cand):
        raise SourceError(f'no {style_id}.json in {root}. Nothing was loaded and no other copy is substituted; '
                          'the style is available as catalogue metadata only')
    real = os.path.realpath(cand)
    if not inside(real, root):
        raise SourceError(f'{cand} links outside the source root; refused, nothing was loaded')
    if not os.path.isfile(real):
        raise SourceError(f'{cand} is not a regular file; nothing was loaded')
    if os.path.getsize(real) > MAX_SOURCE_BYTES:
        raise SourceError(f'{cand} is larger than a source package should be; nothing was loaded')
    try:
        with open(real, 'r', encoding='utf-8') as f:
            pkg = json.load(f)
    except (OSError, ValueError) as e:
        raise SourceError(f'{cand} is not readable JSON ({e}); nothing was loaded')
    if not isinstance(pkg, dict) or not isinstance(pkg.get('prompt'), str):
        raise SourceError(f'{cand} must be a JSON object with a text "prompt"; nothing was loaded')
    identified_by = check_identity(pkg, style_id, cand)
    digest = hashlib.sha256(pkg['prompt'].encode('utf-8')).hexdigest()
    expected = entry['source']['prompt_sha256']
    if digest != expected:
        raise SourceError(f'{cand}: prompt sha256 {digest} does not match the catalogue ({expected}). It may be '
                          'edited or a different version; nothing was loaded')
    return {'ref': f'library:{style_id}', 'id': style_id, 'name': entry['name'], 'prompt': pkg['prompt'],
            'prompt_sha256': digest, 'hash_verified': True, 'identified_by': identified_by, 'source_file': real,
            'notice': RIGHTS,
            'runtime_validation': index.get('availability', {}).get('runtime_validation', 'none')}


# --- command line -------------------------------------------------------------------------------------------------
def positive_int(text):
    try:
        return check_limit(int(text))
    except (ValueError, CatalogueError):
        raise argparse.ArgumentTypeError(f'must be a whole number of at least 1, not {text!r}')


def print_problems(problems):
    if problems:
        print('Problems (these records were skipped):', file=sys.stderr)
        for p in problems:
            print(f'  {p["path"]}: {p["problem"]}', file=sys.stderr)


def line(row):
    if row['origin'] == 'library':
        return f'{row["ref"]:<30} {row["name"][:34]:<34} {row["family"]}'
    extra = ''.join(f' · {x}' for x in (row['kind'] == 'reference' and 'reference',
                                        row['brand'] and f'brand {row["brand"]}',
                                        row['original_brand'] and f'first made for {row["original_brand"]} (context only)',
                                        row['path']) if x)
    return f'{row["ref"]:<30} {row["name"][:34]:<34} {row["status"]}{"" if row["ready_to_reuse"] else " (not ready)"}{extra}'


def cmd_list(a):
    data = browse(a.family, a.styles_root, a.index)
    if a.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    print(f'{data["total"]} entries. {NOTICE}')
    for row in data['items']:
        print(line(row))
    if data.get('family') and a.styles_root:
        print('Saved styles have no family label, so a family filter leaves them out.')
    print_problems(data['problems'])


def cmd_search(a):
    data = search(' '.join(a.terms), a.family, a.limit, a.styles_root, a.index)
    if a.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print_problems(data['problems'])
        return
    print(f'Shortlist for "{data["query"]}" (terms: {", ".join(data["terms"])}). {NOTICE}')
    if not data['shortlist']:
        print('No matches.')
    for i, row in enumerate(data['shortlist'], 1):
        print(f'{i:>2}. {line(row)}  [{row["matched_terms"]}]')
        for r in row['reasons']:
            print(f'      - {r}')
    if data['drafts']:
        print('Drafts that match (visible for reference, not ready to reuse):')
        for row in data['drafts']:
            print(f'    {line(row)}  [{row["matched_terms"]}]')
    print(f'Showing {data["shown"]} of {data["total_matches"]} matches. Browse everything: {data["browse_all"]}')
    print_problems(data['problems'])


def cmd_families(a):
    data = families(a.index)
    if a.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    for f in data:
        print(f'{f["family"]:<28} {f["slug"]:<26} {f["count"]}')


def cmd_show(a):
    data = show(a.ref, a.styles_root, a.index)
    if a.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    for k, v in data.items():
        if k in ('fields', 'record'):
            continue
        print(f'{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}')


def cmd_load(a):
    data = load_source(a.id, a.source_root, a.index)
    if a.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(data['prompt'])
    print(f'{data["ref"]}: sha256 verified. {data["notice"]}', file=sys.stderr)


def build_parser():
    ap = argparse.ArgumentParser(prog='catalogue.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--index', type=Path, help='catalogue index to read (default: the bundled catalogue/index.json)')
    sub = ap.add_subparsers(dest='cmd', required=True, metavar='{list,search,families,show,load}')

    def common(p, styles=True):
        p.add_argument('--json', action='store_true', help='print JSON')
        if styles:
            p.add_argument('--styles-root', type=Path, help='saved-styles folder (<slug>/style.json) to include')

    p = sub.add_parser('list', help='browse every library entry (and saved styles with --styles-root)')
    p.add_argument('--family', help='only this library family (name or slug)')
    common(p)
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser('search', help='keyword/tag shortlist with match reasons')
    p.add_argument('terms', nargs='+', help='words describing the look, subject or mood')
    p.add_argument('--family', help='only this library family (name or slug)')
    p.add_argument('--limit', type=positive_int, default=DEFAULT_LIMIT, help=f'shortlist size (default {DEFAULT_LIMIT})')
    common(p)
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser('families', help='library family labels with counts')
    common(p, styles=False)
    p.set_defaults(fn=cmd_families)
    p = sub.add_parser('show', help='one entry: library:<id>, <id> or personal:<slug>')
    p.add_argument('ref')
    common(p)
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser('load', help='verify and print the prompt from YOUR local copy of one library style')
    p.add_argument('id', help='library id, e.g. watercolor')
    p.add_argument('--source-root', type=Path, required=True,
                   help='folder holding <id>.json; only that one file is read')
    common(p, styles=False)
    p.set_defaults(fn=cmd_load)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        a.fn(a)
    except CatalogueError as e:
        print(f'catalogue: {e}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
