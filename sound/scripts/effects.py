#!/usr/bin/env python3
"""Kit to Clip effects: sound effects that follow the picture, made from the motion trace (finish/scripts/trace.mjs).

  effects.py <motion.json> <plan.json> --out <dir> [--seed 1]

Writes <dir>/sfx.wav (stereo, 48 kHz), <dir>/cue-sheet.json (for `finish.py sync`) and <dir>/effects.json (what was
placed). Every sound has a visible cause:

  whoosh  loudness and brightness follow the element's visible speed (moving AND resizing, only the part a viewer can
          see), pan follows its x position, and the sound leads the picture by 15 ms.
  hits    a sound on the frame the element comes to rest near a scored beat (its speed falls under 3% of the move's
          peak), 10 ms early. Kinds: note (a plucked note with a bell an octave up; must be in key), boom (a low tuned
          drop; in key), thump (an untuned low hit), tick (an untuned short click), file (a library effect; its notes
          are checked against the key).

plan.json:
  { "key": "A minor",                                   optional; tuned sounds are refused when a note is outside it
    "duration": 15,                                     optional; default the trace's duration
    "whoosh": [ { "ids": ["c0", "c1"], "gain": 0.2, "vref": 2500, "lo": 350, "hi": 4200 } ],
    "hits":   [ { "id": "c0", "at": 4.6875, "kind": "note", "note": 69, "gain": 0.55, "cue": "chip 1 locks" } ] }
  vref  the speed (px/s) that counts as full loudness; default the element's own fastest move.
  note  MIDI number (69 = A4). at = the scored time of the picture moment (a beat), in seconds.
  pan   optional per hit, -1 left to 1 right; default from the element's x at the landing.

cue-sheet.json: one entry per hit, {cue, picture_t (the frame the element comes to rest: what a viewer sees), sound_t
(when the sound starts), scored_t (the beat the plan asked for)}. `finish.py anchors` checks the picture against the beats;
`finish.py sync <render> --cues cue-sheet.json` checks the sound against the picture on the finished file.

Needs numpy and scipy (the video engine's Python has both: source <kit-to-clip>/scripts/env.sh first).
"""
import argparse
import json
import sys
import wave
from pathlib import Path

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pitch  # noqa: E402

SR = 48000
LEAD_WHOOSH = 0.015        # seconds the whoosh leads the picture
LEAD_HIT = 0.010           # seconds a hit leads the frame the element comes to rest
REST = 0.03                # "at rest" = speed under this share of the move's peak


class PlanError(Exception):
    pass


# ---------------------------------------------------------------- sources
def saw(f, n):
    """Band-limited sawtooth (polyBLEP), so a high note does not alias."""
    dt = np.broadcast_to(np.asarray(f, float) / SR, (n,))
    ph = np.cumsum(dt) % 1.0
    y = 2 * ph - 1
    m = ph < dt
    tt = ph[m] / dt[m]
    y[m] -= tt + tt - tt * tt - 1
    m = ph > 1 - dt
    tt = (ph[m] - 1) / dt[m]
    y[m] -= tt * tt + tt + tt + 1
    return y


def filt_sweep(x, cut, kind="lowpass", q_bw=None, block=256):
    """A filter whose cutoff moves with the sound: `cut` is one cutoff (Hz) per sample. Works on blocks of `block`."""
    y = np.zeros_like(x)
    zi = None
    for s in range(0, len(x), block):
        c = float(np.clip(cut[min(s, len(cut) - 1)], 30, SR / 2 * 0.95))
        if kind == "bandpass":
            sos = signal.butter(1, [c / q_bw, min(c * q_bw, SR / 2 * 0.95)], "bandpass", fs=SR, output="sos")
        else:
            sos = signal.butter(2, c, kind, fs=SR, output="sos")
        if zi is None or zi.shape[0] != sos.shape[0]:
            zi = np.zeros((sos.shape[0], 2) + x.shape[1:])
        y[s:s + block], zi = signal.sosfilt(sos, x[s:s + block], axis=0, zi=zi)
    return y


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def pluck(m, length=0.45, bright=6.0):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(m)
    x = saw(f, n) * 0.6 + np.sin(2 * np.pi * f * t) * 0.5
    y = filt_sweep(x, f * (1 + bright * np.exp(-t / 0.07)))
    return y * np.exp(-t / 0.22) * np.minimum(1, t / 0.002)


def bell(m, length=0.5):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(m)
    y = sum(a * np.sin(2 * np.pi * f * k * t) * np.exp(-t / (0.5 / k ** 0.5)) for k, a in [(1, 1), (2, 0.35), (3, 0.18), (4.2, 0.08)])
    return y * np.minimum(1, t / 0.003)


def attack_click(rng, n, ms=4):
    """A few ms of high-passed noise on the front of a low sound: a bass tone alone has almost no high end, so its start
    is felt but barely seen by an onset detector (and a listener on a phone speaker gets no attack either)."""
    k = int(ms / 1000 * SR)
    y = np.zeros(n)
    y[:k] = signal.sosfilt(signal.butter(2, 3000, "high", fs=SR, output="sos"), rng.standard_normal(k)) * 0.4
    return y


