"""③ Voice: each take's word times, matched to the script's clean copy.

Standard library only. The words come from Parakeet (the toolbox card `parakeet`, a separate local program); tests set
KIT_TO_CLIP_TRANSCRIBE to a fake that takes the same arguments and writes the same JSON. The match runs on the clean
copy (the script without tags), so a misheard product name keeps the script's spelling and is flagged for a check.

    words file  <video>/voice/<seg>.words.json   {segment, file, engine, heard, words: [{text, start, end, flag?}], flagged}
    film.json   voice.takes[<seg>] = {file, state: timing|timed|failed, words_file, words, flagged, error?}
"""
import difflib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
TOOLBOX = HERE.parent / 'scripts' / 'toolbox.py'
AUDIO = ('.wav', '.mp3', '.m4a', '.aif', '.aiff', '.flac', '.ogg')
TAG = re.compile(r'<[^<>]*>')
TIMEOUT = 15 * 60                                  # the first run loads the model; a long take takes a while


def clean(text):
    """Spoken words only, as the Story room's clean copy: tags out, spaces tidied."""
    t = TAG.sub(' ', str(text or ''))
    t = re.sub(r'\s+([,.!?;:])', r'\1', t)
    return re.sub(r'\s+', ' ', t).strip()


def words(text):
    return [w for w in clean(text).split(' ') if re.search(r'\w', w)]


def norm(w):
    return re.sub(r'[\W_]+', '', w.lower())


def from_parakeet(data):
    """Parakeet's JSON holds sentences of sub-word tokens; a token that starts with a space starts a new word."""
    out = []
    for s in data.get('sentences') or []:
        for t in s.get('tokens') or []:
            text = t.get('text') or ''
            if not out or text[:1].isspace():
                out.append({'text': text.strip(), 'start': t['start'], 'end': t['end']})
            else:
                out[-1]['text'] += text
                out[-1]['end'] = t['end']
    return [w for w in out if w['text']]


def transcriber():
    """The command that hears a file, or None when Parakeet is not installed."""
    fake = os.environ.get('KIT_TO_CLIP_TRANSCRIBE')
    if fake:
        return shlex.split(fake), 'fake'
    r = subprocess.run([sys.executable, str(TOOLBOX), 'path', 'parakeet', 'cli'], text=True, capture_output=True, timeout=30)
    cli = r.stdout.strip()
    return ([cli], 'parakeet') if r.returncode == 0 and cli and Path(cli).is_file() else (None, None)


def hear(audio):
    """Run the transcriber on one file; returns (words, engine). Raises RuntimeError with a plain reason."""
    cmd, engine = transcriber()
    if not cmd:
        raise RuntimeError('Parakeet is not installed. Claude can install it after your yes (toolbox card parakeet, '
                           'about 900 MB), or type the words in')
    with tempfile.TemporaryDirectory(prefix='k2c-voice-') as out:
        r = subprocess.run(cmd + [str(audio), '--output-format', 'json', '--output-dir', out], text=True,
                           capture_output=True, timeout=TIMEOUT)
        made = Path(out) / (Path(audio).stem + '.json')
        if r.returncode or not made.is_file():
            last = (r.stderr or r.stdout).strip().splitlines()[-1:] or ['no output']
            raise RuntimeError(f'the transcriber stopped: {last[0][:300]}')
        return from_parakeet(json.loads(made.read_text(encoding='utf-8'))), engine


def align(script_text, heard):
    """Each clean-copy word with the time it was heard. A word heard differently but in its place keeps its time and is
    flagged; a word not heard at all gets the span around it and is flagged."""
    want = words(script_text)
    a, b = [norm(w) for w in want], [norm(h['text']) for h in heard]
    rows = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == 'equal' or (op == 'replace' and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                h = heard[j1 + k]
                row = {'text': want[i1 + k], 'start': h['start'], 'end': h['end']}
                if op == 'replace':
                    row['flag'] = f'heard as "{h["text"]}"'
                rows.append(row)
        elif op in ('replace', 'delete'):
            lo = heard[j1]['start'] if j1 < j2 else (heard[j1 - 1]['end'] if j1 else 0.0)
            hi = heard[j2 - 1]['end'] if j1 < j2 else (heard[j1]['start'] if j1 < len(heard) else lo)
            step = (hi - lo) / (i2 - i1)
            for k in range(i2 - i1):
                rows.append({'text': want[i1 + k], 'start': round(lo + k * step, 3), 'end': round(lo + (k + 1) * step, 3),
                             'flag': 'not found' if j1 == j2 else 'heard as "' + ' '.join(h['text'] for h in heard[j1:j2]) + '"'})
    return rows


def time_take(video, seg, text, rel):
    """Hear one take and write its words file. Returns the take's new fields."""
    heard, engine = hear(Path(video) / rel)
    rows = align(text, heard)
    flagged = sum(1 for r in rows if r.get('flag'))
    words_rel = f'voice/{seg}.words.json'
    doc = {'segment': seg, 'file': rel, 'engine': engine, 'heard': ' '.join(h['text'] for h in heard), 'words': rows,
           'flagged': flagged, 'length': heard[-1]['end'] if heard else 0}
    path = Path(video) / words_rel
    fd, tmp = tempfile.mkstemp(prefix='.words-', dir=path.parent)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=False) + '\n')
    os.replace(tmp, path)
    return {'state': 'timed', 'words_file': words_rel, 'words': len(rows), 'flagged': flagged,
            'heard_words': len(heard), 'engine': engine}
