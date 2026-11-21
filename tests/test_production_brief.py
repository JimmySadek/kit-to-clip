"""Behavior checks for the durable production brief (scripts/brief.py). Run with unittest discovery.

Every check uses real files in a temporary folder and runs the real command line in a separate process, the way a
director or builder would. Nothing of brief.py itself is mocked.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO if (REPO / 'SKILL.md').exists() else REPO / 'addons' / 'kit-to-clip'
SCRIPT = SKILL / 'scripts' / 'brief.py'

OK, INVALID, STALE, BUSY, REFUSED = 0, 1, 3, 4, 5


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'scripts/brief.py is not implemented yet')
        self.tmp = tempfile.TemporaryDirectory(prefix='kit-brief-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.work = self.base / 'video-job'
        self.brief = self.work / 'brief.md'
        self.env = dict(os.environ, KIT_TO_CLIP_BRIEF_LOCK_WAIT='5')
        self.patches = 0
        self.inputs = set()

    # --- helpers -------------------------------------------------------------------------------------------------

    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                              env=env or self.env, timeout=60)

    def ok(self, *args):
        r = self.run_cli(*args)
        self.assertEqual(r.returncode, OK, f'{args} failed: {r.stdout}{r.stderr}')
        return r

    def patch_file(self, data, raw=None):
        self.patches += 1
        p = self.base / f'patch-{self.patches}.json'
        p.write_text(raw if raw is not None else json.dumps(data), encoding='utf-8')
        return p

    def data(self):
        return json.loads(self.ok('show', '--file', self.brief, '--json').stdout)

    def rev(self):
        return self.data()['revision']

    def init(self, request='A 15 second teaser for the spring launch'):
        return self.ok('init', '--out', self.brief, '--request', request)

    def update(self, patch, expect=OK):
        r = self.run_cli('update', '--file', self.brief, '--expected', self.rev(), '--patch', self.patch_file(patch))
        self.assertEqual(r.returncode, expect, f'update {patch}: {r.stdout}{r.stderr}')
        return r

    def approve(self, gate, state='yes', note='the test viewer said yes in chat', expect=OK):
        r = self.run_cli('approve', '--file', self.brief, '--expected', self.rev(), '--gate', gate, '--state', state,
                         '--note', note)
        self.assertEqual(r.returncode, expect, f'approve {gate} {state}: {r.stdout}{r.stderr}')
        return r

    def handoff(self):
        r = self.ok('handoff', '--file', self.brief, '--expected', self.rev())
        return json.loads(r.stdout)

    def current(self):
        """gate -> state of the approvals that still count, read from the persisted data."""
        return {a['gate']: a['state'] for a in self.data()['approvals'] if a['status'] == 'current'}

    def invalidated(self):
        return [a for a in self.data()['approvals'] if a['status'] == 'invalidated']

    def media(self, name, content):
        p = self.work / name
        p.write_bytes(content)
        self.inputs.add(name)
        return p

    def sound_job(self, timing_driver):
        """A brief with narration and background music, approved all the way through listening."""
        self.init()
        voice = self.media('voice.wav', b'voice take 1')
        music = self.media('music.wav', b'music take 1')
        self.update({'route': 'idea', 'brand': {'mode': 'original'}, 'style': {'name': 'calm editorial'},
                     'destination': {'format': 'reel', 'aspect': '9:16', 'duration_seconds': 15},
                     'story': {'onscreen': ['Spring is here', 'Shop now'], 'script': 'Spring is here.'},
                     'audio': {'timing_driver': timing_driver,
                               'voice': {'choice': 'generated', 'path': voice.name},
                               'music': {'choice': 'supplied', 'path': str(music), 'bpm': 120},
                               'effects': {'choice': 'none'}}})
        for gate in ('layout', 'voice-choice', 'music-choice', 'stills', 'render', 'listening'):
            self.approve(gate)
        self.assertEqual(set(self.current()), {'layout', 'voice-choice', 'music-choice', 'stills', 'render',
                                               'listening'})
        return voice, music

    def assert_only_brief(self):
        """No lock, temp file or second source of truth is left next to the brief."""
        extra = [p.name for p in self.work.iterdir() if p.name not in self.inputs | {'brief.md'}]
        self.assertEqual(extra, [])

    # --- creation, persistence and resume ------------------------------------------------------------------------

    def test_init_starts_unchosen_and_never_overwrites(self):
        # Guessing a brand or style here would skip the person's choice; overwriting would destroy their brief.
        self.init()
        d = self.data()
        self.assertEqual(d['revision'], 1)
        self.assertEqual(d['request'], 'A 15 second teaser for the spring launch')
        self.assertEqual(d['route'], 'unchosen')
        self.assertEqual(d['brand']['mode'], 'unchosen')
        self.assertNotIn('id', d['brand'])
        self.assertEqual(d['style'], {})
        self.assertEqual(d['audio']['timing_driver'], 'unchosen')
        self.assertEqual(d['audio']['voice']['choice'], 'unchosen')
        self.assertEqual(d['audio']['music']['choice'], 'unchosen')
        self.assertEqual(d['audio']['effects']['choice'], 'unchosen', 'unknown effects are never assumed silent')
        self.assertEqual(d['approvals'], [])
        text = self.brief.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('# '), 'brief.md must open as a readable Markdown document')
        self.assertIn('spring launch', text.split('```json')[0], 'the request must be readable above the data')
        before = self.brief.read_bytes()
        r = self.run_cli('init', '--out', self.brief, '--request', 'something else')
        self.assertNotEqual(r.returncode, OK)
        self.assertEqual(self.brief.read_bytes(), before)
        self.assert_only_brief()

    def test_brief_resumes_in_a_new_process_with_history(self):
        # A session that crashes after an approval must find the same brief, decisions and approvals next time.
        self.init()
        self.update({'route': 'footage', 'destination': {'platform': 'instagram', 'duration_seconds': 12.5},
                     'decisions': {'tone': 'warm, no hype'}, 'open_questions': {'cta': 'Which call to action?'}})
        self.approve('layout', note='the test viewer: layout looks right')
        d = self.data()
        self.assertEqual(d['revision'], 3)
        self.assertEqual(d['route'], 'footage')
        self.assertEqual(d['destination'], {'platform': 'instagram', 'duration_seconds': 12.5})
        self.assertEqual(d['decisions'], {'tone': 'warm, no hype'})
        self.assertEqual(len(d['history']), 3)
        rec = d['approvals'][0]
        self.assertEqual((rec['gate'], rec['state'], rec['input_revision'], rec['status']),
                         ('layout', 'yes', 2, 'current'))
        self.assertEqual(rec['note'], 'the test viewer: layout looks right')
        human = self.ok('show', '--file', self.brief).stdout
        self.assertIn('layout', human)
        self.assertIn('Which call to action?', human)
        self.assert_only_brief()

    def test_patch_merges_objects_and_null_clears(self):
        # Progressive filling: a later patch must not wipe the fields an earlier patch set.
        self.init()
        self.update({'destination': {'platform': 'tiktok', 'aspect': '9:16'}})
        self.update({'destination': {'duration_seconds': 10}, 'open_questions': {'cta': 'Which?', 'end': 'Logo?'}})
        self.update({'destination': {'aspect': None}, 'open_questions': {'cta': None}})
        d = self.data()
        self.assertEqual(d['destination'], {'platform': 'tiktok', 'duration_seconds': 10})
        self.assertEqual(d['open_questions'], {'end': 'Logo?'})

    # --- revisions, malformed input and file safety --------------------------------------------------------------

    def test_stale_revision_is_rejected_with_no_data_loss(self):
        self.init()
        self.update({'route': 'idea'})
        before = self.brief.read_bytes()
        patch = self.patch_file({'route': 'mixed'})
        r = self.run_cli('update', '--file', self.brief, '--expected', 1, '--patch', patch)
        self.assertEqual(r.returncode, STALE, r.stderr)
        r = self.run_cli('approve', '--file', self.brief, '--expected', 1, '--gate', 'layout', '--state', 'yes',
                         '--note', 'yes')
        self.assertEqual(r.returncode, STALE, r.stderr)
        r = self.run_cli('handoff', '--file', self.brief, '--expected', 1)
        self.assertEqual(r.returncode, STALE, r.stderr)
        self.assertEqual(r.stdout.strip(), '', 'a stale handoff must not hand anything over')
        self.assertEqual(self.brief.read_bytes(), before)
        self.assert_only_brief()

    def test_malformed_patches_change_nothing(self):
        self.init()
        before = self.brief.read_bytes()
        bad = [
            {'colour': 'red'},                                   # unsupported top-level field
            {'brand': {'colour': 'red'}},                        # unsupported nested field
            {'route': 'video'},                                  # not a route
            {'brand': {'mode': 'borrowed'}},
            {'audio': {'timing_driver': 'beat'}},
            {'audio': {'voice': {'choice': 'robot'}}},
            {'destination': {'duration_seconds': -3}},           # durations must be finite and positive
            {'destination': {'duration_seconds': 0}},
            {'destination': {'duration_seconds': '15'}},
            {'destination': {'width': True}},
            {'audio': {'music': {'bpm': 1e400}}},                 # overflows to infinity
            {'request': ''},
            {'request': None},
            {'assets': {'../escape': {'path': 'a.png'}}},       # asset ids are plain names
            {'assets': {'logo': {'path': 'logo.png', 'size': 3}}},
            {'decisions': ['a list is not a decision map']},
            {'revision': 99},                                    # system fields are not patchable
            {'approvals': []},
        ]
        raw = ['[1, 2]', '{"route": ', '{"destination": {"duration_seconds": NaN}}',
               '{"destination": {"duration_seconds": Infinity}}', '{"route": "idea", "route": "footage"}']
        for patch in bad + raw:
            with self.subTest(patch=patch):
                p = self.patch_file(None, raw=patch) if isinstance(patch, str) else self.patch_file(patch)
                r = self.run_cli('update', '--file', self.brief, '--expected', 1, '--patch', p)
                self.assertEqual(r.returncode, INVALID, f'{r.stdout}{r.stderr}')
                self.assertEqual(self.brief.read_bytes(), before)
        self.assert_only_brief()

    def test_hand_broken_brief_is_refused_not_rewritten(self):
        self.init()
        text = self.brief.read_text(encoding='utf-8').replace('"revision": 1', '"revision": "one"')
        self.brief.write_text(text, encoding='utf-8')
        before = self.brief.read_bytes()
        r = self.run_cli('update', '--file', self.brief, '--expected', 1, '--patch', self.patch_file({'route': 'idea'}))
        self.assertEqual(r.returncode, INVALID)
        self.assertEqual(self.brief.read_bytes(), before)

    def test_symlinks_and_wrong_names_are_refused(self):
        # A symlinked brief.md could make a write land outside the work folder.
        outside = self.base / 'outside.md'
        outside.write_text('precious')
        self.work.mkdir()
        self.brief.symlink_to(outside)
        r = self.run_cli('init', '--out', self.brief, '--request', 'x')
        self.assertNotEqual(r.returncode, OK)
        self.assertEqual(outside.read_text(), 'precious')
        self.brief.unlink()
        # A dangling link must not create its target either.
        target = self.base / 'created-through-link.md'
        self.brief.symlink_to(target)
        r = self.run_cli('init', '--out', self.brief, '--request', 'x')
        self.assertNotEqual(r.returncode, OK)
        self.assertFalse(target.exists())
        self.brief.unlink()
        # An existing brief reached through a link is refused for updates, and the real file stays untouched.
        real = self.base / 'real-job' / 'brief.md'
        self.ok('init', '--out', real, '--request', 'real')
        before = real.read_bytes()
        self.brief.symlink_to(real)
        r = self.run_cli('update', '--file', self.brief, '--expected', 1, '--patch', self.patch_file({'route': 'idea'}))
        self.assertNotEqual(r.returncode, OK)
        self.assertEqual(real.read_bytes(), before)
        self.assertTrue(self.brief.is_symlink())
        self.brief.unlink()
        # The brief is always called brief.md.
        r = self.run_cli('init', '--out', self.work / 'notes.txt', '--request', 'x')
        self.assertNotEqual(r.returncode, OK)
        self.assertFalse((self.work / 'notes.txt').exists())

    def test_concurrent_writers_with_one_revision_cannot_both_win(self):
        self.init()
        procs = []
        for i in range(8):
            p = self.patch_file({'decisions': {f'writer{i}': f'writer {i} was here'}})
            procs.append(subprocess.Popen([sys.executable, str(SCRIPT), 'update', '--file', str(self.brief),
                                           '--expected', '1', '--patch', str(p)], env=self.env,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        codes = [p.wait(timeout=60) for p in procs]
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        self.assertEqual(codes.count(OK), 1, codes)
        self.assertTrue(all(c in (OK, STALE, BUSY) for c in codes), codes)
        d = self.data()
        self.assertEqual(d['revision'], 2)
        self.assertEqual(len(d['decisions']), 1)
        self.assert_only_brief()

    def test_a_held_lock_blocks_writers_but_not_readers(self):
        self.init()
        before = self.brief.read_bytes()
        lock = self.work / 'brief.md.lock'
        lock.write_text('another writer')
        env = dict(self.env, KIT_TO_CLIP_BRIEF_LOCK_WAIT='0.3')
        start = time.monotonic()
        r = self.run_cli('update', '--file', self.brief, '--expected', 1, '--patch', self.patch_file({'route': 'idea'}),
                         env=env)
        self.assertEqual(r.returncode, BUSY, r.stderr)
        self.assertLess(time.monotonic() - start, 20)
        self.assertEqual(self.brief.read_bytes(), before)
        self.assertEqual(lock.read_text(), 'another writer', 'someone else\'s lock must not be removed')
        self.ok('show', '--file', self.brief, '--json')
        self.ok('handoff', '--file', self.brief, '--expected', 1)
        lock.unlink()

    # --- approvals: recording consent, in order ------------------------------------------------------------------

    def test_approvals_follow_the_gate_order(self):
        self.init()
        self.approve('stills', expect=REFUSED)                       # no layout yet
        self.approve('render', expect=REFUSED)
        self.approve('listening', expect=REFUSED)
        self.approve('layout', state='n/a', expect=REFUSED)          # n/a is only for absent sound
        self.approve('layout', state='no', note='the test viewer: too busy')
        self.approve('stills', expect=REFUSED)                       # a "no" layout does not open stills
        self.approve('layout', note='the test viewer: better now')
        self.approve('stills')
        self.approve('render', expect=REFUSED)                       # voice and music are still unchosen
        self.approve('music-choice', state='n/a', expect=REFUSED)    # music is not known to be absent
        self.update({'audio': {'music': {'choice': 'supplied', 'path': 'track.wav'}, 'voice': {'choice': 'none'},
                               'effects': {'choice': 'none'}}})
        self.assertEqual(self.current(), {'layout': 'yes', 'stills': 'yes'}, 'choosing sound must not undo visuals')
        self.approve('voice-choice', state='n/a', note='no narration in this one')
        self.approve('music-choice', expect=REFUSED)                 # the named track does not exist
        self.media('track.wav', b'beat')
        self.approve('render', expect=REFUSED)                       # music needs its own choice first
        self.approve('music-choice')
        self.approve('listening', expect=REFUSED)                    # nothing rendered yet
        self.approve('listening', state='n/a', expect=REFUSED)       # there is sound to listen to
        self.approve('render')
        self.approve('listening', note='the test viewer listened to the file: flows now')
        self.assertEqual(self.current(), {'layout': 'yes', 'stills': 'yes', 'voice-choice': 'n/a',
                                          'music-choice': 'yes', 'render': 'yes', 'listening': 'yes'})
        r = self.run_cli('approve', '--file', self.brief, '--expected', self.rev(), '--gate', 'layout', '--state',
                         'yes', '--note', '')
        self.assertNotEqual(r.returncode, OK, 'an approval without the person\'s words is not evidence')

    def test_silent_video_closes_sound_gates_with_na(self):
        self.init()
        self.update({'audio': {'timing_driver': 'visual', 'voice': {'choice': 'none'}, 'music': {'choice': 'none'},
                               'effects': {'choice': 'none'}}})
        self.approve('layout')
        self.approve('stills')
        self.approve('render')                                       # no sound choices are needed
        self.approve('listening', state='n/a', note='silent video')
        self.assertEqual(self.handoff()['next_gate'], None)

    def test_a_new_no_reopens_the_gates_after_it(self):
        self.init()
        self.update({'audio': {'voice': {'choice': 'none'}, 'music': {'choice': 'none'}, 'effects': {'choice': 'none'}}})
        self.approve('layout')
        self.approve('stills')
        self.approve('layout', state='no', note='the test viewer changed his mind about the layout')
        self.assertEqual(self.current(), {'layout': 'no'})
        old = [a['gate'] for a in self.data()['approvals'] if a['status'] != 'current']
        self.assertEqual(sorted(old), ['layout', 'stills'], 'older records are kept, not deleted')

    # --- dependency-aware invalidation ---------------------------------------------------------------------------

    def test_changed_voice_invalidates_voice_choice_and_visual_timing(self):
        voice, _ = self.sound_job('narration')
        new_voice = self.media('voice-2.wav', b'voice take 2')
        self.update({'audio': {'voice': {'path': new_voice.name}}})
        self.assertEqual(self.current(), {'music-choice': 'yes'})
        gone = {a['gate']: a for a in self.invalidated()}
        self.assertEqual(set(gone), {'voice-choice', 'layout', 'stills', 'render', 'listening'})
        self.assertTrue(all(a['invalidated']['reason'] and a['invalidated']['revision'] == self.rev()
                            for a in gone.values()))
        self.assertEqual(self.handoff()['next_gate'], 'layout')

    def test_changed_script_counts_as_a_new_voice(self):
        self.sound_job('narration')
        self.update({'story': {'script': 'Spring is finally here.'}})
        self.assertEqual(self.current(), {'music-choice': 'yes'})

    def test_background_music_change_is_selective(self):
        self.sound_job('narration')
        new_music = self.media('music-2.wav', b'music take 2')
        self.update({'audio': {'music': {'path': str(new_music)}}})
        self.assertEqual(self.current(), {'layout': 'yes', 'stills': 'yes', 'voice-choice': 'yes'})
        self.assertEqual({a['gate'] for a in self.invalidated()}, {'music-choice', 'render', 'listening'})

    def test_music_that_drives_timing_also_invalidates_layout_and_stills(self):
        self.sound_job('music')
        self.update({'audio': {'music': {'bpm': 96}}})
        self.assertEqual(self.current(), {'voice-choice': 'yes'})

    def test_brand_change_invalidates_visuals_but_keeps_sound_choices(self):
        self.sound_job('narration')
        self.update({'brand': {'mode': 'palette', 'id': 'acme'}})
        self.assertEqual(self.current(), {'voice-choice': 'yes', 'music-choice': 'yes'})

    def test_metadata_only_update_keeps_creative_approvals(self):
        self.sound_job('narration')
        before = self.current()
        self.update({'open_questions': {'post': 'Which day do we post?'}, 'decisions': {'post-day': 'Friday'}})
        self.update({'open_questions': {'post': None}})
        self.assertEqual(self.current(), before)
        self.assertEqual(self.invalidated(), [])
        h = self.handoff()
        self.assertEqual(h['next_gate'], None)
        self.assertEqual(h['open_questions'], {})

    def test_same_values_do_not_invalidate(self):
        self.sound_job('narration')
        self.update({'brand': {'mode': 'original'}, 'route': 'idea'})
        self.assertEqual(self.invalidated(), [])

    # --- handoff ---------------------------------------------------------------------------------------------------

    def test_layout_stage_handoff_lists_what_is_missing(self):
        # A builder may start the layout before final gates exist, but must see what is still undecided.
        self.init()
        logo = self.media('logo.png', b'logo bytes')
        kit = self.base / 'brand-kit'
        (kit / 'deep').mkdir(parents=True)
        (kit / 'deep' / 'secret.txt').write_text('not to be scanned')
        self.update({'brand': {'mode': 'full', 'kit': str(kit)},
                     'assets': {'logo': {'path': 'logo.png', 'role': 'end card'},
                                'hero': {'path': 'hero.mp4', 'role': 'footage'}},
                     'open_questions': {'cta': 'Which call to action?'}})
        before = self.brief.read_bytes()
        h = self.handoff()
        self.assertEqual(h['revision'], 2)
        self.assertRegex(h['digest'], r'^[0-9a-f]{64}$')
        self.assertEqual(h['next_gate'], 'layout')
        self.assertEqual(h['open_questions'], {'cta': 'Which call to action?'})
        self.assertEqual(h['inputs']['brand']['mode'], 'full')
        unresolved = ' '.join(h['unresolved'])
        for needed in ('route', 'timing_driver', 'voice', 'music', 'hero.mp4'):
            self.assertIn(needed, unresolved)
        files = {f['field']: f for f in h['files']}
        self.assertEqual(files['assets.logo.path']['status'], 'ok')
        self.assertEqual(files['assets.logo.path']['sha256'], sha(logo))
        self.assertEqual(files['assets.hero.path']['status'], 'missing')
        self.assertEqual(files['brand.kit']['status'], 'directory')
        self.assertNotIn('secret', json.dumps(h), 'a named folder is not scanned')
        self.assertFalse(h['may_render'])
        self.assertEqual(self.brief.read_bytes(), before, 'handoff only reads')
        self.assert_only_brief()
        self.update({'decisions': {'cta': 'Shop now'}})
        self.assertNotEqual(self.handoff()['digest'], h['digest'])

    def test_files_changed_outside_the_brief_make_dependent_approvals_stale(self):
        voice, music = self.sound_job('narration')
        h = self.handoff()
        self.assertTrue(h['may_render'])
        self.assertTrue(all(a['stale'] is False for a in h['approvals'].values()))
        music.write_bytes(b'someone replaced the track')
        h = self.handoff()
        stale = {g for g, a in h['approvals'].items() if a['stale']}
        self.assertEqual(stale, {'music-choice', 'render', 'listening'})
        self.assertIn('audio.music.path', ' '.join(h['approvals']['render']['stale_reasons']))
        files = {f['field']: f for f in h['files']}
        self.assertEqual(files['audio.music.path']['status'], 'changed')
        self.assertEqual(files['audio.music.path']['sha256'], sha(music))
        self.assertFalse(h['may_render'])
        self.assertEqual(h['next_gate'], 'music-choice')
        # A stale prerequisite does not count when the next approval is recorded.
        voice.unlink()
        h = self.handoff()
        self.assertTrue(h['approvals']['layout']['stale'])
        self.assertEqual({f['field']: f['status'] for f in h['files']}['audio.voice.path'], 'missing')
        self.approve('stills', expect=REFUSED)

    # --- review fixes: effects, prerequisite propagation, readiness ----------------------------------------------

    def test_effects_are_sound_and_never_assumed_silent(self):
        # An effects-only video still has sound: listening cannot be n/a, and unknown effects block the render.
        self.init()
        self.update({'audio': {'timing_driver': 'visual', 'voice': {'choice': 'none'}, 'music': {'choice': 'none'}}})
        self.approve('layout')
        self.approve('stills')
        self.approve('render', expect=REFUSED)                       # effects are still unchosen
        self.assertIn('effects', ' '.join(self.handoff()['unresolved']))
        whoosh = self.media('whoosh.wav', b'whoosh take 1')
        self.update({'audio': {'effects': {'choice': 'supplied', 'path': whoosh.name, 'details': 'logo whoosh'}}})
        self.assertEqual(self.current(), {'layout': 'yes', 'stills': 'yes'}, 'effects do not change the visuals')
        files = {f['field']: f for f in self.handoff()['files']}
        self.assertEqual(files['audio.effects.path']['sha256'], sha(whoosh))
        self.approve('render')
        self.approve('listening', state='n/a', expect=REFUSED)       # there is sound to listen to
        self.approve('listening', note='the test viewer listened: whoosh lands on the logo')
        # Replacing the effects reopens only render and listening.
        whoosh2 = self.media('whoosh-2.wav', b'whoosh take 2')
        self.update({'audio': {'effects': {'path': whoosh2.name}}})
        self.assertEqual(self.current(), {'layout': 'yes', 'stills': 'yes'})
        self.assertEqual({a['gate'] for a in self.invalidated()}, {'render', 'listening'})
        # Effects changed on disk make render and listening stale, nothing else.
        self.approve('render')
        self.approve('listening', note='the test viewer listened again')
        whoosh2.write_bytes(b'someone replaced the whoosh')
        stale = {g for g, a in self.handoff()['approvals'].items() if a['stale']}
        self.assertEqual(stale, {'render', 'listening'})

    def test_stale_prerequisites_propagate_and_a_new_render_reopens_listening(self):
        _, _ = self.sound_job('narration')
        frame = self.media('stills.png', b'the frames the test viewer saw')
        r = self.run_cli('approve', '--file', self.brief, '--expected', self.rev(), '--gate', 'stills', '--state',
                         'yes', '--note', 'the test viewer: these stills', '--evidence', frame)
        self.assertEqual(r.returncode, OK, r.stderr)
        self.assertNotIn('render', self.current(), 'a new stills decision reopens the render built on the old one')
        self.approve('render')
        self.approve('listening')
        self.assertTrue(self.handoff()['may_render'])
        # A renewed render yes supersedes the listening that was done on the older render.
        self.approve('render', note='the test viewer: render again with the fixed caption')
        self.assertNotIn('listening', self.current())
        self.assertIn('listening', {a['gate'] for a in self.invalidated()})
        h = self.handoff()
        self.assertEqual(h['next_gate'], 'listening')
        self.approve('listening')
        # The evidence the stills were approved on changes: stills is stale, so render (and listening) are too.
        frame.write_bytes(b'different frames')
        h = self.handoff()
        self.assertTrue(h['approvals']['stills']['stale'])
        self.assertTrue(h['approvals']['render']['stale'], 'a stale prerequisite makes render stale')
        self.assertTrue(h['approvals']['listening']['stale'])
        self.assertIn('stills', ' '.join(h['approvals']['render']['stale_reasons']))
        self.assertFalse(h['may_render'])
        self.assertEqual(h['next_gate'], 'stills')
        self.approve('listening', expect=REFUSED)                    # same checks as the handoff

    def test_may_render_needs_a_complete_brief_and_the_actual_files(self):
        # Gates can be recorded on a partial brief, but the handoff never says ready while inputs are unresolved.
        self.init()
        self.update({'audio': {'timing_driver': 'visual', 'voice': {'choice': 'none'},
                               'music': {'choice': 'guided', 'details': 'calm piano, no file yet'},
                               'effects': {'choice': 'none'}}})
        for gate in ('layout', 'stills', 'music-choice', 'render'):
            self.approve(gate)
        h = self.handoff()
        self.assertFalse(h['may_render'])
        unresolved = ' '.join(h['unresolved'])
        for needed in ('route', 'duration', 'brand.mode', 'style', 'story', 'audio.music.path'):
            self.assertIn(needed, unresolved)
        # Fill the brief (reopening the visuals), then approve again: now it is ready.
        track = self.media('piano.wav', b'piano')
        self.update({'route': 'idea', 'brand': {'mode': 'original'}, 'style': {'saved_style': 'calm-editorial'},
                     'destination': {'width': 1080, 'height': 1920, 'duration_seconds': 12},
                     'story': {'beats': ['open', 'reveal']}, 'audio': {'music': {'path': track.name}}})
        for gate in ('layout', 'stills', 'music-choice', 'render'):
            self.approve(gate)
        h = self.handoff()
        self.assertEqual(h['unresolved'], [])
        self.assertTrue(h['may_render'])

    # --- review fixes: first narration, map removal, style reference ---------------------------------------------

    def test_first_narration_reopens_preview_stills_but_first_music_stays_selective(self):
        self.init()
        self.update({'audio': {'timing_driver': 'narration'}})
        self.approve('layout')
        self.approve('stills', note='the test viewer: preview stills look right')
        music = self.media('bed.wav', b'background bed')
        self.update({'audio': {'music': {'choice': 'supplied', 'path': music.name}}})
        self.assertEqual(self.current(), {'layout': 'yes', 'stills': 'yes'}, 'background music is selective')
        voice = self.media('voice.wav', b'first narration')
        self.update({'audio': {'voice': {'choice': 'supplied', 'path': voice.name, 'duration_seconds': 35.7}}})
        self.assertEqual(self.current(), {})
        gone = {a['gate']: a for a in self.invalidated()}
        self.assertEqual(set(gone), {'layout', 'stills'})
        self.assertIn('audio.voice', gone['stills']['invalidated']['reason'])
        # With no approvals yet, a first choice simply records it.
        other = self.base / 'other-job' / 'brief.md'
        self.ok('init', '--out', other, '--request', 'x')
        p = self.patch_file({'audio': {'voice': {'choice': 'supplied', 'path': 'v.wav'}}})
        self.ok('update', '--file', other, '--expected', 1, '--patch', p)
        d = json.loads(self.ok('show', '--file', other, '--json').stdout)
        self.assertEqual(d['approvals'], [])

    def test_null_removes_an_asset_entry_but_never_the_media(self):
        self.init()
        logo = self.media('logo.png', b'logo')
        self.update({'assets': {'logo': {'path': logo.name, 'role': 'end card'}, 'hero': {'path': 'hero.mp4'}}})
        self.update({'assets': {'logo': None}})
        self.assertEqual(self.data()['assets'], {'hero': {'path': 'hero.mp4'}})
        self.assertTrue(logo.is_file(), 'clearing metadata must not delete the media file')
        self.update({'style': {'name': 'x', 'reference': {'catalogue_id': 'cat-1'}}})
        self.update({'style': {'reference': None}})
        self.assertEqual(self.data()['style'], {'name': 'x'})

    def test_style_reference_is_structured_and_its_files_fingerprinted(self):
        self.init()
        root = self.base / 'private-collection'
        (root / 'deep').mkdir(parents=True)
        (root / 'deep' / 'unlisted-secret.txt').write_text('not to be scanned')
        prompt = root / 'prompt.md'
        prompt.write_text('the original prompt')
        code = root / 'scene.html'
        code.write_text('<div>scene</div>')
        ref = {'catalogue_id': 'atlas-042', 'origin': 'user collection', 'prompt_file': str(prompt),
               'code_file': str(code), 'source_root': str(root), 'source_sha256': sha(code),
               'permitted_use': 'commercial, credit not required'}
        self.update({'style': {'name': 'atlas glow', 'saved_style': 'atlas-glow', 'notes': 'softer', 'reference': ref}})
        self.assertEqual(self.data()['style']['reference'], ref)
        h = self.handoff()
        files = {f['field']: f for f in h['files']}
        self.assertEqual(files['style.reference.prompt_file']['sha256'], sha(prompt))
        self.assertEqual(files['style.reference.code_file']['sha256'], sha(code))
        self.assertNotIn('unlisted-secret', json.dumps(h), 'source_root is a pointer, never scanned')
        self.approve('layout')
        code.write_text('<div>edited scene</div>')
        self.assertTrue(self.handoff()['approvals']['layout']['stale'])
        before = self.brief.read_bytes()
        for bad in ({'source_sha256': 'not-a-hash'}, {'catalogue_id': 42}, {'licence': 'mine'},
                    {'prompt_file': ''}):
            with self.subTest(bad=bad):
                self.update({'style': {'reference': bad}}, expect=INVALID)
                self.assertEqual(self.brief.read_bytes(), before)

    # --- review fixes: hand edits ---------------------------------------------------------------------------------

    def test_hand_edited_summary_is_refused_until_reconciled(self):
        self.init()
        self.update({'route': 'idea'})
        insight = 'the test viewer, by hand: keep the pause before the reveal.'
        text = self.brief.read_text(encoding='utf-8').replace('## Request', f'{insight}\n\n## Request', 1)
        self.brief.write_text(text, encoding='utf-8')
        before = self.brief.read_bytes()
        r = self.run_cli('update', '--file', self.brief, '--expected', 2,
                         '--patch', self.patch_file({'open_questions': {'q': 'Which?'}}))
        self.assertNotEqual(r.returncode, OK)
        self.assertIn('summary', r.stderr)
        r = self.run_cli('approve', '--file', self.brief, '--expected', 2, '--gate', 'layout', '--state', 'yes',
                         '--note', 'yes')
        self.assertNotEqual(r.returncode, OK)
        self.assertEqual(self.brief.read_bytes(), before, 'the hand-written text is never discarded silently')
        self.assertEqual(self.data()['route'], 'idea', 'reading still works')
        h = self.handoff()
        self.assertTrue(h['summary_needs_reconciliation'])
        self.assertIn('summary', ' '.join(h['unresolved']))
        self.assertFalse(h['may_render'])
        # The person's text is carried into the data on purpose, and only then is the summary regenerated.
        r = self.run_cli('update', '--file', self.brief, '--expected', 2, '--summary-reconciled',
                         '--patch', self.patch_file({'decisions': {'pause': insight}}))
        self.assertEqual(r.returncode, OK, r.stderr)
        d = self.data()
        self.assertEqual(d['decisions'], {'pause': insight})
        self.assertIn(insight, json.dumps(d['history'][-1]), 'history keeps the replaced hand-written lines')
        self.assertFalse(self.handoff()['summary_needs_reconciliation'])
        # Blank lines added by an editor are not a meaningful edit.
        self.brief.write_text(self.brief.read_text(encoding='utf-8').replace('## Request', '\n\n## Request', 1),
                              encoding='utf-8')
        self.update({'route': 'mixed'})

    def _rewrite_data(self, change, reseal):
        text = self.brief.read_text(encoding='utf-8')
        head, rest = text.split('```json\n', 1)
        payload, tail = rest.split('\n```\n', 1)
        data = json.loads(payload)
        change(data)
        if reseal:
            data.pop('seal', None)
            canon = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            data['seal'] = 'sha256:' + hashlib.sha256(canon.encode('utf-8')).hexdigest()
        self.brief.write_text(head + '```json\n' + json.dumps(data, indent=4) + '\n```\n' + tail, encoding='utf-8')

    def test_hand_edited_data_is_refused_by_the_seal(self):
        self.init()
        self.update({'audio': {'voice': {'choice': 'none'}, 'music': {'choice': 'none'}, 'effects': {'choice': 'none'}}})
        self.approve('layout')
        self.approve('stills')
        self.assertRegex(self.data()['seal'], r'^sha256:[0-9a-f]{64}$')
        # Re-indenting the data is not a change.
        self._rewrite_data(lambda d: None, reseal=False)
        self.ok('handoff', '--file', self.brief, '--expected', 4)
        # Changing the brand by hand would bypass the revision and leave layout/stills approved: refused.
        self._rewrite_data(lambda d: d['brand'].update(mode='full'), reseal=False)
        before = self.brief.read_bytes()
        for args in (('show', '--file', self.brief, '--json'), ('handoff', '--file', self.brief, '--expected', 4),
                     ('update', '--file', self.brief, '--expected', 4, '--patch', self.patch_file({'route': 'idea'})),
                     ('approve', '--file', self.brief, '--expected', 4, '--gate', 'render', '--state', 'yes',
                      '--note', 'yes')):
            with self.subTest(cmd=args[0]):
                r = self.run_cli(*args)
                self.assertEqual(r.returncode, INVALID, r.stdout)
                self.assertIn('seal', r.stderr)
                self.assertNotIn('Traceback', r.stderr)
                self.assertEqual(self.brief.read_bytes(), before)

    def test_malformed_records_give_clean_errors(self):
        self.init()
        bad_edits = [
            lambda d: d.update(approvals=[{'gate': 'layout'}]),
            lambda d: d.update(approvals=[{'gate': 'layout', 'state': 'yes', 'status': 'current', 'note': 'x',
                                           'at': 'now', 'input_revision': 1, 'inputs': {'brand.kit': 'oops'}}]),
            lambda d: d.update(approvals=[{'gate': 'layout', 'state': 'yes', 'status': 'current', 'note': 'x',
                                           'at': 'now', 'input_revision': 1, 'inputs': {}, 'evidence': 'x.png'}]),
            lambda d: d.update(history=[{'revision': 1}]),
            lambda d: d['audio'].pop('voice'),
            lambda d: d['brand'].pop('mode'),
        ]
        original = self.brief.read_text(encoding='utf-8')
        for i, edit in enumerate(bad_edits):
            with self.subTest(edit=i):
                self.brief.write_text(original, encoding='utf-8')
                self._rewrite_data(edit, reseal=True)
                for args in (('show', '--file', self.brief, '--json'),
                             ('handoff', '--file', self.brief, '--expected', 1)):
                    r = self.run_cli(*args)
                    self.assertEqual(r.returncode, INVALID, r.stdout)
                    self.assertNotIn('Traceback', r.stderr)

    # --- review fixes: init publishing and special inputs ---------------------------------------------------------

    def test_racing_inits_publish_exactly_one_private_brief(self):
        procs = [subprocess.Popen([sys.executable, str(SCRIPT), 'init', '--out', str(self.brief), '--request',
                                   f'request {i}'], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(8)]
        codes = [p.wait(timeout=60) for p in procs]
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        self.assertEqual(codes.count(OK), 1, codes)
        d = self.data()
        self.assertRegex(d['request'], r'^request \d$')
        self.assertEqual(os.stat(self.brief).st_mode & 0o777, 0o600, 'a new brief is private to its owner')
        self.update({'route': 'idea'})
        self.assertEqual(os.stat(self.brief).st_mode & 0o777, 0o600, 'an update keeps it private')
        self.assert_only_brief()

    def test_special_inputs_are_reported_not_read(self):
        self.init()
        fifo = self.work / 'pipe.wav'
        os.mkfifo(fifo)
        self.inputs.add('pipe.wav')
        folder = self.work / 'clips'
        folder.mkdir()
        self.inputs.add('clips')
        self.update({'assets': {'pipe': {'path': fifo.name}, 'clips': {'path': folder.name},
                                'gone': {'path': 'gone.mp4'}}})
        h = self.handoff()                                           # must return, not block on the pipe
        files = {f['field']: f['status'] for f in h['files']}
        self.assertEqual(files, {'assets.clips.path': 'directory', 'assets.gone.path': 'missing',
                                 'assets.pipe.path': 'not a regular file'})
        self.assertIn('pipe.wav', ' '.join(h['unresolved']))

    # --- source code assets: the files that build an approved layout ---------------------------------------------

    def source_job(self):
        """sound_job plus one role=source scene file, with stills, render and listening approved on it."""
        self.sound_job('narration')
        scene = self.media('scene.js', b'// synthetic scene code v1')
        self.update({'assets': {'scene': {'path': scene.name, 'role': 'source'}}})
        for gate in ('stills', 'render', 'listening'):
            self.approve(gate)
        return scene

    def test_adding_source_code_after_layout_keeps_layout_but_reopens_stills_render_listening(self):
        # Code written to build an approved layout does not change that layout, but the frames it draws are new.
        self.sound_job('narration')
        scene = self.media('scene.js', b'// synthetic scene code v1')
        self.update({'assets': {'scene': {'path': scene.name, 'role': 'source'}}})
        self.assertEqual(self.current(), {'layout': 'yes', 'voice-choice': 'yes', 'music-choice': 'yes'})
        self.assertEqual({a['gate'] for a in self.invalidated()}, {'stills', 'render', 'listening'})
        h = self.handoff()
        self.assertEqual(h['next_gate'], 'stills')
        row = {f['field']: f for f in h['files']}['assets.scene.path']
        self.assertEqual((row['area'], row['status'], row['sha256']), ('source', 'ok', sha(scene)))
        # With only layout approved, more source code still leaves it alone; stills are fingerprinted with it.
        self.approve('stills')
        css = self.media('scene.css', b'/* synthetic styles v1 */')
        self.update({'assets': {'css': {'path': css.name, 'role': 'source'}}})
        self.assertEqual(self.current(), {'layout': 'yes', 'voice-choice': 'yes', 'music-choice': 'yes'})
        self.approve('stills')
        stills = [a for a in self.data()['approvals'] if a['gate'] == 'stills' and a['status'] == 'current'][0]
        self.assertEqual(stills['inputs']['assets.css.path']['sha256'], sha(css))
        # Removing a source reopens what was drawn with it, not the layout.
        self.approve('render')
        self.update({'assets': {'css': None}})
        self.assertEqual(self.current(), {'layout': 'yes', 'voice-choice': 'yes', 'music-choice': 'yes'})

    def test_source_bytes_changing_on_disk_make_stills_render_listening_stale_not_layout(self):
        scene = self.source_job()
        self.assertTrue(self.handoff()['may_render'])
        scene.write_bytes(b'// synthetic scene code v2')
        h = self.handoff()
        stale = {g for g, a in h['approvals'].items() if a['stale']}
        self.assertEqual(stale, {'stills', 'render', 'listening'})
        self.assertIn('assets.scene.path', ' '.join(h['approvals']['render']['stale_reasons']))
        row = {f['field']: f for f in h['files']}['assets.scene.path']
        self.assertEqual((row['status'], row['sha256']), ('changed', sha(scene)))
        self.assertFalse(h['may_render'])
        self.assertEqual(h['next_gate'], 'stills')
        self.approve('render', expect=REFUSED)                       # stale stills do not count
        for gate in ('stills', 'render', 'listening'):
            self.approve(gate)
        self.assertTrue(self.handoff()['may_render'])
        # A source that goes missing blocks the render too.
        scene.unlink()
        h = self.handoff()
        self.assertEqual({g for g, a in h['approvals'].items() if a['stale']}, {'stills', 'render', 'listening'})
        self.assertIn('scene.js', ' '.join(h['unresolved']))
        self.assertFalse(h['may_render'])

    def test_creative_assets_and_role_switches_still_reopen_layout(self):
        self.sound_job('narration')
        logo = self.media('logo.png', b'synthetic logo v1')
        self.update({'assets': {'logo': {'path': logo.name, 'role': 'end card'}}})
        self.assertEqual(self.current(), {'voice-choice': 'yes', 'music-choice': 'yes'})
        for gate in ('layout', 'stills', 'render', 'listening'):
            self.approve(gate)
        logo.write_bytes(b'synthetic logo v2')
        self.assertTrue(self.handoff()['approvals']['layout']['stale'], 'a changed image still changes the layout')
        logo.write_bytes(b'synthetic logo v1')
        self.assertFalse(self.handoff()['approvals']['layout']['stale'])
        # Turning a creative asset into source code, or back, is not a code-only change.
        for role in ('source', 'end card'):
            with self.subTest(role=role):
                self.update({'assets': {'logo': {'role': role}}})
                self.assertEqual(self.current(), {'voice-choice': 'yes', 'music-choice': 'yes'})
                for gate in ('layout', 'stills', 'render', 'listening'):
                    self.approve(gate)
        # Only the exact role "source" marks build code.
        near = self.media('near.js', b'// synthetic near miss')
        self.update({'assets': {'near': {'path': near.name, 'role': 'Source'}}})
        self.assertEqual(self.current(), {'voice-choice': 'yes', 'music-choice': 'yes'})

    def test_notes_on_a_source_asset_keep_every_approval(self):
        self.source_job()
        before = self.data()['approvals']
        self.update({'assets': {'scene': {'notes': 'synthetic note: written by the test builder, MIT'}}})
        self.assertEqual(self.data()['approvals'], before)
        self.assertTrue(self.handoff()['may_render'])

    def test_a_folder_named_as_a_file_input_blocks_the_render_but_a_brand_kit_folder_does_not(self):
        self.init()
        kit = self.base / 'brand-kit'
        kit.mkdir()
        (kit / 'inner-secret.txt').write_text('not to be scanned')
        self.update({'route': 'idea', 'brand': {'mode': 'full', 'kit': str(kit)}, 'style': {'name': 'test look'},
                     'destination': {'aspect': '16:9', 'duration_seconds': 8}, 'story': {'summary': 'test story'},
                     'audio': {'timing_driver': 'visual', 'voice': {'choice': 'none'}, 'music': {'choice': 'none'},
                               'effects': {'choice': 'none'}}})
        for gate in ('layout', 'stills', 'render'):
            self.approve(gate)
        self.approve('listening', state='n/a', note='silent test video')
        h = self.handoff()
        self.assertEqual(h['unresolved'], [])
        self.assertTrue(h['may_render'], 'a brand kit folder is a pointer, not a missing file')
        self.assertNotIn('inner-secret', json.dumps(h))
        folder = self.work / 'scene-folder'
        folder.mkdir()
        self.inputs.add('scene-folder')
        cases = [
            ('assets.src.path', {'assets': {'src': {'path': folder.name, 'role': 'source'}}},
             {'assets': {'src': None}}),
            ('assets.clip.path', {'assets': {'clip': {'path': folder.name, 'role': 'footage'}}},
             {'assets': {'clip': None}}),
            ('style.reference.code_file', {'style': {'reference': {'code_file': folder.name}}},
             {'style': {'reference': None}}),
            ('audio.effects.path', {'audio': {'effects': {'choice': 'supplied', 'path': folder.name}}},
             {'audio': {'effects': {'choice': 'none'}}}),
        ]
        for field, patch, undo in cases:
            with self.subTest(field=field):
                self.update(patch)
                for gate in ('layout', 'stills'):
                    if gate not in self.current():
                        self.approve(gate)
                self.approve('render', expect=REFUSED)
                h = self.handoff()
                self.assertEqual({f['field']: f['status'] for f in h['files']}[field], 'directory')
                self.assertIn(field, ' '.join(h['unresolved']))
                self.assertFalse(h['may_render'])
                self.update(undo)
        # A source entry with no file cannot be final either.
        self.update({'assets': {'src': {'role': 'source'}}})
        self.assertIn('assets.src', ' '.join(self.handoff()['unresolved']))

    def test_help_is_available(self):
        for cmd in ([], ['init'], ['update'], ['approve'], ['show'], ['handoff']):
            r = self.run_cli(*cmd, '--help')
            self.assertEqual(r.returncode, OK, cmd)
            self.assertIn('usage', r.stdout)


if __name__ == '__main__':
    unittest.main()
