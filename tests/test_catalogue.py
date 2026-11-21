"""Behavior checks for catalogue discovery (scripts/catalogue.py). Run with unittest discovery.

Library prompts are never part of these tests: source-loading checks use synthetic packages and a synthetic
index written to a temporary folder.
"""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO if (REPO / 'SKILL.md').exists() else REPO / 'addons' / 'kit-to-clip'
SCRIPT = SKILL / 'scripts' / 'catalogue.py'
INDEX = SKILL / 'catalogue' / 'index.json'

# Records file opens and filesystem mutations while a test switches recording on. Audit hooks cannot be
# removed, so the hook is installed once and does nothing unless RECORDING is set.
RECORDING = {'on': False, 'opens': [], 'mutations': []}
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
MUTATING_EVENTS = {'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.symlink', 'os.link', 'os.chmod',
                   'os.truncate', 'os.utime', 'shutil.copyfile', 'shutil.copytree', 'shutil.move', 'shutil.rmtree'}


def _hook(event, args):
    if not RECORDING['on']:
        return
    if event == 'open':
        path, mode, flags = (list(args) + [None, None, None])[:3]
        if isinstance(path, (str, bytes, os.PathLike)):
            RECORDING['opens'].append(os.fsdecode(path))
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or \
                (isinstance(flags, int) and flags & WRITE_FLAGS)
            if writing:
                RECORDING['mutations'].append(('open-for-write', os.fsdecode(path)))
    elif event in MUTATING_EVENTS:
        RECORDING['mutations'].append((event, repr(args)[:200]))


sys.addaudithook(_hook)


@contextlib.contextmanager
def recording():
    RECORDING.update(on=True, opens=[], mutations=[])
    try:
        yield RECORDING
    finally:
        RECORDING['on'] = False


def snapshot(root):
    out = {}
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink():
            out[str(p)] = ('link', os.readlink(p))
        elif p.is_file():
            st = p.stat()
            out[str(p)] = ('file', p.read_bytes(), st.st_mtime_ns)
        else:
            out[str(p)] = ('dir',)
    return out


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class CatalogueBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Fail (not skip) when the helper is missing: missing behavior must show up red.
        if not SCRIPT.is_file():
            raise AssertionError(f'catalogue helper is not implemented yet: {SCRIPT}')
        if not INDEX.is_file():
            raise AssertionError(f'catalogue index is missing: {INDEX}')
        spec = importlib.util.spec_from_file_location('kit_catalogue_test', SCRIPT)
        cls.cat = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cat)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kit-catalogue-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()

    # --- helpers -------------------------------------------------------------------------------------------
    def style(self, root, slug, **fields):
        d = root / slug
        d.mkdir(parents=True)
        data = {'slug': slug, 'title': slug.replace('-', ' ').title(), 'author': 'Tester', 'version': 1,
                'status': 'draft', 'brand': None, 'made_for': None, 'platforms': [], 'mood': None,
                'structure': [], 'dos': [], 'donts': [], 'references': [], 'motion_rules': []}
        data.update(fields)
        (d / 'style.json').write_text(json.dumps(data))
        return d

    def synthetic_index(self, prompts):
        """Write a minimal index whose hashes match the given synthetic prompts."""
        real = json.loads(INDEX.read_text())
        styles = []
        for i, (sid, prompt) in enumerate(prompts.items(), 1):
            styles.append({'id': sid, 'order': i, 'name': f'Synthetic {sid.title()}', 'family': 'Test Family',
                           'ground': 'unknown', 'look': ['synthetic'], 'motion': [], 'explains': [], 'fit': [],
                           'comparison_labels': [],
                           'preview': {'style_frame_video': None, 'explainer_clip': None},
                           'source': {'prompt_sha256': sha(prompt), 'code_chars': 1, 'js_blocks': 1}})
        data = {k: v for k, v in real.items() if k != 'styles'}
        data['styles'] = styles
        data['families'] = ['Test Family']
        p = self.base / 'synthetic-index.json'
        p.write_text(json.dumps(data))
        return p

    def package(self, root, sid, prompt, **extra):
        root.mkdir(parents=True, exist_ok=True)
        data = {'id': sid, 'prompt': prompt}
        data.update(extra)
        p = root / f'{sid}.json'
        p.write_text(json.dumps(data))
        return p

    def refs(self, result, key='shortlist'):
        return [r['ref'] for r in result[key]]

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                              cwd=str(self.base))


