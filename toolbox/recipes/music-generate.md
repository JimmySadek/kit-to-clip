# Original music from a description (ACE-Step 1.5)

**The default music source.** Free, MIT for the code and the models, and it runs on this computer (Apple silicon
through MLX). Offer it first in the music question (`sound/README.md`, step 1). The built-in music maker
(`sound/scripts/score.py`) is the fallback: no model, ready in seconds, every cue exact.

**Say before the ✋:** the first run downloads about 9.4 GB of models into `<engine>/tools/ace-step/checkpoints`, and
each take takes minutes.

## Make the music with `ace_takes.py`

```bash
python3 <kit-to-clip>/sound/scripts/ace_takes.py "energetic sports highlight track, punchy drums, synth bass, bright stabs" \
    --bpm 128 --key "A minor" --bars 8 --sections hook:2,build:2,drop:3,end:1 --takes 3 --seed 11 --out sound/
```

A raw take is not ready for a video. Measured on 9 Oct 2026: the beats sat 45 to 160 ms after the tempo grid, the drop
landed where the model chose, endings could fade to near silence, mixes were 80 to 94% bass, and the true peaks were
hot. `ace_takes.py` does what a builder did by hand that day:

1. **Makes the takes** with `toolbox/helpers/ace_music.py`: seeds 11, 23, 37 (the seed, +12, +26). Each take is made
   `--extra-bars` longer (default: 4, or half the bars when that is more), because ACE-Step fades out over its last
   bars: the fade falls after the cut. Take files made with the same settings, extra bars included, are reused, so a
   re-run is cheap.
2. **Puts each take on the grid.** It finds where the beats really are in the whole take (spread and tempo too),
   shifts it so beat 0 is at 0.000 s, and keeps exactly `bars x 4 x 60 / bpm` seconds. The last half beat fades out,
   so the cut does not click.
3. **Scores each take against the sections**, from the loudness of every bar of the cut audio: the build rises, the
   drop is clearly above the build, the end is not silent. Tight beats, a hit on the end cue, less bass and peaks that
   need little limiting add points. No hit in the music on the end cue is a note, not a failure: the effects plan lands
   a recorded hit there.
4. **Keeps the best**, levelled like `score.py` (-18 LUFS, true peak under -3 dBTP), as `sound/music.wav` and
   `sound/score.json` in `score.py`'s format. The rest of the sound pipeline works unchanged.

What it leaves:

- `sound/takes/take-s<seed>-x<extra>.wav`: every raw take, and `take-s<seed>-x<extra>-ready.wav`, cut, on the grid
  and levelled.
- `sound/takes.json`: every take's numbers and why the winner won. A `warning` means every take missed a check: say
  so, and offer more takes (`--takes 5`), other seeds (`--seed 40`) or `score.py`.
- No ACE-Step installed: it stops with exit 3 and prints the `score.py` command to use instead.

**The listening checkpoint stays ✋.** The takes are unheard by the agent. Play them to the person (all of them, if
they like) before any picture is built. If they prefer another take, run the same command with `--pick <seed>`: the
takes are reused, so it takes seconds.

**What it cannot do:** move the model's drop or write a real ending. After the cut, the music fades over the last half
beat: put a recorded hit on the end cue in the effects plan when the video needs a clear ending. It picks the take that
follows the plan best. If none does, more seeds or the fallback are the answer.

## Description and settings

- **Describe genre, mood, instruments and tempo**, and the shape you want ("a rising build into a big drop, ends on one
  big hit"). Ask for "bright", "airy" or "clear highs" when the brief needs sparkle: the mixes lean on the bass.
- **Length is whole bars of 4/4** (our sound rule): 8 bars at 128 bpm is exactly 15.00 s. The model makes 10 to 600 s.
- **The seed makes the same take again.** Keep the winner's seed in the project notes (`score.json` has it).
- **Instrumental.** For a sung track, call the helper directly with `--lyrics words.txt`, using only words the person
  wrote or approved, then measure it with `ace_takes.py --measure <file> --bpm ... --bars ...`.
- **`--with-lm`** adds a planning model for better song structure, at the cost of a bigger download and more time.

One take by hand, without the scoring (the low-level helper):

```bash
PY=$(python3 <kit-to-clip>/scripts/toolbox.py path ace-step python)
"$PY" <kit-to-clip>/toolbox/helpers/ace_music.py "<description>" assets/music.wav --bpm 120 --key "A minor" --bars 8 --seed 7
```

## Beats

Trust `score.json`. `npx hyperframes beats` reads ACE-Step beats about 25 ms later than `ace_takes.py` and
`finish.py sync`: it lands on the low body of the kick, not on its attack. On seed 23 of the 9 Oct test, the three
read +151, +125 and +122 ms.

## Honesty and rights

- **ACE-Step's own notice:** generated music can sound like existing songs by accident. Never prompt with artist or
  song names ("in the style of …"). Describe genre, mood, instruments and tempo instead.
- **For brand work, keep the files:** the description, seed, model (`acestep-v15-turbo`) and date. `ace_music.py`
  writes them next to each take as `take-s<seed>-x<extra>.json`; `takes.json` and `score.json` keep them too.

## Tested

- **8 Oct 2026 (M1 Max):** a 16 s instrumental at 120 bpm in A minor took 5 min 21 s on the first run, including the
  9.4 GB model download. It came out exactly 16.00 s long. 92% of its energy was in the lows (centroid 317 Hz). Its
  true peak was +4.6 dBFS after AAC encoding.
- **9 Oct 2026, three 45 s takes (24 bars at 128 bpm):** `ace_takes.py --measure` found the beats at +154, +125 and
  -1 ms (spread 6 to 8 ms, tempo 127.98 to 128.05). Seed 23 scored best (53), the take a builder had chosen by hand
  that day from measurements. It still failed "the drop is not clearly above the build": its loudness jumped
  mid-build. Seeds 11 and 37 faded to silence at the end.
- **9 Oct 2026, `ace_takes.py` end to end, 8 bars at 128 bpm (15 s), 3 takes:** each take took 66 to 90 s with the
  models already downloaded; a re-run that reused them took 7 s. Beats found at +21, +6 and +12 ms (spread 6 to 10
  ms), all 0.0 ms after the shift. Seed 37 won (15.3 points, next best -1.1): `music.wav` is exactly 15.000 s
  (720000 samples), -18.0 LUFS, true peak -4.5 dBFS. **Every take faded out over its last 2 to 3 bars** (silent from
  about 11 s), although the description asked for "ends on one big hit", so every take failed "the end is near
  silence" and the tool warned. For a short video whose ending must hit, expect more takes, or use `score.py`.
- **9 Oct 2026, the same brief with 4 extra bars (made 22.5 s, cut to 15 s), 3 new takes:** 59 to 118 s each. End
  against the drop: +0.8, +0.7 and +0.5 dB (before, without extra bars: -49.7, -44.3 and -56.6 dB). Beats at +48,
  -28 and +20 ms (spread 4 to 16 ms), all 0.0 ms after the shift. Seed 11 won (60.6 points, next 50.6): `music.wav` is
  exactly 15.000 s, -18.0 LUFS, true peak -3.2 dBFS, and the cut is silent in its last 2 ms. Every take now failed
  "the build does not rise" over the 2-bar build, so the tool warned. The music goes on to the cut, so the end is a
  half-beat fade: plan a recorded hit on the end cue.
