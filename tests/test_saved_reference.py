"""Saving an approved video's treatment as a personal code reference (scripts/styles.py capture / handoff).

Every film.json, brief, project and approval here is a synthetic TEST fixture (briefs made with scripts/brief.py): the approval notes say
so, and no real person's decision, style or video project is read or changed. Each test works in its own temporary
folder, removed afterwards.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO if (REPO / 'SKILL.md').exists() else REPO / 'addons' / 'kit-to-clip'
STYLES = SKILL / 'scripts' / 'styles.py'
BRIEF = SKILL / 'scripts' / 'brief.py'
CATALOGUE = SKILL / 'scripts' / 'catalogue.py'
TEST_OK = 'TEST FIXTURE ONLY: synthetic approval recorded by the test suite, not a person\'s decision'

INDEX_HTML = """<!doctype html><html><head>
<link rel="stylesheet" href="styles.css">
<link rel="stylesheet" href="brand.css">
<script src="vendor/gsap.min.js"></script>
<script src="https://cdn.example.test/lib.js"></script>
</head><body>
<img src="assets/logo.png" alt="">
<video src="clips/raw.mp4"></video>
<script src="scene.js"></script>
</body></html>
"""
STYLES_CSS = '@import "type.css";\nbody { background: url(assets/paper.png); }\n'
TYPE_CSS = 'h1 { font-family: serif; }\n'
SCENE_JS = "const tl = gsap.timeline();\nfetch('prompts/private-pack.json');\n"
SOURCES = ('index.html', 'styles.css', 'type.css', 'scene.js')
TEST_SAVE = 'TEST FIXTURE ONLY: synthetic words standing in for a person approving the finished video for saving'


def source_assets(rels, prefix='project/'):
    """Brief assets naming build files with role "source", so the brief fingerprints them for its approvals."""
    return {'src-' + ''.join(c if c.isalnum() else '-' for c in rel): {
        'path': prefix + rel, 'role': 'source', 'notes': 'TEST synthetic build source'} for rel in rels}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tree(root):
    """Every path under root with its bytes (files) or link target, to prove nothing was changed or deleted."""
    out = {}
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink():
            out[str(p)] = ('link', os.readlink(p))
        elif p.is_file():
            out[str(p)] = ('file', p.read_bytes())
        else:
            out[str(p)] = ('dir',)
    return out


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brief = load('kit_brief_for_reference_test', BRIEF)
        cls.cat = load('kit_catalogue_for_reference_test', CATALOGUE)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='kit-saved-reference-test-')
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.lib = self.base / 'lib'
        self.registry = self.lib / 'styles'

    # --- fixtures --------------------------------------------------------------------------------------------
    def project(self, job):
        p = job / 'project'
        files = {'index.html': INDEX_HTML, 'styles.css': STYLES_CSS, 'type.css': TYPE_CSS, 'scene.js': SCENE_JS,
                 'vendor/gsap.min.js': '/* synthetic gsap */', 'brand.css': ':root { --acme: red; }',
                 '.env': 'API_KEY=synthetic-secret', 'node_modules/pkg/index.js': 'module.exports = 1',
                 '.git/config': '[core]', 'notes/unrelated.md': 'unrelated private notes',
                 'prompts/private-pack.json': json.dumps({'id': 'watercolor', 'prompt': 'synthetic private prompt'})}
        for rel, text in files.items():
            (p / rel).parent.mkdir(parents=True, exist_ok=True)
            (p / rel).write_text(text)
        for rel, data in {'assets/logo.png': b'\x89PNG synthetic logo', 'assets/paper.png': b'\x89PNG paper',
                          'clips/raw.mp4': b'synthetic footage bytes', 'renders/final.mp4': b'synthetic render',
                          'snapshots/approved-frame.png': b'\x89PNG approved frame'}.items():
            (p / rel).parent.mkdir(parents=True, exist_ok=True)
            (p / rel).write_bytes(data)
        return p

    def approved_brief(self, name='job', music=True, listening=True, route='idea', sources=SOURCES, extra=None):
        """A brief taken through every gate with brief.py itself. Returns (brief.md, final revision, project).

        The build's editable files are named in the brief's assets with role "source" before the stills and render
        decisions, so the render approval fingerprints them. The stills yes is given on the preview still; render yes
        is permission to render (no evidence); listening is given on the rendered mix."""
        job = self.base / 'work' / name
        project = self.project(job)
        b = job / 'brief.md'
        self.brief.init_brief(b, 'TEST: a 12 second explainer about quarterly payroll for Acme Co')
        assets = {'logo': {'path': 'project/assets/logo.png', 'role': 'logo',
                           'notes': 'TEST asset drawn for this fixture; licence CC0'}}
        assets.update(source_assets(sources))
        patch = {'route': route,
                 'destination': {'platform': 'tiktok', 'aspect': '9:16', 'duration_seconds': 12},
                 'story': {'summary': 'Quarterly payroll explained in three beats',
                           'beats': ['payroll is due', 'Acme automates it', 'relax']},
                 'style': {'name': 'Ink wash', 'notes': 'loose ink wash on paper',
                           'reference': {'catalogue_id': 'watercolor', 'origin': 'library',
                                         'permitted_use': 'TEST: private use only'}},
                 'brand': {'mode': 'full', 'id': 'acme', 'name': 'Acme Co', 'palette': ['#ff0000 primary']},
                 'assets': assets,
                 'audio': {'timing_driver': 'visual', 'voice': {'choice': 'none'}, 'effects': {'choice': 'none'},
                           'music': {'choice': 'supplied', 'path': 'music.wav'} if music else {'choice': 'none'}}}
        if route == 'footage':
            patch['assets']['footage'] = {'path': 'project/clips/raw.mp4', 'role': 'footage',
                                          'notes': 'TEST footage supplied for this fixture'}
            patch['style'] = None
            patch['brand'] = {'mode': 'original'}
        if extra:
            extra(job, patch)
        if music:
            (job / 'music.wav').write_bytes(b'RIFF synthetic music')
        rev = self.brief.update(b, 1, patch)['revision']
        rev = self.brief.approve(b, rev, 'layout', 'yes', TEST_OK)['revision']
        rev = self.brief.approve(b, rev, 'stills', 'yes', TEST_OK, evidence='project/snapshots/approved-frame.png')['revision']
        if music:
            rev = self.brief.approve(b, rev, 'music-choice', 'yes', TEST_OK)['revision']
        rev = self.brief.approve(b, rev, 'render', 'yes', TEST_OK)['revision']   # permission to render, no file yet
        if music and listening:
            rev = self.brief.approve(b, rev, 'listening', 'yes', TEST_OK, evidence='project/renders/final.mp4')['revision']
        return b, rev, project

    # --- running styles.py -----------------------------------------------------------------------------------
    def run_styles(self, *args, root=True):
        argv = [sys.executable, '-B', str(STYLES)] + (['--root', str(self.lib)] if root else []) + list(map(str, args))
        return subprocess.run(argv, capture_output=True, text=True, cwd=str(self.base))

    def capture(self, b, rev, project, *extra, title='Ink Wash Explainer', final='renders/final.mp4', note=TEST_SAVE):
        save = (['--finished-output', project / final] if final else []) + (['--approval-note', note] if note else [])
        return self.run_styles('capture', '--brief', b, '--expected', rev, '--project', project, '--title', title,
                               *save, *extra)

    def full_capture(self, b, rev, project, **kw):
        return self.capture(b, rev, project, '--tag', 'watercolour', '--tag', 'ink wash',
                            '--medium', 'loose ink wash with paper grain',
                            '--motion', 'brush strokes draw on, then bleed outwards',
                            '--pacing', 'one idea per beat, about four seconds each',
                            '--asset', 'assets/logo.png',
                            '--preview', project / 'snapshots/approved-frame.png',
                            '--preview', project / 'renders/final.mp4', **kw)

    def record(self, slug='ink-wash-explainer'):
        return json.loads((self.registry / slug / 'style.json').read_text())

    def assert_refused(self, r, *words):
        self.assertNotEqual(r.returncode, 0, r.stdout)
        for w in words:
            self.assertIn(w, r.stderr.lower())
        self.assertFalse(self.registry.exists() and any(self.registry.iterdir()), list(self.registry.rglob('*'))
                         if self.registry.exists() else None)


class CaptureTests(Base):
    def test_source_edited_after_layout_is_captured_after_renewed_build_approvals(self):
        b, rev, project = self.approved_brief()
        (project / 'scene.js').write_text('const approvedScene = "revised after layout";\n')
        for gate in ('stills', 'render', 'listening'):
            rev = self.brief.approve(b, rev, gate, 'yes', TEST_OK)['revision']
        handoff = self.brief.handoff(b, rev)
        self.assertTrue(handoff['may_render'], handoff)
        row = next(row for row in handoff['files'] if row['field'] == 'assets.src-scene-js.path')
        self.assertEqual(row['status'], 'ok', row)
        result = self.capture(b, rev, project)
        self.assertEqual(result.returncode, 0, result.stderr)
        copied = self.registry / 'ink-wash-explainer' / 'source' / 'scene.js'
        self.assertEqual(copied.read_bytes(), (project / 'scene.js').read_bytes())

    def test_capture_keeps_editable_source_metadata_and_provenance(self):
        b, rev, project = self.approved_brief()
        r = self.full_capture(b, rev, project)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.registry / 'ink-wash-explainer'
        data = self.record()
        self.assertEqual((data['kind'], data['status'], data['version']), ('reference', 'approved', 1))
        self.assertIsNone(data['brand'])            # never auto-applied to the next job
        self.assertIsNone(data['author'])           # author is optional
        self.assertEqual(data['slots'], [])         # a reference does not pretend to have slots
        self.assertEqual(data['tags'], ['watercolour', 'ink wash'])
        ins = data['instructions']
        self.assertEqual(ins['medium'], 'loose ink wash with paper grain')
        self.assertIn('brush strokes', ins['motion'])
        self.assertIn('four seconds', ins['pacing'])
        self.assertEqual(ins['style_notes'], 'loose ink wash on paper')   # carried from the brief's style
        # The original story and brand are kept apart from the reusable instructions, as context only.
        ctx = data['original_context']
        self.assertEqual(ctx['brand']['name'], 'Acme Co')
        self.assertIn('payroll', ctx['story']['summary'])
        self.assertIn('context only', ctx['note'])
        self.assertNotIn('Acme', json.dumps({k: v for k, v in data.items() if k not in ('original_context',
                                                                                        'provenance')}))
        prov = data['provenance']
        self.assertEqual(prov['brief_revision'], rev)
        self.assertEqual(prov['brief'], str(b))
        self.assertEqual(prov['approvals']['render']['note'], TEST_OK)
        self.assertEqual(prov['approvals']['listening']['state'], 'yes')
        self.assertEqual(prov['style_reference']['catalogue_id'], 'watercolor')
        # Editable sources: the selected entry plus the local source it references, byte for byte.
        ref = data['reference']
        self.assertEqual(ref['entry'], 'source/index.html')
        files = {f['path']: f for f in ref['files']}
        for rel in ('index.html', 'styles.css', 'type.css', 'scene.js', 'assets/logo.png'):
            self.assertIn(f'source/{rel}', files)
            self.assertEqual((d / 'source' / rel).read_bytes(), (project / rel).read_bytes())
            self.assertEqual(files[f'source/{rel}']['sha256'], sha(project / rel))
        self.assertEqual(files['source/assets/logo.png']['role'], 'asset')
        self.assertIn('CC0', files['source/assets/logo.png']['provenance'])
        # Every saved file is named in the brief and was unchanged under the current render approval.
        self.assertEqual(files['source/scene.js']['brief_field'], 'assets.src-scene-js.path')
        self.assertEqual(files['source/assets/logo.png']['brief_field'], 'assets.logo.path')
        # Previews: stills are kept under previews/ (not "approved/"); a video preview is pointed to, not copied.
        previews = {Path(p.get('path') or p.get('external_path')).name: p for p in ref['previews']}
        self.assertEqual(previews['approved-frame.png']['path'], 'previews/approved-frame.png')
        self.assertTrue((d / previews['approved-frame.png']['path']).is_file())
        self.assertEqual(previews['approved-frame.png']['evidence_for'], ['stills'])
        self.assertFalse((d / 'approved').exists())
        self.assertNotIn('path', previews['final.mp4'])
        self.assertEqual(previews['final.mp4']['evidence_for'], ['listening'])   # the mix the listening yes was on
        self.assertTrue(previews['final.mp4']['finished_output'])
        # The explicit final save: the finished file is fingerprinted where it is, with the caller-supplied words.
        final = prov['final_save']
        self.assertEqual(final['approval_note'], TEST_SAVE)
        self.assertEqual(final['finished_output']['path'], str(project / 'renders/final.mp4'))
        self.assertEqual(final['finished_output']['sha256'], sha(project / 'renders/final.mp4'))
        self.assertFalse(final['finished_output']['copied'])
        self.assertIn('listening yes', final['basis'])
        self.assertIn('permission', final['basis'])
        self.assertTrue(final['listening_evidence_matches'])
        self.assertIn('source/scene.js', final['source_coverage']['files'])
        self.assertEqual(prov['approvals']['stills']['state'], 'yes')
        self.assertTrue((d / 'style.md').is_file())
        self.assertIn('context only', (d / 'style.md').read_text())

    def test_unrelated_private_and_large_files_are_never_copied(self):
        b, rev, project = self.approved_brief()
        r = self.full_capture(b, rev, project)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.registry / 'ink-wash-explainer'
        kept = {str(p.relative_to(d)) for p in d.rglob('*') if p.is_file()}
        for name in ('.env', 'config', 'unrelated.md', 'private-pack.json', 'raw.mp4', 'final.mp4', 'gsap.min.js',
                     'brand.css', 'paper.png', 'brief.md', 'music.wav'):
            self.assertFalse([k for k in kept if Path(k).name == name], (name, kept))
        self.assertFalse([k for k in kept if 'node_modules' in k or '.git' in k], kept)

    def test_external_and_uncopied_dependencies_are_stated_as_portability_limits(self):
        b, rev, project = self.approved_brief()
        self.assertEqual(self.full_capture(b, rev, project).returncode, 0)
        ref = self.record()['reference']
        self.assertFalse(ref['portable'])
        self.assertNotIn('self-contained', ref['portability'].lower())
        self.assertEqual([e['ref'] for e in ref['external']], ['https://cdn.example.test/lib.js'])
        why = {n['ref']: n['reason'] for n in ref['not_copied']}
        self.assertIn('vendor', why['vendor/gsap.min.js'])
        self.assertIn('brand', why['brand.css'])
        self.assertIn('video', why['clips/raw.mp4'])
        self.assertIn('--asset', why['assets/paper.png'])
        self.assertIn('prompt', why['prompts/private-pack.json'])

    def test_a_reference_with_every_dependency_kept_is_called_self_contained(self):
        solo = lambda job, patch: (job / 'project' / 'solo.html').write_text(
            '<html><head><link rel="stylesheet" href="type.css"></head></html>')
        b, rev, project = self.approved_brief(sources=SOURCES + ('solo.html',), extra=solo)
        r = self.capture(b, rev, project, '--source', 'solo.html')
        self.assertEqual(r.returncode, 0, r.stderr)
        ref = self.record()['reference']
        self.assertTrue(ref['portable'])
        self.assertIn('self-contained', ref['portability'].lower())
        # The scan is pattern-based, so the claim is about what it can see, not every dynamic dependency.
        self.assertIn('static', ref['portability'].lower())
        self.assertIn('run time', ref['dependency_scan'])
        self.assertEqual(ref['entry'], 'source/solo.html')

    def test_capture_changes_and_deletes_nothing_it_reads(self):
        b, rev, project = self.approved_brief()
        before = tree(self.base / 'work')
        self.assertEqual(self.full_capture(b, rev, project).returncode, 0)
        self.assertEqual(tree(self.base / 'work'), before)

    def test_approved_footage_edit_needs_no_format_slots_or_brand(self):
        b, rev, project = self.approved_brief(route='footage', music=False)
        r = self.capture(b, rev, project, '--title', 'Plain Cut')
        self.assertEqual(r.returncode, 0, r.stderr)
        data = self.record('plain-cut')
        self.assertEqual(data['kind'], 'reference')
        self.assertEqual(data['original_context']['brand']['mode'], 'original')
        self.assertIn('video', {n['ref']: n['reason'] for n in data['reference']['not_copied']}['clips/raw.mp4'])

    def test_capture_works_from_the_brief_command_line_too(self):
        # The same contract when every step is the real brief.py CLI.
        job = self.base / 'work' / 'cli'
        project = self.project(job)
        b = job / 'brief.md'
        py = lambda *a: subprocess.run([sys.executable, '-B', str(BRIEF), *map(str, a)], capture_output=True,
                                       text=True, input=a[-1] if a[-1].startswith('{') else None)
        self.assertEqual(py('init', '--out', b, '--request', 'TEST: a silent loop').returncode, 0)
        patch = json.dumps({'route': 'idea', 'destination': {'aspect': '16:9', 'duration_seconds': 6},
                            'story': {'summary': 'a calm loop'}, 'style': {'name': 'Calm'}, 'brand': {'mode': 'original'},
                            'assets': source_assets(SOURCES),
                            'audio': {'timing_driver': 'visual', 'voice': {'choice': 'none'},
                                      'music': {'choice': 'none'}, 'effects': {'choice': 'none'}}})
        r = subprocess.run([sys.executable, '-B', str(BRIEF), 'update', '--file', str(b), '--expected', '1',
                            '--patch', '-'], input=patch, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for rev, gate in ((2, 'layout'), (3, 'stills'), (4, 'render')):
            r = py('approve', '--file', b, '--expected', rev, '--gate', gate, '--state', 'yes', '--note', TEST_OK)
            self.assertEqual(r.returncode, 0, r.stderr)
        r = self.capture(b, 5, project, '--title', 'Calm Loop')
        self.assertEqual(r.returncode, 0, r.stderr)
        prov = self.record('calm-loop')['provenance']
        self.assertEqual(prov['approvals']['listening'], {'silent': True})
        # A silent video: the basis is stills + render permission + the explicit save words, never a listening yes.
        basis = prov['final_save']['basis']
        self.assertIn('stills yes', basis)
        self.assertIn('permission to render', basis)
        self.assertIn('no listening review', basis)
        self.assertNotIn('listening yes', basis)
        self.assertIsNone(prov['final_save']['listening_evidence_matches'])


class FilmCaptureTests(Base):
    """The normal path: the person's ✋ final film yes in film.json approvals (no brief.py)."""

    def film(self, approvals=None, sources=SOURCES, sha=None):
        """A video folder with film.json naming the build files in inputs; the finished video is made after them."""
        video = self.base / 'work' / 'film-job'
        project = self.project(video)
        inputs = [{'kind': 'source', 'path': 'project/' + rel, 'note': 'TEST synthetic build source'} for rel in sources]
        inputs.append({'kind': 'image', 'path': 'project/assets/logo.png', 'note': 'TEST logo drawn for this fixture; CC0'})
        if sha:
            inputs[0]['sha256'] = sha
        film = {'kit_to_clip_film': 1, 'title': 'TEST payroll explainer', 'about': 'Quarterly payroll in three beats',
                'brand': {'name': 'Acme', 'skill': 'acme-brand'}, 'inputs': inputs,
                'parts': [{'id': 'p1', 'name': 'Hook', 'from': 0, 'to': 4}],
                'approvals': approvals if approvals is not None else {
                    'storyboard': {'yes': TEST_OK, 'at': '2026-10-21'},
                    'final': {'yes': TEST_OK, 'at': '2026-10-21'}}}
        (video / 'film.json').write_text(json.dumps(film))
        old = (project / 'renders/final.mp4').stat().st_mtime - 60
        for p in project.rglob('*'):
            if p.is_file() and p.name != 'final.mp4':
                os.utime(p, (old, old))
        return video / 'film.json', project

    def capture_film(self, film, project, *extra, title='Ink Wash Explainer', note=TEST_SAVE):
        return self.run_styles('capture', '--film', film, '--project', project, '--title', title,
                               '--finished-output', project / 'renders/final.mp4', '--approval-note', note, *extra)

    def test_the_final_film_yes_saves_the_named_build(self):
        film, project = self.film()
        r = self.capture_film(film, project, '--asset', 'assets/logo.png')
        self.assertEqual(r.returncode, 0, r.stderr)
        data = self.record()
        self.assertEqual((data['kind'], data['status']), ('reference', 'approved'))
        self.assertIsNone(data['brand'])                                   # never auto-applied to the next job
        prov = data['provenance']
        self.assertEqual(prov['film'], str(film))
        self.assertNotIn('brief', prov)
        self.assertEqual(prov['approvals']['final'], {'state': 'yes', 'note': TEST_OK, 'at': '2026-10-21'})
        basis = prov['final_save']['basis']
        self.assertIn('storyboard yes', basis)
        self.assertIn('final film yes', basis)
        self.assertNotIn('render', basis)
        files = {row['path']: row for row in data['reference']['files']}
        self.assertEqual(files['source/scene.js']['film_field'], 'inputs[3].path')
        self.assertEqual(files['source/assets/logo.png']['provenance'], 'TEST logo drawn for this fixture; CC0')
        self.assertEqual(data['original_context']['brand']['id'], 'acme-brand')
        self.assertIn('Film ', (self.registry / 'ink-wash-explainer' / 'style.md').read_text())

    def test_no_final_film_yes_is_refused(self):
        for approvals in ({}, {'storyboard': {'yes': TEST_OK}}, {'final': {'yes': '  '}}, {'final': 'yes'}):
            with self.subTest(approvals=approvals):
                film, project = self.film(approvals=approvals)
                self.assert_refused(self.capture_film(film, project), 'final film yes')

    def test_a_yes_recorded_by_the_studio_saves(self):
        studio_yes = {'asked': 'final film v1', 'yes': TEST_OK, 'at': '2026-10-21T10:00:00Z', 'via': 'studio', 'event': 31}
        film, project = self.film(approvals={'storyboard': {'yes': TEST_OK, 'at': '2026-10-21', 'via': 'chat'},
                                             'final': studio_yes})
        r = self.capture_film(film, project)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.record()['provenance']['approvals']['final'],
                         {'state': 'yes', 'note': TEST_OK, 'at': '2026-10-21T10:00:00Z'})

    def test_an_ask_without_a_yes_is_refused(self):
        film, project = self.film(approvals={'final': {'asked': 'final film v2', 'since': 40}})
        self.assert_refused(self.capture_film(film, project), 'final film yes')

    def test_a_build_file_changed_after_the_finished_video_is_refused(self):
        film, project = self.film()
        (project / 'scene.js').write_text('// rewritten after the final film')
        later = (project / 'renders/final.mp4').stat().st_mtime + 60
        os.utime(project / 'scene.js', (later, later))
        self.assert_refused(self.capture_film(film, project), 'project/scene.js', 'changed after the finished video')

    def test_a_recorded_fingerprint_must_still_match(self):
        film, project = self.film(sha='0' * 64)
        self.assert_refused(self.capture_film(film, project), 'project/index.html', 'fingerprint')

    def test_a_file_not_named_in_film_json_is_refused(self):
        film, project = self.film(sources=('styles.css', 'type.css', 'scene.js'))
        self.assert_refused(self.capture_film(film, project), 'index.html', 'not named in film.json')

    def test_film_or_brief_exactly_one(self):
        film, project = self.film()
        b, rev, _ = self.approved_brief()
        both = self.run_styles('capture', '--film', film, '--brief', b, '--expected', rev, '--project', project,
                               '--title', 'Both', '--finished-output', project / 'renders/final.mp4',
                               '--approval-note', TEST_SAVE)
        self.assert_refused(both, '--film')
        neither = self.run_styles('capture', '--project', project, '--title', 'Neither',
                                  '--finished-output', project / 'renders/final.mp4', '--approval-note', TEST_SAVE)
        self.assert_refused(neither, '--film')
        no_rev = self.run_styles('capture', '--brief', b, '--project', project, '--title', 'No Rev',
                                 '--finished-output', project / 'renders/final.mp4', '--approval-note', TEST_SAVE)
        self.assert_refused(no_rev, '--expected')