class IndexTests(CatalogueBase):
    def test_all_86_library_ids_are_unique_and_carry_provenance(self):
        # A dropped or duplicated id would silently hide a style or make loading ambiguous.
        index = self.cat.load_index()
        ids = [s['id'] for s in index['styles']]
        self.assertEqual(len(ids), 86)
        self.assertEqual(len(set(ids)), 86)
        hashes = [s['source']['prompt_sha256'] for s in index['styles']]
        self.assertEqual(len(set(hashes)), 86)
        for s in index['styles']:
            self.assertRegex(s['source']['prompt_sha256'], r'^[0-9a-f]{64}$', s['id'])
            self.assertIn('style_frame_video', s['preview'], s['id'])
            self.assertIn('explainer_clip', s['preview'], s['id'])
            self.assertTrue(s['look'], f"{s['id']} has no look descriptors")
            # The index is metadata only: no bundled prompt or code.
            self.assertFalse({'prompt', 'code', 'html', 'private_style_card'} & set(s), s['id'])
        self.assertEqual(len(index['families']), len({s['family'] for s in index['styles']}))

    def test_index_states_availability_rights_and_validation_limits(self):
        # Without these statements a reader could take metadata for licensed, tested source.
        index = self.cat.load_index()
        avail = index['availability']
        self.assertIn('metadata', avail)
        self.assertIn('source', avail)
        self.assertIn('runtime_validation', avail)
        self.assertIn('not bundled', avail['source'].lower())
        self.assertIn('no ', avail['runtime_validation'].lower())
        self.assertIn('inferred', index['fields']['fit'].lower())
        self.assertTrue(index['collection']['publisher'])
        self.assertTrue(index['limitations'])

    def test_corrupt_index_with_duplicate_ids_is_rejected(self):
        p = self.synthetic_index({'alpha': 'a', 'beta': 'b'})
        data = json.loads(p.read_text())
        data['styles'][1]['id'] = 'alpha'
        p.write_text(json.dumps(data))
        with self.assertRaises(self.cat.CatalogueError):
            self.cat.load_index(p)


