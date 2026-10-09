#!/usr/bin/env python3
"""Kit to Clip ace_takes: original music from a description with ACE-Step 1.5, made ready for the sound pipeline. It
makes a few takes, puts each one on the tempo grid, scores it against the sections, keeps the best and writes the same
music.wav and score.json as score.py, so effects.py, finish.py anchors and finish.py sync work unchanged.

  ace_takes.py "<description>" --bpm 128 --key "A minor" --bars 24 --sections hook:4,build:8,drop:10,end:2
               [--takes 3] [--seed 11] [--extra-bars N] [--lufs -18] [--pick SEED] [--with-lm] [--ace-python PATH] --out <dir>
  ace_takes.py --measure <file.wav> --bpm 128 --bars 24 [--sections ...]      numbers for one file, writes nothing
  ace_takes.py --self-test                                                     proves the measures on made-up takes

What it fixes in a raw take (measured 2026-10-09): the beats sit 45 to 160 ms late, so it finds the grid offset and
shifts the audio until beat 0 is at 0.000 s, then keeps exactly bars x 4 x 60 / bpm seconds. Endings fade out over the
model's last bars, so each take is made --extra-bars longer (default max(4, half the bars)) and cut after the target
bars, the last half beat fading out: the fade falls after the cut. The drop lands where the model chooses, so it
measures the loudness of every bar and scores each take: the build rises, the drop is clearly above the build, the end
is not silent, the beats are tight, a hit on the end cue (no hit is a note: the effects plan can land a recorded one),
the bass does not swamp the mix, the peaks need little limiting. The best take is levelled like score.py (-18 LUFS,
true peak under -3 dBTP). Every take is kept in <dir>/takes/ (the raw file and a ready one) so the person can listen to
all of them; <dir>/takes.json holds every number and why the winner won. A re-run with the same folder reuses the takes (cheap), and
--pick SEED makes another take the music after listening.

Takes: seeds seed, seed+12, seed+26, then +12 each. A take takes minutes; the first run downloads about 9.4 GB.
Needs numpy, scipy and ffmpeg (the engine's Python: source <kit-to-clip>/scripts/env.sh first) and, to make takes, the
music-generate power (ACE-Step). The music is unheard by the agent: the person's ear decides.
Exit 0 ok, 1 no take could be made (or a self-test check failed), 2 bad input, 3 ACE-Step is not installed.
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.fft import next_fast_len
from scipy.ndimage import gaussian_filter1d

HERE = Path(__file__).resolve().parent
KIT = HERE.parent.parent                                   # <kit-to-clip>
sys.path.insert(0, str(HERE))
import pitch  # noqa: E402
import score  # noqa: E402  (levelling, true-peak limiter, sections, analysis: the same code score.py uses)

SR = score.SR
ENV_RATE = 1000                                            # the onset envelope has one value per millisecond
MODEL = "acestep-v15-turbo"
SEED_STEPS = [0, 12, 26]


class TakeError(Exception):
    pass


# ---------------------------------------------------------------- reading and measuring audio
def read_stereo(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode or not r.stdout:
        raise TakeError(f"could not read {path}")
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).astype(float)


def onset_envelope(mono):
    """How sharply the sound gets louder, once per millisecond: the rise of the log envelope, full band and highs. Every
    filter is zero-phase and the smoothing is symmetric and done on the log, so a hit's peak sits on its onset (no lag to
    correct; smoothing the envelope before the log would put the peak about 2.5 ms early)."""
    out = None
    for sos in (signal.butter(2, 30, "high", fs=SR, output="sos"), signal.butter(4, 2000, "high", fs=SR, output="sos")):
        y = signal.sosfiltfilt(sos, mono)
        e = np.abs(signal.hilbert(y, N=next_fast_len(len(y))))[: len(y)]
        L = gaussian_filter1d(np.log(e + 1e-3 * e.mean() + 1e-12), SR * 0.002)[:: SR // ENV_RATE]
        d = np.maximum(0, np.gradient(L))                  # smoothed in the log domain: a step's slope peaks on the step
        d /= np.percentile(d, 99.5) + 1e-12
        out = d if out is None else out + d
    return out


def beat_peaks(env, centres, half=0.035):
    """The strongest onset within +-half seconds of each centre: (time, strength) or (None, 0) off the file's edges."""
    res = []
    for c in centres:
        lo, hi = int(round((c - half) * ENV_RATE)), int(round((c + half) * ENV_RATE))
        if lo < 1 or hi >= len(env) - 1:
            res.append((None, 0.0))
            continue
        seg = env[lo:hi + 1]
        j = int(np.argmax(seg))
        y0, y1, y2 = env[lo + j - 1], env[lo + j], env[lo + j + 1]
        den = y0 - 2 * y1 + y2
        frac = 0.5 * (y0 - y2) / den if den < 0 else 0.0
        res.append(((lo + j + frac) / ENV_RATE, float(y1)))
    return res