class ApprovalTests(Base):
    def test_render_without_listening_is_not_final_even_with_passing_numbers(self):
        # A loudness report is a measurement, not the person's listening yes.
        b, rev, project = self.approved_brief(listening=False)
        (project / 'finish-report.json').write_text(json.dumps({'loudness_lufs': -14.0, 'true_peak': -1.2,
                                                                 'checks': 'all passed'}))
        self.assert_refused(self.capture(b, rev, project), 'listening')

    def test_no_render_approval_is_refused(self):
        job = self.base / 'work' / 'early'
        project = self.project(job)
        b = job / 'brief.md'
        self.brief.init_brief(b, 'TEST: unfinished')
        rev = self.brief.update(b, 1, {'route': 'idea', 'style': {'name': 'x'}})['revision']
        rev = self.brief.approve(b, rev, 'layout', 'yes', TEST_OK)['revision']
        self.assert_refused(self.capture(b, rev, project), 'render')

    def test_a_changed_input_after_approval_is_refused(self):
        b, rev, project = self.approved_brief()
        (b.parent / 'music.wav').write_bytes(b'RIFF different music')
        self.assert_refused(self.capture(b, rev, project), 'changed')

    def test_a_changed_listening_evidence_is_refused(self):
        b, rev, project = self.approved_brief()
        (project / 'renders/final.mp4').write_bytes(b'another render')
        self.assert_refused(self.capture(b, rev, project), 'evidence')

    def test_a_stale_revision_is_refused(self):
        b, rev, project = self.approved_brief()
        self.assert_refused(self.capture(b, rev - 1, project), 'revision')

    def test_a_later_change_to_the_brief_reopens_and_refuses(self):
        b, rev, project = self.approved_brief()
        rev = self.brief.update(b, rev, {'story': {'summary': 'a different story'}})['revision']
        self.assert_refused(self.capture(b, rev, project), 'render')

    def test_a_hand_edited_brief_is_refused(self):
        b, rev, project = self.approved_brief()
        b.write_text(b.read_text().replace('"revision": %d' % rev, '"revision": 99'))
        self.assert_refused(self.capture(b, rev, project), 'brief')