class SearchTests(CatalogueBase):
    def test_exact_name_ranks_first_with_reason(self):
        result = self.cat.search('Watercolor Wash')
        first = result['shortlist'][0]
        self.assertEqual(first['ref'], 'library:watercolor')
        self.assertTrue(any(r.startswith('exact name match') for r in first['reasons']), first['reasons'])

    def test_british_spelling_finds_the_same_style(self):
        self.assertEqual(self.refs(self.cat.search('watercolour'))[0], 'library:watercolor')

    def test_name_match_outranks_tag_only_matches(self):
        # "neon" is a look tag on several retro styles; the style named for it must lead.
        result = self.cat.search('neon')
        refs = self.refs(result)
        self.assertEqual(refs[0], 'library:neon-sign')
        self.assertIn('library:synthwave', refs)
        synth = next(r for r in result['shortlist'] if r['ref'] == 'library:synthwave')
        self.assertFalse(any('name' in r for r in synth['reasons']), synth['reasons'])

    def test_tag_query_returns_real_reason_strings(self):
        result = self.cat.search('pastel', limit=50)
        rows = {r['ref']: r for r in result['shortlist']}
        self.assertIn('library:soft-3d', rows)
        self.assertIn('look tag "pastel"', ' '.join(rows['library:soft-3d']['reasons']))
        self.assertIn('library:isometric', rows)  # its name contains the word
        self.assertTrue(any('name' in r for r in rows['library:isometric']['reasons']))

    def test_inferred_fit_is_labelled_as_inferred(self):
        result = self.cat.search('finance', limit=50)
        self.assertTrue(result['shortlist'])
        for row in result['shortlist']:
            joined = ' '.join(row['reasons'])
            if 'fit' in joined:
                self.assertIn('inferred', joined)

    def test_results_carry_no_relevance_scores(self):
        result = self.cat.search('retro pixel game', limit=20)
        for row in result['shortlist']:
            self.assertNotIn('score', row)
            self.assertNotIn('%', ' '.join(row['reasons']))
            self.assertRegex(row['matched_terms'], r'^\d+ of \d+ terms$')

    def test_multi_term_query_prefers_rows_matching_more_terms(self):
        result = self.cat.search('green terminal', limit=20)
        self.assertEqual(result['shortlist'][0]['ref'], 'library:crt-terminal')

    def test_ranking_tiers_on_a_synthetic_catalogue(self):
        # Earlier catalogue order is given to the entry that should lose each comparison, so only the
        # documented tiers (exact name, terms covered, name, traits, inferred fit) can put the winner first.
        p = self.synthetic_index({k: k for k in ('glowmach', 'theglow', 'tagged', 'neon', 'fitonly', 'looktag')})
        data = json.loads(p.read_text())
        spec = {'glowmach': ('Glow Machine', [], []), 'theglow': ('The Glow', [], []),
                'tagged': ('Plain One', ['neon tubes', 'pastel'], []), 'neon': ('Neon', [], []),
                'fitonly': ('Plain Two', [], ['cozy']), 'looktag': ('Plain Three', ['cozy'], [])}
        for s in data['styles']:
            s['name'], s['look'], s['fit'] = spec[s['id']]
        p.write_text(json.dumps(data))
        order = lambda q: self.refs(self.cat.search(q, index_path=p, limit=10))
        self.assertEqual(order('the glow')[:2], ['library:theglow', 'library:glowmach'])  # exact name first
        self.assertEqual(order('neon pastel')[:2], ['library:tagged', 'library:neon'])   # more terms covered
        self.assertEqual(order('neon')[:2], ['library:neon', 'library:tagged'])          # name over tag
        self.assertEqual(order('cozy'), ['library:looktag', 'library:fitonly'])          # trait over inferred fit

    def test_family_filter_restricts_results_and_accepts_slug(self):
        a = self.cat.search('paper', family='Paper & Craft', limit=50)
        b = self.cat.search('paper', family='paper-craft', limit=50)
        self.assertEqual(self.refs(a), self.refs(b))
        self.assertTrue(a['shortlist'])
        for row in a['shortlist']:
            self.assertEqual(row['family'], 'Paper & Craft')
        with self.assertRaises(self.cat.CatalogueError) as ctx:
            self.cat.search('paper', family='No Such Family')
        self.assertIn('Paper & Craft', str(ctx.exception))

    def test_family_word_matches_family_with_reason(self):
        result = self.cat.search('painterly', limit=50)
        self.assertEqual(len(result['shortlist']), 6)
        self.assertTrue(all('family "Painterly"' in ' '.join(r['reasons']) for r in result['shortlist']))

    def test_ordering_is_deterministic_and_ties_follow_catalogue_order(self):
        a = self.cat.search('painterly', limit=50)
        b = self.cat.search('painterly', limit=50)
        self.assertEqual(self.refs(a), self.refs(b))
        orders = {s['id']: s['order'] for s in self.cat.load_index()['styles']}
        got = [orders[r.split(':', 1)[1]] for r in self.refs(a)]
        self.assertEqual(got, sorted(got))  # all six tie on family only

    def test_limit_keeps_browse_path_and_counts(self):
        result = self.cat.search('print', limit=2)
        self.assertEqual(len(result['shortlist']), 2)
        self.assertGreater(result['total_matches'], 2)
        self.assertIn('list', result['browse_all'])
        with self.assertRaises(self.cat.CatalogueError):
            self.cat.search('print', limit=0)

    def test_no_match_returns_empty_shortlist_with_browse_path(self):
        result = self.cat.search('zzqxv')
        self.assertEqual(result['shortlist'], [])
        self.assertEqual(result['total_matches'], 0)
        self.assertIn('list', result['browse_all'])
        self.assertIn('not a guarantee', result['notice'].lower())

    def test_browse_lists_everything_in_catalogue_order(self):
        items = self.cat.browse()['items']
        self.assertEqual(len(items), 86)
        self.assertEqual(items[0]['ref'], 'library:flat-space')
        self.assertEqual(len(self.cat.browse(family='Print')['items']), 6)