def grid_offset(env, bpm, n_beats):
    """Where the beats really are against the tempo grid. Cross-correlates the onset envelope with a click every beat
    (1 ms steps over one beat), then refines with each beat's own onset. Returns the offset of beat 0 in seconds (positive
    means the music is late), the spread of the beats around the grid, how many beats were found and the tempo they keep."""
    P = 60.0 / bpm
    sm = gaussian_filter1d(env, 3)
    phis = np.arange(0, P, 1.0 / ENV_RATE)
    k = np.arange(n_beats + 1)
    idx = np.rint((phis[:, None] + k[None, :] * P) * ENV_RATE).astype(int)
    vals = np.where(idx < len(sm), sm[np.minimum(idx, len(sm) - 1)], 0.0)
    phi = float(phis[int(np.argmax(vals.sum(axis=1)))])
    peaks = beat_peaks(env, phi + k * P)
    found = [(i, t, s) for i, (t, s) in enumerate(peaks) if t is not None]
    if not found:
        raise TakeError("no beats found")
    thr = 0.3 * np.median([s for _, _, s in found])
    good = [(i, t) for i, t, s in found if s >= thr]
    devs = np.array([t - (phi + i * P) for i, t in good])
    offset = phi + float(np.median(devs))
    if offset > P / 2:                                     # the nearest beat: shift by less than half a beat
        offset -= P
    spread = float(np.std(devs)) * 1000
    tempo = None
    if len(good) >= 8:
        slope = np.polyfit([i for i, _ in good], [t for _, t in good], 1)[0]
        tempo = round(60.0 / slope, 2)
    return {"offset_s": round(offset, 4), "spread_ms": round(spread, 1), "beats_found": len(good),
            "beats_total": n_beats, "tempo_measured": tempo}


def k_weight(x):
    """ITU-R BS.1770 K-weighting at 48 kHz (the filter LUFS uses)."""
    x = signal.lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, 0.73248077421585], x, axis=0)
    return signal.lfilter([1.0, -2.0, 1.0], [1, -1.99004745483398, 0.99007225036621], x, axis=0)


def window_loudness(kw, starts, length):
    """K-weighted loudness (LUFS-like, ungated) of each window, floored at -70."""
    out = []
    for s in starts:
        seg = kw[int(s):int(s + length)]
        ms = float((seg ** 2).mean(axis=0).sum()) if len(seg) else 0.0
        out.append(round(max(-70.0, -0.691 + 10 * np.log10(ms + 1e-12)), 2))
    return out


def pmean(db_values):
    """The loudness of several windows together (an energy average, so a hit then a silent tail is not -70)."""
    return float(10 * np.log10(np.mean(10 ** (np.asarray(db_values) / 10.0))))


def align(x, offset, n_target, fade_s=0.02):
    """Shift so beat 0 is at 0.000 s, then trim or pad to exactly n_target samples. Sound cut off at the end fades out
    over fade_s (half a beat for a take made with extra bars), so the cut never clicks."""
    s = int(round(offset * SR))
    y = x[s:].copy() if s >= 0 else np.concatenate([np.zeros((-s, 2)), x])
    if s > 0:
        f = int(0.001 * SR)
        y[:f] *= np.linspace(0, 1, f)[:, None]              # 1 ms fade-in: no click where the audio was cut
    if len(y) > n_target:
        cut = len(y) - n_target
        y = y[:n_target]
        if np.abs(x[-cut:]).max() > 1e-4:                  # sound was cut off at the end: fade it out
            f = min(n_target, int(fade_s * SR))
            y[-f:] *= np.linspace(1, 0, f)[:, None]
    elif len(y) < n_target:
        y = np.concatenate([y, np.zeros((n_target - len(y), 2))])
    return y


# ---------------------------------------------------------------- scoring a take against the sections
def ramp(v, lo, hi):
    """0 at lo, 1 at hi, straight in between (lo may be above hi)."""
    return float(np.clip((v - lo) / (hi - lo), 0.0, 1.0))


