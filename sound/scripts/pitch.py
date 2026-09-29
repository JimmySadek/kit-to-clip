#!/usr/bin/env python3
"""Kit to Clip pitch: which note is a sound effect? So a tuned effect never lands out of key against the music.

  pitch.py measure <audio> [<audio> ...]                       note and fundamental frequency of each file
  pitch.py index   <sfx-dir> [--out sfx-pitch.json]           measure every audio file in a folder, write the index
  pitch.py check   --key "A minor" <audio> [<audio> ...]      say which files are outside the key (exit 1 if any)

The fundamental is found with a harmonic product spectrum: the spectrum is multiplied by itself squeezed by 2, 3 and 4,
so only a frequency whose overtones are also present survives. Counting raw spectral peaks would take an overtone for
a note (a saw wave on A has C# as its fifth harmonic). A file with no stable, clear pitch (a whoosh, a click, an impact)
is reported as `untuned`: it fits any key. A sound can hold two notes (`notes`); all of them must be in key.
Never pitch-shift a library effect to make it fit: build a note in key instead (effects.py, kind "note").

Needs numpy and ffmpeg (the video engine's Python has numpy: source <kit-to-clip>/scripts/env.sh first).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 48000
NOTE_NAMES = "C C# D D# E F F# G G# A A# B".split()
FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10]}
AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".aif", ".aiff"}


def parse_key(key):
    """'A minor', 'C# major', 'Bb major' or {'tonic': 'A', 'mode': 'minor'} -> (name, set of pitch classes 0-11)."""
    if isinstance(key, dict):
        tonic, mode = key.get("tonic", ""), key.get("mode", "")
    else:
        parts = str(key).split()
        tonic, mode = (parts + ["", ""])[:2]
    tonic = FLATS.get(tonic.capitalize(), tonic.upper() if len(tonic) == 1 else tonic[:1].upper() + tonic[1:])
    if tonic not in NOTE_NAMES or mode.lower() not in SCALES:
        raise ValueError(f'key "{key}" is not understood: use a note and "major" or "minor", like "A minor"')
    root = NOTE_NAMES.index(tonic)
    return f"{tonic} {mode.lower()}", {(root + i) % 12 for i in SCALES[mode.lower()]}


def midi_name(m):
    return f"{NOTE_NAMES[int(m) % 12]}{int(m) // 12 - 1}"


def read_audio(path, sr=SR):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    if r.returncode or not r.stdout:
        raise RuntimeError(f"could not read {path}")
    return np.frombuffer(r.stdout, np.float32).astype(float)


def fundamental(x, sr=SR, fmin=150.0, fmax=3000.0):
    """(frequency in Hz, how clear the pitch is) of a short sound. Clearness is the share of the spectrum's energy that
    sits on the fundamental and its overtones: near 1 for a note, low for noise."""
    n = len(x)
    m = np.abs(np.fft.rfft(x * np.hanning(n), n=8 * n))
    freqs = np.fft.rfftfreq(8 * n, 1 / sr)
    hps = m.copy()
    for h in (2, 3, 4):
        hps[: len(m) // h] *= m[::h][: len(m) // h]
    band = (freqs > fmin) & (freqs < fmax)
    k = int(np.argmax(np.where(band, hps, 0)))
    f0 = float(freqs[k])
    # A tone with no overtones can make the product settle on a third or a half of its real frequency. Trust a lower
    # frequency only if it carries sound of its own: else the strongest peak is the note.
    p = int(np.argmax(np.where(band, m, 0)))
    near = (freqs > f0 * 0.97) & (freqs < f0 * 1.03)
    if freqs[p] > f0 * 1.4 and m[near].max() < 0.15 * m[p]:
        k, f0 = p, float(freqs[p])
    width = max(2, int(8 * 20 * n / sr / 1))                      # about +-20 Hz in bins
    harm = sum(m[max(0, int(round(k * h)) - width): int(round(k * h)) + width].sum() for h in (1, 2, 3, 4) if int(round(k * h)) < len(m))
    return f0, float(harm / (m.sum() + 1e-12))


TONAL_CLEARNESS = 0.18      # share of the spectrum on the fundamental and its overtones; calibrated on the 19 media-use effects:
                            # chime .71, notification .88, ping .62, error .27, sparkle .19 are notes; whooshes (.17 and lower),
                            # glitches, typing, key presses and impacts are not
TONAL_STABLE = 0.60         # and the same note in at least this share of the sound's loud stretches


def measure(path):
    """Note(s) of one effect. The sound is read in 120 ms stretches; each loud stretch gives a note (harmonic product
    spectrum). A tuned effect keeps one note (`note`), and may flash a second (`notes` lists every note that holds at
    least 15% of the sound: a sparkle sustains G and flashes C). `fundamental_hz` is the median for the main note."""
    a = read_audio(path)
    win, hop = int(0.12 * SR), int(0.06 * SR)
    stretches = [a[i:i + win] for i in range(0, max(1, len(a) - win + 1), hop)] or [a]
    rms = np.array([np.sqrt((x ** 2).mean()) for x in stretches])
    loud = [x for x, r in zip(stretches, rms) if r >= 0.1 * rms.max() and len(x) >= win // 2]
    found = []
    for x in loud:
        f0, clear = fundamental(x)
        found.append((f0, clear, int(round(12 * np.log2(f0 / 440) + 69)) % 12))
    counts = np.bincount([pc for _, _, pc in found], minlength=12) / max(1, len(found))
    main = int(np.argmax(counts))
    clear = float(np.median([c for _, c, _ in found]))
    tuned = bool(clear >= TONAL_CLEARNESS and counts[main] >= TONAL_STABLE)
    hz = float(np.median([f for f, _, pc in found if pc == main]))
    out = {"file": Path(path).name, "tuned": tuned, "clearness": round(clear, 2)}
    if tuned:
        out.update(note=NOTE_NAMES[main], fundamental_hz=round(hz, 1),
                   notes=[NOTE_NAMES[i] for i in np.argsort(-counts) if counts[i] >= 0.15])
    else:
        out.update(note=None, fundamental_hz=None, notes=[])
    return out


def cmd_measure(a):
    for f in a.files:
        r = measure(f)
        print(f"{r['file']:28s} " + (f"{r['note']:3s} {r['fundamental_hz']:8.1f} Hz notes {'+'.join(r['notes'])} (clearness {r['clearness']})"
                                     if r["tuned"] else f"untuned (clearness {r['clearness']})"))


def cmd_index(a):
    d = Path(a.dir)
    files = sorted(f for f in d.iterdir() if f.suffix.lower() in AUDIO)
    if not files:
        print(f"pitch: no audio files in {d}", file=sys.stderr)
        sys.exit(2)
    out = {"_about": "Fundamental frequency and note of each effect, measured with a harmonic product spectrum by "
                     "sound/scripts/pitch.py. Untuned effects fit any key.", "effects": {}}
    for f in files:
        r = measure(f)
        out["effects"][f.stem] = {k: r[k] for k in ("file", "tuned", "note", "notes", "fundamental_hz", "clearness")}
        print(f"{f.name:28s} " + (f"{r['note']:3s} {r['fundamental_hz']:8.1f} Hz notes {'+'.join(r['notes'])}" if r["tuned"] else "untuned"))
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(f"wrote {a.out}")


def cmd_check(a):
    try:
        name, pcs = parse_key(a.key)
    except ValueError as e:
        print(f"pitch: {e}", file=sys.stderr)
        sys.exit(2)
    bad = 0
    for f in a.files:
        r = measure(f)
        if not r["tuned"]:
            print(f"✓ {r['file']}: untuned, fits {name}")
        elif all(NOTE_NAMES.index(n) in pcs for n in r["notes"]):
            print(f"✓ {r['file']}: {'+'.join(r['notes'])} in {name}")
        else:
            bad += 1
            out = [n for n in r["notes"] if NOTE_NAMES.index(n) not in pcs]
            print(f"✗ {r['file']}: {'+'.join(r['notes'])} ({r['fundamental_hz']} Hz), {'+'.join(out)} outside {name}: pick another effect or make a note in key")
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("measure"); p.add_argument("files", nargs="+")
    p = sub.add_parser("index"); p.add_argument("dir"); p.add_argument("--out", default="sfx-pitch.json")
    p = sub.add_parser("check"); p.add_argument("--key", required=True); p.add_argument("files", nargs="+")
    a = ap.parse_args()
    {"measure": cmd_measure, "index": cmd_index, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
