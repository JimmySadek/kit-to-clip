#!/usr/bin/env python3
"""Kit to Clip effects: sound effects that follow the picture, made from the motion trace (finish/scripts/trace.mjs).

  effects.py <motion.json> <plan.json> --out <dir> [--seed 1]

Writes <dir>/sfx.wav (stereo, 48 kHz), <dir>/cue-sheet.json (for `finish.py sync`) and <dir>/effects.json (what was
placed). Every sound has a visible cause:

  whoosh  loudness and brightness follow the element's visible speed (moving AND resizing, only the part a viewer can
          see), pan follows its x position, and the sound leads the picture by 15 ms.
  hits    a sound on the frame the element comes to rest near a scored beat (its speed falls under 3% of the move's
          peak), 10 ms early. Kinds: note (a plucked note with a bell an octave up; must be in key), boom (a low tuned
          drop; in key), slam (a big landing: a boom with a thump under it and a soft click; in key), chime (a note and a
          quieter note a perfect fifth above; both in key), thump (an untuned low hit), tick (an untuned short click),
          file (a library effect; its notes are checked against the key).
  risers  a swell (filtered noise and a rising tone) that ENDS on the frame the element comes to rest, so it builds up to
          the landing. "length" is its length in seconds (0.25 to 4.0, default 1.0); "note" (optional, in key) is the
          tone's target. Its cue is its end, the landing.
  room    a short, dark room reverb on the whole layer, so the sounds sit in a space instead of sounding dry.

Never add an element only to carry a sound: every hit and riser follows a real move you can see.

plan.json:
  { "key": "A minor",                                   optional; tuned sounds are refused when a note is outside it
    "duration": 15,                                     optional; default the trace's duration
    "room": { "wet": 0.22, "decay": 1.1 },              optional; default as shown; "room": false turns the room off
    "whoosh": [ { "ids": ["c0", "c1"], "gain": 0.2, "vref": 2500, "lo": 350, "hi": 4200 } ],
    "hits":   [ { "id": "c0", "at": 4.6875, "kind": "note", "note": 69, "gain": 0.55, "cue": "chip 1 locks" },
                { "id": "c1", "at": 9.0, "kind": "riser", "length": 1.5, "note": 76, "cue": "chip 2 locks" } ] }
  vref  the speed (px/s) that counts as full loudness; default the element's own fastest move.
  note  MIDI number (69 = A4). at = the scored time of the picture moment (a beat), in seconds.
  pan   optional per hit, -1 left to 1 right; default from the element's x at the landing.
  room  wet is the share of reverb (0 to 1); decay is the seconds for the tail to fall 60 dB (0.2 to 4).

cue-sheet.json: one entry per hit, {cue, picture_t (the frame the element comes to rest: what a viewer sees), sound_t
(when the sound starts; for a riser, when it ends), scored_t (the beat the plan asked for)}. `finish.py anchors` checks the
picture against the beats; `finish.py sync <render> --cues cue-sheet.json` checks the sound against the picture on the
finished file.

Needs numpy and scipy (the video engine's Python has both: source <kit-to-clip>/scripts/env.sh first).
"""
import argparse
import json
import subprocess
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
RISER_MIN, RISER_MAX = 0.25, 4.0   # seconds
ROOM_WET, ROOM_DECAY = 0.22, 1.1   # the default room: wet share, and seconds for the tail to fall 60 dB


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


def slam(m, rng, length=0.9):
    """A big landing: a low tuned drop (as boom) with a thump under it and a soft 3.5 ms click on the front. The low end
    leads: the thump is half as loud as the drop."""
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(m) * (1 + 0.6 * np.exp(-t / 0.05))
    drop = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.45)
    low = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t / 0.035)) / SR) * np.exp(-t / 0.16)
    return drop + 0.5 * low + attack_click(rng, n, ms=3.5) * 0.5


def riser(rng, length, top):
    """A swell that ends on its landing: filtered noise that sweeps up, and a tone that rises two octaves to `top` (Hz).
    It grows as it goes (u squared, u = the share of the riser done) and fades out over its last 8 ms, so it stops
    on the landing without a click."""
    n = int(length * SR)
    t = np.arange(n) / SR
    u = t / length
    tone = np.sin(2 * np.pi * np.cumsum((top / 4) * 4 ** u) / SR) * 0.35
    air = filt_sweep(rng.standard_normal(n), 300 + 3500 * u, "bandpass", q_bw=1.6) * 0.6
    end = np.minimum(1, (length - t) / 0.008)
    return (tone + air) * u ** 2 * end


# ---------------------------------------------------------------- the room
def room_ir(seed, decay):
    """A short, dark room: seeded decorrelated stereo noise that falls 60 dB in `decay` seconds, after a 12 ms
    pre-delay, low-passed at about 5.2 kHz (no fizz) and high-passed at about 180 Hz (no mud). Unit energy per side."""
    rng = np.random.default_rng([seed, 7])
    L = int(SR * decay)
    t = np.arange(L) / SR
    env = 10 ** (-3 * t / decay)
    pre = int(0.012 * SR)
    ir = np.zeros((L + pre, 2))
    for c in range(2):
        ir[pre:, c] = rng.standard_normal(L) * env
    b, a = signal.butter(2, 5200 / (SR / 2), "low")
    ir = signal.lfilter(b, a, ir, axis=0)
    b, a = signal.butter(1, 180 / (SR / 2), "high")
    ir = signal.lfilter(b, a, ir, axis=0)
    return ir / np.sqrt((ir ** 2).sum(axis=0, keepdims=True))