def boom(m, rng, length=0.6):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(m) * (1 + 0.6 * np.exp(-t / 0.05))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.45) + attack_click(rng, n)


def thump(rng, length=0.35):
    n = int(length * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t / 0.035)) / SR) * np.exp(-t / 0.16)
    return y + attack_click(rng, n)


def tick(rng, length=0.06):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = signal.sosfilt(signal.butter(2, 2500, "high", fs=SR, output="sos"), rng.standard_normal(n))
    return x * np.exp(-t / 0.008) * np.minimum(1, t / 0.0008)


# ---------------------------------------------------------------- the trace
def visible_speed(M, name):
    """Speed of an element in px/s (position and size), counting only what a viewer can see: a frame's motion is
    weighted by the smaller of the visible fractions before and after it."""
    F = M["frames"]
    xs, ys = (np.array([f[name][k] for f in F]) for k in ("x", "y"))
    ws, hs, vis = (np.array([f[name][k] for f in F]) for k in ("w", "h", "vis"))
    d = np.hypot(np.hypot(np.diff(xs), np.diff(ys)), np.hypot(np.diff(ws), np.diff(hs)))
    return np.r_[0, d] * M["fps"] * np.minimum(vis, np.r_[vis[:1], vis[:-1]]), xs


def arrival(v, fps, at, window=0.2):
    """The frame near the scored time where the element comes to rest: the first frame from 0.1 s before `at` on where
    its speed is under 3% of its peak in the second before. None when it is still moving (or never moved) by then."""
    fr = np.arange(len(v)) / fps
    before = np.where((fr <= at + 1e-6) & (fr > at - 1.2))[0]
    vmax = v[before].max() if len(before) else 0
    if vmax <= 0:
        return None
    lo, hi = int(round((at - 0.1) * fps)), min(len(v), int(round((at + window) * fps)))
    after = [k for k in range(max(0, lo), hi) if v[k] < REST * vmax]
    return after[0] / fps if after else None


# ---------------------------------------------------------------- the plan
def load_plan(M, plan):
    known = set(M["ids"])
    key = None
    if plan.get("key"):
        try:
            key = pitch.parse_key(plan["key"])
        except ValueError as e:
            raise PlanError(str(e))
    problems = []
    for w in plan.get("whoosh", []):
        problems += [f"whoosh: no element named {i!r} in the trace (traced: {', '.join(sorted(known))})" for i in w.get("ids", []) if i not in known]
    for i, h in enumerate(plan.get("hits", [])):
        where = f"hit {i + 1} ({h.get('cue') or h.get('id')})"
        if h.get("id") not in known:
            problems.append(f"{where}: no element named {h.get('id')!r} in the trace (traced: {', '.join(sorted(known))})")
        if not isinstance(h.get("at"), (int, float)):
            problems.append(f"{where}: needs \"at\", the scored time in seconds")
        kind = h.get("kind", "note")
        if kind not in ("note", "boom", "thump", "tick", "file"):
            problems.append(f"{where}: kind {kind!r} is not note, boom, thump, tick or file")
        if kind in ("note", "boom"):
            if not isinstance(h.get("note"), int):
                problems.append(f"{where}: a {kind} needs \"note\", a MIDI number (69 = A4)")
            elif key and h["note"] % 12 not in key[1]:
                problems.append(f"{where}: note {pitch.midi_name(h['note'])} is outside {key[0]}. Use a note in key, "
                                f"such as {', '.join(pitch.midi_name(m) for m in range(60, 72) if m % 12 in key[1])}")
        if kind == "file" and not Path(h.get("file", "")).is_file():
            problems.append(f"{where}: file {h.get('file')!r} not found")
        elif kind == "file" and key:
            r = pitch.measure(h["file"])
            if r["tuned"] and not all(pitch.NOTE_NAMES.index(n) in key[1] for n in r["notes"]):
                problems.append(f"{where}: {Path(h['file']).name} sounds {'+'.join(r['notes'])}, outside {key[0]}. "
                                "Pick another effect, or use kind \"note\" with a note in key. Do not pitch-shift a library effect.")
    if problems:
        raise PlanError("\n  ".join(["the plan cannot be built:"] + problems))
    return key