def measure_take(x, bpm, bars, sections, lufs_target=-18.0, analysis=None):
    """Every number for one take (stereo array). sections: [("hook", n), ("build", n), ("drop", n), ("end", n)] in bars.
    analysis: score.analyze() of the raw file (bass share, loudness, true peak), or None. A take longer than the target
    (made with extra bars) is put on the grid as a whole, then exactly the target bars are kept from beat 0: the model's
    outro falls after the cut, and the last half beat fades out. Everything after that is measured on the cut audio."""
    P = 60.0 / bpm
    n_beats = bars * 4
    n_target = int(round(n_beats * P * SR))
    raw_env = onset_envelope(x.mean(axis=1))
    grid = grid_offset(raw_env, bpm, max(n_beats, int(len(x) / SR / P)))
    y = align(x, grid["offset_s"], n_target, fade_s=P / 2)
    env = onset_envelope(y.mean(axis=1))
    after = grid_offset(env, bpm, n_beats)
    kw = k_weight(y)
    bar_len = 4 * P * SR
    bars_db = window_loudness(kw, [b * bar_len for b in range(bars)], bar_len)
    beats_db = window_loudness(kw, [k * P * SR for k in range(n_beats)], P * SR)
    start, sec = 0, {}
    for name, nb in sections:
        sec[name] = (start, start + nb)
        start += nb
    L = np.array(bars_db)
    hook = L[slice(*sec["hook"])]
    build = L[slice(*sec["build"])]
    drop = L[slice(*sec["drop"])]
    end = L[slice(*sec["end"])]
    if len(build) >= 2:
        build_rise = float(np.polyfit(np.arange(len(build)), build, 1)[0] * (len(build) - 1))
    else:
        build_rise = float(build[0] - pmean(hook))
    drop_lift = float(pmean(drop[:2]) - pmean(build))
    drop_step = float(drop[0] - build[-1])
    end_vs_drop = float(pmean(end) - pmean(drop))
    strengths = np.array([s for _, s in beat_peaks(env, np.arange(n_beats) * P, half=0.04)])
    end_beat = sec["end"][0] * 4
    drop_beats = strengths[sec["drop"][0] * 4: sec["drop"][1] * 4]
    hit_ratio = float(strengths[end_beat] / (np.median(drop_beats) + 1e-9))
    hit_db = float(beats_db[end_beat] - pmean(drop))
    steps = [L[i] - L[i - 1] for i in range(1, len(L))]          # the music's own drop: its biggest bar-to-bar lift
    mdrop = 1 + int(np.argmax(steps)) if steps else sec["drop"][0]
    m = {"grid": grid, "grid_after_shift": after, "shift_s": grid["offset_s"], "seconds": round(n_target / SR, 4),
         "take_seconds": round(len(x) / SR, 3), "cut_s": round(max(0.0, len(x) / SR - grid["offset_s"] - n_target / SR), 3),
         "bar_loudness": bars_db,
         "sections_loudness": {k: round(pmean(L[slice(*v)]), 2) for k, v in sec.items()},
         "build_rise_db": round(build_rise, 2), "drop_lift_db": round(drop_lift, 2), "drop_step_db": round(drop_step, 2),
         "end_vs_drop_db": round(end_vs_drop, 2), "final_hit_ratio": round(hit_ratio, 2), "final_hit_db": round(hit_db, 2),
         "measured_drop_bar": mdrop, "measured_drop_beat": mdrop * 4, "measured_drop_step_db": round(float(max(steps)) if steps else 0.0, 2),
         "planned_drop_beat": sec["drop"][0] * 4}
    if analysis:
        m.update({"raw_lufs": analysis["lufs"], "raw_true_peak": analysis["true_peak"], "bass_pct": analysis["bass"],
                  "centroid_hz": analysis["centroid_hz"]})
        m["limiting_db"] = round(max(0.0, (analysis["true_peak"] - analysis["lufs"]) - (score.PEAK_CEILING_DB - lufs_target)), 1)
    m["points"], m["failed"], m["notes"] = points_for(m)
    m["score"] = round(sum(m["points"].values()) - 10 * len(m["failed"]), 1)   # may go below 0: poor takes still rank
    return m, y


def points_for(m):
    """Points out of 100, the checks a take fails (each failure costs 10 points) and notes (no cost). The beats are
    judged on the audio that is kept (after the shift and the cut)."""
    g = m["grid_after_shift"]
    found = g["beats_found"] / max(1, g["beats_total"])
    pts = {"grid": 15 * ramp(g["spread_ms"], 40, 10) * ramp(found, 0.4, 0.9),
           "build": 20 * ramp(m["build_rise_db"], 0, 3),
           "drop": 15 * ramp(m["drop_lift_db"], 0, 4) + 10 * ramp(m["drop_step_db"], 0, 2),
           "end": 15 * ramp(m["end_vs_drop_db"], -18, -6),
           "final_hit": 5 * ramp(m["final_hit_ratio"], 0.3, 1.0) + 5 * ramp(m["final_hit_db"], -12, -3)}
    if "bass_pct" in m:
        pts["balance"] = 10 * ramp(m["bass_pct"], 95, 70)
        pts["peaks"] = 5 * ramp(m["limiting_db"], 6, 0)
    failed, notes = [], []
    drop_on_plan = m["measured_drop_beat"] == m["planned_drop_beat"] and m["measured_drop_step_db"] >= 3
    if m["build_rise_db"] < 1.0:
        if drop_on_plan:      # the drop the picture times to is where the plan wants it: a flat build is taste, not a fault
            notes.append("the build is flat, but the music drops on the planned beat: fine for the picture")
        else:
            failed.append("the build does not rise")
    if m["drop_lift_db"] < 1.5:
        failed.append("the drop is not clearly above the build")
    if m["end_vs_drop_db"] < -12 or m["sections_loudness"]["end"] < -45:
        failed.append("the end is near silence")
    if m["final_hit_ratio"] < 0.5 or m["final_hit_db"] < -9:          # the sound plan can land a recorded hit there
        notes.append(NO_HIT_NOTE)
    if m["measured_drop_beat"] != m["planned_drop_beat"] and m["measured_drop_step_db"] >= 3:
        notes.append(f"the music's own drop is on beat {m['measured_drop_beat']} (bar {m['measured_drop_bar'] + 1}, "
                     f"+{m['measured_drop_step_db']} dB), not the planned beat {m['planned_drop_beat']}: put the big move there")
    if g["spread_ms"] > 30 or found < 0.5:
        failed.append("the beats are loose against the tempo")
    return {k: round(v, 1) for k, v in pts.items()}, failed, notes


