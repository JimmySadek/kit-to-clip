#!/usr/bin/env python3
"""Kit to Clip finish: plan a HyperFrames cut for a destination, then finish and verify the rendered file.

  finish.py plan   --profile tiktok[,instagram-feed] [--project <dir>]
      prints the canvas and the safe box in pixels; with --project also writes platform.json and platform.css (canvas + safe-area CSS variables) for the build.

  finish.py finish <render.mp4> --profile tiktok[,...] --out <dir> [--name my-video] [--cover-at 12.5]
                   [--cues cue-sheet.json | --no-sync "reason"]
      per profile: canvas check (never stretches), loudness master to -14 LUFS with a true-peak ceiling (measure, gain,
      true-peak limiter, then correct on the encoded file until loudness and peak are both in; the report states the
      loudness range), master encode, share encode under the size cap, cover PNG, 1 fps contact sheet, safe-area overlay
      PNG, and <name>-<profile>.report.json with every measured number. Exit 1 if any check fails.
      A render with sound is refused unless a passing sync report exists for exactly this file (see sync), or
      --no-sync "reason" says why not (for example "footage's own sound"); the reason is printed and recorded.
      Checks on the encoded file: a flat first frame (--allow-flat-open if intended), black flashes under 0.5 s,
      and for looping profiles (website-loop, gif) an invisible loop seam; long black holds and freezes mid-video
      are warnings. The gif profile also writes -share.gif (15 fps, loops forever, under its size cap).

  finish.py sync <render> --cues <cue-sheet.json> [--out report.json] [--window -33,45]
      does the sound follow the picture? On the encoded file, for each cue (a picture moment) it finds the strongest
      sound onset within -100/+150 ms of the picture time and passes it inside -33 ms (one frame late) to +45 ms (early).
      Also reports how well picture changes and sound onsets match over the whole file (no pass mark). Writes
      <render>.sync.json next to the render, which `finish` reads. Cue sheet: [{"cue": "...", "picture_t": 4.69, "sound_t": 4.66}].

  finish.py audio <mix.wav|video>
      what the render will do to a mix before finish sees it: HyperFrames turns a track down when its AAC true peak is over
      -1 dBFS. Reports loudness, range, true peaks and the predicted loss.

  finish.py flash <render>
      the flash guard on its own (it also runs inside finish and loop): fails when any part of the picture about the
      size of a quarter of the central field of view flashes more than 3 times in one second (WCAG 2.3.1, general and
      saturated-red flashes). A screening aid, not a certified Harding test.

  finish.py check  --project <dir>
      loads the composition in headless Chrome and fails on script errors, missing files or no registered
      timeline (things HyperFrames lint does not catch). Needs node + puppeteer-core (HyperFrames ships it).

  finish.py loop   <render> --out <dir> [--name n] [--export mp4,webm,mov,apng,webp,gif] [--gif-profile gif]
      loop and loader deliveries from one render (a transparent MOV or WebM from `hyperframes render --format mov`
      keeps its alpha in webm, mov, apng, webp and gif): fails when the loop seam jumps, when an export's encoder is
      missing, when the GIF breaks its profile's size or frame cap, or when it flashes (WCAG 2.3.1). Writes a poster PNG,
      a still for reduced motion (--rest-at, default the last frame), and report.json whose embed_html shows the still to
      people who turn motion off and adds a pause button to loops over 5 s (WCAG 2.2.2).

  finish.py snippet --project <dir> --out <dir> [--name n]
      a live HTML snippet: the composition plays and loops in any browser without HyperFrames (single-file
      compositions only: no sub-compositions, video or audio), honouring reduced motion. Checked in headless Chrome.

  finish.py anchors --project <dir> [--bpm 120 | --beats beats/<audio>.json] [--words transcript.json]
                    [--window -0.034,0.045] [--scene-window -0.2,1.8]
      scenes tied to the music or the voice: every element with data-anchor ("beat:8", "word:launch", "word:launch#2",
      "t:3.5") must start moving, or come to rest, inside the window around its anchor. Measured on the running timeline
      (the composition is loaded like the renderer does and sampled frame by frame), not from data-start or data-at.
      Elements marked data-anchor-scope="scene" get the wide window. Fails on drift, an element that never moves, an
      anchor it cannot resolve, or no anchors at all.

  finish.py hook   --project <dir> [--by 3]
      the first three seconds: fails when the first frame shows only background, when no readable text or logo is on
      screen by --by seconds (so it works muted), or when nothing moves in the first second.

  Also in this folder: trace.mjs (motion.json: how each element moves, frame by frame, for sound that follows the picture).

Stdlib + ffmpeg/ffprobe, plus numpy for sync and audio (the engine's Python has it). Exit codes: 0 pass, 1 check failed, 2 usage/profile problem.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILES = json.loads((HERE.parent / "profiles.json").read_text())
DEF = PROFILES["defaults"]
# Apple's AAC encoder keeps true peak under the ceiling on sharp transients; ffmpeg's native aac can overshoot ~3 dB
AAC = "aac_at" if "aac_at" in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout else "aac"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt:format=duration,size",
             "-of", "json", str(path)])
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    num, den = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    return {"w": v.get("width"), "h": v.get("height"), "fps": round(int(num) / max(1, int(den)), 3), "vcodec": v.get("codec_name"),
            "audio": a is not None, "duration": float(d["format"]["duration"]), "bytes": int(d["format"]["size"])}


def loudness(path):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-"])
    txt = r.stderr
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", txt)
    tp = re.findall(r"Peak:\s+(-?[\d.inf]+) dBFS", txt)
    return (float(i[-1]) if i else None, float(tp[-1]) if tp and tp[-1] != "-inf" else None)


def get_profiles(arg):
    names = [p.strip() for p in arg.split(",") if p.strip()]
    missing = [n for n in names if n not in PROFILES["profiles"]]
    if missing:
        print(f"finish: no profile for {', '.join(missing)}. Known: {', '.join(PROFILES['profiles'])}. "
              "Ask for the destination's canvas and interface areas instead of guessing.", file=sys.stderr)
        sys.exit(2)
    return [(n, PROFILES["profiles"][n]) for n in names]


# ---------------------------------------------------------------- plan
def cmd_plan(a):
    profs = get_profiles(a.profile)
    proj = Path(a.project) if a.project else None
    out = {"profiles": {}, "note": PROFILES["_about"]}
    css = ["/* Kit to Clip finish: canvas + safe areas (heuristic, verify in the upload preview) */"]
    for n, p in profs:
        out["profiles"][n] = p
        if p["canvas"]:
            W, H = p["canvas"]
            s = p["safe"]
            css.append(f".cut-{n} {{ --canvas-w: {W}px; --canvas-h: {H}px; --safe-top: {round(H*s['top'])}px; --safe-bottom: {round(H*s['bottom'])}px; "
                       f"--safe-left: {round(W*s['left'])}px; --safe-right: {round(W*s['right'])}px; }}")
    if proj:
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "platform.json").write_text(json.dumps(out, indent=1))
        (proj / "platform.css").write_text("\n".join(css) + "\n")
    for n, p in profs:
        c = p["canvas"]
        print(f"{n}: canvas {c[0]}x{c[1] if c else ''}" if c else f"{n}: canvas free", "| safe", p["safe"], "|", p["safe_source"])
        if c:
            sf = p["safe"]
            print(f"  safe box in pixels: x {round(c[0] * sf['left'])}-{c[0] - round(c[0] * sf['right'])}, "
                  f"y {round(c[1] * sf['top'])}-{c[1] - round(c[1] * sf['bottom'])} "
                  f"(top {round(c[1] * sf['top'])}, bottom {round(c[1] * sf['bottom'])}, left {round(c[0] * sf['left'])}, right {round(c[0] * sf['right'])})")
        snd = p.get("sound")
        if snd:
            print(f"  sound: {snd.get('music', '')} ({snd.get('note', '')})")
        if p.get("audio") != "none":
            print("  a video with sound must pass the sync check before it is finished (finish.py sync, see the sound module)")
    if proj:
        print(f"wrote {proj/'platform.json'} and platform.css")


# ---------------------------------------------------------------- finish
def loudness_stats(path):
    """(integrated loudness in LUFS, loudness range in LU, true peak in dBFS) of a file's audio; None where it cannot be measured."""
    txt = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr
    tail = txt[txt.rindex("Summary"):] if "Summary" in txt else ""
    num = lambda pat: (lambda m: float(m.group(1)) if m else None)(re.search(pat, tail))
    return num(r"I:\s+(-?[\d.]+) LUFS"), num(r"LRA:\s+([\d.]+) LU"), num(r"Peak:\s+(-?[\d.]+) dBFS")


