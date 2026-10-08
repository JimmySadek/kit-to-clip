# Original music from a description (ACE-Step 1.5)

**Early tool:** free, MIT for the code and the models, and it runs on this computer (Apple silicon through MLX). The
first run downloads about 9.4 GB of models into `<engine>/tools/ace-step/checkpoints`. Say so before the ✋.

```bash
PY=$(python3 <kit-to-clip>/scripts/toolbox.py path ace-step python)
"$PY" <kit-to-clip>/toolbox/helpers/ace_music.py "energetic sports highlight track, punchy drums, synth bass, bright stabs" \
      assets/music.wav --bpm 120 --key "A minor" --bars 8 --seed 7
```

- **Length is whole bars of 4/4** (our sound rule): `--bars 8` at 120 bpm is exactly 16.00 s. Pick the tempo first, so
  the video's length is whole bars.
- **`--seed` makes the same track again.** Keep it in the project notes. Change only the seed for another take of the
  same idea.
- **Instrumental by default.** `--lyrics words.txt` sings them. Use only words the person wrote or approved.
- **`--with-lm`** adds a planning model for better song structure, at the cost of a bigger download and more time.

## Before it goes into the video
1. **Measure it:** `python3 <kit-to-clip>/finish/scripts/finish.py audio music.wav` and
   `python3 <kit-to-clip>/sound/scripts/score.py analyze music.wav`.
2. **Its peaks are hot.** Tested: -14.1 LUFS, but +4.6 dBFS true peak after AAC encoding, so the render would turn it
   down about 6 dB. Limit at -3 dBTP before it goes in (`sound/README.md`, the mix step). `finish` masters the
   delivery afterwards anyway.
3. **Beats:** `npx hyperframes beats <project>` gives the hits for cuts. Expect the strongest hits on the bar lines.
4. **Listening checkpoint ✋.** The track is unheard by the agent until the person listens. It is generated music:
   play it to them before building the picture on it.

## Honesty and rights
- **ACE-Step's own notice:** generated music can sound like existing songs by accident. Don't prompt with artist or
  song names ("in the style of …"). Describe genre, mood, instruments and tempo instead.
- **For brand work, keep the files:** the description, seed, model (`acestep-v15-turbo`) and date. `ace_music.py`
  writes them next to the track as `<name>.json`.

## Tested 2026-10-08 (M1 Max)
- **A 16 s instrumental at 120 bpm in A minor** took 5 min 21 s on the first run, including the 9.4 GB model
  download. It came out exactly 16.00 s long.
- **The strongest hits fell exactly every 0.5 s** (1.49, 3.49, 5.49, 6.00, 6.50 …), so the tempo grid held. The
  detector's overall estimate reads double time (255; half is 128), so trust the hit grid over that number.
- **The mix is bass-heavy:** 92% of the energy in the lows, spectral centroid 317 Hz. Ask for "bright", "airy" or
  "clear highs" when the brief needs sparkle.