class SafetyTests(Base):
    def test_an_existing_slug_is_never_overwritten(self):
        b, rev, project = self.approved_brief()
        self.assertEqual(self.full_capture(b, rev, project).returncode, 0)
        before = tree(self.registry)
        r = self.full_capture(b, rev, project)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('already', r.stderr)
        self.assertEqual(tree(self.registry), before)
        # A legacy template folder of the same name is not touched either.
        legacy = self.registry / 'court-cam'
        legacy.mkdir()
        (legacy / 'style.json').write_text(json.dumps({'slug': 'court-cam', 'title': 'Court Cam', 'status': 'approved'}))
        before = tree(self.registry)
        self.assertNotEqual(self.capture(b, rev, project, '--slug', 'court-cam').returncode, 0)
        self.assertEqual(tree(self.registry), before)

    def test_a_symlink_at_the_new_slug_is_refused(self):
        b, rev, project = self.approved_brief()
        outside = self.base / 'outside'
        outside.mkdir()
        self.registry.mkdir(parents=True)
        os.symlink(outside, self.registry / 'linked')
        r = self.capture(b, rev, project, '--slug', 'linked')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_unsafe_slugs_and_paths_are_refused_before_writing(self):
        b, rev, project = self.approved_brief()
        outside = self.base / 'outside.html'
        outside.write_text('<html></html>')
        os.symlink(outside, project / 'escape.html')
        os.symlink(project / '.env', project / 'innocent.css')       # an ordinary name hiding a credential file
        cases = [('--source', 'innocent.css'), ('--asset', 'prompts/private-pack.json'),('--slug', '../escape'), ('--slug', 'a/b'), ('--slug', '.hidden'), ('--slug', 'Upper Case'),
                 ('--source', '../outside.html'), ('--source', str(outside)), ('--source', 'escape.html'),
                 ('--source', '.env'), ('--source', 'clips/raw.mp4'), ('--source', 'missing.html'),
                 ('--asset', '../outside.html'), ('--asset', 'clips/raw.mp4'), ('--asset', '.git/config'),
                 ('--asset', 'node_modules/pkg/index.js')]
        for flag, value in cases:
            with self.subTest(flag=flag, value=value):
                r = self.capture(b, rev, project, flag, value)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertFalse(self.registry.exists() and any(self.registry.iterdir()))
        self.assertFalse((self.base / 'escape').exists())

    def test_nothing_is_saved_inside_the_skill_package(self):
        # The skill root is swapped for a synthetic one so a failure here can never write into the real package.
        b, rev, project = self.approved_brief()
        styles = load('kit_styles_skill_root_test', STYLES)
        fake = self.base / 'fake-skill'
        fake.mkdir()
        styles.ROOT = fake
        linked = self.base / 'linked-root'
        os.symlink(fake, linked)
        for root in (fake, fake / 'deep', linked):
            with self.subTest(root=root):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()), \
                        self.assertRaises(SystemExit) as ctx:
                    styles.main(['--root', str(root), 'capture', '--brief', str(b), '--expected', str(rev),
                                 '--project', str(project), '--title', 'Inside', '--approval-note', TEST_SAVE,
                                 '--finished-output', str(project / 'renders/final.mp4')])
                self.assertNotIn(ctx.exception.code, (0, None))
                self.assertIn('package', str(ctx.exception.code) + err.getvalue())
        self.assertEqual(list(fake.iterdir()), [])