def master_audio(src, dst_audio, target_i, target_tp, lra_max=11):
    """Loudness master that lands on the target whatever the mix. Measure the source, set the gain to reach the target,
    limit true peak (4x oversampled, 5 ms look-ahead, 80 ms release), encode, then measure the file that will ship and
    correct: loudness out means the gain moves, peak over means the limiter's ceiling drops (the AAC encoder adds up to
    about 1 dB to the peak, and turning the whole track down instead would leave the loudness short). Repeat until both
    are in. The older loudnorm flow could not add gain past the peak ceiling, so a spiky mix came out quiet (-15.3 LUFS for
    a target of -14 LUFS). Returns the numbers for the report and warnings for the person."""
    i0, lra0, tp0 = loudness_stats(src)
    if i0 is None or tp0 is None or i0 < -60:
        raise RuntimeError("the audio is silent or too quiet to master")
    gain, ceiling_db = target_i - i0, target_tp - 0.3
    wav = Path(dst_audio).with_suffix(".limited.wav")
    for _ in range(10):
        af = (f"volume={gain:.3f}dB,aresample=192000,alimiter=limit={10 ** (ceiling_db / 20):.4f}:attack=5:release=80:level=false,"
              "aresample=48000")
        rr = run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-af", af, "-c:a", "pcm_f32le", str(wav)])
        if rr.returncode:
            raise RuntimeError(rr.stderr)
        rr = run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", AAC, "-b:a", "256k", str(dst_audio)])
        if rr.returncode:
            raise RuntimeError(rr.stderr)
        after_i, after_lra, after_tp = loudness_stats(dst_audio)
        loud_ok, peak_ok = abs(target_i - after_i) <= 0.3, after_tp is None or after_tp <= target_tp
        if loud_ok and peak_ok:
            break
        gain += target_i - after_i
        if not peak_ok:
            ceiling_db = max(-8.0, ceiling_db - (after_tp - target_tp) - 0.1)
    wav.unlink(missing_ok=True)
    limiter_db = max(0.0, tp0 + gain - ceiling_db)
    warnings = []
    if limiter_db > 3:
        warnings.append(f"the limiter takes about {limiter_db:.1f} dB off the loudest peaks to reach {target_i:g} LUFS: it will sound squashed. "
                        "Quieten the spikes in the mix (drums, clicks, hits) instead of letting the limiter do it")
    if after_lra is not None and after_lra > lra_max:
        warnings.append(f"the loudness range is {after_lra:.0f} LU (over {lra_max:g}): quiet parts may vanish on a phone speaker")
    return {"before_lufs": i0, "before_tp": tp0, "before_lra": lra0, "gain_db": round(gain, 2), "ceiling_db": round(ceiling_db, 2),
            "limiter_db": round(limiter_db, 1), "after_lufs": after_i, "after_tp": after_tp, "after_lra": after_lra, "warnings": warnings}


def encode_share(src_video, audio, dst, max_mb, start_crf=23):
    crf = start_crf
    while True:
        r = run(["ffmpeg", "-v", "error", "-y", "-i", str(src_video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                 "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(dst)])
        if r.returncode:
            raise RuntimeError(r.stderr)
        mb = dst.stat().st_size / 1048576
        if mb <= max_mb or crf >= 32:
            return crf, round(mb, 2)
        crf += 2


def motion_gate(video):
    """What only the encoded file shows: a flat first frame, short black flashes, long freezes mid-video.
    Returns (checks, warnings). Thresholds calibrated on real branded renders (28 Sep 2026): at pix_th 0.05 a dark
    brand gradient is not black, and a freeze-frame format holds a frame up to 1.8 s on purpose."""
    checks, warnings = {}, []
    px = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-frames:v", "1", "-vf", "scale=160:-2,format=gray",
                         "-f", "rawvideo", "-"], capture_output=True).stdout
    if px:
        mean = sum(px) / len(px)
        spread = (sum((b - mean) ** 2 for b in px) / len(px)) ** 0.5
        flat = spread < 2.0
        checks["first_frame"] = {"pass": not flat, "detail": f"one flat colour (luma {mean:.0f}): the video opens on nothing" if flat
                                 else f"has content (luma spread {spread:.1f})"}
    txt = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vf", "blackdetect=d=0:pix_th=0.05", "-an", "-f", "null", "-"]).stderr
    runs = [(float(a), float(d)) for a, d in re.findall(r"black_start:([\d.]+) black_end:[\d.]+ black_duration:([\d.]+)", txt)]
    flashes = [(a, d) for a, d in runs if d < 0.5]
    checks["black_flash"] = {"pass": not flashes, "detail": "; ".join(f"{d * 1000:.0f} ms black at {a:.2f} s" for a, d in flashes) if flashes else "none"}
    warnings += [f"black for {d:.1f} s from {a:.2f} s (intended?)" for a, d in runs if d >= 0.5]
    txt = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vf", "freezedetect=n=-60dB:d=2.5", "-an", "-f", "null", "-"]).stderr
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", txt)]
    durs = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", txt)]
    # a freeze that runs into the end has no duration line: that is the end card holding, which is fine
    warnings += [f"picture frozen {d:.1f} s from {a:.2f} s (intended hold?)" for a, d in zip(starts, durs)]
    checks["flash"] = flash_check(video)
    return checks, warnings


def loop_seam(video, workdir):
    """A seamless loop jumps no more from its last frame back to its first than between two neighbouring frames.
    Returns (seam MSE, median neighbour MSE), both on 360 px wide RGB frames so the numbers compare. Pixel
    difference, not SSIM: SSIM averages the whole frame and hides a small object jumping."""
    first, last = workdir / ".seam-first.png", workdir / ".seam-last.png"
    # 8-bit RGB like the neighbour pairs below: a 10-bit or alpha source would otherwise give 16-bit PNGs and MSE
    # numbers on a different scale
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-frames:v", "1", "-vf", "scale=360:-2,format=rgb24", str(first)])
    run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.5", "-i", str(video), "-vf", "scale=360:-2,format=rgb24", "-update", "1", str(last)])
    seam = re.findall(r"mse_avg:([\d.]+)", run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(last), "-i", str(first),
                                                   "-lavfi", "psnr=stats_file=-", "-f", "null", "-"]).stdout)
    for f in (first, last):
        f.unlink(missing_ok=True)
    graph = ("[0:v]scale=360:-2,format=rgb24,split[x][y];[x]trim=start_frame=1,setpts=PTS-STARTPTS[a];"
             "[y]setpts=PTS-STARTPTS[b];[a][b]psnr=stats_file=-")
    pairs = sorted(float(v) for v in re.findall(r"mse_avg:([\d.]+)", run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
                                                                          "-filter_complex", graph, "-f", "null", "-"]).stdout))
    if not seam or not pairs:
        return None, None
    return float(seam[-1]), pairs[len(pairs) // 2]


# ---------------------------------------------------------------- flash guard (WCAG 2.3.1)
FLASH_GRID = 6            # 6 x 6 cells: one cell is about a quarter of a 10-degree field of view on a typical screen
FLASH_DELTA = 0.10        # a general flash: opposing changes of at least 10% relative luminance ...
FLASH_DARK = 0.80         # ... where the darker state is below 0.80
FLASH_MAX_PER_S = 3       # more than three flashes in any one second fails
RED_RATIO = 0.80          # saturated red: R / (R + G + B) >= 0.8 (sRGB values)


def _transitions(series, delta):
    """Times (frame indices) where a cell's value finishes a swing of at least `delta`, ignoring smaller wiggles.
    Each swing is one transition; two opposing transitions make one flash."""
    out, lo_i, hi_i, direction = [], 0, 0, 0
    lo = hi = series[0]
    for i, v in enumerate(series):
        if direction >= 0:                       # rising (or unknown): track the peak, a fall of delta ends the rise
            if v > hi:
                hi, hi_i = v, i
            if hi - v >= delta and hi - lo >= delta:
                out.append((hi_i, "up", lo, hi))
                direction, lo, lo_i = -1, v, i
            elif direction == 0 and v < lo:
                lo, lo_i = v, i
        if direction < 0:                        # falling: track the trough, a rise of delta ends the fall
            if v < lo:
                lo, lo_i = v, i
            if v - lo >= delta and hi - lo >= delta:
                out.append((lo_i, "down", lo, hi))
                direction, hi, hi_i = 1, v, i
    if direction > 0 and hi - lo >= delta:
        out.append((hi_i, "up", lo, hi))
    elif direction < 0 and hi - lo >= delta:
        out.append((lo_i, "down", lo, hi))
    return out


def flash_check(video):
    """WCAG 2.3.1 (three flashes or below) on the encoded file, per cell of a 6 x 6 grid: general flashes (relative
    luminance swings of 10% or more with the darker state under 0.80) and saturated-red flashes. Returns a check dict.
    A screening aid, not a certified Harding test: run one of those before broadcast."""
    np = _numpy()
    info = probe(video)
    fps = info.get("fps") or 30
    w = 96
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={w}:-2:flags=area,format=rgb24", "-f", "rawvideo", "-"],
                       capture_output=True)
    if r.returncode or not r.stdout:
        return {"pass": True, "detail": "could not read the frames (not checked)"}
    h_probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                              str(video)], capture_output=True, text=True).stdout.strip().split(",")
    try:
        sw, sh = int(h_probe[0]), int(h_probe[1])
        h = int(round(w * sh / sw / 2) * 2)
    except (ValueError, IndexError):
        h = 54
    frames = np.frombuffer(r.stdout, np.uint8)
    n = frames.size // (w * h * 3)
    if n < 2:
        return {"pass": True, "detail": "too short to flash"}
    rgb = frames[: n * w * h * 3].reshape(n, h, w, 3).astype(float) / 255.0
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lum = lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722
    total = rgb.sum(axis=3) + 1e-6
    red = (rgb[..., 0] / total >= RED_RATIO) & (rgb[..., 0] > 0.2)
    ys = np.array_split(np.arange(h), FLASH_GRID)
    xs = np.array_split(np.arange(w), FLASH_GRID)
    worst = (0, None, None, "general")             # (flashes in one second, time, cell, kind)
    window = max(1, int(round(fps)))
    for gy, yy in enumerate(ys):
        for gx, xx in enumerate(xs):
            cell = lum[:, yy[0]:yy[-1] + 1, xx[0]:xx[-1] + 1].mean(axis=(1, 2))
            trans = [t for t in _transitions(list(cell), FLASH_DELTA) if t[2] < FLASH_DARK]
            redcell = red[:, yy[0]:yy[-1] + 1, xx[0]:xx[-1] + 1].mean(axis=(1, 2))
            rtrans = _transitions(list(redcell), 0.5)            # half the cell turning saturated red, and back
            for kind, tlist in (("general", trans), ("red", rtrans)):
                times = [t[0] for t in tlist]
                j = 0
                for i in range(len(times)):
                    while times[i] - times[j] >= window:
                        j += 1
                    flashes = (i - j + 1) // 2
                    if flashes > worst[0]:
                        worst = (flashes, times[j] / fps, (gx, gy), kind)
    count, at, cell, kind = worst
    ok = count <= FLASH_MAX_PER_S
    where = f" at {at:.2f} s (grid cell {cell[0] + 1},{cell[1] + 1} of {FLASH_GRID}x{FLASH_GRID})" if at is not None else ""
    word = ("saturated-red " if kind == "red" else "") + ("flash" if count == 1 else "flashes")
    return {"pass": ok, "detail": (f"at most {count} {word} in any second{where}" if ok else
                                   f"{count} {word} in one second{where}: over the safe limit of {FLASH_MAX_PER_S} (WCAG 2.3.1); "
                                   "slow the cuts or reduce the brightness change")}


