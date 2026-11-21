"""Behavior checks for the local gallery. Run with unittest discovery."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO if (REPO / 'SKILL.md').exists() else REPO / 'addons' / 'kit-to-clip'


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kit-gallery-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def gallery(self):
        script = SKILL / 'scripts' / 'gallery.py'
        self.assertTrue(script.is_file(), 'The local gallery generator is not implemented yet')
        spec = importlib.util.spec_from_file_location('kit_gallery_test', script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def manifest(self, rows):
        p = self.base / 'samples.json'
        p.write_text(json.dumps({'schema': 1, 'samples': rows}))
        return p

    def rows(self):
        return [{'id': 'look:glass', 'category': 'looks', 'name': 'Frosted glass',
                 'status': 'trial', 'about': 'Translucent panes.', 'style': 'glass'}]

    def test_output_keeps_existing_files(self):
        # An overwrite bug would destroy a person's edited gallery.
        g = self.gallery()
        out = self.base / 'gallery'
        out.mkdir()
        (out / 'index.html').write_text('my edits')
        with self.assertRaises(FileExistsError):
            g.build(out, self.rows(), brand=None, samples=None)
        self.assertEqual((out / 'index.html').read_text(), 'my edits')

    def test_neutral_samples_are_labelled_even_for_a_chosen_brand(self):
        # A wrong brand filter would hide neutral examples or mislabel them as branded.
        g = self.gallery()
        (self.base / 'poster.png').write_bytes(b'poster fixture')
        manifest = self.manifest([{'id': 'look:glass', 'kind': 'neutral-demo', 'poster': 'poster.png'}])
        data = g.build(self.base / 'gallery', self.rows(), brand='acme', samples=manifest)
        preview = data['items'][0]['preview']
        self.assertEqual(preview['label'], 'Neutral demo')
        self.assertTrue((self.base / 'gallery' / preview['poster']).is_file())
        self.assertEqual(data['brand'], 'acme')

    def test_wrong_brand_video_is_not_copied(self):
        # Removing the brand match would expose the wrong branded sample.
        g = self.gallery()
        (self.base / 'sample.mp4').write_bytes(b'video fixture')
        manifest = self.manifest([{'id': 'look:glass', 'kind': 'brand', 'brand': 'other', 'video': 'sample.mp4'}])
        out = self.base / 'gallery'
        data = g.build(out, self.rows(), brand='acme', samples=manifest)
        self.assertIsNone(data['items'][0]['preview'])
        self.assertEqual(list((out / 'assets').iterdir()), [])

    def test_paths_cannot_escape_the_sample_folder(self):
        # A path-validation bug would copy arbitrary local files into the gallery.
        g = self.gallery()
        nested = self.base / 'input'
        nested.mkdir()
        (self.base / 'private.png').write_bytes(b'private')
        p = nested / 'samples.json'
        for media in ['../private.png', str(self.base / 'private.png'), 'https://example.com/private.png']:
            with self.subTest(media=media):
                p.write_text(json.dumps({'schema': 1, 'samples': [
                    {'id': 'look:glass', 'kind': 'neutral-demo', 'poster': media}]}))
                with self.assertRaises(ValueError):
                    g.build(self.base / 'gallery', self.rows(), brand=None, samples=p)
                self.assertFalse((self.base / 'gallery').exists())

    def test_symlinks_cannot_export_media_outside_the_sample_folder(self):
        g = self.gallery()
        nested = self.base / 'input'
        nested.mkdir()
        (self.base / 'private.png').write_bytes(b'private')
        (nested / 'poster.png').symlink_to(self.base / 'private.png')
        p = nested / 'samples.json'
        p.write_text(json.dumps({'schema': 1, 'samples': [
            {'id': 'look:glass', 'kind': 'neutral-demo', 'poster': 'poster.png'}]}))
        with self.assertRaises(ValueError):
            g.build(self.base / 'gallery', self.rows(), brand=None, samples=p)

    def test_unknown_sample_ids_fail_before_output_is_written(self):
        g = self.gallery()
        p = self.manifest([{'id': 'look:typo', 'kind': 'neutral-demo', 'poster': 'absent.png'}])
        with self.assertRaises(ValueError):
            g.build(self.base / 'gallery', self.rows(), brand=None, samples=p)
        self.assertFalse((self.base / 'gallery').exists())

    def test_untrusted_names_remain_data_not_html(self):
        # Interpolating names into markup or an executable script makes this unsafe.
        g = self.gallery()
        rows = self.rows()
        rows[0]['name'] = '</script><img src=x onerror=alert(1)>'
        out = self.base / 'gallery'
        g.build(out, rows, brand=None, samples=None)
        html = (out / 'index.html').read_text()
        js = (out / 'data.js').read_text()
        self.assertNotIn('<img src=x', html)
        self.assertNotIn('</script>', js)
        payload = json.loads(js.removeprefix('window.KIT_GALLERY = ').strip().removesuffix(';'))
        self.assertEqual(payload['items'][0]['name'], rows[0]['name'])

    def test_registry_includes_new_looks_and_draft_saved_styles(self):
        # Missing integration would leave the new looks or saved styles undiscoverable.
        g = self.gallery()
        project = self.base / 'project'
        project.mkdir()
        styles = self.base / 'styles'
        folder = styles / 'my-style'
        folder.mkdir(parents=True)
        (folder / 'style.json').write_text(json.dumps({
            'slug': 'my-style', 'title': 'My draft', 'status': 'draft', 'brand': None}))
        items = g.catalog(project, brand=None, styles_root=styles)
        ids = {x['id'] for x in items}
        for key in ['look:glass', 'look:pixel', 'look:chalkboard', 'look:flat-vector', 'style:neutral:my-style']:
            self.assertIn(key, ids)
        saved = next(x for x in items if x['id'] == 'style:neutral:my-style')
        self.assertEqual(saved['status'], 'draft')
        self.assertTrue(any(x['category'] == 'formats' for x in items))

    def test_library_discovery_has_all_86_without_a_private_collection(self):
        g = self.gallery()
        project = self.base / 'project'
        project.mkdir()
        styles = self.base / 'empty-styles'
        styles.mkdir()
        items = g.catalog(project, styles_root=styles)
        library = [x for x in items if x['category'] == 'library']
        self.assertEqual(len(library), 86)
        self.assertEqual(len({x['id'] for x in library}), 86)
        self.assertTrue(all(x['origin'] == 'atlas' for x in library))
        self.assertTrue(all(x.get('source_required') for x in library))
        self.assertTrue(all(x['original_previews'].get('explainer_clip') for x in library))
        data = g.build(self.base / 'gallery', items)
        self.assertFalse(any(x.get('preview') for x in data['items']))
        self.assertFalse(any((self.base / 'gallery' / 'assets').iterdir()))

    def test_saved_style_brand_is_context_rather_than_a_discovery_filter(self):
        g = self.gallery()
        styles = self.base / 'styles'
        folder = styles / 'paper'
        folder.mkdir(parents=True)
        (folder / 'style.json').write_text(json.dumps({
            'slug': 'paper', 'title': 'Paper', 'status': 'approved', 'brand': 'previous-brand',
            'kind': 'reference', 'tags': ['paper', 'gentle'],
            'instructions': {'medium':'Layered paper', 'motion':'Gentle drift'}}))
        items = g.catalog(self.base, brand='new-brand', styles_root=styles)
        saved = next(x for x in items if x['id'] == 'style:previous-brand:paper')
        self.assertEqual(saved['brand'], 'previous-brand')
        self.assertEqual(saved['reuse_kind'], 'reference')
        self.assertIn('paper', saved['tags'])
        self.assertIn('Layered paper', saved['about'])

    def test_failed_default_saved_registry_keeps_the_library_available(self):
        g = self.gallery()
        real_run = subprocess.run
        def run(args, **kwargs):
            if str(SKILL/'scripts/styles.py') in args:
                return subprocess.CompletedProcess(args,2,stdout='',stderr='Saved registry unavailable')
            return real_run(args,**kwargs)
        with mock.patch.object(g.subprocess,'run',side_effect=run):
            items=g.catalog(self.base)
        self.assertEqual(sum(x['category']=='library' for x in items),86)
        self.assertTrue(any(x['category']=='saved' and x.get('broken') for x in items))

    def test_corrupt_personal_record_does_not_hide_the_library(self):
        g = self.gallery()
        styles = self.base / 'styles'
        broken = styles / 'broken'
        broken.mkdir(parents=True)
        (broken / 'style.json').write_text('{not json')
        items = g.catalog(self.base, styles_root=styles)
        self.assertEqual(sum(x['category'] == 'library' for x in items), 86)
        problem = next(x for x in items if x.get('broken') and x['category'] == 'saved')
        self.assertIn('JSON', problem['about'])

    def test_missing_personal_collection_is_a_clean_cli_error(self):
        result = subprocess.run([sys.executable,str(SKILL/'scripts/gallery.py'),'--list',
            '--styles-root',str(self.base/'missing')],text=True,capture_output=True)
        self.assertEqual(result.returncode,2)
        self.assertIn('not a folder',result.stderr)
        self.assertNotIn('Traceback',result.stderr)

    def test_reviewed_personal_still_is_reused_without_loading_its_code(self):
        g=self.gallery()
        folder=self.base/'styles'/'paper'
        (folder/'previews').mkdir(parents=True)
        still=folder/'previews'/'approved.png'
        still.write_bytes(b'synthetic reviewed still')
        record={'slug':'paper','title':'Paper','status':'approved','kind':'reference',
            'original_context':{'brand':{'id':'previous-brand'}},
            'reference':{'previews':[{'path':'previews/approved.png','approval_evidence':True,
                'sha256':hashlib.sha256(still.read_bytes()).hexdigest()}]}}
        (folder/'style.json').write_text(json.dumps(record))
        # An unreadable/broken source is deliberately not opened during discovery.
        (folder/'source.js').write_text('not executable source')
        items=g.catalog(self.base,styles_root=self.base/'styles')
        data=g.build(self.base/'gallery',items)
        saved=next(row for row in data['items'] if row['category']=='saved')
        self.assertEqual(saved['preview']['label'],'Saved reference preview')
        self.assertEqual((self.base/'gallery'/saved['preview']['poster']).read_bytes(),still.read_bytes())
        self.assertEqual(saved['original_brand'],'previous-brand')
        self.assertFalse(any(key.startswith('_') for key in saved))
        still.write_bytes(b'changed since review')
        changed=g.build(self.base/'gallery-changed',items)
        stale=next(row for row in changed['items'] if row['category']=='saved')
        self.assertIsNone(stale['preview'])
        self.assertIn('changed',stale['preview_warning'])


if __name__ == '__main__':
    unittest.main()