NO_HIT_NOTE = "no hit in the music on the end cue: add a recorded hit on the end cue (effects plan)"


NICE = {"grid": "tighter beats", "build": "a build that rises more", "drop": "a bigger drop on its cue",
        "end": "a fuller ending", "final_hit": "a clearer final hit", "balance": "less bass swamping the mix",
        "peaks": "peaks that need less limiting"}


def why_text(win, others):
    w = win["measure"]
    line = (f"seed {win['seed']} scored {w['score']}: build rises {w['build_rise_db']:+.1f} dB, drop {w['drop_lift_db']:+.1f} dB "
            f"over the build, end {w['end_vs_drop_db']:+.1f} dB against the drop")
    if not others:
        return line + " (the only take)."
    ru = max(others, key=lambda t: t["measure"]["score"])
    r = ru["measure"]
    gaps = sorted(((w["points"].get(k, 0) - r["points"].get(k, 0), k) for k in w["points"]), reverse=True)
    better = [NICE[k] for gap, k in gaps if gap > 0.5][:2]
    line += f". Next best: seed {ru['seed']} at {r['score']}"
    if better:
        line += f"; the winner has {' and '.join(better)}"
    if r["failed"] and len(r["failed"]) > len(w["failed"]):
        line += f"; seed {ru['seed']} fails: {', '.join(r['failed'])}"
    return line + "."


# ---------------------------------------------------------------- making takes with ACE-Step
def ace_python(given):
    if given:
        return given if Path(given).exists() else None
    r = subprocess.run([sys.executable, str(KIT / "scripts" / "toolbox.py"), "path", "ace-step", "python"], capture_output=True, text=True)
    p = r.stdout.strip()
    return p if r.returncode == 0 and p and Path(p).exists() else None


def take_matches(meta, a, key_name, seed):
    """A take is reused only when it was made with the same settings: the same extra bars too (another length is
    another take)."""
    try:
        k = pitch.parse_key(meta.get("key", ""))[0]
    except ValueError:
        return False
    return (meta.get("bpm") == a.bpm and meta.get("bars") == a.bars + a.extra_bars and meta.get("extra_bars", 0) == a.extra_bars
            and meta.get("seed") == seed and k == key_name and meta.get("description") == a.description)


def default_extra_bars(bars):
    return max(4, math.ceil(bars * 0.5))


def make_take(py, a, key_name, seed, wav):
    wav = wav.resolve()
    cmd = [py, str(KIT / "toolbox" / "helpers" / "ace_music.py"), a.description, str(wav), "--bpm", str(a.bpm),
           "--key", key_name, "--bars", str(a.bars + a.extra_bars), "--seed", str(seed)] + (["--with-lm"] if a.with_lm else [])
    t0 = time.time()
    with open(wav.with_suffix(".log"), "w") as log:
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=wav.parent)   # ACE-Step writes .cache/ where it runs
    took = round(time.time() - t0, 1)
    if r.returncode or not wav.exists():
        raise TakeError(f"ACE-Step failed (exit {r.returncode}); see {wav.with_suffix('.log')}")
    side = wav.with_suffix(".json")
    meta = json.loads(side.read_text()) if side.exists() else {}
    meta.update({"description": a.description, "key": key_name, "seconds_to_make": took, "extra_bars": a.extra_bars,
                 "target_bars": a.bars})
    side.write_text(json.dumps(meta, indent=2))
    return took