def cmd_flash(a):
    src = Path(a.video)
    if not src.exists():
        print(f"finish: {src} not found", file=sys.stderr)
        sys.exit(2)
    c = flash_check(src)
    print(("✓" if c["pass"] else "✗") + f" flash guard: {c['detail']}")
    sys.exit(0 if c["pass"] else 1)


def gif_fps(g, duration):
    """The profile's frame rate, lowered when a frame cap (e.g. LinkedIn's 250 frames) would otherwise be exceeded."""
    fps = g["fps"]
    if g.get("max_frames") and duration > 0:
        fps = min(fps, math.floor(g["max_frames"] / duration * 100) / 100)
    return fps


def make_gif(master, dst, g, alpha=False):
    """Palette GIF that loops forever; steps the width down until it fits the size cap. Returns (width, MB, fps, frames).
    alpha=True keeps a transparent background (GIF has 1-bit transparency)."""
    fps = gif_fps(g, probe(master)["duration"])
    for width in dict.fromkeys([g["max_width"], 540, 480, 360]):
        # one palette from the whole picture, position-fixed (bayer) dithering so still areas stay identical frame to
        # frame, and only the changed rectangle stored per frame: a mostly still loop stays small
        graph = (f"[0:v]fps={fps},scale={width}:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=full"
                 + (":reserve_transparent=1" if alpha else "") + "[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
                 + (":alpha_threshold=128" if alpha else ""))
        r = run(["ffmpeg", "-v", "error", "-y", "-i", str(master), "-filter_complex", graph, "-loop", "0", str(dst)])
        if r.returncode:
            raise RuntimeError(r.stderr)
        mb = round(dst.stat().st_size / 1048576, 2)
        if mb <= g["max_mb"]:
            break
    frames = count_frames(dst)
    return width, mb, fps, frames