def room(sfx, wet, decay, seed):
    """The dry layer with its room: dry * (1 - wet / 2) + wet * room. The never-clip scaling runs after this."""
    ir = room_ir(seed, decay)
    N = len(sfx)
    tail = np.stack([signal.fftconvolve(sfx[:, c], ir[:, c])[:N] for c in range(2)], axis=1)
    return sfx * (1 - wet / 2) + tail * wet


def room_plan(plan):
    """None when the room is off, else (wet, decay). An absent "room" is the default room."""
    r = plan.get("room", {})
    if r is False:
        return None
    if r is True:
        r = {}
    return float(r.get("wet", ROOM_WET)), float(r.get("decay", ROOM_DECAY))


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
def resolve_file(name):
    """A library effect by power and file name, "kenney-impact:impactPunch_heavy_000.ogg", becomes its path in the
    installed power (toolbox.py path <power> audio). A plain path is returned as it is."""
    if not isinstance(name, str) or ":" not in name or "/" in name.split(":", 1)[0]:
        return name
    power, rel = name.split(":", 1)
    toolbox = Path(__file__).resolve().parents[2] / "scripts" / "toolbox.py"
    r = subprocess.run([sys.executable, str(toolbox), "path", power, "audio"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise PlanError(f"the power {power!r} is not installed (toolbox.py which recorded-effects), so {name!r} has no file")
    return str(Path(r.stdout.strip()) / rel)


def load_plan(M, plan):
    for h in plan.get("hits", []):
        if h.get("kind") == "file":
            h["file"] = resolve_file(h.get("file", ""))
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
        if kind not in ("note", "boom", "slam", "chime", "riser", "thump", "tick", "file"):
            problems.append(f"{where}: kind {kind!r} is not note, boom, slam, chime, riser, thump, tick or file")
        if kind in ("note", "boom", "slam", "chime"):
            if not isinstance(h.get("note"), int):
                problems.append(f"{where}: a {kind} needs \"note\", a MIDI number (69 = A4)")
            elif key and h["note"] % 12 not in key[1]:
                problems.append(f"{where}: note {pitch.midi_name(h['note'])} is outside {key[0]}. Use a note in key, "
                                f"such as {', '.join(pitch.midi_name(m) for m in range(60, 72) if m % 12 in key[1])}")
            elif key and kind == "chime" and (h["note"] + 7) % 12 not in key[1]:
                problems.append(f"{where}: the fifth above, {pitch.midi_name(h['note'] + 7)}, is outside {key[0]}. "
                                "Use a note whose fifth is in key, such as the root of the key")
        if kind == "riser":
            if h.get("note") is not None:
                if not isinstance(h["note"], int):
                    problems.append(f"{where}: a riser's \"note\" is a MIDI number (69 = A4), or left out")
                elif key and h["note"] % 12 not in key[1]:
                    problems.append(f"{where}: riser note {pitch.midi_name(h['note'])} is outside {key[0]}. Use a note in key")
            if not isinstance(h.get("length", 1.0), (int, float)):
                problems.append(f"{where}: a riser's \"length\" is a number of seconds (0.25 to 4.0)")
        if kind == "file" and not Path(h.get("file", "")).is_file():
            problems.append(f"{where}: file {h.get('file')!r} not found")
        elif kind == "file" and key:
            r = pitch.measure(h["file"])
            if r["tuned"] and not all(pitch.NOTE_NAMES.index(n) in key[1] for n in r["notes"]):
                problems.append(f"{where}: {Path(h['file']).name} sounds {'+'.join(r['notes'])}, outside {key[0]}. "
                                "Pick another effect, or use kind \"note\" with a note in key. Do not pitch-shift a library effect.")
    r = plan.get("room", {})
    if r is not False and r is not True and not isinstance(r, dict):
        problems.append("room: use false (no room), or an object like {\"wet\": 0.22, \"decay\": 1.1}")
    elif isinstance(r, dict):
        wet, decay = r.get("wet", ROOM_WET), r.get("decay", ROOM_DECAY)
        if not isinstance(wet, (int, float)) or not 0 <= wet <= 1:
            problems.append("room: \"wet\" is the share of reverb, from 0 to 1")
        if not isinstance(decay, (int, float)) or not 0.2 <= decay <= 4:
            problems.append("room: \"decay\" is the seconds for the tail to fall 60 dB, from 0.2 to 4")
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
        if kind in ("note", "chime"):
            add(pluck(h["note"]), t_hit, g, pan)
            add(bell(h["note"] + 12), t_hit, g * 0.22, pan)
            if kind == "chime":                               # a quieter note a perfect fifth above
                add(pluck(h["note"] + 7), t_hit, g * 0.5, pan)
                add(bell(h["note"] + 19), t_hit, g * 0.5 * 0.22, pan)
        elif kind == "boom":
            add(boom(h["note"], rng), t_hit, g, pan)
        elif kind == "slam":
            add(slam(h["note"], rng), t_hit, g, pan)
        elif kind == "riser":                                 # it ends on the landing: its sound_t is the end
            length = min(RISER_MAX, max(RISER_MIN, float(h.get("length", 1.0))))
            top = hz(h["note"]) if h.get("note") is not None else hz(81)      # untuned: A5
            add(riser(rng, length, top), t_hit - length, g, pan)
            add(tick(rng), t_hit, g * 0.5, pan)                # a soft tick on the landing: the onset `finish sync` listens for
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
        if kind == "riser":
            placed[-1].update(length=round(length, 3), start=round(t_hit - length, 4))
    rs = room_plan(plan)
    if rs is not None:                                        # the room is on the whole layer, before the never-clip scaling
        sfx = room(sfx, *rs, seed)
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