def cmd_make(a):
    try:
        key_name, pcs = pitch.parse_key(a.key)
        if not 60 <= a.bpm <= 200:
            raise score.ScoreError("the tempo must be between 60 and 200 bpm")
        secs = score.parse_sections(a.sections, a.bars)
    except (ValueError, score.ScoreError) as e:
        print(f"ace_takes: {e}", file=sys.stderr)
        return 2
    if a.extra_bars is None:
        a.extra_bars = default_extra_bars(a.bars)
    if a.extra_bars < 0:
        print("ace_takes: --extra-bars must be 0 or more", file=sys.stderr)
        return 2
    seconds = a.bars * 4 * 60.0 / a.bpm
    make_seconds = (a.bars + a.extra_bars) * 4 * 60.0 / a.bpm
    if not 10 <= make_seconds <= 600:
        print(f"ace_takes: {a.bars} + {a.extra_bars} extra bars at {a.bpm} bpm is {make_seconds:.1f} s; ACE-Step makes 10 to 600 s", file=sys.stderr)
        return 2
    if a.takes < 1:
        print("ace_takes: --takes must be at least 1", file=sys.stderr)
        return 2
    out = Path(a.out)
    tdir = out / "takes"
    tdir.mkdir(parents=True, exist_ok=True)
    steps = SEED_STEPS + [SEED_STEPS[-1] + 12 * i for i in range(1, max(1, a.takes - len(SEED_STEPS) + 1))]
    seeds = [a.seed + s for s in steps[: a.takes]]
    if a.pick is not None and a.pick not in seeds:
        seeds.append(a.pick)
    py = None
    takes = []
    for seed in seeds:
        stem = f"take-s{seed}" + (f"-x{a.extra_bars}" if a.extra_bars else "")
        wav = tdir / f"{stem}.wav"
        side = wav.with_suffix(".json")
        t = {"seed": seed, "file": str(wav)}
        if wav.exists():
            meta = json.loads(side.read_text()) if side.exists() else {}
            if not take_matches(meta, a, key_name, seed):
                print(f"ace_takes: {wav} was made with other settings or another description ({side}). It is kept: use a new --out folder.",
                      file=sys.stderr)
                return 2
            t["made"] = "reused"
            t["seconds_to_make"] = meta.get("seconds_to_make")
            print(f"  take seed {seed}: reused {wav}")
        else:
            if py is None:
                py = ace_python(a.ace_python)
                if py is None:
                    print("ace_takes: the music generator (ACE-Step, the music-generate power) is not installed. Offer it with "
                          f"`python3 {KIT / 'scripts' / 'toolbox.py'} install ace-step` after a ✋ yes (the first run downloads about "
                          f"9.4 GB), or make the music offline now: `python3 {HERE / 'score.py'} make --style pulse --bpm {a.bpm} "
                          f"--key \"{key_name}\" --bars {a.bars} --out {out}`.", file=sys.stderr)
                    return 3
            print(f"  take seed {seed}: making {make_seconds:.2f} s with ACE-Step ({a.bars} bars + {a.extra_bars} extra, cut after "
                  f"{seconds:.2f} s; this takes minutes) ...", flush=True)
            try:
                t["seconds_to_make"] = make_take(py, a, key_name, seed, wav)
                t["made"] = "new"
            except TakeError as e:
                print(f"  take seed {seed}: {e}", file=sys.stderr)
                t["error"] = str(e)
                takes.append(t)
                continue
        try:
            x = read_stereo(wav)
            t["measure"], ready = measure_take(x, a.bpm, a.bars, secs, a.lufs, score.analyze(wav))
        except TakeError as e:
            t["error"] = str(e)
            takes.append(t)
            continue
        y, i, p = score.to_level(ready, a.lufs, score.PEAK_CEILING_DB - 0.2)   # 0.2 dB margin: ffmpeg reads a hot mix at -2.9
        t["ready_file"] = str(tdir / f"{stem}-ready.wav")
        score.write_wav(t["ready_file"], y)
        t["ready"] = {"lufs": i, "true_peak": p}
        m = t["measure"]
        print(f"  take seed {seed}: grid {m['grid']['offset_s'] * 1000:+.0f} ms (spread {m['grid']['spread_ms']} ms), "
              f"build {m['build_rise_db']:+.1f} dB, drop {m['drop_lift_db']:+.1f} dB, end {m['end_vs_drop_db']:+.1f} dB, "
              f"bass {m.get('bass_pct', '?')}%, score {m['score']}" + (f", fails: {'; '.join(m['failed'])}" if m["failed"] else "")
              + (f" (note: {'; '.join(m['notes'])})" if m["notes"] else ""))
        takes.append(t)
    ok = [t for t in takes if "measure" in t]
    if not ok:
        print("ace_takes: no take could be made. See the logs in " + str(tdir) + ", or make the music offline with score.py.", file=sys.stderr)
        (out / "takes.json").write_text(json.dumps({"description": a.description, "takes": takes}, indent=1))
        return 1
    by_score = sorted(ok, key=lambda t: t["measure"]["score"], reverse=True)
    if a.pick is not None:
        chosen = [t for t in ok if t["seed"] == a.pick]
        if not chosen:
            print(f"ace_takes: take seed {a.pick} could not be measured", file=sys.stderr)
            return 1
        win = chosen[0]
        why = f"seed {a.pick} was picked by the person after listening (--pick). " + why_text(win, [t for t in ok if t is not win])
    else:
        win = by_score[0]
        why = why_text(win, by_score[1:])
    warning = None
    if win["measure"]["failed"]:
        warning = (f"every take missed at least one check; the best one (seed {win['seed']}) fails: {', '.join(win['measure']['failed'])}. "
                   "Listen before using it. Try more takes (--takes 5) or other seeds (--seed), or the offline music maker (score.py).")
        if a.pick is not None:
            warning = f"the picked take fails: {', '.join(win['measure']['failed'])}. It is used because the person picked it."
    shutil.copyfile(win["ready_file"], out / "music.wav")
    final = score.analyze(out / "music.wav")
    b = {}
    start = 0
    for name, nb in secs:
        b[name] = start * 4
        start += nb
    spec = {"about": "Timing for the picture, the effects and the music: everything reads these beats. Beat n is at n x 60 / bpm seconds.",
            "style": "ace-step", "bpm": a.bpm, "beatsPerBar": 4, "bars": a.bars, "duration": round(a.bars * 4 * 60.0 / a.bpm, 4),
            "key": key_name, "scale_pc": sorted(pcs), "progression": None, "chords": None,
            "sections": {n: [b[n], b[n] + nb * 4] for n, nb in secs},
            "cues": {"hook": 0, "build": b["build"], "drop": b["drop"], "end": b["end"], "final": b["end"]},
            "notes_used": None, "seed": win["seed"],
            "source": {"tool": "ace_takes.py", "model": MODEL, "description": a.description, "shift_s": win["measure"]["shift_s"],
                       "extra_bars": a.extra_bars, "final_hit_in_music": NO_HIT_NOTE not in win["measure"]["notes"],
                       "measured_drop_beat": win["measure"]["measured_drop_beat"], "measured_drop_step_db": win["measure"]["measured_drop_step_db"],
                       "note": "generated music: chords and notes are the model's own (not listed); the cues are the requested sections, "
                               "and the take was chosen because its loudness follows them. Generated music can resemble existing songs by accident."}}
    (out / "score.json").write_text(json.dumps(spec, indent=1))
    report = {"about": "Every ACE-Step take, its numbers and why the winner won. Points: grid 15, build 20, drop 25, end 15, final hit 10, "
                       "bass balance 10, peaks 5; each failed check costs 10, a note costs nothing. Loudness is K-weighted per bar (like LUFS). "
                       "Each take was made extra_bars longer, put on the grid as a whole and cut to the target bars, so the model's outro falls after the cut.",
              "description": a.description, "bpm": a.bpm, "key": key_name, "bars": a.bars, "sections": dict(secs),
              "duration": spec["duration"], "extra_bars": a.extra_bars, "model": MODEL, "lufs_target": a.lufs,
              "winner": win["seed"], "why": why, "warning": warning, "notes": win["measure"]["notes"], "music": {"file": str(out / "music.wav"), "seconds": final["seconds"], "lufs": final["lufs"],
                                            "true_peak": final["true_peak"], "bass_pct": final["bass"], "centroid_hz": final["centroid_hz"]},
              "takes": takes}
    (out / "takes.json").write_text(json.dumps(report, indent=1))
    print(f"✓ ace_takes: seed {win['seed']} -> {out / 'music.wav'} ({final['seconds']} s, {final['lufs']} LUFS, true peak {final['true_peak']} dBFS)")
    print(f"  why: {why}")
    if warning:
        print(f"⚠ {warning}")
    for n in win["measure"]["notes"]:
        print(f"  note: {n}")
    print(f"  every take is in {tdir} ({stem.replace(str(seed), '<seed>')}.wav raw, -ready.wav cut, on the grid and levelled); "
          f"numbers in {out / 'takes.json'}.")
    print(f"  time the picture to {out / 'score.json'}. The music is unheard by the agent: play the takes to the person; "
          f"another take is one command away (--pick <seed>).")
    return 0