def count_frames(video):
    r = run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames",
             "-of", "default=nw=1:nk=1", str(video)])
    try:
        return int(r.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


def gif_checks(g, width, mb, fps, frames):
    checks = {"gif_size": {"pass": mb <= g["max_mb"], "detail": f"{mb} MB at {width}px, {fps} fps, loops forever (cap {g['max_mb']} MB)"}}
    if g.get("max_frames"):
        checks["gif_frames"] = {"pass": frames is not None and frames <= g["max_frames"],
                                "detail": f"{frames} frames (cap {g['max_frames']})"}
    return checks


def cmd_finish(a):
    src = Path(a.render)
    if not src.exists():
        print(f"finish: {src} not found", file=sys.stderr)
        sys.exit(2)
    profs = get_profiles(a.profile)          # validate destinations before creating anything
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    info = probe(src)
    name = a.name or src.stem
    sync_check, sync_rep = sync_gate(a, src, info, profs)      # refuses (exit 1) before anything is written
    failed = False
    for pname, p in profs:
        rep = {"profile": pname, "source": str(src), "source_info": info, "checks": {}}
        if sync_check and p.get("audio") != "none" and p.get("sync_required", True):
            rep["checks"]["sync"] = sync_check
            if sync_rep:
                rep["sync"] = sync_rep
        canvas = p["canvas"]
        if canvas and [info["w"], info["h"]] != canvas:
            src_ar, dst_ar = info["w"] / info["h"], canvas[0] / canvas[1]
            if abs(src_ar - dst_ar) > 0.01:
                rep["checks"]["canvas"] = {"pass": False, "detail": f"render is {info['w']}x{info['h']}, {pname} needs {canvas[0]}x{canvas[1]}: "
                                           "different aspect ratio, needs a recomposed cut (not stretched, not auto-cropped)"}
                failed = True
                (out / f"{name}-{pname}.report.json").write_text(json.dumps(rep, indent=1))
                print(f"✗ {pname}: {rep['checks']['canvas']['detail']}")
                continue
            rep["checks"]["canvas"] = {"pass": True, "detail": f"same aspect, scaled {info['w']}x{info['h']} -> {canvas[0]}x{canvas[1]}"}
        else:
            rep["checks"]["canvas"] = {"pass": True, "detail": f"{info['w']}x{info['h']}"}
        base = out / f"{name}-{pname}"
        scale = ["-vf", f"scale={canvas[0]}:{canvas[1]}:flags=lanczos"] if canvas and [info["w"], info["h"]] != canvas else []
        # master video: copy when possible (no generation loss), otherwise high-quality re-encode
        vtmp = out / f".{name}-{pname}.video.mp4"
        vargs = (["-c:v", "copy"] if not scale and info["vcodec"] == "h264"
                 else scale + ["-c:v", "libx264", "-preset", "slow", "-crf", str(DEF["master_crf"]), "-pix_fmt", "yuv420p"])
        r = run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-an", *vargs, str(vtmp)])
        if r.returncode:
            raise RuntimeError(r.stderr)
        if p.get("audio") == "none" or not info["audio"]:
            master = base.with_name(base.name + "-master.mp4")
            vtmp.replace(master)
            rep["audio"] = "none"
            rep["checks"]["loudness"] = {"pass": True, "detail": "no audio track (by profile or source)"}
            share_src_audio = None
        else:
            atmp = out / f".{name}-{pname}.audio.m4a"
            snd = p.get("sound", {})
            au = master_audio(src, atmp, snd.get("loudness_lufs", DEF["loudness_lufs"]), DEF["true_peak_db"], snd.get("loudness_range_max", 11))
            rep["audio"] = au
            ok = (au["after_lufs"] is not None and abs(au["after_lufs"] - DEF["loudness_lufs"]) <= 1.0
                  and (au["after_tp"] is None or au["after_tp"] <= DEF["true_peak_db"]))
            rep["checks"]["loudness"] = {"pass": ok, "detail": f"{au['after_lufs']} LUFS, {au['after_tp']} dBTP, range {au['after_lra']} LU "
                                         f"(target {DEF['loudness_lufs']} ±1, ≤ {DEF['true_peak_db']})"}
            failed |= not ok
            master = base.with_name(base.name + "-master.mp4")
            r = run(["ffmpeg", "-v", "error", "-y", "-i", str(vtmp), "-i", str(atmp), "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart", str(master)])
            if r.returncode:
                raise RuntimeError(r.stderr)
            share_src_audio = atmp
        share = base.with_name(base.name + "-share.mp4")
        if share_src_audio:
            crf, mb = encode_share(vtmp if vtmp.exists() else master, share_src_audio, share, DEF["share_max_mb"])
        else:
            r = run(["ffmpeg", "-v", "error", "-y", "-i", str(master), "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(share)])
            crf, mb = 23, round(share.stat().st_size / 1048576, 2)
        rep["checks"]["share_size"] = {"pass": mb <= DEF["share_max_mb"], "detail": f"{mb} MB at CRF {crf} (cap {DEF['share_max_mb']} MB)"}
        failed |= mb > DEF["share_max_mb"]
        # checks only the encoded file can answer, then loop and GIF extras for looping destinations
        dur = probe(master)["duration"]
        mchecks, rep["warnings"] = motion_gate(master)
        rep["warnings"] += rep.get("audio", {}).get("warnings", []) if isinstance(rep.get("audio"), dict) else []
        if a.allow_flat_open and not mchecks.get("first_frame", {"pass": True})["pass"]:
            mchecks["first_frame"] = {"pass": True, "detail": mchecks["first_frame"]["detail"].split(":")[0] + ", allowed by --allow-flat-open"}
        rep["checks"].update(mchecks)
        failed |= not all(c["pass"] for c in mchecks.values())
        if p.get("loop"):
            seam, usual = loop_seam(master, out)
            ok = seam is not None and seam <= max(2 * usual, 10)
            rep["checks"]["loop_seam"] = {"pass": ok, "detail": (f"last-to-first frame change {seam:.0f} vs {usual:.0f} between neighbouring frames"
                                          + ("" if ok else ": the loop visibly jumps back")) if seam is not None else "could not measure"}
            failed |= not ok
        extra = []
        if p.get("gif"):
            gif = base.with_name(base.name + "-share.gif")
            gchecks = gif_checks(p["gif"], *make_gif(master, gif, p["gif"]))
            rep["checks"].update(gchecks)
            failed |= not all(c["pass"] for c in gchecks.values())
            extra.append(("gif", "-share.gif"))
        # cover, contact sheet, safe-area overlay (from the finished master, not from snapshots)
        cover_at = a.cover_at if a.cover_at is not None else round(dur * 0.4, 2)
        run(["ffmpeg", "-v", "error", "-y", "-ss", str(cover_at), "-i", str(master), "-frames:v", "1", str(base.with_name(base.name + "-cover.png"))])
        cols = 10
        run(["ffmpeg", "-v", "error", "-y", "-i", str(master), "-vf",
             f"fps=1,scale=216:-2,drawtext=text='%{{pts\\:hms}}':x=4:y=4:fontsize=14:fontcolor=white:box=1:boxcolor=black@0.6,tile={cols}x{math.ceil(dur/cols)}",
             "-frames:v", "1", str(base.with_name(base.name + "-contact.png"))])
        if canvas:
            W, H = canvas
            s = p["safe"]
            boxes = [f"drawbox=x=0:y=0:w={W}:h={int(H*s['top'])}:color=red@0.35:t=fill",
                     f"drawbox=x=0:y={H-int(H*s['bottom'])}:w={W}:h={int(H*s['bottom'])}:color=red@0.35:t=fill",
                     f"drawbox=x={W-int(W*s['right'])}:y=0:w={int(W*s['right'])}:h={H}:color=red@0.35:t=fill",
                     f"drawbox=x=0:y=0:w={int(W*s['left'])}:h={H}:color=red@0.35:t=fill"]
            run(["ffmpeg", "-v", "error", "-y", "-i", str(base.with_name(base.name + "-cover.png")), "-vf", ",".join(boxes),
                 str(base.with_name(base.name + "-safe-check.png"))])
        rep["outputs"] = {k: str(base.with_name(base.name + suf)) for k, suf in
                          [("master", "-master.mp4"), ("share", "-share.mp4"), ("cover", "-cover.png"), ("contact", "-contact.png"), ("safe_check", "-safe-check.png"), *extra]}
        rep["duration"] = dur
        for tmp in out.glob(f".{name}-{pname}.*"):
            tmp.unlink()
        (out / f"{name}-{pname}.report.json").write_text(json.dumps(rep, indent=1))
        mark = "✓" if all(c["pass"] for c in rep["checks"].values()) else "✗"
        print(f"{mark} {pname}: " + " | ".join(f"{k}: {v['detail']}" for k, v in rep["checks"].items()))
        for w in rep["warnings"]:
            print(f"  ⚠ {w}")
    sys.exit(1 if failed else 0)


# ---------------------------------------------------------------- loop exports
LOOP_EXPORTS = ("mp4", "webm", "mov", "apng", "webp", "gif")


def stream_info(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,pix_fmt:stream_tags",
             "-of", "json", str(path)])
    st = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    tags = {k.lower(): str(v) for k, v in (st.get("tags") or {}).items()}
    pix = st.get("pix_fmt", "")
    alpha = bool(re.search(r"(yuva|rgba|argb|bgra|abgr|gbrap|ya)", pix)) or tags.get("alpha_mode") == "1"
    return st.get("codec_name"), alpha


def has_encoder(name):
    return re.search(rf"\s{re.escape(name)}\s", run(["ffmpeg", "-hide_banner", "-encoders"]).stdout) is not None


def cmd_loop(a):
    src = Path(a.render)
    if not src.exists():
        print(f"finish: {src} not found", file=sys.stderr)
        sys.exit(2)
    wanted = [e.strip() for e in a.export.split(",") if e.strip()]
    unknown = [e for e in wanted if e not in LOOP_EXPORTS]
    if unknown:
        print(f"finish: unknown export {', '.join(unknown)}. Known: {', '.join(LOOP_EXPORTS)}", file=sys.stderr)
        sys.exit(2)
    gp = get_profiles(a.gif_profile)[0][1] if "gif" in wanted else None
    if gp is not None and not gp.get("gif"):
        print(f"finish: profile {a.gif_profile} has no gif settings", file=sys.stderr)
        sys.exit(2)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    name = a.name or src.stem
    codec, alpha = stream_info(src)
    dec = ["-c:v", "libvpx-vp9"] if codec == "vp9" and alpha else []      # ffmpeg's own VP9 decoder drops the alpha
    info = probe(src)
    rep = {"source": str(src), "source_info": {**info, "alpha": alpha}, "checks": {}, "outputs": {}, "warnings": []}
    seam, usual = loop_seam(src, out)
    ok = seam is not None and (seam <= max(2 * usual, 10) or a.allow_seam)
    rep["checks"]["loop_seam"] = {"pass": ok, "detail": (f"last-to-first frame change {seam:.0f} vs {usual:.0f} between neighbouring frames"
                                  + ("" if seam <= max(2 * usual, 10) else ": the loop visibly jumps back" + (", allowed by --allow-seam" if a.allow_seam else "")))
                                  if seam is not None else "could not measure"}
    if not alpha and any(e in wanted for e in ("webm", "mov", "apng", "webp")):
        rep["warnings"].append("the render has no transparency, so every export is opaque (render with --format mov for alpha)")
    rep["checks"]["flash"] = flash_check(src)
    base = out / name
    poster = base.with_name(name + "-poster.png")
    run(["ffmpeg", "-v", "error", "-y", *dec, "-i", str(src), "-frames:v", "1", str(poster)])
    rep["outputs"]["poster"] = str(poster)
    # reduced motion (WCAG 2.3.3, MDN prefers-reduced-motion): a still of the loop at rest, shown instead of the motion
    still = base.with_name(name + "-still.png")
    if a.rest_at is not None:          # an exact moment: seek on the output side, which is frame-accurate
        run(["ffmpeg", "-v", "error", "-y", *dec, "-i", str(src), "-ss", f"{a.rest_at:.3f}", "-frames:v", "1", str(still)])
        where = f"at {a.rest_at:.2f} s"
    else:                              # the last frame: decode the final half second and keep the last image
        run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.5", *dec, "-i", str(src), "-update", "1", str(still)])
        where = "on the last frame"
    ok = still.exists() and still.stat().st_size > 0
    rep["checks"]["reduced_motion"] = {"pass": ok, "detail": f"still {where}, for people who turn motion off" if ok
                                       else "could not write the still"}
    if ok:
        rep["outputs"]["still"] = str(still)
    enc = {
        "mp4": (".mp4", ["-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart"], "libx264"),
        "webm": (".webm", ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-row-mt", "1", "-auto-alt-ref", "0",
                           "-pix_fmt", "yuva420p" if alpha else "yuv420p", "-an"], "libvpx-vp9"),
        "mov": (".mov", ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le" if alpha else "yuv444p10le", "-an"], "prores_ks"),
        "apng": (".png", ["-plays", "0", "-pix_fmt", "rgba" if alpha else "rgb24", "-f", "apng"], "apng"),
    }
    for e in wanted:
        if e in enc:
            suf, args, encoder = enc[e]
            dst = base.with_name(f"{name}-loop{suf}" if e != "apng" else f"{name}-loop.apng.png")
            if not has_encoder(encoder):
                rep["checks"][f"export_{e}"] = {"pass": False, "detail": f"this ffmpeg has no {encoder} encoder"}
                continue
            r = run(["ffmpeg", "-v", "error", "-y", *dec, "-i", str(src), *args, str(dst)])
            good = r.returncode == 0 and dst.exists() and dst.stat().st_size > 0
            rep["checks"][f"export_{e}"] = {"pass": good, "detail": f"{round(dst.stat().st_size / 1048576, 2)} MB" if good else r.stderr.strip()[-300:]}
            if good:
                rep["outputs"][e] = str(dst)
        elif e == "webp":
            dst = base.with_name(f"{name}-loop.webp")
            q = ["-q:v", "75"]
            if has_encoder("libwebp_anim"):
                r = run(["ffmpeg", "-v", "error", "-y", *dec, "-i", str(src), "-c:v", "libwebp_anim", "-loop", "0", "-lossless", "0", *q,
                         *(["-pix_fmt", "yuva420p"] if alpha else []), "-an", str(dst)])
                good, how = r.returncode == 0, "ffmpeg libwebp_anim"
                err = r.stderr
            elif run(["which", "img2webp"]).returncode == 0:
                tmp = out / f".{name}-webp-frames"
                tmp.mkdir(exist_ok=True)
                run(["ffmpeg", "-v", "error", "-y", *dec, "-i", str(src), "-pix_fmt", "rgba" if alpha else "rgb24", str(tmp / "f%05d.png")])
                frames = sorted(tmp.glob("f*.png"))
                ms = max(1, round(1000 / (info["fps"] or 30)))
                r = run(["img2webp", "-loop", "0", "-lossy", "-q", "75", "-d", str(ms), *map(str, frames), "-o", str(dst)])
                good, how, err = r.returncode == 0, "img2webp", r.stderr
                for f in frames:
                    f.unlink()
                tmp.rmdir()
            else:
                good, how, err = False, "", "no WebP encoder: this ffmpeg has no libwebp_anim and img2webp is missing (re-run setup/install.sh)"
            good = good and dst.exists() and dst.stat().st_size > 0
            rep["checks"]["export_webp"] = {"pass": good, "detail": f"{round(dst.stat().st_size / 1048576, 2)} MB via {how}" if good else err.strip()[-300:]}
            if good:
                rep["outputs"]["webp"] = str(dst)
        elif e == "gif":
            dst = base.with_name(f"{name}-loop.gif")
            if dec:        # decode the VP9 alpha once into a lossless intermediate the GIF filters can read
                mid = out / f".{name}-gif-src.mov"
                run(["ffmpeg", "-v", "error", "-y", *dec, "-i", str(src), "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", str(mid)])
                gsrc = mid
            else:
                gsrc = src
            gc = gif_checks(gp["gif"], *make_gif(gsrc, dst, gp["gif"], alpha=alpha))
            if dec:
                mid.unlink(missing_ok=True)
            rep["checks"].update({f"{k} ({a.gif_profile})": v for k, v in gc.items()})
            rep["outputs"]["gif"] = str(dst)
    if "webm" in rep["outputs"] or "mp4" in rep["outputs"]:
        sources = "".join(f'<source src="{Path(rep["outputs"][k]).name}" type="video/{k}">' for k in ("webm", "mp4") if k in rep["outputs"])
        stillname = Path(rep["outputs"].get("still", poster)).name
        long_loop = (info["duration"] or 0) > 5
        # WCAG 2.2.2: moving content that lasts more than 5 s and plays with other content needs a pause control
        button = ('<button class="k2c-pause" type="button" aria-label="Pause animation" '
                  'onclick="var v=this.previousElementSibling.previousElementSibling;if(v.paused){v.play();this.textContent=\'❚❚\';'
                  'this.setAttribute(\'aria-label\',\'Pause animation\')}else{v.pause();this.textContent=\'▶\';'
                  'this.setAttribute(\'aria-label\',\'Play animation\')}">❚❚</button>') if long_loop else ""
        rep["embed_html"] = (
            f'<div class="k2c-loop-wrap"><video class="k2c-loop" autoplay muted loop playsinline poster="{poster.name}">{sources}</video>'
            f'<img class="k2c-still" src="{stillname}" alt="">{button}</div>\n'
            '<style>.k2c-loop-wrap{position:relative;display:inline-block}.k2c-still{display:none}'
            '.k2c-pause{position:absolute;right:8px;bottom:8px;font:14px/1 sans-serif;padding:6px 8px;border:0;border-radius:4px;'
            'background:rgba(0,0,0,.55);color:#fff;cursor:pointer}'
            '@media (prefers-reduced-motion: reduce){.k2c-loop,.k2c-pause{display:none}.k2c-still{display:block;max-width:100%}}</style>')
    (out / f"{name}-loop.report.json").write_text(json.dumps(rep, indent=1))
    failed = not all(c["pass"] for c in rep["checks"].values())
    print(("✗" if failed else "✓") + f" loop {name} ({'transparent' if alpha else 'opaque'}): "
          + " | ".join(f"{k}: {v['detail']}" for k, v in rep["checks"].items()))
    for w in rep["warnings"]:
        print(f"  ⚠ {w}")
    sys.exit(1 if failed else 0)


# ---------------------------------------------------------------- snippet
SNIPPET_JS = """// Kit to Clip live snippet: plays this composition's timelines, looping, in any browser (no HyperFrames needed).
// Reduced motion: it holds still on the frame named by data-rest-at on the root (seconds), else the last frame.
(function () {
  if (window.__hf && typeof window.__hf.seek === "function") return;     // inside HyperFrames: the runtime drives it
  window.addEventListener("load", function () {
    var tls = window.__timelines || {}, root = document.querySelector("[data-composition-id]");
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    Object.keys(tls).forEach(function (k) {
      var tl = tls[k];
      if (still) { var at = Number(root && root.getAttribute("data-rest-at")); tl.pause(isNaN(at) || !root.hasAttribute("data-rest-at") ? tl.duration() : at); }
      else tl.repeat(-1).play(0);
    });
    window.__reelSnippet = { playing: !still, timelines: Object.keys(tls) };
  });
})();
"""
SNIPPET_SKIP = {"renders", "snapshots", "node_modules", ".git", "__pycache__"}


def cmd_snippet(a):
    import shutil
    proj = Path(a.project).resolve()
    idx = proj / "index.html"
    if not idx.exists():
        print(f"finish: no index.html in {proj}", file=sys.stderr)
        sys.exit(2)
    html = idx.read_text()
    blockers = [w for w, pat in (("sub-compositions (data-composition-src)", r"data-composition-src"), ("video", r"<video\b"), ("audio", r"<audio\b"))
                if re.search(pat, html)]
    if blockers:
        print(f"finish: a live snippet needs a single-file composition; this one uses {', '.join(blockers)}. "
              "Deliver the rendered loop exports instead (finish.py loop).", file=sys.stderr)
        sys.exit(2)
    name = a.name or proj.name
    dst = Path(a.out) / f"{name}-snippet"
    if dst.exists():
        shutil.rmtree(dst)
    for f in proj.rglob("*"):
        rel = f.relative_to(proj)
        if f.is_dir() or any(part in SNIPPET_SKIP for part in rel.parts) or rel.name.startswith(".") or rel.suffix in (".mp4", ".mov", ".webm", ".wav"):
            continue
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst / rel)
    (dst / "play.js").write_text(SNIPPET_JS)
    # outside HyperFrames nobody creates window.__timelines before the composition's own script registers into it
    init = '<script>window.__timelines = window.__timelines || {};</script>'
    out_html = re.sub(r"<head[^>]*>", lambda m: m.group(0) + init, html, count=1) if re.search(r"<head[^>]*>", html) else init + html
    out_html = out_html.replace("</body>", '<script src="play.js"></script>\n</body>') if "</body>" in out_html else out_html + '\n<script src="play.js"></script>\n'
    (dst / "index.html").write_text(out_html)
    m = re.search(r'data-width="(\d+)"[^>]*data-height="(\d+)"', html)
    w, h = (m.group(1), m.group(2)) if m else ("1080", "1080")
    (dst / "EMBED.md").write_text(f"# {name}: live snippet\n\nCopy this folder next to your page, then:\n\n"
                                  f'```html\n<iframe src="{name}-snippet/index.html" width="{w}" height="{h}" style="border:0;max-width:100%;aspect-ratio:{w}/{h};height:auto" '
                                  f'title="{name}" loading="lazy"></iframe>\n```\n\nIt loops forever and holds still for people who ask for reduced motion.\n')
    r = subprocess.run(["node", str(HERE / "snippetcheck.mjs"), str(dst)], env=dict(os.environ))
    sys.exit(r.returncode)


# ---------------------------------------------------------------- safe
SAFE_BOXES = {"tiktok": "120,252,840,1280", "instagram": "65,269,1015,1248", "instagram-reels": "65,269,1015,1248"}


def safe_box_for(name):
    """The safe box 'x0,y0,x1,y1' for a platform: a tuned box above, else any finish profile with a canvas (its safe
    margins in pixels), else the text itself when it is already four numbers. None when nothing matches."""
    if name in SAFE_BOXES:
        return SAFE_BOXES[name]
    p = PROFILES["profiles"].get(name)
    if isinstance(p, dict) and p.get("canvas"):
        (W, H), sf = p["canvas"], p["safe"]
        return f"{round(W * sf['left'])},{round(H * sf['top'])},{W - round(W * sf['right'])},{H - round(H * sf['bottom'])}"
    return name if re.fullmatch(r"\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*", name) else None


def cmd_safe(a):
    box = safe_box_for(a.platform)
    if box is None:
        names = sorted(set(SAFE_BOXES) | {n for n, p in PROFILES["profiles"].items() if isinstance(p, dict) and p.get("canvas")})
        print(f"finish safe: unknown platform {a.platform!r}. Use a profile ({', '.join(names)}) or x0,y0,x1,y1", file=sys.stderr)
        sys.exit(2)
    r = subprocess.run(["node", str(HERE / "safecheck.mjs"), str(Path(a.project).resolve()), box, str(a.step)], env=dict(os.environ))
    sys.exit(r.returncode)


# ---------------------------------------------------------------- anchors
ANCHOR_HIT_WINDOW = "-0.034,0.045"     # seconds, event minus anchor: from one frame (30 fps) early to a little late
ANCHOR_SCENE_WINDOW = "-0.2,1.8"       # for elements marked data-anchor-scope="scene": a scene may follow its beat by a moment


def measured_anchors(proj):
    """What the running timeline does, not what attributes say: [{label, anchor, declared, scope, events}] for every
    data-anchor element. anchorscheck.mjs loads the composition the way the renderer does, seeks through it frame by
    frame and reports when each element starts and stops moving (motion.mjs)."""
    r = subprocess.run(["node", str(HERE / "anchorscheck.mjs"), str(proj)], capture_output=True, text=True, env=dict(os.environ))
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("@@anchors ")), None)
    if r.returncode or line is None:
        print((r.stdout.strip() or r.stderr.strip()), file=sys.stderr if r.returncode == 2 else sys.stdout)
        sys.exit(r.returncode or 1)
    return json.loads(line[len("@@anchors "):])["rows"]


