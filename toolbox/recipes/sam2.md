# Object masks in video (SAM 2): text behind the player, spotlights, tracked cutouts

Meta's SAM 2.1 (small), installed from Meta's own repository at a pinned commit. It runs on this computer, on the
Apple GPU (MPS) when there is one. **Don't use the PyPI package named `sam2`:** it is a third-party repackage.

```bash
PY=$(python3 <kit-to-clip>/scripts/toolbox.py path sam2 python)
"$PY" <kit-to-clip>/toolbox/helpers/sam2_mask.py clip.mp4 out/ --point 636,540 --at 15.6 --start 15.6 --length 2
"$PY" <kit-to-clip>/toolbox/helpers/sam2_mask.py clip.mp4 out/ --box 560,380,760,920 --start 15.6 --length 2
```

- **Telling it what to follow:** `--point X,Y` is one click on the object, and `--box` is a box around it. Both are in
  the clip's own pixels, on the frame at `--at` (default: the first frame of the range). To pick the point, extract
  that frame with a grid (`drawgrid` in ffmpeg) and read the coordinates.
- **What you get:**
  - `object.webm`: the object only, VP9 with transparency, same frames as the range
  - `mask.mp4`: black and white
  - `masks/`: the mask frames
  - `report.json`: frames followed, frames lost, average cover
- **Exit 3** means the object was lost in more than a quarter of the frames. Try a box, a different frame, or a
  shorter range.

## Text behind the player (the composition)
Stack three layers, all with the same `data-start` and `data-media-start`:
1. the original clip
2. the title
3. `object.webm`

The title then passes behind the person while the background stays behind the title. Decode VP9 alpha with
`-c:v libvpx-vp9` when checking with ffmpeg; ffmpeg's built-in VP9 decoder drops the alpha.

## Limits
- **One shot per run.** Keep the range inside one shot (`reference.py cuts`).
- **About 0.7 s per 1080p frame on an M1 Max**, so 2 s at 30 fps takes about a minute. Mask only the seconds the
  effect needs.
- **People only and it's quick?** `hf-cutout` (HyperFrames remove-background) is faster for a person filling the frame.
  SAM 2 is for one chosen object among many: a ball, a racket, one player out of four.
- **Fast blur:** the ball at full speed is a streak, so masks of it can flicker. Check `mask.mp4` at the fastest
  frames.

## Tested 2026-10-08
- **A synthetic moving ball:** followed through 30 of 30 frames on MPS.
- **The padel smash** (one click on the player, 2 s): followed through 60 of 60 frames in 57 s. "SMASH" was placed
  behind him: his body covers the letters, while the other player, not selected, stays behind them