class PersonalStyleTests(CatalogueBase):
    def test_approved_personal_style_joins_shortlist_with_origin_and_paths(self):
        root = self.base / 'styles'
        d = self.style(root, 'cosy-thread', title='Cosy Thread', status='approved', brand='acme',
                       mood='handmade cosy textile', platforms=['tiktok'], version=3)
        result = self.cat.search('textile', styles_root=root, limit=20)
        rows = {r['ref']: r for r in result['shortlist']}
        self.assertIn('personal:cosy-thread', rows)
        self.assertIn('library:felt-quilt', rows)  # library results are merged, not replaced
        mine = rows['personal:cosy-thread']
        self.assertEqual(mine['origin'], 'personal')
        self.assertEqual(mine['brand'], 'acme')
        self.assertEqual(mine['status'], 'approved')
        self.assertTrue(mine['ready_to_reuse'])
        self.assertEqual(Path(mine['path']), d)
        self.assertTrue(any('mood' in r for r in mine['reasons']), mine['reasons'])
        self.assertFalse(rows['library:felt-quilt']['ready_to_reuse'])

    def test_draft_is_visible_but_not_recommended(self):
        root = self.base / 'styles'
        self.style(root, 'neon-draft', title='Neon Draft', status='draft', mood='neon night')
        result = self.cat.search('neon', styles_root=root, limit=50)
        self.assertNotIn('personal:neon-draft', self.refs(result))
        drafts = {r['ref']: r for r in result['drafts']}
        self.assertIn('personal:neon-draft', drafts)
        self.assertEqual(drafts['personal:neon-draft']['status'], 'draft')
        self.assertFalse(drafts['personal:neon-draft']['ready_to_reuse'])
        listed = {r['ref']: r for r in self.cat.browse(styles_root=root)['items']}
        self.assertEqual(listed['personal:neon-draft']['status'], 'draft')

    def test_personal_and_library_ids_cannot_collide(self):
        root = self.base / 'styles'
        self.style(root, 'watercolor', title='My Watercolor', status='approved')
        result = self.cat.search('watercolor', styles_root=root, limit=10)
        refs = self.refs(result)
        self.assertIn('personal:watercolor', refs)
        self.assertIn('library:watercolor', refs)
        self.assertEqual(self.cat.show('watercolor')['origin'], 'library')
        self.assertEqual(self.cat.show('library:watercolor')['name'], 'Watercolor Wash')
        mine = self.cat.show('personal:watercolor', styles_root=root)
        self.assertEqual((mine['origin'], mine['name']), ('personal', 'My Watercolor'))
        with self.assertRaises(self.cat.CatalogueError):
            self.cat.show('personal:watercolor')  # no styles root given: nothing personal is read

    def test_malformed_records_are_reported_without_hiding_good_ones(self):
        root = self.base / 'styles'
        self.style(root, 'good', title='Good Glow', status='approved', mood='glow')
        for slug, body in [('broken', '{not json'), ('a-list', '[1, 2]'),
                           ('bad-title', json.dumps({'title': 7, 'status': 'approved'})),
                           ('bad-status', json.dumps({'title': 'Bad Status', 'status': ['approved']}))]:
            (root / slug).mkdir(parents=True)
            (root / slug / 'style.json').write_text(body)
        result = self.cat.search('glow', styles_root=root, limit=50)
        self.assertIn('personal:good', self.refs(result))
        problem_paths = {Path(p['path']).parent.name for p in result['problems']}
        self.assertEqual(problem_paths, {'broken', 'a-list', 'bad-title', 'bad-status'})
        for p in result['problems']:
            self.assertTrue(p['problem'])
        self.assertEqual({Path(p['path']).parent.name for p in self.cat.browse(styles_root=root)['problems']},
                         problem_paths)

    def test_style_folder_linking_outside_root_is_not_read(self):
        root = self.base / 'styles'
        outside = self.base / 'elsewhere'
        self.style(outside, 'secret', title='Secret Glow', status='approved')
        root.mkdir()
        os.symlink(outside / 'secret', root / 'secret')
        with recording() as rec:
            result = self.cat.search('glow', styles_root=root, limit=50)
        self.assertNotIn('personal:secret', self.refs(result))
        self.assertTrue(any('outside' in p['problem'] for p in result['problems']), result['problems'])
        self.assertFalse(any(str(outside) in o for o in rec['opens']), rec['opens'])

    def test_missing_styles_root_is_a_clear_error(self):
        with self.assertRaises(self.cat.CatalogueError):
            self.cat.search('glow', styles_root=self.base / 'nope')