def cmd_anchors(a):
    proj = Path(a.project).resolve()
    if not (proj / "index.html").exists():
        print(f"finish: no index.html in {proj}", file=sys.stderr)
        sys.exit(2)
    try:
        win = {"hit": tuple(float(x) for x in a.window.split(",")), "scene": tuple(float(x) for x in a.scene_window.split(","))}
        assert all(len(w) == 2 for w in win.values())
    except (ValueError, AssertionError):
        print("finish: --window and --scene-window are two numbers in seconds, like -0.034,0.045", file=sys.stderr)
        sys.exit(2)
    beats = None
    beats_file = Path(a.beats) if a.beats else next(iter(sorted((proj / "beats").glob("*.json"))), None) if (proj / "beats").is_dir() else None
    if beats_file:
        beats = [b["time"] for b in json.loads(Path(beats_file).read_text()).get("beats", [])]
    words_file = Path(a.words) if a.words else (proj / "transcript.json" if (proj / "transcript.json").is_file() else None)
    words = json.loads(Path(words_file).read_text()) if words_file else None
    rows = measured_anchors(proj)
    if not rows:
        print("✗ anchors: no element has data-anchor, so no timing was checked (anchor scenes to a beat or a word first)")
        sys.exit(1)
    bad, good = [], []
    for row in rows:
        label, anchor, declared, scope, events = row["label"], row["anchor"], row["declared"], row["scope"], row["events"]
        kind, _, val = anchor.partition(":")
        t, why = None, None
        if kind == "t":
            t = float(val)
        elif kind == "beat":
            n = int(val)
            if beats is not None:
                t, why = (beats[n], None) if 0 <= n < len(beats) else (None, f"beat {n} is past the {len(beats)} beats in {beats_file}")
            elif a.bpm:
                t = n * 60 / a.bpm
            else:
                why = "a beat anchor needs --bpm or a beats file (hyperframes beats)"
        elif kind == "word":
            text, _, k = val.partition("#")
            if words is None:
                why = "a word anchor needs a transcript (hyperframes transcribe, or --words)"
            else:
                norm = lambda w: re.sub(r"[^\w']", "", w.lower())
                hits = [w for w in words if norm(w.get("text", "")) == norm(text)]
                idx = int(k or 1) - 1
                t, why = (hits[idx]["start"], None) if 0 <= idx < len(hits) else (None, f"'{text}'" + (f" #{k}" if k else "") + " is not in the transcript")
        else:
            why = f"unknown anchor '{anchor}' (use beat:N, word:text, t:seconds)"
        if not why and not events:
            why = "nothing on it ever moves or fades in, so there is no timing to check"
        if why:
            bad.append(f"{label} [{anchor}]: {why}")
            continue
        lo, hi = win["scene" if scope == "scene" else "hit"]
        inside = [e for e in events if lo - 1e-6 <= e["t"] - t <= hi + 1e-6]
        ev = min(inside or events, key=lambda e: abs(e["t"] - t))     # an event inside the window wins over a nearer one outside it
        drift = ev["t"] - t
        decl = f", declared {float(declared):.2f} s" if declared not in (None, "") else ""
        line = f"{label} [{anchor}] {ev['kind']} {ev['t']:.3f} s{decl}, anchor {t:.3f} s ({drift:+.3f} s)"
        if inside:
            good.append(line)
        else:
            bad.append(line + f": drifted outside {lo:+g}..{hi:+g} s")
    if bad:
        print(f"✗ anchors: {len(bad)} of {len(rows)} anchored element(s) off their anchor (measured on the running timeline)")
        for b in bad:
            print("  - " + b)
        sys.exit(1)
    print(f"✓ anchors: {len(rows)} anchored element(s) start or come to rest on their beat or word (measured on the running timeline)")
    for g_ in good:
        print("  " + g_)


