"""Discovery records alone must not imply available editable source."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
SKILL=REPO if (REPO/'SKILL.md').exists() else REPO/'addons/kit-to-clip'


class SavedReferenceIntegrationTests(unittest.TestCase):
    def test_metadata_only_reference_is_not_source_ready(self):
        with tempfile.TemporaryDirectory(prefix='kit-reference-metadata-') as tmp:
            base=Path(tmp)
            folder=base/'styles'/'paper'
            folder.mkdir(parents=True)
            for manifest in (None,{}, {'previews':[]}):
                record={'slug':'paper','title':'Paper','status':'approved','kind':'reference','brand':None,
                    'tags':['paper'],'instructions':{'medium':'Layered paper'}}
                if manifest is not None:
                    record['reference']=manifest
                (folder/'style.json').write_text(json.dumps(record))
                result=subprocess.run([sys.executable,str(SKILL/'scripts/styles.py'),'--root',str(base),
                    'handoff','--style','paper'],text=True,capture_output=True)
                if result.returncode==0:
                    self.assertFalse(json.loads(result.stdout)['ready_to_reuse'],result.stdout)
                else:
                    self.assertNotIn('Traceback',result.stderr)

    def test_a_saved_source_survives_archiving_the_original_finished_video(self):
        with tempfile.TemporaryDirectory(prefix='kit-reference-history-') as tmp:
            base=Path(tmp)
            folder=base/'styles'/'paper'
            source=folder/'source'/'index.html'
            source.parent.mkdir(parents=True)
            source.write_text('<html>Synthetic approved editable reference</html>')
            (folder/'style.json').write_text(json.dumps({'slug':'paper','title':'Paper','status':'approved',
                'kind':'reference','reference':{'entry':'source/index.html','files':[{'path':'source/index.html',
                    'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'role':'source'}]},
                'provenance':{'final_save':{'approval_note':'TEST FIXTURE ONLY',
                    'finished_output':{'path':str(base/'archived-video.mp4'),'size':10,'sha256':'0'*64}}}}))
            result=subprocess.run([sys.executable,str(SKILL/'scripts/styles.py'),'--root',str(base),
                'handoff','--style','paper'],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout)
            self.assertTrue(data['ready_to_reuse'],result.stdout)
            self.assertTrue(data['provenance_warnings'])
            self.assertEqual(data['missing_files'],[])


if __name__=='__main__':
    unittest.main()
