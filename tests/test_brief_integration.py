"""Integration contracts for data preservation and sound/preview approval boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


_REPO = Path(__file__).resolve().parents[1]
SCRIPT = (_REPO if (_REPO / 'SKILL.md').is_file() else _REPO / 'addons/kit-to-clip') / 'scripts/brief.py'


class BriefIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kit-brief-integration-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.brief = self.folder / 'brief.md'
        self.call('init', '--out', str(self.brief), '--request', 'Test fixture, no production approval')
        self.update({'route': 'idea',
                     'destination': {'width': 320, 'height': 180, 'duration_seconds': 10},
                     'story': {'summary': 'A synthetic test message', 'onscreen': ['Test message']},
                     'style': {'name': 'Original test direction'},
                     'brand': {'mode': 'original'},
                     'audio': {'timing_driver': 'visual'}})

    def call(self, *args, input=None, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], input=input, text=True, capture_output=True)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def data(self):
        return json.loads(self.call('show', '--file', str(self.brief), '--json').stdout)

    def update(self, patch):
        return self.call('update', '--file', str(self.brief), '--expected', str(self.data()['revision']),
                         '--patch', '-', input=json.dumps(patch))

    def approve(self, gate, state='yes', expected=0):
        return self.call('approve', '--file', str(self.brief), '--expected', str(self.data()['revision']),
                         '--gate', gate, '--state', state, '--note', 'Synthetic test decision only', expected=expected)

    def test_a_human_note_is_kept_or_update_refuses_without_losing_it(self):
        # Silently regenerating only from JSON would lose an insight written into the human brief.
        note = 'Creative note: the opening needs a quiet pause before the reveal.\n\n'
        changed = note + self.brief.read_text()
        self.brief.write_text(changed)
        revision = self.data()['revision']
        result = subprocess.run([sys.executable, str(SCRIPT), 'update', '--file', str(self.brief),
                                 '--expected', str(revision), '--patch', '-'],
                                input=json.dumps({'open_questions': {'review': 'Which opening?'}}),
                                text=True, capture_output=True)
        if result.returncode == 0:
            self.assertIn(note.strip(), self.brief.read_text())
        else:
            self.assertEqual(changed, self.brief.read_text())

    def test_effects_only_video_cannot_skip_listening(self):
        # Silence in voice and music does not establish that a video has no sound.
        effect = self.folder / 'effect.wav'
        effect.write_bytes(b'synthetic file for fingerprint testing')
        self.update({'audio': {'voice': {'choice': 'none'}, 'music': {'choice': 'none'},
                               'effects': {'choice': 'supplied', 'path': str(effect)}}})
        self.approve('layout')
        self.approve('stills')
        self.approve('render')
        self.approve('listening', 'n/a', expected=5)

    def test_first_narration_after_preview_stills_reopens_stills(self):
        # A visual preview made before voice selection cannot approve final voice-timed frames.
        self.update({'audio': {'timing_driver': 'narration'}})
        self.approve('layout')
        self.approve('stills')
        voice = self.folder / 'voice.wav'
        voice.write_bytes(b'synthetic new narration file')
        self.update({'audio': {'voice': {'choice': 'supplied', 'path': str(voice), 'duration_seconds': 35.7}}})
        self.assertFalse(any(r['gate'] == 'stills' and r['status'] == 'current'
                             for r in self.data()['approvals']))


if __name__ == '__main__':
    unittest.main()