# ---------------------------------------------------------------- sync
# Does the sound follow the picture? Measured on the encoded file, per picture moment ("cue"). Positive offset = the
# sound comes before the picture. The pass window is what people notice (ITU-R BT.1359: sound ahead of the picture is
# noticed from about 45 ms, sound behind it from about 125 ms; one frame late at 30 fps, 33 ms, is the strict limit).
SYNC_SR = 48000
SYNC_PASS_MS = (-33.0, 45.0)
SYNC_SEARCH_S = (-0.10, 0.15)      # where to look for the sound of a cue, around its picture time
SYNC_MIN_STRENGTH = 0.15           # an onset must reach this share of the file's strong onsets, or the cue has no sound


def _numpy():
    try:
        import numpy
        return numpy
    except ImportError:
        print("finish: the sync check needs numpy. The video engine's Python has it: source <kit-to-clip>/scripts/env.sh first.",
              file=sys.stderr)
        sys.exit(2)


def read_audio_mono(path, sr=SYNC_SR):
    np = _numpy()
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    if r.returncode or not r.stdout:
        return np.zeros(0)
    return np.frombuffer(r.stdout, np.float32).astype(float)


def spectral_flux(a, sr=SYNC_SR, hop=240, win=1024):
    """Sound onsets: how much the spectrum grows from one 21 ms window to the next, every 5 ms.
    Returns (flux per window, time of each window's centre in seconds)."""
    np = _numpy()
    starts = np.arange(0, max(0, len(a) - win), hop)
    if len(starts) < 2:
        return np.zeros(1), np.zeros(1)
    w = np.hanning(win)
    cols = np.arange(win)
    flux, prev = [0.0], None
    for i in range(0, len(starts), 1500):          # in chunks: a long video must not need gigabytes
        chunk = starts[i:i + 1500]
        lm = np.log1p(np.abs(np.fft.rfft(a[chunk[:, None] + cols[None, :]] * w, axis=1)) * 10)
        if prev is not None:
            flux.append(float(np.maximum(0, lm[0] - prev).sum()))
        flux.extend(np.maximum(0, np.diff(lm, axis=0)).sum(axis=1).tolist())
        prev = lm[-1]
    return np.array(flux), starts / sr + win / 2 / sr