class PersonalReferenceTests(CatalogueBase):
    """Records written by styles.py capture (kind "reference") next to legacy templates (no kind)."""

    def reference(self, root, slug, **fields):
        data = dict(kind='reference', status='approved', brand=None, tags=['ink wash', 'paper'],
                    instructions={'medium': 'loose ink on paper', 'motion': 'strokes draw on and bleed',
                                  'pacing': 'four seconds a beat'},
                    reference={'entry': 'source/index.html', 'portable': False,
                               'portability': 'depends on 1 external file',
                               'files': [{'path': 'source/index.html', 'role': 'source'}]},
                    original_context={'note': 'context only', 'brand': {'mode': 'full', 'id': 'acme', 'name': 'Acme Co'},
                                      'story': {'summary': 'quarterly payroll'}},
                    provenance={'brief_revision': 7})
        data.update(fields)
        return self.style(root, slug, **data)

    def test_a_record_without_kind_is_a_legacy_template(self):
        root = self.base / 'styles'
        self.style(root, 'court-cam', title='Court Cam', status='approved', mood='court')
        self.style(root, 'explicit', title='Explicit', status='approved', kind='template')
        rows = {r['ref']: r for r in self.cat.browse(styles_root=root)['items']}
        self.assertEqual(rows['personal:court-cam']['kind'], 'template')
        self.assertEqual(rows['personal:explicit']['kind'], 'template')
        self.assertEqual(rows['personal:court-cam']['tags'], [])
        self.assertIsNone(rows['personal:court-cam']['original_brand'])

    def test_tags_and_reusable_instructions_are_searched_with_reasons(self):
        root = self.base / 'styles'
        self.reference(root, 'ink-ref', title='Ink Ref')
        for query, label in (('paper', 'tag'), ('bleed', 'motion'), ('beat', 'pacing'), ('loose', 'medium')):
            with self.subTest(query=query):
                result = self.cat.search(query, styles_root=root, limit=100)
                mine = next(r for r in result['shortlist'] if r['ref'] == 'personal:ink-ref')
                self.assertTrue(any(r.startswith(label) for r in mine['reasons']), mine['reasons'])
                self.assertEqual(mine['kind'], 'reference')
                self.assertIn('reference', mine['availability'])

    def test_original_story_and_brand_are_shown_but_not_searched_or_applied(self):
        root = self.base / 'styles'
        self.reference(root, 'ink-ref', title='Ink Ref')
        row = self.cat.show('personal:ink-ref', styles_root=root)
        self.assertIsNone(row['brand'])
        self.assertEqual(row['original_brand'], 'Acme Co')
        self.assertEqual(row['reference_source']['entry'], str(root / 'ink-ref' / 'source' / 'index.html'))
        self.assertFalse(row['reference_source']['portable'])
        self.assertEqual(row['record']['provenance'], {'brief_revision': 7})
        for query in ('acme', 'payroll'):
            result = self.cat.search(query, styles_root=root, limit=100)
            self.assertNotIn('personal:ink-ref', self.refs(result) + self.refs(result, 'drafts'))

    def test_a_draft_reference_is_visible_but_not_recommended(self):
        root = self.base / 'styles'
        self.reference(root, 'ink-draft', title='Ink Draft', status='draft')
        result = self.cat.search('paper', styles_root=root, limit=100)
        self.assertNotIn('personal:ink-draft', self.refs(result))
        self.assertFalse({r['ref']: r for r in result['drafts']}['personal:ink-draft']['ready_to_reuse'])

    def test_bad_kind_or_reference_block_is_reported_without_hiding_good_ones(self):
        root = self.base / 'styles'
        self.reference(root, 'good', title='Good Paper')
        self.reference(root, 'odd-kind', title='Odd Kind', kind='banana')
        self.reference(root, 'num-kind', title='Num Kind', kind=7)
        self.reference(root, 'no-manifest', title='No Manifest', reference='source')
        result = self.cat.search('paper', styles_root=root, limit=100)
        self.assertIn('personal:good', self.refs(result))
        bad = {Path(p['path']).parent.name: p['problem'] for p in result['problems']}
        self.assertEqual(set(bad), {'odd-kind', 'num-kind', 'no-manifest'})
        self.assertIn('kind', bad['odd-kind'])
        self.assertIn('reference', bad['no-manifest'])

    def test_a_hand_made_reference_without_a_manifest_is_listed_without_source_paths(self):
        root = self.base / 'styles'
        self.style(root, 'hand-made', title='Hand Made', status='approved', kind='reference', tags=['paper'])
        rows = {r['ref']: r for r in self.cat.browse(styles_root=root)['items']}
        self.assertEqual(rows['personal:hand-made']['kind'], 'reference')
        self.assertIsNone(rows['personal:hand-made']['reference_source'])


