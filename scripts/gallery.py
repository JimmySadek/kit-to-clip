#!/usr/bin/env python3
"""Build a local gallery from style metadata, saved references and legacy recipes.

gallery.py --project <repo> --out <new-folder> [--brand <id>] [--samples samples.json]
See references/style-gallery.md for sample associations and approval boundaries.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
LOOKS = {
    'clean': ('Clean', 'An accent ring draws on and a dot lands.'),
    'cut-paper': ('Cut paper', 'Layered shapes, soft shadows and paper grain.'),
    'risograph': ('Risograph', 'Two inks, halftone dots and print texture.'),
    'sketchbook': ('Sketchbook', 'Pencil loops, arrows and a marker underline.'),
    'isometric': ('Isometric', 'Stacked blocks on an isometric grid.'),
    'glass': ('Frosted glass', 'Translucent panes reveal connections in depth.'),
    'pixel': ('16-bit pixel', 'Block-shaped nodes join along stepped paths.'),
    'chalkboard': ('Chalkboard', 'Outlined nodes and an arrow draw on.'),
    'flat-vector': ('Flat vector science', 'Large shapes explain input, process and output.'),
}
MEDIA = {'poster': {'.png', '.jpg', '.jpeg', '.webp'}, 'video': {'.mp4', '.webm'}}
FORMAT_COPY = {
    'brand-reel': 'A headline, a key number, three points and a brand end card, timed to music.',
    'explainer': 'A narrated explanation with captions and nine illustration looks.',
    'teaser-loop': 'A still announcement brought to life as a seamless loop.',
}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def catalog(project, brand=None, styles_root=None):
    """Read the existing registries without changing brand selection or preferences."""
    formats = module('gallery_formats', ROOT / 'formats/scripts/formats.py')
    catalogue = module('gallery_catalogue', ROOT / 'scripts/catalogue.py')
    try:
        index = catalogue.load_index()
    except catalogue.CatalogueError as error:
        raise ValueError(str(error)) from error
    rows = []
    for item in index['styles']:
        tags = [tag for field in ('look', 'motion', 'explains', 'fit') for tag in item.get(field, [])]
        rows.append({'id': 'library:' + item['id'], 'category': 'library', 'origin': 'atlas',
                     'style': item['id'], 'name': item['name'], 'family': item['family'],
                     'status': 'reference', 'about': ', '.join(item.get('look', [])),
                     'tags': tags, 'motion': item.get('motion', []), 'fit': item.get('fit', []),
                     'original_previews': item.get('preview', {}), 'source_required': True,
                     'limitations': index.get('limitations', []), 'brand': None})
    for f in formats.collect(Path(project).resolve()):
        if brand and f['brand'] not in ('any', brand):
            continue
        rows.append({'id': f"format:{f['brand']}:{f['id']}", 'category': 'formats', 'format': f['id'],
                     'name': f.get('name') or f['id'], 'status': f.get('status') or 'broken',
                     'about': f.get('broken') or (FORMAT_COPY.get(f['id']) if f['source'] == 'neutral' else None) or f.get('about') or '', 'brand': f['brand'],
                     'broken': bool(f.get('broken'))})
    explainer = json.loads((ROOT / 'formats/neutral/explainer/format.json').read_text())
    new_looks = ['glass', 'pixel', 'chalkboard', 'flat-vector']
    ordered = [s for s in new_looks if s in explainer['styles']]
    ordered += [s for s in explainer['styles'] if s not in new_looks]
    for style in ordered:
        name, about = LOOKS.get(style, (style.replace('-', ' ').capitalize(), 'Explainer illustration style.'))
        rows.append({'id': 'look:' + style, 'category': 'looks', 'style': style, 'name': name,
                     'status': explainer['status'], 'about': about, 'brand': 'any'})
    if styles_root is not None:
        try:
            personal, records, problems = catalogue.read_personal(styles_root)
        except catalogue.CatalogueError as error:
            raise ValueError(str(error)) from error
        saved = [{**records[s['ref']], 'slug': s['id'], 'path': s['path']} for s in personal]
        for problem in problems:
            path = Path(problem['path'])
            rows.append({'id': 'problem:' + path.parent.name, 'category': 'saved', 'name': path.parent.name,
                         'status': 'broken', 'about': problem['problem'], 'broken': True})
    else:
        args = [sys.executable, str(ROOT / 'scripts/styles.py'), 'list', '--json']
        result = subprocess.run(args, cwd=project, capture_output=True, text=True)
        saved, problems = [], []
        if result.returncode:
            problems.append({'path':'saved-styles', 'problem':'Saved styles could not be read: ' + result.stderr.strip()})
        else:
            try:
                listed = json.loads(result.stdout)
                for entry in listed:
                    folder = Path(entry['path'])
                    row, record = catalogue.read_record(folder.parent, folder)
                    if row is None:
                        problems.append(record)
                    else:
                        saved.append({**record, 'slug':row['id'], 'path':row['path']})
                if result.stderr.strip():
                    problems.append({'path':'saved-styles', 'problem':result.stderr.strip()})
            except (ValueError, KeyError, TypeError, OSError) as error:
                problems.append({'path':'saved-styles', 'problem':'Saved registry could not be read: ' + str(error)})
        for number, problem in enumerate(problems):
            rows.append({'id':f'problem:registry-{number}', 'category':'saved', 'name':'Saved styles need attention',
                         'status':'broken', 'about':problem['problem'], 'broken':True})
    for s in saved:
        instructions = s.get('instructions') if isinstance(s.get('instructions'), dict) else {}
        details = []
        for key in ('medium', 'motion', 'pacing'):
            value = instructions.get(key)
            if isinstance(value, str):
                details.append(value)
            elif isinstance(value, list):
                details += [v for v in value if isinstance(v, str)]
        context = s.get('original_context') or {}
        context_brand = context.get('brand') if isinstance(context, dict) else None
        original_brand = context_brand.get('id') if isinstance(context_brand, dict) else None
        rows.append({'id': f"style:{s.get('brand') or 'neutral'}:{s['slug']}", 'category': 'saved',
                     'style': s['slug'], 'name': s.get('title') or s['slug'],
                     'status': s.get('status') or 'draft', 'about': s.get('signature') or '; '.join(details) or 'A saved video recipe.',
                     'brand': s.get('brand'), 'reuse_kind': s.get('kind') or 'template',
                     'original_brand': original_brand,
                     'tags': [t for t in s.get('tags', []) if isinstance(t, str)] if isinstance(s.get('tags'), list) else [],
                     'origin': 'personal',
                     '_saved_root': s.get('path'),
                     '_previews': (s.get('reference') or {}).get('previews', []) if isinstance(s.get('reference'), dict) else [],
                     'family': s.get('family') or 'Personal reference'})
    return rows


def sample_sources(manifest, ids, brand):
    """Resolve explicitly associated local media, without walking unrelated folders."""
    if manifest is None:
        return {}
    manifest = Path(manifest).resolve()
    data = json.loads(manifest.read_text())
    if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('samples'), list):
        raise ValueError('samples.json needs schema 1 and a samples list')
    result, seen = {}, set()
    for sample in data['samples']:
        if not isinstance(sample, dict) or sample.get('id') not in ids:
            raise ValueError('unknown sample id; use gallery.py --list to see the current ids')
        key = sample['id']
        if key in seen:
            raise ValueError('duplicate sample id: ' + key)
        seen.add(key)
        kind = sample.get('kind')
        if kind not in ('neutral-demo', 'brand'):
            raise ValueError('sample kind must be neutral-demo or brand')
        if kind == 'brand' and not sample.get('brand'):
            raise ValueError('a branded sample needs its brand id')
        files = {}
        for role, extensions in MEDIA.items():
            raw = sample.get(role)
            if raw is None:
                continue
            if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or '://' in raw:
                raise ValueError('sample media must be a relative local path')
            path = (manifest.parent / raw).resolve()
            if not path.is_relative_to(manifest.parent) or path.suffix.lower() not in extensions:
                raise ValueError('sample media leaves its folder or has an unsupported file type')
            if path.is_file():
                files[role] = path
        if kind == 'brand' and sample['brand'] != brand:
            continue
        if files:
            result[key] = {'label': 'Neutral demo' if kind == 'neutral-demo' else 'Your brand', 'files': files}
    return result


def personal_sample(row):
    """Reuse a reviewed local still only. Discovery never opens code or preview pixels."""
    root = row.get('_saved_root')
    if not root:
        return None, None
    root = Path(root).resolve()
    warning = None
    candidates = row.get('_previews')
    if not isinstance(candidates, list):
        return None, None
    for preview in candidates:
        if not isinstance(preview, dict) or preview.get('approval_evidence') is not True:
            continue
        raw = preview.get('path')
        if not isinstance(raw, str):
            continue
        path = (root / raw).resolve()
        if Path(raw).is_absolute() or not path.is_relative_to(root) or path.suffix.lower() not in MEDIA['poster']:
            warning = 'Saved preview leaves its reference folder or has an unsupported image type.'
            continue
        try:
            content = path.read_bytes()
        except OSError:
            warning = 'Saved preview is missing or unreadable. Open the reference to refresh it.'
            continue
        if hashlib.sha256(content).hexdigest() != preview.get('sha256'):
            warning = 'Saved preview changed since its recorded review. Open the reference to refresh it.'
            continue
        return {'label':'Saved reference preview', 'files':{'poster':path}}, None
    return None, warning


def build(out, items, brand=None, samples=None, query=None):
    """Write a fresh static gallery. Existing output is never replaced."""
    out = Path(out)
    if out.exists():
        raise FileExistsError(f'{out} already exists; choose a new output folder')
    ids = [r['id'] for r in items]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate gallery ids in the registries')
    sources = sample_sources(samples, set(ids), brand)
    data = {'schema': 1, 'brand': brand, 'query': query or '', 'items': []}
    for row in items:
        item = {key:value for key,value in row.items() if not key.startswith('_')}
        item['preview'] = None
        sample = sources.get(row['id'])
        if not sample:
            sample, warning = personal_sample(row)
            if warning:
                item['preview_warning'] = warning
            if sample:
                sources[row['id']] = sample
        if sample:
            item['preview'] = {'label': sample['label']}
            for role, path in sample['files'].items():
                item['preview'][role] = f'assets/{len(data["items"])}-{role}{path.suffix.lower()}'
        data['items'].append(item)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'assets').mkdir()
    for row in data['items']:
        if row['preview']:
            for role, path in sources[row['id']]['files'].items():
                shutil.copy2(path, out / row['preview'][role])
    for name in ('index.html', 'gallery.css', 'gallery.js'):
        shutil.copy2(ROOT / 'references/gallery' / name, out / name)
    payload = json.dumps(data, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    (out / 'data.js').write_text('window.KIT_GALLERY = ' + payload + ';\n')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--brand', help='already chosen brand id; this never selects or installs a brand')
    parser.add_argument('--styles-root', type=Path, help='explicit saved-styles folder instead of normal discovery')
    parser.add_argument('--samples', type=Path)
    parser.add_argument('--query', help='initial topic/look terms from the video brief; the full catalogue stays browsable')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--list', action='store_true', help='print gallery ids and status, without writing')
    args = parser.parse_args()
    try:
        items = catalog(args.project.resolve(), args.brand, args.styles_root)
        if args.list:
            print(json.dumps(items, indent=2))
            return
        if not args.out:
            parser.error('--out is required unless --list is used')
        data = build(args.out, items, args.brand, args.samples, args.query)
        count = sum(bool(x['preview']) for x in data['items'])
        print(f'gallery: {args.out.resolve() / "index.html"} ({len(items)} entries, {count} local previews)')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'gallery: {error}\n')


if __name__ == '__main__':
    main()