def picture_vs_sound(video, audio, fps):
    """Whole file, reported only: how well the moments the picture changes match the moments the sound starts (a video
    whose sound ignores its picture scores near 0), and how well picture motion follows loudness."""
    np = _numpy()
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "scale=108:192,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)
    frames = np.frombuffer(r.stdout, np.uint8)
    n = len(frames) // (108 * 192)
    if n < 10 or len(audio) < 1:
        return None, None
    v = frames[: n * 108 * 192].reshape(n, 192, 108).astype(float)
    motion = np.r_[0, np.abs(np.diff(v, axis=0)).mean(axis=(1, 2))]
    spf = max(1, round(SYNC_SR / fps))
    rms = np.array([np.sqrt((audio[i * spf:(i + 1) * spf] ** 2).mean()) if len(audio[i * spf:(i + 1) * spf]) else 0.0 for i in range(n)])
    onset = np.r_[0, np.maximum(0, np.diff(20 * np.log10(rms + 1e-6)))]
    sm = lambda x, k=5: np.convolve(x, np.ones(k) / k, "same")

    def corr(x, y):
        return None if x.std() < 1e-12 or y.std() < 1e-12 else round(float(np.corrcoef(x, y)[0, 1]), 2)
    return corr(sm(np.abs(np.diff(np.r_[0, motion]))), sm(onset)), corr(sm(motion), sm(rms))


def file_sha1(path):
    import hashlib
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sync_report_path(render):
    render = Path(render)
    return render.with_name(render.stem + ".sync.json")


def load_cues(path):
    try:
        cues = json.loads(Path(path).read_text())
        assert isinstance(cues, list) and cues
        for c in cues:
            assert isinstance(c.get("cue"), str) and isinstance(c.get("picture_t"), (int, float))
    except (OSError, ValueError, AssertionError, AttributeError):
        print(f"finish: {path} is not a cue sheet. It is a JSON list like "
              '[{"cue": "chip 1 locks", "picture_t": 4.6875, "sound_t": 4.6775}]: one entry for each moment the sound is meant to hit.',
              file=sys.stderr)
        sys.exit(2)
    return cues


def measure_sync(render, cues, window_ms=SYNC_PASS_MS):
    """The sync report for one render: per cue the strongest sound onset within -100/+150 ms of its picture time."""
    np = _numpy()
    info = probe(render)
    a = read_audio_mono(render)
    fl, ft = spectral_flux(a)
    strong = float(np.percentile(fl, 99)) if len(fl) > 1 else 0.0
    rows = []
    for c in cues:
        t = float(c["picture_t"])
        idx = np.where((ft > t + SYNC_SEARCH_S[0]) & (ft < t + SYNC_SEARCH_S[1]))[0]
        if not len(idx) or strong <= 0:
            rows.append({"cue": c["cue"], "picture_t": t, "onset_t": None, "offset_ms": None, "pass": False, "why": "no sound here"})
            continue
        k = idx[np.argmax(fl[idx])]
        strength = float(fl[k] / strong)
        off = (t - float(ft[k])) * 1000
        if strength < SYNC_MIN_STRENGTH:
            rows.append({"cue": c["cue"], "picture_t": t, "onset_t": None, "offset_ms": None, "pass": False, "why": "no sound here",
                         "strength": round(strength, 2)})
            continue
        rows.append({"cue": c["cue"], "picture_t": t, "onset_t": round(float(ft[k]), 3), "offset_ms": round(off),
                     "pass": window_ms[0] <= off <= window_ms[1], "strength": round(strength, 2)})
    r_onsets, r_loud = whole_file_match(render, a, info["fps"])
    passed = sum(r["pass"] for r in rows)
    return {"render": str(render), "sha1": file_sha1(render), "duration": info["duration"], "pass_window_ms": list(window_ms),
            "positive_means": "the sound comes before the picture", "cues": rows, "cues_passed": passed, "cues_total": len(rows),
            "pass": passed == len(rows),
            "whole_file": {"picture_changes_vs_sound_onsets": r_onsets, "picture_motion_vs_loudness": r_loud,
                           "note": "reported only, no pass mark. A video whose sound ignores its picture scores near 0."}}


def whole_file_match(render, audio, fps):
    try:
        return picture_vs_sound(render, audio, fps)
    except Exception as e:                                # a report-only number must never sink the check
        print(f"  ⚠ whole-file match not measured: {e}")
        return None, None


def print_sync(rep):
    for r in rep["cues"]:
        if r["onset_t"] is None:
            print(f"   {r['cue']:24s} picture {r['picture_t']:7.3f} s  no sound onset near it")
        else:
            print(f"   {r['cue']:24s} picture {r['picture_t']:7.3f} s  sound {r['onset_t']:7.3f} s  ({r['offset_ms']:+d} ms){'' if r['pass'] else '  ✗'}")
    lo, hi = rep["pass_window_ms"]
    bad = [r["cue"] for r in rep["cues"] if not r["pass"]]
    print(f"{'✓' if rep['pass'] else '✗'} sync: {rep['cues_passed']} of {rep['cues_total']} cues have their sound inside {lo:+.0f}..{hi:+.0f} ms of the picture"
          + (f"; off: {', '.join(dict.fromkeys(bad))}" if bad else "") + " (positive = sound early)")
    w = rep["whole_file"]
    print(f"  whole file (reported only): picture changes vs sound onsets {w['picture_changes_vs_sound_onsets']}, "
          f"picture motion vs loudness {w['picture_motion_vs_loudness']}")


def cmd_sync(a):
    src = Path(a.render)
    if not src.exists():
        print(f"finish: {src} not found", file=sys.stderr)
        sys.exit(2)
    if not probe(src)["audio"]:
        print(f"finish: {src} has no sound, so there is nothing to check", file=sys.stderr)
        sys.exit(2)
    try:
        lo, hi = (float(x) for x in a.window.split(","))
    except ValueError:
        print("finish: --window is two numbers in milliseconds, like -33,45", file=sys.stderr)
        sys.exit(2)
    rep = measure_sync(src, load_cues(a.cues), (lo, hi))
    print_sync(rep)
    out = Path(a.out) if a.out else sync_report_path(src)
    out.write_text(json.dumps(rep, indent=1))
    print(f"  report: {out}")
    sys.exit(0 if rep["pass"] else 1)


