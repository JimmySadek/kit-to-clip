#!/usr/bin/env python3
"""Kit to Clip score: original music made offline, in any key, in four styles. An option, never a requirement: a track
you bring, or the library, works as well. Everything is synthesised (no samples, no licences), so it is a good bed,
not a produced record.

  score.py styles                                   the styles, with their default tempo and key
  score.py preview --out <dir>                      a 4-bar preview of every style, to listen to and choose from
  score.py make --style pulse --out <dir> [--bpm 128] [--key "A minor"] [--bars 8] [--sections hook:2,build:2,drop:3,end:1]
                [--progression 1,1,6,7] [--seed 1] [--lufs -18] [--stems]
        writes <dir>/music.wav and <dir>/score.json. score.json is the one source of timing: bpm, sections and cues in
        beats (beat n is at n x 60 / bpm seconds). Time the picture to it, then trace the picture and make the effects.
  score.py mix <music.wav> <sfx.wav> --out mix.wav [--music-db 0] [--sfx-db 0] [--lufs -15]
        sums music and effects, sets the level and limits true peak at -3 dBTP, so the render (which turns down any
        track whose peaks are hot) leaves it alone.
  score.py analyze <audio>                          length, loudness, peak, how busy, how bright, bass share

Whole bars: the video is exactly bars x 4 beats, so 15 s is 8 bars at 128 bpm and 12 s is 6 bars at 120. Every tonal
note is built from the key's scale and asserted in key; a note outside it stops the build. The structure is four
sections: hook (the opening), build (rising), drop (the biggest moment and its lift), end (a final hit and its tail).

Needs numpy and scipy (the video engine's Python has both: source <kit-to-clip>/scripts/env.sh first).
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.ndimage import minimum_filter1d
from scipy.signal import fftconvolve

sys.path.insert(0, str(Path(__file__).resolve().parent))
import effects as fx  # noqa: E402
import pitch  # noqa: E402

SR = 48000
db = lambda x: 10 ** (x / 20.0)
PEAK_CEILING_DB = -3.0                # true peak of everything this writes: the render lowers a track over -1.0 dBFS after AAC

STYLES = {
    "pulse": {"about": "energetic electronic: a heartbeat, a rising build, a four-on-the-floor drop with an arpeggio",
              "bpm": 128, "key": "A minor", "progression": {"minor": [1, 1, 6, 7, 1, 6, 3, 1], "major": [1, 1, 6, 4, 1, 5, 6, 1]}},
    "calm": {"about": "calm ambient: a slow pad that opens, a soft bell arpeggio, a low drone, a gentle pulse only at the drop",
             "bpm": 90, "key": "D major", "progression": {"minor": [1, 6, 3, 7], "major": [1, 5, 6, 4]}},
    "uplift": {"about": "bright and positive: piano-like chord stabs, a light kick and claps, an airy arpeggio",
               "bpm": 118, "key": "G major", "progression": {"minor": [1, 6, 3, 7], "major": [1, 5, 6, 4]}},
    "cinematic": {"about": "slow and big: a low drone and strings, drum hits, one long crescendo, a huge final hit",
                  "bpm": 76, "key": "D minor", "progression": {"minor": [1, 6, 3, 7], "major": [1, 5, 6, 4]}},
}


class ScoreError(Exception):
    pass


# ---------------------------------------------------------------- the song: time, key, chords
class Song:
    def __init__(self, style, bpm, bars, key, sections, progression, seed):
        self.style, self.bpm, self.bars = style, bpm, bars
        self.BT = 60.0 / bpm
        self.BAR = 4 * self.BT
        self.T = bars * self.BAR
        self.N = int(round(self.T * SR))
        self.key_name, self.pcs = pitch.parse_key(key)
        tonic, mode = self.key_name.split()
        self.mode = mode
        self.tonic_pc = pitch.NOTE_NAMES.index(tonic)
        self.semis = pitch.SCALES[mode]
        self.prog = progression
        self.rng = np.random.default_rng(seed)
        self.t = np.arange(self.N) / SR
        self.b = {"hook": 0}                                   # section start beats
        beat = 0
        for name, nb in sections:
            self.b[name] = beat
            beat += nb * 4
        self.b["total"] = beat
        self.sections = sections
        self.notes_used = set()
        self.IR = self._ir()

    def B(self, n):
        return n * self.BT

    def at(self, t):
        return int(round(t * SR))

    def stereo(self):
        return np.zeros((self.N, 2))

    def midi(self, degree, octave):
        """MIDI note of a scale degree (0 = the tonic, 7 = the tonic an octave up) with the tonic at `octave`."""
        o, d = divmod(degree, 7)
        return 12 * (octave + 1) + self.tonic_pc + self.semis[d] + 12 * o

    def note(self, m):
        assert m % 12 in self.pcs, f"note {pitch.midi_name(m)} is outside {self.key_name}"
        self.notes_used.add(int(m))
        return m

    def hz(self, m):
        return 440.0 * 2 ** ((self.note(m) - 69) / 12.0)

    def chord_degs(self, bar):
        d = self.prog[bar % len(self.prog)] - 1
        return [d, d + 2, d + 4]

    def chord_name(self, bar):
        d = self.prog[bar % len(self.prog)] - 1
        s = [self.midi(d + k, 0) % 12 for k in (0, 2, 4)]
        root = pitch.NOTE_NAMES[s[0]]
        third, fifth = (s[1] - s[0]) % 12, (s[2] - s[0]) % 12
        return root + ("dim" if fifth == 6 else "m" if third == 3 else "")

    def add(self, buf, x, t, g=1.0, pan=0.0):
        s = self.at(t)
        if s >= self.N:
            return
        if s < 0:
            x, s = x[-s:], 0
        e = min(self.N, s + len(x))
        x = x[: e - s]
        if x.ndim == 1:
            x = np.stack([x * (1 - max(0, pan)), x * (1 + min(0, pan))], axis=1)
        buf[s:e] += x * g

    def curve(self, pts):
        """A value that moves over the piece: pts = [(beat, value), ...], one value per sample."""
        return np.interp(self.t, [self.B(b) for b, _ in pts], [v for _, v in pts])

    def _ir(self, sec=1.8, bright=5000):
        n = int(sec * SR)
        tt = np.arange(n) / SR
        ir = np.random.default_rng(7).standard_normal((n, 2)) * np.exp(-tt / (sec / 5.5))[:, None]
        ir = signal.sosfilt(signal.butter(2, bright, "low", fs=SR, output="sos"), ir, axis=0)
        ir[: int(0.012 * SR)] = 0
        return ir / np.sqrt((ir ** 2).sum(axis=0))

    def verb(self, x, wet):
        return fftconvolve(x, self.IR, axes=0)[: len(x)] * wet


# ---------------------------------------------------------------- the kit of sounds
def env_adsr(n, a, d, s, r, sus_len):
    e = np.zeros(n)
    A, D, R, L = int(a * SR), int(d * SR), int(r * SR), int(sus_len * SR)
    i = 0
    for seg in (np.linspace(0, 1, max(1, A), endpoint=False), np.linspace(1, s, max(1, D), endpoint=False)):
        k = min(len(seg), n - i)
        e[i:i + k] = seg[:k]
        i += k
    k = max(0, min(L - i, n - i))
    e[i:i + k] = s
    i += k
    k = min(R, n - i)
    e[i:i + k] = np.linspace(s, 0, max(1, R))[:k]
    return e


def kick(rng, g=1.0, click=0.4):
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t / 0.035)) / SR) * np.exp(-t / 0.16)
    k = int(0.004 * SR)
    y[:k] += signal.sosfilt(signal.butter(2, 3000, "high", fs=SR, output="sos"), rng.standard_normal(k)) * click
    return y * g


def clap(rng):
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    e = np.zeros(n)
    for k, o in enumerate([0, 0.011, 0.022]):
        s = int(o * SR)
        e[s:] += np.exp(-t[: n - s] / (0.012 if k < 2 else 0.12))
    return signal.sosfilt(signal.butter(2, [900, 5500], "bandpass", fs=SR, output="sos"), rng.standard_normal(n)) * e


def hat(rng, open_=False):
    n = int((0.22 if open_ else 0.05) * SR)
    t = np.arange(n) / SR
    return signal.sosfilt(signal.butter(4, 7000, "high", fs=SR, output="sos"), rng.standard_normal(n)) * np.exp(-t / (0.07 if open_ else 0.012))


def shaker(rng):
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    return signal.sosfilt(signal.butter(2, [5000, 11000], "bandpass", fs=SR, output="sos"), rng.standard_normal(n)) * np.exp(-t / 0.018) * np.minimum(1, t / 0.006)


def crash(rng, length=2.2):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = signal.sosfilt(signal.butter(2, 4500, "high", fs=SR, output="sos"), rng.standard_normal((n, 2)), axis=0)
    return x * (np.exp(-t / 0.6) * (1 - np.exp(-t / 0.002)))[:, None]


def reverse_cymbal(rng, length, cut=3500, decay=0.35):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = signal.sosfilt(signal.butter(2, cut, "high", fs=SR, output="sos"), rng.standard_normal((n, 2)), axis=0)
    return x * np.exp(-(t[::-1]) / decay)[:, None]


def riser(s, start_beat, end_beat, lo=300, hi=8000, tonal_deg=None, octave=1):
    """Noise that sweeps up (and, if asked, a rising saw pair on the tonic), swelling to the end."""
    buf = s.stereo()
    n = s.at(s.B(end_beat) - s.B(start_beat))
    tt = np.arange(n) / SR
    x = fx.filt_sweep(s.rng.standard_normal((n, 2)), lo * (hi / lo) ** (tt / tt[-1]), "bandpass", q_bw=1.5) * ((tt / tt[-1]) ** 2.2)[:, None]
    s.add(buf, x, s.B(start_beat), 0.5)
    if tonal_deg is not None:
        for k in (0, 1):
            m = s.midi(tonal_deg, octave + k)
            s.hz(m)
            y = fx.saw(s.hz(m) * 2 ** (tt / tt[-1]), n) * (tt / tt[-1]) ** 2.5 * 0.08
            s.add(buf, np.stack([y, y], axis=1), s.B(start_beat), 1.0)
    return buf


def pad_layer(s, octave, attack, release, cut_pts, gain_pts, level=0.12, detune=7, voices=2, add_octave=False):
    """A chord pad, bar by bar: detuned saws, a filter that opens and closes with the story, a level that follows it."""
    buf = s.stereo()
    for bar in range(s.bars):
        t0, n = bar * s.BAR, int(s.BAR * SR) + int((release + 0.1) * SR)
        ms = [s.midi(d, octave) for d in s.chord_degs(bar)]
        if add_octave:
            ms.append(s.midi(s.chord_degs(bar)[0] + 7, octave))
        for m in ms:
            f0 = s.hz(m)
            for side, det in ((0, -detune), (1, detune)):
                for d2 in ([0, det * 0.5][:voices]):
                    x = fx.saw(f0 * 2 ** (d2 / 1200), n) * level * env_adsr(n, attack, 0.2, 0.9, release, s.BAR)
                    a = s.at(t0)
                    seg = x[: max(0, min(n, s.N - a))]
                    buf[a:a + len(seg), side] += seg
    buf = fx.filt_sweep(buf, s.curve(cut_pts))
    return buf * s.curve(gain_pts)[:, None]


def drone_layer(s, degree, octave, cut_pts, gain_pts, level=0.5):
    """One low note held for the whole piece (saw and sine), its brightness and level following the story."""
    m = s.midi(degree, octave)
    f = s.hz(m)
    x = (fx.saw(f, s.N) * 0.35 + np.sin(2 * np.pi * f * s.t) * 0.55) * level
    x = fx.filt_sweep(x[:, None], s.curve(cut_pts))[:, 0] * s.curve(gain_pts)
    return np.stack([x, x], axis=1)


def bass_note(s, buf, m, t, length_beats, cutoff, g, decay=0.09):
    n = int(s.BT * length_beats * SR)
    tt = np.arange(n) / SR
    f = s.hz(m)
    y = fx.filt_sweep((fx.saw(f, n) * 0.4 + np.sin(2 * np.pi * f * tt) * 0.45)[:, None], np.full(n, float(cutoff)))[:, 0] * np.exp(-tt / decay)
    s.add(buf, y, t, g)


def arp_layer(s, beats, octave, gain, wet, echo=True, sparse=None, pattern=(0, 1, 2, 1, 3, 2, 1, 2), bright=5.0, bell_mix=0.0):
    """A plucked arpeggio of the chord tones (and the tonic an octave up) at each beat in `beats`, bouncing left and right."""
    buf = s.stereo()
    for k, b in enumerate(beats):
        if sparse is not None and (k % len(sparse)) not in sparse:
            continue
        bar = int(b // 4)
        degs = s.chord_degs(bar) + [s.chord_degs(bar)[0] + 7]
        m = s.midi(degs[pattern[k % len(pattern)] % 4], octave)
        pan = -0.35 if k % 2 else 0.35
        s.add(buf, fx.pluck(s.note(m), 0.5, bright), s.B(b), gain, pan)
        if bell_mix:
            s.add(buf, fx.bell(s.note(m + 12), 0.6), s.B(b), gain * bell_mix, -pan)
    out = buf
    if echo:
        e = s.stereo()
        d = s.at(0.75 * s.BT)
        for r in range(1, 4):
            e[d * r:, 0] += buf[:-d * r, 1] * 0.35 ** r
            e[d * r:, 1] += buf[:-d * r, 0] * 0.35 ** r
        out = buf + e
    return out + s.verb(buf, wet)


def sidechain(s, kick_times, depth=0.45):
    side = np.ones(s.N)
    for tk in kick_times:
        a, n = s.at(tk), min(s.N - s.at(tk), s.at(0.3))
        if n > 0:
            side[a:a + n] = np.minimum(side[a:a + n], 1 - depth * np.exp(-np.arange(n) / SR / 0.09))
    return signal.sosfiltfilt(signal.butter(1, 40, "low", fs=SR, output="sos"), side)


def rising(a, b, i, n):                                  # a value that climbs from a to b over n steps
    return a + (b - a) * i / max(1, n)


# ---------------------------------------------------------------- the styles
def style_pulse(s):
    b1, b2, b3, T = s.b["build"], s.b["drop"], s.b["end"], s.b["total"]
    rng = s.rng
    stems = {}
    stems["pad"] = pad_layer(s, 3, 0.12, 0.3, [(0, 500), (b1, 700), (b2 - 0.5, 3600), (b2, 5200), (b3, 6000), (b3 + 0.2, 3000), (T, 1200)],
                             [(0, 0), (0.5, 0.55), (b1, 0.6), (b2 - 0.2, 0.85), (b2 - 0.19, 0.2), (b2, 0.9), (b3, 1.0), (T, 0)], add_octave=True)
    dr, kicks = s.stereo(), []
    K = lambda b, g=1.0: (s.add(dr, kick(rng, g), s.B(b)), kicks.append(s.B(b)))
    for b in range(0, b1, 4):
        K(b, 0.7)                                                     # hook: a heartbeat on each bar
    half = b1 + (b2 - b1) / 2
    for b in np.arange(b1, half, 1):
        K(b, 0.8)                                                     # build, first half: quarters
    for b in np.arange(half, b2 - 0.5, 0.5):
        K(b, 0.85)                                                    # build, second half: eighths
    roll = np.arange(half, b2, 0.25)
    for i, b in enumerate(roll):
        s.add(dr, clap(rng), s.B(b), 0.15 + 0.55 * i / len(roll))     # a rising clap roll
    for b in range(b2, b3):
        K(b, 1.0)                                                     # drop: four on the floor
    for b in np.arange(b2 + 1, b3, 2):
        s.add(dr, clap(rng), s.B(b), 0.6)
    for b in np.arange(b2, b3, 0.5):
        s.add(dr, hat(rng, open_=(b % 1 == 0.5)), s.B(b), 0.18 if b % 1 else 0.12, 0.3 if b % 1 else -0.2)
    K(b3, 1.1)                                                        # the final hit
    for tb in (b2, b2 + (b3 - b2) / 2, b3):
        s.add(dr, crash(rng), s.B(tb), 0.28)
    stems["drums"] = dr + s.verb(dr, 0.12)
    bs = s.stereo()
    root = lambda bar, o: s.midi(s.chord_degs(bar)[0], o)
    for b in np.arange(0, b1, 0.5):
        bass_note(s, bs, root(int(b // 4), 2), s.B(b), 0.45, 420, 0.55 if b % 1 == 0 else 0.35)
    for b in np.arange(b1, b2 - 0.25, 0.25):
        bass_note(s, bs, root(int(b // 4), 2), s.B(b), 0.22, 400 + 1400 * (b - b1) / (b2 - b1), 0.35 + 0.25 * (b - b1) / (b2 - b1), 0.05)
    for b in np.arange(b2, b3, 0.5):
        bass_note(s, bs, root(int(b // 4), 2), s.B(b), 0.48, 1100, 0.75 if b % 1 else 0.5, 0.14)
    for tb, deg_o, ln in ((b2, 1, 1.8), (b3, 1, 2.0)):
        s.add(bs, fx.boom(s.note(root(int(tb // 4) if tb < b3 else s.bars - 1, deg_o)), rng, ln), s.B(tb), 0.9)
    stems["bass"] = bs
    stems["arp"] = arp_layer(s, np.arange(b2, b3, 0.5), 5, 0.16, 0.2)
    fm = riser(s, b1, b2 - 0.25, tonal_deg=0)
    s.add(fm, reverse_cymbal(rng, s.B(2)), s.B(b2) - s.B(2), 0.35)
    s.add(fm, reverse_cymbal(rng, s.B(2)), s.B(b3) - s.B(2), 0.25)
    stems["fx"] = fx.filt_sweep(fm, np.full(s.N, 12000.0))
    return stems, {"pad": -9, "bass": -7, "drums": -6, "arp": -10, "fx": -8}, [t for t in kicks if t >= s.B(b2) - 1e-6], ("pad", "bass", "arp")


def style_calm(s):
    b1, b2, b3, T = s.b["build"], s.b["drop"], s.b["end"], s.b["total"]
    rng = s.rng
    stems = {}
    stems["pad"] = pad_layer(s, 3, 0.9, 1.2, [(0, 350), (b1, 700), (b2, 1800), (b3, 2600), (T, 900)],
                             [(0, 0), (2, 0.5), (b1, 0.6), (b2, 0.85), (b3, 0.9), (T, 0)], level=0.13, detune=9, add_octave=True)
    stems["drone"] = drone_layer(s, 0, 2, [(0, 200), (b2, 500), (T, 300)], [(0, 0), (2, 0.5), (b2, 0.7), (b3, 0.8), (T, 0)], level=0.4)
    stems["arp"] = arp_layer(s, np.arange(b1 + 4, b3, 0.5), 5, 0.12, 0.35, sparse=(0, 3, 5), pattern=(0, 2, 1, 3, 2, 1), bright=3.0, bell_mix=0.4)
    bl = s.stereo()
    for i, bar in enumerate(range(int(b2 // 4), int(b3 // 4))):
        for d in s.chord_degs(bar):
            s.add(bl, fx.bell(s.note(s.midi(d, 5)), 1.6), s.B(bar * 4) + 0.02 * i, 0.12 if i else 0.2, -0.3 + 0.3 * (d % 3))
    for d in s.chord_degs(int(b3 // 4)):
        s.add(bl, fx.bell(s.note(s.midi(d, 5)), 2.4), s.B(b3), 0.22, -0.2 + 0.2 * (d % 3))
    stems["bells"] = bl + s.verb(bl, 0.45)
    pc = s.stereo()
    for b in np.arange(b2, b3, 4):
        s.add(pc, kick(rng, 0.35, click=0.05), s.B(b))
    for b in np.arange(b2 + 0.5, b3, 1):
        s.add(pc, shaker(rng), s.B(b), 0.1, 0.25 if int(b) % 2 else -0.25)
    stems["pulse"] = pc
    fm = riser(s, b1, b2, lo=400, hi=3500)
    s.add(fm, reverse_cymbal(rng, s.B(3), cut=2500, decay=0.6), s.B(b2) - s.B(3), 0.18)
    stems["fx"] = fx.filt_sweep(fm * 0.5, np.full(s.N, 8000.0))
    return stems, {"pad": -8, "drone": -9, "arp": -10, "bells": -9, "pulse": -9, "fx": -12}, [], ()


def style_uplift(s):
    b1, b2, b3, T = s.b["build"], s.b["drop"], s.b["end"], s.b["total"]
    rng = s.rng
    stems = {}
    stems["pad"] = pad_layer(s, 3, 0.05, 0.25, [(0, 1500), (b1, 2500), (b2, 5000), (b3, 6000), (T, 1500)],
                             [(0, 0), (0.3, 0.4), (b1, 0.5), (b2, 0.7), (b3, 0.75), (T, 0)], level=0.1)
    st = s.stereo()
    for bar in range(s.bars):
        beat0 = bar * 4
        offs = [0, 2] if beat0 < b1 else [0, 1, 2, 3] if beat0 < b2 else [0, 1.5, 2.5] if beat0 < b3 else [0]
        for o in offs:
            for d in s.chord_degs(bar):
                s.add(st, fx.pluck(s.note(s.midi(d, 4)), 0.35, 3.0), s.B(beat0 + o), 0.13, 0.15 * (d % 3 - 1))
    stems["stabs"] = st + s.verb(st, 0.15)
    dr, kicks = s.stereo(), []
    K = lambda b, g=1.0: (s.add(dr, kick(rng, g), s.B(b)), kicks.append(s.B(b)))
    for b in np.arange(0, b1, 2):
        K(b, 0.55)
    for b in np.arange(0, b1, 0.5):
        s.add(dr, hat(rng), s.B(b), 0.1, 0.25 if b % 1 else -0.25)
    for b in np.arange(b1, b2, 1):
        K(b, 0.8)
    for b in np.arange(b1 + 1, b2, 2):
        s.add(dr, clap(rng), s.B(b), 0.45)
    for i, b in enumerate(np.arange(b2 - 4, b2, 0.25)):
        s.add(dr, clap(rng), s.B(b), 0.1 + 0.45 * i / 16)
    for b in range(int(b2), int(b3)):
        K(b, 1.0)
    for b in np.arange(b2 + 1, b3, 2):
        s.add(dr, clap(rng), s.B(b), 0.6)
    for b in np.arange(b2, b3, 0.5):
        s.add(dr, hat(rng, open_=(b % 1 == 0.5)), s.B(b), 0.16 if b % 1 else 0.1, 0.3 if b % 1 else -0.2)
    for b in np.arange(b2, b3, 0.25):
        s.add(dr, shaker(rng), s.B(b), 0.07, 0.3 * (-1 if int(b * 4) % 2 else 1))
    K(b3, 1.0)
    for tb in (b2, b3):
        s.add(dr, crash(rng), s.B(tb), 0.26)
    stems["drums"] = dr + s.verb(dr, 0.1)
    bs = s.stereo()
    rootm = lambda bar, o: s.midi(s.chord_degs(bar)[0], o)
    fifthm = lambda bar, o: s.midi(s.chord_degs(bar)[2], o)
    for b in np.arange(0, b2, 1):
        bass_note(s, bs, rootm(int(b // 4), 2), s.B(b), 0.8, 500, 0.5, 0.2)
    for i, b in enumerate(np.arange(b2, b3, 0.5)):
        m = rootm(int(b // 4), 2) if i % 2 == 0 else fifthm(int(b // 4), 2)
        bass_note(s, bs, m, s.B(b), 0.45, 1300, 0.7 if b % 1 else 0.5, 0.13)
    s.add(bs, fx.boom(s.note(rootm(int(b3 // 4) if b3 < T else s.bars - 1, 1)), rng, 1.2), s.B(b3), 0.6)
    stems["bass"] = bs
    stems["arp"] = arp_layer(s, np.arange(b2, b3, 0.25), 5, 0.1, 0.18, pattern=(0, 1, 2, 3, 2, 1, 3, 2), bright=6.0, bell_mix=0.3)
    fm = riser(s, b1, b2 - 0.25, tonal_deg=0, octave=2)
    s.add(fm, reverse_cymbal(rng, s.B(2)), s.B(b2) - s.B(2), 0.3)
    stems["fx"] = fx.filt_sweep(fm, np.full(s.N, 12000.0))
    return stems, {"pad": -10, "stabs": -8, "drums": -6, "bass": -7, "arp": -10, "fx": -9}, [t for t in kicks if t >= s.B(b2) - 1e-6], ("pad", "stabs", "bass", "arp")


def style_cinematic(s):
    b1, b2, b3, T = s.b["build"], s.b["drop"], s.b["end"], s.b["total"]
    rng = s.rng
    stems = {}
    stems["strings"] = pad_layer(s, 3, 1.2, 1.5, [(0, 500), (b1, 900), (b2, 2400), (b3, 3000), (T, 800)],
                                 [(0, 0), (2, 0.35), (b1, 0.5), (b2, 0.85), (b3, 0.9), (T, 0)], level=0.13, detune=11, add_octave=True)
    stems["drone"] = drone_layer(s, 0, 1, [(0, 180), (b2, 600), (T, 300)], [(0, 0), (2, 0.6), (b2, 0.8), (b3, 1.0), (T, 0)], level=0.7)
    hits = s.stereo()
    rootm = lambda bar, o: s.midi(s.chord_degs(bar)[0], o)
    for i, b in enumerate(np.arange(b1, b2, 1)):
        s.add(hits, fx.thump(rng), s.B(b), 0.1 + 0.5 * i / max(1, len(np.arange(b1, b2, 1))))   # soft toms swelling through the build
    for b in np.arange(b2, b3, 2):
        s.add(hits, fx.boom(s.note(rootm(int(b // 4), 2)), rng, 1.2), s.B(b), 0.6)
        s.add(hits, fx.tick(rng), s.B(b), 0.3)
    for tb, g in ((b1, 0.4), (b2, 0.9)):
        s.add(hits, fx.boom(s.note(rootm(int(tb // 4), 1)), rng, 1.8), s.B(tb), g)
    s.add(hits, fx.boom(s.note(rootm(s.bars - 1, 1)), rng, 2.4), s.B(b3), 1.0)
    s.add(hits, crash(rng, 3.0), s.B(b2), 0.3)
    s.add(hits, crash(rng, 3.5), s.B(b3), 0.4)
    stems["hits"] = hits + s.verb(hits, 0.3)
    mel = s.stereo()
    for i, bar in enumerate(range(int(b1 // 4), int(b3 // 4))):
        degs = s.chord_degs(bar)
        d = [degs[0], degs[2], degs[1]][i % 3]
        s.add(mel, fx.bell(s.note(s.midi(d + 7, 5)), 2.2), s.B(bar * 4), 0.18, 0.4 * (-1) ** i)
        s.add(mel, fx.pluck(s.note(s.midi(d, 5)), 0.6, 2.0), s.B(bar * 4), 0.08, 0.4 * (-1) ** i)
    stems["melody"] = mel + s.verb(mel, 0.5)
    fm = riser(s, b1, b2 - 0.25, lo=150, hi=6000, tonal_deg=0, octave=2)
    s.add(fm, reverse_cymbal(rng, s.B(4), cut=2500, decay=0.8), s.B(b2) - s.B(4), 0.4)
    s.add(fm, reverse_cymbal(rng, s.B(4), cut=2500, decay=0.8), s.B(b3) - s.B(4), 0.4)
    stems["fx"] = fx.filt_sweep(fm, np.full(s.N, 10000.0))
    return stems, {"strings": -9, "drone": -9, "hits": -6, "melody": -11, "fx": -9}, [], ()


BUILDERS = {"pulse": style_pulse, "calm": style_calm, "uplift": style_uplift, "cinematic": style_cinematic}


# ---------------------------------------------------------------- measuring, limiting, writing
def measure(path):
    """(integrated LUFS, true peak dBFS) of a file."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    tail = r.stderr[r.stderr.rindex("Summary"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", tail).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail).group(1))