class ReuseTests(Base):
    def captured(self):
        b, rev, project = self.approved_brief()
        r = self.full_capture(b, rev, project)
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.registry / 'ink-wash-explainer'

    def test_new_on_a_reference_stops_with_fresh_build_guidance(self):
        self.captured()
        out = self.base / 'next-job'
        r = self.run_styles('new', '--style', 'ink-wash-explainer', '--out', out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('reference', r.stderr)
        self.assertIn('handoff', r.stderr)
        self.assertIn('fresh', r.stderr)
        self.assertFalse(out.exists())              # nothing built, no brand bridge run

    def test_handoff_is_read_only_and_never_carries_the_old_brand(self):
        d = self.captured()
        before = tree(self.lib)
        r = self.run_styles('handoff', '--style', 'ink-wash-explainer')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(tree(self.lib), before)
        h = json.loads(r.stdout)
        self.assertEqual(h['kind'], 'reference')
        self.assertTrue(h['ready_to_reuse'])
        self.assertIsNone(h['brand'])
        self.assertIn('fresh', h['brand_rule'])
        self.assertEqual(h['original_context']['brand']['name'], 'Acme Co')
        self.assertEqual(Path(h['entry']), d / 'source' / 'index.html')
        self.assertEqual(h['changed_files'], [])
        self.assertIn('loose ink wash', h['instructions']['medium'])
        self.assertTrue(h['next_steps'])

    def test_handoff_reports_saved_files_that_changed_since_capture(self):
        d = self.captured()
        (d / 'source' / 'scene.js').write_text('// edited later')
        h = json.loads(self.run_styles('handoff', '--style', 'ink-wash-explainer').stdout)
        self.assertEqual(h['changed_files'], ['source/scene.js'])

    def test_handoff_refuses_a_style_folder_linking_outside_the_registry(self):
        d = self.captured()
        moved = self.base / 'moved'
        os.rename(d, moved)
        os.symlink(moved, d)
        r = self.run_styles('handoff', '--style', 'ink-wash-explainer')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('outside', r.stderr)
        for bad in ('../moved', 'a/b'):
            self.assertNotEqual(self.run_styles('handoff', '--style', bad).returncode, 0)

    def test_catalogue_recommends_it_for_another_story_without_its_brand(self):
        self.captured()
        found = self.cat.search('watercolour brush motion for a recipe explainer', styles_root=self.registry, limit=20)
        mine = next(r for r in found['shortlist'] if r['ref'] == 'personal:ink-wash-explainer')
        self.assertEqual(mine['kind'], 'reference')
        self.assertTrue(mine['ready_to_reuse'])
        self.assertIsNone(mine['brand'])
        self.assertEqual(mine['original_brand'], 'Acme Co')
        reasons = ' '.join(mine['reasons'])
        self.assertIn('tag "watercolour"', reasons)
        self.assertIn('motion', reasons)
        shown = self.cat.show('personal:ink-wash-explainer', styles_root=self.registry)
        self.assertEqual(shown['tags'], ['watercolour', 'ink wash'])
        self.assertTrue(shown['reference_source']['entry'].endswith('source/index.html'))
        self.assertEqual(shown['record']['provenance']['style_reference']['catalogue_id'], 'watercolor')
        # The old story and brand are context, not search bait for unrelated work.
        self.assertNotIn('personal:ink-wash-explainer',
                         self.refs(self.cat.search('payroll', styles_root=self.registry, limit=50)))

    def refs(self, result):
        return [r['ref'] for r in result['shortlist']] + [r['ref'] for r in result['drafts']]

    def test_list_json_keeps_old_keys_and_adds_kind_and_tags(self):
        self.captured()
        self.assertEqual(self.run_styles('init', '--title', 'Court Cam', '--author', 'Tester').returncode, 0)
        (self.registry / 'broken').mkdir()
        (self.registry / 'broken' / 'style.json').write_text('{not json')
        r = self.run_styles('list', '--json')
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = {row['slug']: row for row in json.loads(r.stdout)}
        old = {'slug', 'title', 'status', 'author', 'brand', 'made_for', 'platforms', 'length_s', 'version', 'path'}
        for row in rows.values():
            self.assertTrue(old <= set(row), row)
        self.assertEqual(rows['court-cam']['kind'], 'template')
        self.assertEqual(rows['ink-wash-explainer']['kind'], 'reference')
        self.assertEqual(rows['ink-wash-explainer']['tags'], ['watercolour', 'ink wash'])
        self.assertIn('broken', r.stderr)           # reported, without hiding the good ones
        text = self.run_styles('list')
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn('ink-wash-explainer', text.stdout)
        self.assertIn('reference', text.stdout)


class LegacyTemplateTests(Base):
    def test_legacy_template_save_and_new_still_work(self):
        src = self.base / 'draft'
        src.mkdir()
        (src / 'index.html').write_text('<html>legacy</html>')
        (src / 'clip.mp4').write_bytes(b'video')
        self.assertEqual(self.run_styles('init', '--title', 'Court Cam', '--author', 'Tester').returncode, 0)
        r = self.run_styles('save', '--style', 'court-cam', '--project', src, '--approve')
        self.assertEqual(r.returncode, 0, r.stderr)
        data = self.record('court-cam')
        self.assertNotIn('kind', data)              # no forced conversion of the legacy record
        out = self.base / 'from-template'
        r = self.run_styles('new', '--style', 'court-cam', '--out', out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((out / 'index.html').read_text(), '<html>legacy</html>')
        self.assertFalse((out / 'clip.mp4').exists())

    def test_save_refuses_to_replace_a_reference(self):
        b, rev, project = self.approved_brief()
        self.assertEqual(self.full_capture(b, rev, project).returncode, 0)
        before = tree(self.registry)
        r = self.run_styles('save', '--style', 'ink-wash-explainer', '--project', project)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('reference', r.stderr)
        self.assertEqual(tree(self.registry), before)


class CoverageTests(Base):
    """Only bytes the current render approval fingerprinted are saved as approved."""

    def test_a_named_source_rewritten_after_the_render_yes_is_refused(self):
        b, rev, project = self.approved_brief()
        (project / 'scene.js').write_text('// rewritten after the render yes')
        self.assert_refused(self.full_capture(b, rev, project), 'render', 'changed')

    def test_an_unrelated_project_is_refused(self):
        b, rev, project = self.approved_brief()
        other = self.project(self.base / 'work' / 'unrelated-draft')
        (other / 'index.html').write_text('<html>never shown to anyone</html>')
        r = self.run_styles('capture', '--brief', b, '--expected', rev, '--project', other, '--title', 'Wrong Job',
                            '--approval-note', TEST_SAVE, '--finished-output', project / 'renders/final.mp4')
        self.assert_refused(r, 'not named in the brief')

    def test_the_default_index_must_be_named_in_the_brief(self):
        b, rev, project = self.approved_brief(sources=('styles.css', 'type.css', 'scene.js'))
        self.assert_refused(self.capture(b, rev, project), 'index.html', 'not named in the brief')

    def test_explicit_sources_and_assets_outside_the_approval_are_refused(self):
        b, rev, project = self.approved_brief()
        (project / 'solo.html').write_text('<html></html>')
        for flag, value in (('--source', 'solo.html'), ('--asset', 'assets/paper.png')):
            with self.subTest(flag=flag):
                self.assert_refused(self.capture(b, rev, project, flag, value), value, 'not named in the brief')

    def test_sources_named_after_layout_and_before_stills_are_covered_without_a_second_layout_yes(self):
        job = self.base / 'work' / 'late-sources'
        project = self.project(job)
        b = job / 'brief.md'
        self.brief.init_brief(b, 'TEST: a silent loop')
        rev = self.brief.update(b, 1, {'route': 'idea', 'destination': {'aspect': '16:9', 'duration_seconds': 6},
                                       'story': {'summary': 'a calm loop'}, 'style': {'name': 'Calm'},
                                       'brand': {'mode': 'original'},
                                       'audio': {'timing_driver': 'visual', 'voice': {'choice': 'none'},
                                                 'music': {'choice': 'none'}, 'effects': {'choice': 'none'}}})['revision']
        layout_rev = rev = self.brief.approve(b, rev, 'layout', 'yes', TEST_OK)['revision']
        rev = self.brief.update(b, rev, {'assets': source_assets(SOURCES)})['revision']
        for gate in ('stills', 'render'):
            rev = self.brief.approve(b, rev, gate, 'yes', TEST_OK)['revision']
        r = self.capture(b, rev, project, '--title', 'Late Sources')
        self.assertEqual(r.returncode, 0, r.stderr)
        prov = self.record('late-sources')['provenance']
        self.assertEqual(prov['approvals']['layout']['input_revision'], layout_rev - 1)
        self.assertIn('source/scene.js', prov['final_save']['source_coverage']['files'])

    def test_an_unnamed_scanned_dependency_is_left_out_with_the_reason(self):
        b, rev, project = self.approved_brief(sources=('index.html', 'styles.css', 'type.css'))
        (project / 'scene.js').write_text('// rewritten after the render yes, never approved')
        r = self.capture(b, rev, project)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.registry / 'ink-wash-explainer'
        self.assertFalse((d / 'source' / 'scene.js').exists())
        ref = self.record()['reference']
        why = {n['ref']: n['reason'] for n in ref['not_copied']}
        self.assertIn('not named in the brief', why['scene.js'])
        self.assertIn('render approval', why['scene.js'])
        self.assertFalse(ref['portable'])


class PrivateLibraryTests(Base):
    def library_brief(self):
        def lib(job, patch):
            folder = job / 'project' / 'library' / 'deep'
            folder.mkdir(parents=True)
            (folder / 'watercolor-code.js').write_text('import "../../leak.js"; // synthetic private library code')
            (job / 'project' / 'leak.js').write_text('// only reachable through the private library')
            (job / 'project' / 'index.html').write_text(
                INDEX_HTML.replace('<script src="scene.js">', '<script src="library/deep/watercolor-code.js">'
                                   '</script><script src="scene.js">'))
            patch['style']['reference']['source_root'] = 'project/library'
            patch['assets'].update(source_assets(('library/deep/watercolor-code.js', 'leak.js')))
        return self.approved_brief(extra=lib)

    def test_files_under_the_brief_source_root_are_never_copied_or_scanned(self):
        b, rev, project = self.library_brief()
        r = self.full_capture(b, rev, project)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.registry / 'ink-wash-explainer'
        kept = {p.relative_to(d).as_posix() for p in d.rglob('*') if p.is_file()}
        self.assertFalse([k for k in kept if 'library' in k or 'leak' in k], kept)
        why = {n['ref']: n['reason'] for n in self.record()['reference']['not_copied']}
        self.assertIn('private library', why['library/deep/watercolor-code.js'])
        self.assertNotIn('leak.js', why)            # the private file's own references were never read

    def test_selecting_a_file_under_the_source_root_is_refused(self):
        b, rev, project = self.library_brief()
        r = self.capture(b, rev, project, '--source', 'library/deep/watercolor-code.js')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('private library', r.stderr)
        self.assertFalse(self.registry.exists() and any(self.registry.iterdir()))

    def test_a_renamed_prompt_package_is_still_refused(self):
        def renamed(job, patch):
            (job / 'project' / 'look.json').write_text(json.dumps({'info': {'prompt': 'synthetic private prompt'}}))
            patch['assets'].update(source_assets(('look.json',)))
        b, rev, project = self.approved_brief(extra=renamed)
        r = self.capture(b, rev, project, '--source', 'look.json')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('prompt', r.stderr)


class FinalSaveTests(Base):
    def test_render_permission_alone_is_not_a_finished_video_approval(self):
        b, rev, project = self.approved_brief(music=False)
        for final, note in ((None, TEST_SAVE), ('renders/final.mp4', None)):
            with self.subTest(final=final, note=note):
                r = self.capture(b, rev, project, final=final, note=note)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn('--finished-output' if final is None else '--approval-note', r.stderr)
        self.assertFalse(self.registry.exists() and any(self.registry.iterdir()))

    def test_empty_words_missing_or_non_video_output_are_refused(self):
        b, rev, project = self.approved_brief()
        (project / 'approved-final.txt').write_text('a file whose name says approved')
        self.assert_refused(self.capture(b, rev, project, note='   '), 'approval-note')
        self.assert_refused(self.capture(b, rev, project, final='renders/missing.mp4'), 'finished-output')
        self.assert_refused(self.capture(b, rev, project, final='approved-final.txt'), 'finished-output')

    def test_the_finished_video_is_fingerprinted_not_copied(self):
        b, rev, project = self.approved_brief()
        (project / 'renders/final.mp4').write_bytes(b'synthetic render')
        self.assertEqual(self.capture(b, rev, project).returncode, 0)
        d = self.registry / 'ink-wash-explainer'
        self.assertFalse([p for p in d.rglob('*.mp4')])
        self.assertEqual(self.record()['status'], 'approved')

    def test_listening_on_a_different_file_is_stated_not_hidden(self):
        b, rev, project = self.approved_brief()
        (project / 'renders/final-v2.mp4').write_bytes(b'a later render')
        r = self.capture(b, rev, project, final='renders/final-v2.mp4')
        self.assertEqual(r.returncode, 0, r.stderr)
        final = self.record()['provenance']['final_save']
        self.assertFalse(final['listening_evidence_matches'])
        self.assertIn('different file', final['basis'])


class HandoffStateTests(Base):
    def captured(self):
        b, rev, project = self.approved_brief()
        r = self.full_capture(b, rev, project)
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.registry / 'ink-wash-explainer', project

    def handoff(self):
        r = self.run_styles('handoff', '--style', 'ink-wash-explainer')
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_changed_or_missing_files_are_not_ready_to_reuse(self):
        d, _ = self.captured()
        self.assertTrue(self.handoff()['ready_to_reuse'])
        (d / 'source' / 'scene.js').write_text('// edited later')
        h = self.handoff()
        self.assertEqual(h['changed_files'], ['source/scene.js'])
        self.assertFalse(h['ready_to_reuse'])
        (d / 'source' / 'type.css').unlink()
        self.assertIn('source/type.css', self.handoff()['missing_files'])

    def test_a_changed_or_missing_finished_output_is_flagged(self):
        d, project = self.captured()
        (project / 'renders/final.mp4').write_bytes(b'a re-render after the save')
        h = self.handoff()
        self.assertEqual(h['finished_output']['status'], 'changed')
        self.assertIn('finished output', ' '.join(h['provenance_warnings']))
        self.assertTrue(h['ready_to_reuse'])
        (project / 'renders/final.mp4').unlink()
        h = self.handoff()
        self.assertEqual(h['finished_output']['status'], 'missing')
        self.assertIn('finished output', ' '.join(h['provenance_warnings']))

    def test_a_leftover_capture_work_folder_is_never_listed(self):
        self.captured()
        crash = self.registry / '.capture-ink-wash-explainer-crashed'
        crash.mkdir()
        (crash / 'style.json').write_text(json.dumps({'slug': 'ghost', 'title': 'Ghost', 'status': 'approved',
                                                      'kind': 'reference'}))
        r = self.run_styles('list', '--json')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([row['slug'] for row in json.loads(r.stdout)], ['ink-wash-explainer'])
        self.assertNotIn('ghost', self.run_styles('list').stdout)
        rows, _, _ = self.cat.read_personal(self.registry)
        self.assertEqual([row['id'] for row in rows], ['ink-wash-explainer'])
        self.assertNotEqual(self.run_styles('handoff', '--style', crash.name).returncode, 0)

    def test_a_still_that_was_not_reviewed_is_not_called_approved(self):
        b, rev, project = self.approved_brief()
        (project / 'snapshots/draft-frame.png').write_bytes(b'\x89PNG never reviewed')
        r = self.capture(b, rev, project, '--preview', project / 'snapshots/draft-frame.png')
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.record()['reference']['previews'][0]
        self.assertEqual((row['path'], row['evidence_for'], row['approval_evidence']),
                         ('previews/draft-frame.png', [], False))
        md = (self.registry / 'ink-wash-explainer' / 'style.md').read_text()
        line = next(l for l in md.splitlines() if 'draft-frame' in l)
        self.assertNotIn('approv', line)
        self.assertIn('not recorded as', line)


if __name__ == '__main__':
    unittest.main()