def sync_gate(a, src, info, profs):
    """The hard gate of `finish`: a render with sound needs a passing sync report for exactly this file, or --no-sync with
    a reason. Returns (check dict, full report or None) to record in each finish report, or exits 1 when refused."""
    keeps_sound = [n for n, p in profs if info["audio"] and p.get("audio") != "none" and p.get("sync_required", True)]
    if not keeps_sound:
        return None, None
    if a.no_sync and a.cues:
        print("finish: use either --cues or --no-sync, not both", file=sys.stderr)
        sys.exit(2)
    if a.no_sync:
        print(f"  ⚠ sync check skipped by --no-sync: {a.no_sync}")
        return {"pass": True, "skipped": True, "detail": f"skipped: {a.no_sync}"}, None
    path = sync_report_path(src)
    rep, why = None, None
    if a.cues:
        rep = measure_sync(src, load_cues(a.cues))
        print_sync(rep)
        path.write_text(json.dumps(rep, indent=1))
    elif path.exists():
        rep = json.loads(path.read_text())
        if rep.get("sha1") != file_sha1(src):
            rep, why = None, f"the sync report {path.name} is for an earlier version of this render. Run sync again on this file."
    else:
        why = "this video has sound, and nothing shows the sound follows the picture."
    if rep is not None and not rep["pass"]:
        bad = [r["cue"] for r in rep["cues"] if not r["pass"]]
        why = (f"the sound does not follow the picture: {len(bad)} of {rep['cues_total']} cues are off ({', '.join(dict.fromkeys(bad))}). "
               "Move the sound or the picture, render again, and run sync again.")
    if why:
        print(f"✗ finish refused: {why}", file=sys.stderr)
        if rep is None:
            print("  If the sound is meant to hit picture moments, list them in a cue sheet and run:\n"
                  f"    finish.py sync {src} --cues <cue-sheet.json>\n"
                  "  If it is the footage's own sound (a clip that keeps its original audio), say so:\n"
                  "    finish.py finish ... --no-sync \"footage's own sound\"", file=sys.stderr)
        sys.exit(1)
    return {"pass": True, "detail": f"{rep['cues_passed']} of {rep['cues_total']} cues inside "
            f"{rep['pass_window_ms'][0]:+.0f}..{rep['pass_window_ms'][1]:+.0f} ms of the picture"}, rep


# ---------------------------------------------------------------- audio (preflight for a mix that goes into a composition)
def cmd_audio(a):
    """What will the render do to this audio? HyperFrames mixes the tracks and encodes them to AAC more than once (each
    encode adds a little to the peak), measures the true peak of the result and, if it is over -1.0 dBFS, turns the whole
    track down until it sits at -1.5 dBFS. A mix with hot peaks therefore arrives quieter than it was made: two test
    Reels lost 2.9 dB and 1.2 dB this way. This encodes twice and measures the same way, so its answer is close (within
    about 0.3 dB on those two Reels), not exact. Keep the mix's peaks low enough and the render leaves the level alone."""
    src = Path(a.file)
    if not src.exists() or not probe(src)["audio"]:
        print(f"finish: {src} not found or has no sound", file=sys.stderr)
        sys.exit(2)
    i, lra, tp = loudness_stats(src)
    tmps = [src.with_name(f".{src.stem}.aacprobe{n}.m4a") for n in (1, 2)]
    prev = src
    for t in tmps:                                     # two encode generations, as the render does
        run(["ffmpeg", "-v", "error", "-y", "-i", str(prev), "-vn", "-c:a", "aac", "-b:a", "192k", str(t)])
        prev = t
    _, _, aac_tp = loudness_stats(tmps[-1])
    for t in tmps:
        t.unlink(missing_ok=True)
    down = (-1.5 - aac_tp) if aac_tp is not None and aac_tp > -1.0 else 0.0
    print(f"{src.name}: {i} LUFS, range {lra} LU, true peak {tp} dBFS, true peak after two AAC encodes {aac_tp} dBFS")
    if down < 0:
        print(f"⚠ the render will turn this down by about {abs(down):.1f} dB (to about {i + down:.1f} LUFS): the AAC true peak is over -1.0 dBFS. "
              "Lower the mix's peaks (limit at -3 dBTP) so it reaches the render at the level you set.")
    else:
        print("✓ the render should leave this level alone (the AAC true peak is at or under -1.0 dBFS)")
    print("  finish still masters every delivery to -14 LUFS and -1 dBTP; this only says what the render does before that.")


# ---------------------------------------------------------------- hook
def cmd_hook(a):
    proj = Path(a.project).resolve()
    if not (proj / "index.html").exists():
        print(f"finish: no index.html in {proj}", file=sys.stderr)
        sys.exit(2)
    r = subprocess.run(["node", str(HERE / "hookcheck.mjs"), str(proj), str(a.by)], env=dict(os.environ))
    sys.exit(r.returncode)


# ---------------------------------------------------------------- check
def cmd_check(a):
    proj = Path(a.project).resolve()
    if not (proj / "index.html").exists():
        print(f"finish: no index.html in {proj}", file=sys.stderr)
        sys.exit(2)
    env = dict(os.environ)
    r = subprocess.run(["node", str(HERE / "consolecheck.mjs"), str(proj)], env=env)
    sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("plan"); p1.add_argument("--profile", required=True); p1.add_argument("--project", help="also write platform.json and platform.css into this project")
    p2 = sub.add_parser("finish"); p2.add_argument("render"); p2.add_argument("--profile", required=True); p2.add_argument("--out", required=True)
    p2.add_argument("--name"); p2.add_argument("--cover-at", type=float)
    p2.add_argument("--allow-flat-open", action="store_true", help="the video opens on one flat colour on purpose (e.g. a fade from black)")
    p2.add_argument("--cues", help="cue sheet for a video with sound: runs the sync check first and refuses to finish when the sound is off the picture")
    p2.add_argument("--no-sync", metavar="REASON", help="finish a video with sound without a sync check and say why (e.g. \"footage's own sound\"); the reason is printed and recorded")
    p3 = sub.add_parser("check"); p3.add_argument("--project", required=True)
    p4 = sub.add_parser("safe"); p4.add_argument("--project", required=True)
    p4.add_argument("--platform", required=True, help="a finish profile (youtube, instagram-reels, tiktok, ...) or x0,y0,x1,y1"); p4.add_argument("--step", type=float, default=0.2)
    p6 = sub.add_parser("loop"); p6.add_argument("render"); p6.add_argument("--out", required=True); p6.add_argument("--name")
    p6.add_argument("--export", default="mp4,webm,gif", help=f"comma list of {', '.join(LOOP_EXPORTS)}")
    p6.add_argument("--gif-profile", default="gif", help="profile whose gif settings (fps, width, size and frame caps) apply, e.g. linkedin-gif")
    p6.add_argument("--allow-seam", action="store_true", help="the loop jumps back on purpose (e.g. a loader that restarts)")
    p6.add_argument("--rest-at", type=float, help="seconds: the frame shown to people who turn motion off (default: the last frame)")
    p7 = sub.add_parser("snippet"); p7.add_argument("--project", required=True); p7.add_argument("--out", required=True); p7.add_argument("--name")
    p8 = sub.add_parser("anchors"); p8.add_argument("--project", required=True); p8.add_argument("--bpm", type=float)
    p8.add_argument("--beats"); p8.add_argument("--words")
    p8.add_argument("--window", default=ANCHOR_HIT_WINDOW, help="seconds, event minus anchor, for hits (default -0.034,0.045)")
    p8.add_argument("--scene-window", default=ANCHOR_SCENE_WINDOW, help='for elements marked data-anchor-scope="scene" (default -0.2,1.8)')
    p9 = sub.add_parser("sync"); p9.add_argument("render"); p9.add_argument("--cues", required=True, help="cue sheet: [{cue, picture_t, sound_t}]")
    p9.add_argument("--out", help="where to write the sync report (default: next to the render, <name>.sync.json)")
    p9.add_argument("--window", default="-33,45", help="pass window in ms, picture time minus sound time (default -33,45)")
    p10 = sub.add_parser("audio"); p10.add_argument("file", help="the mix (wav, mp3, m4a or a video) that goes into the composition")
    p11 = sub.add_parser("flash"); p11.add_argument("video", help="a render: fails on more than 3 flashes in any second (WCAG 2.3.1)")
    p5 = sub.add_parser("hook"); p5.add_argument("--project", required=True)
    p5.add_argument("--by", type=float, default=3.0, help="readable text or a logo must be on screen by this second")
    a = ap.parse_args()
    {"plan": cmd_plan, "finish": cmd_finish, "check": cmd_check, "safe": cmd_safe, "hook": cmd_hook, "loop": cmd_loop,
     "snippet": cmd_snippet, "anchors": cmd_anchors, "sync": cmd_sync, "audio": cmd_audio, "flash": cmd_flash}[a.cmd](a)


if __name__ == "__main__":
    main()