def build(M, plan, seed=1):
    """(stereo sfx as an (N, 2) array, cue sheet, list of what was placed, warnings)"""
    load_plan(M, plan)
    fps, W = M["fps"], M.get("width", 1080)
    dur = plan.get("duration", M["duration"])
    N = int(dur * SR)
    t_all = np.arange(N) / SR
    rng = np.random.default_rng(seed)
    sfx = np.zeros((N, 2))
    cues, placed, warnings = [], [], []

    def add(x, t, g=1.0, pan=0.0):
        s = int(round(t * SR))
        if s >= N:
            return
        if s < 0:
            x, s = x[-s:], 0
        e = min(N, s + len(x))
        x = x[: e - s]
        if x.ndim == 1:
            x = np.stack([x * (1 - max(0, pan)), x * (1 + min(0, pan))], axis=1)
        sfx[s:e] += x * g

    for w in plan.get("whoosh", []):
        for name in w["ids"]:
            v, xs = visible_speed(M, name)
            ref = w.get("vref") or (v.max() if v.max() > 0 else 1.0)
            sp = np.clip(v / ref, 0, 1.5)
            if sp.max() < 0.05:
                warnings.append(f"whoosh: {name} never visibly moves, so it has no whoosh")
                continue
            up = lambda c: np.interp(t_all, np.arange(len(c)) / fps, c)
            sp_s = np.maximum(signal.sosfiltfilt(signal.butter(1, 12, "low", fs=SR, output="sos"), up(sp)), 0)
            lead = int(round(LEAD_WHOOSH * SR))
            sp_s = np.r_[sp_s[lead:], np.zeros(lead)]
            pan = up(np.clip(xs / W * 2 - 1, -1, 1)) * 0.7
            on = np.where(sp_s > 0.002)[0]
            if not len(on):
                continue
            a, b = max(0, on[0] - 512), min(N, on[-1] + 512)              # filter only where it sounds
            lo, hi = w.get("lo", 350), w.get("hi", 4200)
            x = filt_sweep(rng.standard_normal((b - a, 1)), lo + (hi - lo) * np.clip(sp_s[a:b], 0, 1), "bandpass", q_bw=1.6)[:, 0]
            y = x * sp_s[a:b] ** 1.3 * w.get("gain", 0.2)
            sfx[a:b, 0] += y * (1 - np.maximum(0, pan[a:b]))
            sfx[a:b, 1] += y * (1 + np.minimum(0, pan[a:b]))
            placed.append({"kind": "whoosh", "id": name, "from": round(a / SR, 3), "to": round(b / SR, 3)})

    for h in plan.get("hits", []):
        v, xs = visible_speed(M, h["id"])
        land = arrival(v, fps, h["at"])
        if land is None:
            warnings.append(f"{h.get('cue') or h['id']}: {h['id']} is not at rest within 0.2 s of {h['at']} s "
                            "(still moving, or never moved): the hit sits on the scored time. Fix the picture, then trace again.")
            land = h["at"]
        land = min(land, h["at"])
        if h["at"] - land > 0.06:
            warnings.append(f"{h.get('cue') or h['id']}: {h['id']} is visibly at rest {round((h['at'] - land) * 1000)} ms before its scored time "
                            f"{h['at']} s (a long ease-out settles early). The hit is on the stop, where the eye sees it land.")
        t_hit = land - LEAD_HIT
        pan = h.get("pan", float(np.clip(xs[min(len(xs) - 1, int(round(land * fps)))] / W * 2 - 1, -1, 1)) * 0.5)
        kind, g = h.get("kind", "note"), h.get("gain", 0.5)
        if kind == "note":
            add(pluck(h["note"]), t_hit, g, pan)
            add(bell(h["note"] + 12), t_hit, g * 0.22, pan)
        elif kind == "boom":
            add(boom(h["note"], rng), t_hit, g, pan)
        elif kind == "thump":
            add(thump(rng), t_hit, g, pan)
        elif kind == "tick":
            add(tick(rng), t_hit, g, pan)
        else:
            x = pitch.read_audio(h["file"])
            add(x, t_hit, g, pan)
        name = h.get("cue") or f"{h['id']} lands"
        cues.append({"cue": name, "picture_t": round(land, 4), "sound_t": round(t_hit, 4), "scored_t": round(h["at"], 4)})
        placed.append({"kind": kind, "id": h["id"], "cue": name, "sound_t": round(t_hit, 4)})
    return sfx, cues, placed, warnings


def write_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("motion")
    ap.add_argument("plan")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    try:
        M = json.loads(Path(a.motion).read_text())
        plan = json.loads(Path(a.plan).read_text())
        assert "frames" in M and "ids" in M
    except (OSError, ValueError, AssertionError):
        print("effects: could not read the motion trace or the plan (make the trace with finish/scripts/trace.mjs)", file=sys.stderr)
        sys.exit(2)
    try:
        sfx, cues, placed, warnings = build(M, plan, a.seed)
    except PlanError as e:
        print(f"effects: {e}", file=sys.stderr)
        sys.exit(2)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    peak = float(np.abs(sfx).max())
    if peak > 0.95:                                        # never clip: scale the whole layer down
        sfx *= 0.95 / peak
    write_wav(out / "sfx.wav", sfx)
    (out / "cue-sheet.json").write_text(json.dumps(cues, indent=1))
    (out / "effects.json").write_text(json.dumps(placed, indent=1))
    for w in warnings:
        print(f"  ⚠ {w}")
    print(f"✓ effects: {sum(p['kind'] == 'whoosh' for p in placed)} whoosh(es), {len(cues)} hit(s) -> {out / 'sfx.wav'}; "
          f"cue sheet {out / 'cue-sheet.json'}. The sound is unheard by the agent until you listen.")


if __name__ == "__main__":
    main()