class NoSideEffectTests(CatalogueBase):
    def test_discovery_opens_only_index_and_style_records(self):
        # Discovery must stay cheap and private: it never opens source packages, even ones lying nearby.
        root = self.base / 'styles'
        self.style(root, 'mine', title='Mine', status='approved', mood='neon')
        (root / 'mine' / 'notes.md').write_text('not a record')
        sources = self.base / 'sources'
        self.package(sources, 'neon-sign', 'synthetic')
        with recording() as rec:
            self.cat.search('neon', styles_root=root)
            self.cat.browse(styles_root=root)
            self.cat.show('neon-sign')
            self.cat.show('personal:mine', styles_root=root)
            self.cat.families()
        opened = {os.path.realpath(o) for o in rec['opens'] if o.startswith(str(self.base)) or o == str(INDEX)}
        allowed = {os.path.realpath(root / 'mine' / 'style.json'), os.path.realpath(INDEX)}
        self.assertTrue(opened <= allowed, opened - allowed)
        self.assertFalse([o for o in rec['opens'] if os.path.realpath(o).startswith(str(sources))])
        self.assertIn(os.path.realpath(INDEX), {os.path.realpath(o) for o in rec['opens']})
        self.assertEqual(rec['mutations'], [])

    def test_cli_browsing_changes_no_files(self):
        root = self.base / 'styles'
        self.style(root, 'mine', title='Mine', status='approved', mood='neon')
        self.style(root, 'later', title='Later', status='draft')
        before_tmp, before_skill = snapshot(self.base), snapshot(SKILL / 'catalogue')
        for args in (['list', '--styles-root', root], ['list', '--json', '--family', 'Print'],
                     ['search', 'neon', '--styles-root', root, '--json'], ['search', 'neon', '--limit', '3'],
                     ['show', 'library:neon-sign', '--json'], ['show', 'personal:mine', '--styles-root', root],
                     ['families']):
            r = self.run_cli(*args)
            self.assertEqual(r.returncode, 0, (args, r.stderr))
        self.assertEqual(snapshot(self.base), before_tmp)
        self.assertEqual(snapshot(SKILL / 'catalogue'), before_skill)

    def test_search_command_has_no_source_option(self):
        r = self.run_cli('search', 'neon', '--source-root', self.base)
        self.assertNotEqual(r.returncode, 0)


