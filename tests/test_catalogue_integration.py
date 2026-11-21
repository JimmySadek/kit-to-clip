"""Loader compatibility with the existing private export shape. Contains no publisher source."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO if (REPO / 'SKILL.md').exists() else REPO / 'addons/kit-to-clip'


class PrivateExportTests(unittest.TestCase):
    def test_selected_original_export_loads_without_rewriting_the_collection(self):
        with tempfile.TemporaryDirectory(prefix='kit-private-export-test-') as tmp:
            base = Path(tmp)
            prompt = 'Synthetic reference, containing no publisher prompt or code.'
            index = json.loads((SKILL / 'catalogue/index.json').read_text())
            index['styles'][0]['source']['prompt_sha256'] = hashlib.sha256(prompt.encode()).hexdigest()
            style_id = index['styles'][0]['id']
            index_file = base / 'index.json'
            index_file.write_text(json.dumps(index))
            source = base / 'private'
            source.mkdir()
            package = source / (style_id + '.json')
            raw = json.dumps({'info': {'id':style_id, 'title':'Synthetic export metadata'}, 'prompt':prompt})
            package.write_text(raw)
            # A broken neighbouring package must never be opened or repaired.
            other = source / 'unselected.json'
            other.write_text('not valid json')
            result = subprocess.run([sys.executable, str(SKILL / 'scripts/catalogue.py'), '--index', str(index_file),
                'load', style_id, '--source-root', str(source), '--json'], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(prompt, result.stdout)
            self.assertEqual(package.read_text(), raw)
            self.assertEqual(other.read_text(), 'not valid json')


if __name__ == '__main__':
    unittest.main()
