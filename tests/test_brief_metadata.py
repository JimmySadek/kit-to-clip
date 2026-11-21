"""Noncreative provenance must not discard the person's approved visual decisions."""
import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO if (REPO / 'SKILL.md').exists() else REPO / 'addons/kit-to-clip'
CLI = SKILL / 'scripts/brief.py'


class MetadataApprovalTests(unittest.TestCase):
    def test_provenance_does_not_select_a_style(self):
        spec = importlib.util.spec_from_file_location('brief_selection_test',CLI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for ref in ({'origin':'Atlas','permitted_use':'private'}, {'source_root':'private-source'}, {}):
            self.assertFalse(module._style_set({'style':{'reference':ref}}))
        self.assertTrue(module._style_set({'style':{'reference':{'catalogue_id':'library:synthetic'}}}))

    def test_no_sound_choice_clears_the_active_file_but_keeps_the_original(self):
        with tempfile.TemporaryDirectory(prefix='kit-brief-none-') as tmp:
            brief = Path(tmp)/'brief.md'
            audio = Path(tmp)/'approved.wav'
            audio.write_bytes(b'synthetic test input, not an actual recording')
            def call(*args, patch=None):
                return subprocess.run([sys.executable,str(CLI),*map(str,args)],text=True,capture_output=True,
                    input=json.dumps(patch) if patch is not None else None)
            self.assertEqual(call('init','--out',brief,'--request','Synthetic no-sound test').returncode,0)
            def show():
                return json.loads(call('show','--file',brief,'--json').stdout)
            for kind in ('voice','music','effects'):
                for patch in ({'choice':'supplied','path':'approved.wav','duration_seconds':1}, {'choice':'none'}):
                    result=call('update','--file',brief,'--expected',show()['revision'],'--patch','-',
                        patch={'audio':{kind:patch}})
                    self.assertEqual(result.returncode,0,result.stderr)
                sound=show()['audio'][kind]
                self.assertIsNone(sound.get('path'),sound)
                self.assertIsNone(sound.get('duration_seconds'),sound)
            self.assertEqual(audio.read_bytes(),b'synthetic test input, not an actual recording')
            previous=brief.read_bytes()
            refused=call('update','--file',brief,'--expected',show()['revision'],'--patch','-',
                patch={'audio':{'effects':{'choice':'none','path':'approved.wav'}}})
            self.assertNotEqual(refused.returncode,0)
            self.assertEqual(brief.read_bytes(),previous)

    def test_a_missing_timing_driver_track_is_reported(self):
        for driver,kind in [('narration','voice'),('music','music')]:
            with self.subTest(driver=driver), tempfile.TemporaryDirectory(prefix='kit-brief-driver-') as tmp:
                brief = Path(tmp)/'brief.md'
                def call(*args, patch=None):
                    r = subprocess.run([sys.executable,str(CLI),*map(str,args)],text=True,capture_output=True,
                        input=json.dumps(patch) if patch is not None else None)
                    self.assertEqual(r.returncode,0,r.stderr)
                    return r.stdout
                call('init','--out',brief,'--request','Synthetic timing-driver test')
                call('update','--file',brief,'--expected',1,'--patch','-',patch={
                    'audio':{'timing_driver':driver,kind:{'choice':'none'}}})
                handoff = json.loads(call('handoff','--file',brief,'--expected',2))
                self.assertTrue(any('timing_driver' in issue and kind in issue for issue in handoff['unresolved']),
                    handoff['unresolved'])

    def test_recording_provenance_keeps_approvals_but_changing_the_image_role_reopens_them(self):
        with tempfile.TemporaryDirectory(prefix='kit-brief-metadata-') as tmp:
            base = Path(tmp)
            brief = base / 'brief.md'
            def run(*args, patch=None):
                r = subprocess.run([sys.executable, str(CLI), *map(str,args)], text=True,
                    input=json.dumps(patch) if patch is not None else None, capture_output=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                return r.stdout
            def show():
                return json.loads(run('show','--file',brief,'--json'))
            def update(patch):
                run('update','--file',brief,'--expected',show()['revision'],'--patch','-',patch=patch)
            run('init','--out',brief,'--request','Synthetic test only, not user creative approval')
            (base/'logo.png').write_bytes(b'synthetic file, not an actual image')
            update({'route':'idea','destination':{'width':320,'height':180,'duration_seconds':10},
                'story':{'summary':'A synthetic approval contract test','onscreen':['A test']},
                'style':{'name':'Synthetic reference','reference':{'origin':'test'}},'brand':{'mode':'original'},
                'assets':{'logo':{'path':'logo.png','role':'end card'}},
                'audio':{'timing_driver':'visual','voice':{'choice':'none'},'music':{'choice':'none'},'effects':{'choice':'none'}}})
            for gate,state in [('layout','yes'),('voice-choice','n/a'),('music-choice','n/a'),
                    ('stills','yes'),('render','yes'),('listening','n/a')]:
                run('approve','--file',brief,'--expected',show()['revision'],'--gate',gate,
                    '--state',state,'--note','TEST FIXTURE ONLY. No real creative approval.')
            before = show()['approvals']
            update({'assets':{'logo':{'notes':'Synthetic licence evidence recorded after review'}},
                'style':{'reference':{'origin':'documented test source','permitted_use':'Synthetic test only'}},
                'destination':{'notes':'Publish date to be decided'}})
            self.assertEqual(show()['approvals'], before)
            update({'assets':{'logo':{'role':'full-screen opening instead of end card'}}})
            current = [r for r in show()['approvals'] if r['status']=='current']
            self.assertFalse(any(r['gate'] in ('layout','stills','render','listening') for r in current))


if __name__ == '__main__':
    unittest.main()