def cmd_measure(a):
    try:
        secs = score.parse_sections(a.sections, a.bars)
        m, _ = measure_take(read_stereo(a.measure), a.bpm, a.bars, secs, a.lufs, score.analyze(a.measure))
    except (TakeError, score.ScoreError, RuntimeError) as e:
        print(f"ace_takes: {e}", file=sys.stderr)
        return 2
    print(json.dumps(m, indent=1))
    return 0


# ---------------------------------------------------------------- self-test (no model)
def synth_take(bpm, bars, sections, offset, kind, seed=1, extra=0):
    """A made-up take: a kick on every beat, off-beat hats and a pad, its level following the sections. kind: "good"
    (the build rises, a loud drop, a final hit), "flat" (the build stays at the hook's level), "silent_end" (the end fades
    to nothing, no hit), "outro" (like ACE-Step: the music goes on at the drop's level, then its last 3 bars fade to
    nothing, no hit). offset: where beat 0 sits, in seconds (the take is late by that much). extra: bars made after the
    target bars (the take is that much longer)."""
    rng = np.random.default_rng(seed)
    P = 60.0 / bpm
    total = bars + extra
    n = int(round(total * 4 * P * SR))
    sec, start = {}, 0
    for name, nb in sections:
        sec[name] = (start, start + nb)
        start += nb
    level = np.full(total, -4.0)
    level[slice(*sec["hook"])] = -20
    nbuild = sec["build"][1] - sec["build"][0]
    level[slice(*sec["build"])] = -20 if kind == "flat" else np.linspace(-18, -10, nbuild)
    level[slice(*sec["drop"])] = -4
    if kind == "outro":
        level[-3:] = [-16, -34, -60]
    else:
        level[slice(*sec["end"])] = -12 if kind != "silent_end" else -90
    hit = kind in ("good", "flat")
    t = np.arange(n) / SR
    bar_of = np.clip(((t - offset) // (4 * P)).astype(int), 0, total - 1)
    g = 10 ** (level[bar_of] / 20)
    x = 0.15 * g * (np.sin(2 * np.pi * 110 * t) + 0.6 * np.sin(2 * np.pi * 164.81 * t) + 0.4 * np.sin(2 * np.pi * 220 * t))
    kl = int(0.25 * SR)
    kt = np.arange(kl) / SR
    kick = np.sin(2 * np.pi * (50 * kt + 60 * (1 - np.exp(-kt / 0.03)) * 0.03)) * np.exp(-kt / 0.12)
    kick[: int(0.002 * SR)] += rng.normal(0, 0.5, int(0.002 * SR))
    hat = rng.normal(0, 1, int(0.04 * SR)) * np.exp(-np.arange(int(0.04 * SR)) / SR / 0.01)
    hat = signal.sosfilt(signal.butter(4, 6000, "high", fs=SR, output="sos"), hat)
    end_beat = sec["end"][0] * 4
    for k in range(total * 4):
        bar = k // 4
        if kind == "silent_end" and bar >= sec["end"][0]:
            break
        for at, snd, gain in ((offset + k * P, kick, 0.8), (offset + (k + 0.5) * P, hat, 0.15)):
            s = int(round(at * SR))
            if 0 <= s < n:
                m = min(len(snd), n - s)
                boost = 2.5 if (hit and k == end_beat and snd is kick) else 1.0
                x[s:s + m] += gain * boost * 10 ** (level[bar] / 20) * snd[:m] * (3 if hit and bar >= sec["end"][0] else 1)
    if hit:                                                    # the end: a hit, then a tail that decays
        s = int(round((offset + end_beat * P) * SR))
        tail = np.exp(-np.arange(n - s) / SR / 0.8)
        x[s:] *= np.maximum(tail, 0.3)
    return np.stack([x, x * 0.98], axis=1)


def self_test():
    bpm, bars = 128, 12
    secs = [("hook", 2), ("build", 4), ("drop", 5), ("end", 1)]
    checks = []

    def check(ok, text):
        checks.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} {text}")

    n_target = int(round(bars * 4 * 60 / bpm * SR))
    for off in (0.151, 0.045, 0.160, -0.100):
        x = synth_take(bpm, bars, secs, off, "good")
        m, y = measure_take(x, bpm, bars, secs)
        got = m["grid"]["offset_s"]
        after = m["grid_after_shift"]["offset_s"]
        check(abs(got - off) <= 0.005 and abs(after) <= 0.005 and len(y) == n_target,
              f"grid offset {off * 1000:+.0f} ms recovered as {got * 1000:+.1f} ms (error {abs(got - off) * 1000:.1f} ms, limit 5); "
              f"after the shift {after * 1000:+.1f} ms; length {len(y)} samples = {len(y) / SR:.4f} s (want {n_target})")
    good, _ = measure_take(synth_take(bpm, bars, secs, 0.1, "good"), bpm, bars, secs)
    flat, _ = measure_take(synth_take(bpm, bars, secs, 0.1, "flat"), bpm, bars, secs)
    silent, _ = measure_take(synth_take(bpm, bars, secs, 0.1, "silent_end"), bpm, bars, secs)
    check(not good["failed"], f"the good take passes every check (score {good['score']}, build {good['build_rise_db']:+.1f} dB, "
                              f"drop {good['drop_lift_db']:+.1f} dB, end {good['end_vs_drop_db']:+.1f} dB, hit {good['final_hit_ratio']})"
                              + (f": fails {good['failed']}" if good["failed"] else ""))
    # its drop still lands on the planned beat, so the flat build is a note (fine for the picture), and it ranks lower
    check(flat["score"] < good["score"] and not flat["failed"] and any("the build is flat" in n for n in flat["notes"]),
          f"the flat build loses: {flat['score']} < {good['score']}, flagged {flat['failed']}, notes {flat['notes']}")
    check(silent["score"] < good["score"] and "the end is near silence" in silent["failed"] and NO_HIT_NOTE in silent["notes"],
          f"the silent end loses: {silent['score']} < {good['score']}, flagged {silent['failed']}, note: no hit in the music")
    # a take that fades over its last bars (ACE-Step's outro): made at the target length it ends near silence; made with
    # extra bars and cut, it keeps its end energy
    faded, _ = measure_take(synth_take(bpm, bars, secs, 0.1, "outro"), bpm, bars, secs)
    cut, ycut = measure_take(synth_take(bpm, bars, secs, 0.1, "outro", extra=6), bpm, bars, secs)
    tail = np.abs(ycut[-int(0.002 * SR):]).max()
    check("the end is near silence" in faded["failed"] and "the end is near silence" not in cut["failed"] and cut["end_vs_drop_db"] >= -6
          and len(ycut) == n_target and abs(cut["grid"]["offset_s"] - 0.1) <= 0.005 and tail < 0.01 and not cut["failed"],
          f"a fading take made with 6 extra bars and cut keeps its end: end {faded['end_vs_drop_db']:+.1f} dB against the drop "
          f"without them (fails), {cut['end_vs_drop_db']:+.1f} dB with them; {len(ycut)} samples (want {n_target}); grid "
          f"{cut['grid']['offset_s'] * 1000:+.1f} ms (want +100); last 2 ms peak {tail:.4f} (faded, no click); "
          f"fails: {cut['failed']}")
    # the whole pipeline on made-up takes: reuse, pick, level, score.json in score.py's format
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "music"
        (out / "takes").mkdir(parents=True)
        a = argparse.Namespace(description="self-test", bpm=bpm, key="A minor", bars=bars, sections="hook:2,build:4,drop:5,end:1",
                               takes=3, seed=11, out=str(out), lufs=-18.0, pick=None, with_lm=False, ace_python="/nonexistent",
                               extra_bars=0)
        for seed, kind in ((11, "flat"), (23, "good"), (37, "silent_end")):
            wav = out / "takes" / f"take-s{seed}.wav"
            score.write_wav(wav, synth_take(bpm, bars, secs, 0.12, kind, seed) * 0.9)
            wav.with_suffix(".json").write_text(json.dumps({"bpm": bpm, "bars": bars, "seed": seed, "key": "A minor", "description": "self-test"}))
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cmd_make(a)
        rep = json.loads((out / "takes.json").read_text()) if (out / "takes.json").exists() else {}
        spec = json.loads((out / "score.json").read_text()) if (out / "score.json").exists() else {}
        n = len(read_stereo(out / "music.wav")) if (out / "music.wav").exists() else 0
        tp = rep.get("music", {}).get("true_peak", 99)
        check(rc == 0 and rep.get("winner") == 23 and n == n_target and tp <= -2.95,
              f"pipeline: winner seed {rep.get('winner')} (want 23, the good take), music.wav {n} samples (want {n_target}), "
              f"true peak {tp} dBFS (want <= -3.0, within 0.05), {rep.get('music', {}).get('lufs')} LUFS")
        _, _, _, ref, _ = score.make("pulse", bpm=bpm, key="A minor", bars=bars, sections="hook:2,build:4,drop:5,end:1")
        missing = sorted(set(ref) - set(spec))
        check(not missing and spec.get("cues") == ref["cues"] and spec.get("sections") == ref["sections"],
              f"score.json has every key score.py writes{'' if not missing else ' (missing ' + str(missing) + ')'}, and the same cues "
              f"{spec.get('cues')} and sections")
        a.description = "another description"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc2 = cmd_make(a)
        check(rc2 == 2 and (out / "takes" / "take-s23.wav").exists(),
              "takes made from another description are refused and kept (exit 2), never overwritten")
        a.description, a.takes, a.seed = "self-test", 1, 99
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc3 = cmd_make(a)
        check(rc3 == 3, "a take to make with no ACE-Step installed stops with exit 3 and points to score.py")
        # with extra bars: the take file names its extra bars, is reused only when they match, and is cut to the target
        a.takes, a.seed, a.extra_bars = 1, 50, 6
        wav = out / "takes" / "take-s50-x6.wav"
        score.write_wav(wav, synth_take(bpm, bars, secs, 0.12, "outro", 50, extra=6) * 0.9)
        wav.with_suffix(".json").write_text(json.dumps({"bpm": bpm, "bars": bars + 6, "extra_bars": 6, "seed": 50, "key": "A minor",
                                                        "description": "self-test"}))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc4 = cmd_make(a)
        rep = json.loads((out / "takes.json").read_text())
        n = len(read_stereo(out / "music.wav"))
        a.extra_bars = 4                                                  # other extra bars: another take, which needs ACE-Step
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc5 = cmd_make(a)
        check(rc4 == 0 and rep.get("winner") == 50 and n == n_target and isinstance(rep.get("notes"), list) and not rep.get("warning")
              and rc5 == 3,
              f"pipeline with 6 extra bars: take-s50-x6.wav reused and cut to {n} samples (want {n_target}), "
              f"warning {rep.get('warning')}; with 4 extra bars it is not reused (exit {rc5}, want 3)")
    print(f"ace_takes self-test: {sum(checks)}/{len(checks)} passed")
    return 0 if all(checks) else 1


def main():
    ap = argparse.ArgumentParser(description="ACE-Step takes on the tempo grid, scored against the sections")
    ap.add_argument("description", nargs="?")
    ap.add_argument("--bpm", type=int)
    ap.add_argument("--key", default="A minor")
    ap.add_argument("--bars", type=int, default=8)
    ap.add_argument("--sections", help="hook:N,build:N,drop:N,end:N in bars (default: as score.py)")
    ap.add_argument("--takes", type=int, default=3)
    ap.add_argument("--extra-bars", type=int, help="bars made after the target and cut, so the model's fade-out falls after the cut "
                                                   "(default: max(4, half the bars); 0 keeps the model's own ending)")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out")
    ap.add_argument("--lufs", type=float, default=-18.0, help="music level, as score.py (true peak is always under -3 dBTP)")
    ap.add_argument("--pick", type=int, help="use this take's seed instead of the best score (after the person listened)")
    ap.add_argument("--with-lm", action="store_true", help="ACE-Step's planning model too (bigger download, slower)")
    ap.add_argument("--ace-python", help="the ACE-Step Python (default: toolbox.py path ace-step python)")
    ap.add_argument("--measure", metavar="FILE", help="measure one file and print its numbers; writes nothing")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.bpm:
        ap.error("--bpm is required")
    if a.measure:
        return cmd_measure(a)
    if not a.description or not a.out:
        ap.error('give a description and --out, like: ace_takes.py "punchy electronic, bright synths" --bpm 128 --bars 8 --out sound/')
    return cmd_make(a)


if __name__ == "__main__":
    sys.exit(main())