class SourceLoadTests(CatalogueBase):
    def test_loads_only_the_selected_verified_package(self):
        prompts = {'alpha': 'Synthetic alpha prompt.', 'beta': 'Synthetic beta prompt.'}
        index = self.synthetic_index(prompts)
        sources = self.base / 'sources'
        a = self.package(sources, 'alpha', prompts['alpha'])
        b = self.package(sources, 'beta', prompts['beta'])
        with recording() as rec:
            got = self.cat.load_source('alpha', sources, index_path=index)
        self.assertEqual(got['prompt'], prompts['alpha'])
        self.assertEqual(got['prompt_sha256'], sha(prompts['alpha']))
        self.assertTrue(got['hash_verified'])
        self.assertIn('rights', got['notice'].lower())
        opened = {os.path.realpath(o) for o in rec['opens'] if o.startswith(str(self.base))}
        self.assertIn(os.path.realpath(a), opened)
        self.assertNotIn(os.path.realpath(b), opened)
        self.assertEqual(rec['mutations'], [])

    def test_missing_source_reports_limitation_without_substitute(self):
        index = self.synthetic_index({'alpha': 'A', 'beta': 'B'})
        sources = self.base / 'sources'
        self.package(sources, 'beta', 'B')
        with self.assertRaises(self.cat.SourceError) as ctx:
            self.cat.load_source('alpha', sources, index_path=index)
        self.assertIn('alpha.json', str(ctx.exception))

    def test_hash_mismatch_is_refused(self):
        index = self.synthetic_index({'alpha': 'Original'})
        sources = self.base / 'sources'
        self.package(sources, 'alpha', 'Edited')
        with self.assertRaises(self.cat.SourceError) as ctx:
            self.cat.load_source('alpha', sources, index_path=index)
        self.assertIn('sha256', str(ctx.exception).lower())

    def test_real_catalogue_rejects_a_synthetic_stand_in(self):
        # The project holds no real prompt; a fake package for a real id must never verify.
        sources = self.base / 'sources'
        self.package(sources, 'watercolor', 'Not the real thing.')
        with self.assertRaises(self.cat.SourceError):
            self.cat.load_source('watercolor', sources)

    def test_package_id_must_match_request(self):
        index = self.synthetic_index({'alpha': 'Same', 'beta': 'Other'})
        sources = self.base / 'sources'
        sources.mkdir()
        (sources / 'alpha.json').write_text(json.dumps({'id': 'beta', 'prompt': 'Same'}))
        with self.assertRaises(self.cat.SourceError):
            self.cat.load_source('alpha', sources, index_path=index)

    def test_original_export_shapes_load_unchanged(self):
        # The private collection is exported as {info: {id | styleId}, prompt}; it must load as-is, not be rewritten.
        prompts = {'alpha': 'Synthetic alpha.', 'beta': 'Synthetic beta.', 'gamma': 'Synthetic gamma.'}
        index = self.synthetic_index(prompts)
        sources = self.base / 'sources'
        sources.mkdir()
        bodies = {'alpha': {'info': {'id': 'alpha', 'title': 'Synthetic'}, 'prompt': prompts['alpha']},
                  'beta': {'info': {'styleId': 'beta', 'title': 'Synthetic'}, 'prompt': prompts['beta']},
                  'gamma': {'id': 'gamma', 'prompt': prompts['gamma']}}
        for sid, body in bodies.items():
            (sources / f'{sid}.json').write_text(json.dumps(body))
        before = snapshot(sources)
        for sid in bodies:
            with self.subTest(sid=sid), recording() as rec:
                got = self.cat.load_source(sid, sources, index_path=index)
                self.assertEqual(got['prompt'], prompts[sid])
                self.assertTrue(got['hash_verified'])
                self.assertEqual(rec['mutations'], [])
        self.assertEqual(snapshot(sources), before)

    def test_every_present_identifier_must_be_valid_and_agree(self):
        # Any one identifier naming another style, or a malformed one, means the file is not the selected package.
        index = self.synthetic_index({'alpha': 'Same', 'beta': 'Other'})
        sources = self.base / 'sources'
        sources.mkdir()
        bad = [{'id': 'alpha', 'info': {'styleId': 'beta'}, 'prompt': 'Same'},
               {'info': {'id': 'alpha', 'styleId': 'beta'}, 'prompt': 'Same'},
               {'info': {'id': 'beta'}, 'prompt': 'Same'},
               {'info': {'styleId': 'beta'}, 'prompt': 'Same'},
               {'id': 'alpha', 'info': {'id': 7}, 'prompt': 'Same'},
               {'info': {'id': 'alpha', 'styleId': 'Alpha'}, 'prompt': 'Same'},
               {'info': {'styleId': ''}, 'prompt': 'Same'},
               {'id': None, 'info': {'id': 'alpha'}, 'prompt': 'Same'},
               {'info': {'id': 'alpha'}, 'prompt': 7},
               {'info': 'alpha', 'prompt': 'Same'}]
        for body in bad:
            with self.subTest(body=body):
                (sources / 'alpha.json').write_text(json.dumps(body))
                with self.assertRaises(self.cat.SourceError):
                    self.cat.load_source('alpha', sources, index_path=index)

    def test_identity_is_never_inferred_from_the_filename(self):
        # A matching hash under the right filename is not enough: the package itself must name the style.
        index = self.synthetic_index({'alpha': 'Same'})
        sources = self.base / 'sources'
        sources.mkdir()
        for body in ({'prompt': 'Same'}, {'info': {}, 'prompt': 'Same'}, {'info': {'title': 'alpha'}, 'prompt': 'Same'}):
            with self.subTest(body=body):
                (sources / 'alpha.json').write_text(json.dumps(body))
                with self.assertRaises(self.cat.SourceError) as ctx:
                    self.cat.load_source('alpha', sources, index_path=index)
                self.assertIn('styleId', str(ctx.exception))

    def test_traversal_and_unknown_ids_are_refused_before_reading(self):
        index = self.synthetic_index({'alpha': 'A'})
        sources = self.base / 'sources'
        sources.mkdir()
        self.package(self.base, 'outside', 'A')
        for bad in ('../outside', 'alpha/../../outside', '/etc/passwd', 'ALPHA', 'gamma', '', 'alpha.json'):
            with self.subTest(bad=bad), recording() as rec:
                with self.assertRaises(self.cat.SourceError):
                    self.cat.load_source(bad, sources, index_path=index)
                self.assertFalse([o for o in rec['opens'] if o.startswith(str(self.base)) and
                                  not o.endswith('synthetic-index.json')], rec['opens'])

    def test_symlink_escaping_the_source_root_is_refused(self):
        index = self.synthetic_index({'alpha': 'A'})
        sources = self.base / 'sources'
        sources.mkdir()
        target = self.package(self.base / 'outside', 'alpha', 'A')
        os.symlink(target, sources / 'alpha.json')
        with self.assertRaises(self.cat.SourceError) as ctx:
            self.cat.load_source('alpha', sources, index_path=index)
        self.assertIn('outside', str(ctx.exception))

    def test_source_root_must_be_an_existing_folder(self):
        index = self.synthetic_index({'alpha': 'A'})
        with self.assertRaises(self.cat.SourceError):
            self.cat.load_source('alpha', self.base / 'missing', index_path=index)
        f = self.base / 'file'
        f.write_text('x')
        with self.assertRaises(self.cat.SourceError):
            self.cat.load_source('alpha', f, index_path=index)

    def test_source_root_inside_the_skill_package_is_refused(self):
        # Private sources placed in the distributed package would be published with it.
        index = self.synthetic_index({'alpha': 'A'})
        fake_skill = self.base / 'skill'
        self.package(fake_skill / 'private', 'alpha', 'A')
        original = self.cat.SKILL_ROOT
        self.cat.SKILL_ROOT = fake_skill
        try:
            with self.assertRaises(self.cat.SourceError):
                self.cat.load_source('alpha', fake_skill / 'private', index_path=index)
        finally:
            self.cat.SKILL_ROOT = original