def write_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def lufs_of(x):
    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    f.close()
    write_wav(f.name, x)
    try:
        return measure(f.name)
    finally:
        Path(f.name).unlink(missing_ok=True)


def true_peak_limit(x, ceiling_db=PEAK_CEILING_DB, look=0.005, release=0.08):
    """4x-oversampled limiter: 5 ms look-ahead, 80 ms release, instant attack."""
    up4 = signal.resample_poly(x, 4, 1, axis=0)
    pk = np.abs(up4).max(axis=1).reshape(-1, 4).max(axis=1)[: len(x)]
    need = np.minimum(1.0, db(ceiling_db) / np.maximum(pk, 1e-9))
    g = minimum_filter1d(need, size=max(1, int(look * SR)), origin=-(int(look * SR) // 2 - 1))
    a = np.exp(-1 / (release * SR))
    out, cur = np.empty_like(g), 1.0
    for i, v in enumerate(g):
        cur = v if v < cur else a * cur + (1 - a) * v
        out[i] = cur
    return x * out[:, None]


def to_level(x, target_lufs, ceiling_db=PEAK_CEILING_DB):
    """Gain to the target loudness with true peak limited at the ceiling; loops because the limiter answers the gain."""
    gain = 0.0
    for _ in range(6):
        y = true_peak_limit(x * db(gain), ceiling_db)
        i, p = lufs_of(y)
        if abs(i - target_lufs) < 0.3:
            break
        gain += target_lufs - i
    return y, i, p


def analyze(path):
    a = pitch.read_audio(path)
    dur = len(a) / SR
    i, p = measure(path)
    hop, win = 480, 1024
    frames = np.arange(0, len(a) - win, hop)
    spec = np.array([np.abs(np.fft.rfft(a[f:f + win] * np.hanning(win))) for f in frames])
    freqs = np.fft.rfftfreq(win, 1 / SR)
    e = (spec ** 2).sum(axis=1)
    centroid = float(((spec ** 2) * freqs).sum() / max((spec ** 2).sum(), 1e-12))
    flux = np.maximum(0, np.diff(np.log1p(spec * 10), axis=0)).sum(axis=1)
    thr = flux.mean() + flux.std() if len(flux) else 1                    # an onset stands out from the piece's own spread
    peaks = np.where((flux[1:-1] > flux[:-2]) & (flux[1:-1] >= flux[2:]) & (flux[1:-1] > thr))[0]
    onsets = int(1 + (np.diff(peaks) > 6).sum()) if len(peaks) else 0     # peaks closer than 60 ms are one onset
    total = max((spec ** 2).sum(), 1e-12)
    band = lambda lo, hi: float((spec[:, (freqs >= lo) & (freqs < hi)] ** 2).sum() / total)
    return {"seconds": round(dur, 2), "lufs": i, "true_peak": p, "onsets_per_second": round(onsets / dur, 1), "centroid_hz": round(centroid),
            "bass": round(band(0, 250) * 100), "mid": round(band(250, 2500) * 100), "high": round(band(2500, 24000) * 100)}


def analysis_line(r):
    return (f"{r['seconds']} s, {r['lufs']} LUFS, true peak {r['true_peak']} dBFS, {r['onsets_per_second']} onsets/s, "
            f"centroid {r['centroid_hz']} Hz, bass {r['bass']}% mid {r['mid']}% high {r['high']}%")


# ---------------------------------------------------------------- make
def default_sections(bars):
    if bars < 4:
        raise ScoreError("a score needs at least 4 bars (hook, build, drop and end)")
    hook = max(1, round(bars * 0.25))
    build = max(1, round(bars * 0.25))
    end = 1
    drop = bars - hook - build - end
    if drop < 1:
        hook, build = 1, 1
        drop = bars - 3
    return [("hook", hook), ("build", build), ("drop", drop), ("end", end)]


def parse_sections(text, bars):
    if not text:
        return default_sections(bars)
    try:
        secs = [(n.strip(), int(v)) for n, v in (part.split(":") for part in text.split(","))]
        assert [n for n, _ in secs] == ["hook", "build", "drop", "end"] and all(v >= 1 for _, v in secs)
    except (ValueError, AssertionError):
        raise ScoreError('--sections is hook:N,build:N,drop:N,end:N in that order, each at least 1 bar, like hook:2,build:2,drop:3,end:1')
    if sum(v for _, v in secs) != bars:
        raise ScoreError(f"the sections add up to {sum(v for _, v in secs)} bars, not {bars}")
    return secs


def make(style, bpm=None, key=None, bars=8, sections=None, progression=None, seed=1, lufs=-18.0, stems=False):
    if style not in STYLES:
        raise ScoreError(f"no style {style!r}. Styles: {', '.join(STYLES)}")
    st = STYLES[style]
    bpm = bpm or st["bpm"]
    if not 60 <= bpm <= 200:
        raise ScoreError("the tempo must be between 60 and 200 bpm")
    try:
        key_name, _ = pitch.parse_key(key or st["key"])
    except ValueError as e:
        raise ScoreError(str(e))
    mode = key_name.split()[1]
    prog = progression or st["progression"][mode]
    if not all(1 <= d <= 7 for d in prog):
        raise ScoreError("--progression is scale degrees from 1 to 7, like 1,6,7,3")
    s = Song(style, bpm, bars, key_name, parse_sections(sections, bars), prog, seed)
    layers, gains, kick_times, ducked = BUILDERS[style](s)
    side = sidechain(s, kick_times) if kick_times else None
    mix = np.zeros((s.N, 2))
    out = {}
    for k, x in layers.items():
        y = x * db(gains[k])
        if side is not None and k in ducked:
            y = y * side[:, None]
        out[k] = y
        mix += y
    mix *= np.clip((s.T - s.t) / 0.6, 0, 1)[:, None] ** 0.5               # the last 0.6 s: tails fade
    bus = np.sqrt(np.convolve((mix ** 2).mean(axis=1), np.ones(s.at(0.05)) / s.at(0.05), "same")) + 1e-9
    comp = signal.sosfiltfilt(signal.butter(1, 8, "low", fs=SR, output="sos"), np.minimum(1, (0.25 / bus) ** 0.35))
    mix = np.tanh(mix * comp[:, None] * 1.1) / np.tanh(1.1)
    y, i, p = to_level(mix, lufs)
    spec = {"about": "Timing for the picture, the effects and the music: everything reads these beats. Beat n is at n x 60 / bpm seconds.",
            "style": style, "bpm": bpm, "beatsPerBar": 4, "bars": bars, "duration": round(s.T, 4), "key": s.key_name,
            "scale_pc": sorted(s.pcs), "progression": prog, "chords": [s.chord_name(b) for b in range(bars)],
            "sections": {n: [s.b[n], s.b[n] + nb * 4] for n, nb in s.sections},
            "cues": {"hook": 0, "build": s.b["build"], "drop": s.b["drop"], "end": s.b["end"], "final": s.b["end"]},
            "notes_used": [pitch.midi_name(m) for m in sorted(s.notes_used)], "seed": seed}
    return s, y, out, spec, (i, p)


def cmd_make(a):
    try:
        prog = [int(x) for x in a.progression.split(",")] if a.progression else None
        s, y, stems, spec, (i, p) = make(a.style, a.bpm, a.key, a.bars, a.sections, prog, a.seed, a.lufs, a.stems)
    except ValueError:
        print("score: --progression is scale degrees from 1 to 7, like 1,6,7,3", file=sys.stderr)
        sys.exit(2)
    except ScoreError as e:
        print(f"score: {e}", file=sys.stderr)
        sys.exit(2)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write_wav(out / "music.wav", y)
    (out / "score.json").write_text(json.dumps(spec, indent=1))
    if a.stems:
        (out / "stems").mkdir(exist_ok=True)
        for k, x in stems.items():
            write_wav(out / "stems" / f"{k}.wav", x)
    print(f"✓ score: {a.style}, {spec['bpm']} bpm, {spec['key']}, {a.bars} bars = {spec['duration']:.2f} s -> {out / 'music.wav'}")
    print(f"  {analysis_line(analyze(out / 'music.wav'))}")
    print(f"  sections in beats: " + ", ".join(f"{n} {v[0]}-{v[1]}" for n, v in spec["sections"].items()) +
          f". Beat n is at n x {60 / spec['bpm']:.4f} s. Time the picture to {out / 'score.json'}. The music is unheard by the agent until you listen.")


def cmd_styles(a):
    for k, v in STYLES.items():
        print(f"{k:10s} {v['bpm']:3d} bpm  {v['key']:8s}  {v['about']}")


def cmd_preview(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for k in STYLES:
        s, y, _, spec, _ = make(k, bars=4)
        write_wav(out / f"preview-{k}.wav", y)
        print(f"{k:10s} {spec['bpm']} bpm {spec['key']:8s} {spec['duration']:.1f} s -> {out / ('preview-' + k + '.wav')}")
    print("These are previews: listen to each on a phone speaker and pick one. The music is unheard by the agent.")


def cmd_mix(a):
    ff = lambda p: subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    mm, ee = (np.frombuffer(ff(p), np.float32).reshape(-1, 2).astype(float) for p in (a.music, a.sfx))
    n = max(len(mm), len(ee))
    mix = np.zeros((n, 2))
    mix[: len(mm)] += mm * db(a.music_db)
    mix[: len(ee)] += ee * db(a.sfx_db)
    y, i, p = to_level(mix, a.lufs)
    write_wav(a.out, y)
    print(f"✓ mix: {n / SR:.2f} s, {i} LUFS, true peak {p} dBFS -> {a.out}. Check it with finish.py audio before rendering.")


def cmd_analyze(a):
    print(analysis_line(analyze(a.file)))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("styles")
    p = sub.add_parser("preview"); p.add_argument("--out", required=True)
    p = sub.add_parser("make"); p.add_argument("--style", required=True); p.add_argument("--out", required=True)
    p.add_argument("--bpm", type=float); p.add_argument("--key"); p.add_argument("--bars", type=int, default=8)
    p.add_argument("--sections"); p.add_argument("--progression"); p.add_argument("--seed", type=int, default=1)
    p.add_argument("--lufs", type=float, default=-18.0); p.add_argument("--stems", action="store_true")
    p = sub.add_parser("mix"); p.add_argument("music"); p.add_argument("sfx"); p.add_argument("--out", required=True)
    p.add_argument("--music-db", type=float, default=0.0); p.add_argument("--sfx-db", type=float, default=0.0)
    p.add_argument("--lufs", type=float, default=-15.0)
    p = sub.add_parser("analyze"); p.add_argument("file")
    a = ap.parse_args()
    {"styles": cmd_styles, "preview": cmd_preview, "make": cmd_make, "mix": cmd_mix, "analyze": cmd_analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