class CliTests(CatalogueBase):
    def test_help_describes_commands(self):
        r = self.run_cli('--help')
        self.assertEqual(r.returncode, 0)
        for word in ('list', 'search', 'show', 'load', 'families'):
            self.assertIn(word, r.stdout)
        for shape in ('"info": {"id"', '"styleId"', '{"id": <id>, "prompt"'):
            self.assertIn(shape, r.stdout)  # all accepted package shapes are documented

    def test_search_json_and_text(self):
        r = self.run_cli('search', 'chalkboard', '--json')
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data['shortlist'][0]['ref'], 'library:chalkboard')
        t = self.run_cli('search', 'chalkboard', '--limit', '1')
        self.assertEqual(t.returncode, 0, t.stderr)
        self.assertIn('library:chalkboard', t.stdout)
        self.assertIn('list', t.stdout)  # the browse path is printed

    def test_load_via_cli_prints_prompt_and_failures_exit_nonzero(self):
        prompts = {'alpha': 'Synthetic alpha prompt.'}
        index = self.synthetic_index(prompts)
        sources = self.base / 'sources'
        self.package(sources, 'alpha', prompts['alpha'])
        ok = self.run_cli('--index', index, 'load', 'alpha', '--source-root', sources)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(ok.stdout.strip(), prompts['alpha'])
        self.assertIn('rights', ok.stderr.lower())
        bad = self.run_cli('--index', index, 'load', '../alpha', '--source-root', sources)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('catalogue', bad.stderr.lower())
        missing = self.run_cli('--index', index, 'load', 'alpha')
        self.assertNotEqual(missing.returncode, 0)  # --source-root is required, never guessed

    def test_unknown_ref_and_bad_family_exit_nonzero(self):
        self.assertNotEqual(self.run_cli('show', 'library:nope').returncode, 0)
        r = self.run_cli('list', '--family', 'nope')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Painterly', r.stderr)


if __name__ == '__main__':
    unittest.main()
