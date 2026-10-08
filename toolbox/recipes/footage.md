# Footage powers: smooth slow motion, upscaling

Both run on this computer's GPU (Vulkan through Metal on a Mac). They are free and need no account.

## Smooth slow motion (`rife`)

```bash
bash <kit-to-clip>/toolbox/helpers/slowmo.sh clip.mp4 smash-slow.mp4 --factor 4 --start 15.6 --length 1
```

- **Each moment gets new frames.** `--factor 4` turns 1 s into 4 s of smooth motion at the clip's own frame rate.
  The model is `rife-v4.6`; `--model rife-UHD` is for 4K sources.
- **Then use the clip.** Put `smash-slow.mp4` in the composition as its own `<video>` for the slow part. Don't stack
  a `data-playback-rate` slow-down on it, or the frames repeat again.
- **Where it fails:** occlusions (a ball passing behind a player), scene cuts inside the range, and motion blur so
  heavy the ball is only a streak. Keep the range inside one shot (`reference.py cuts` finds the cuts). Look at 4
  consecutive frames at the fastest moment before using it.
- **Tested 2026-10-08:** 1 s of a padel rally became 120 frames, 117 of them distinct. Plain slow-down gave 119
  frames with only 30 distinct (75% repeats). That took 10 s on an M1 Max. Consecutive frames showed the players and
  rackets moving in small, clean steps.

## Upscaling (`realesrgan`)

```bash
UP=$(python3 <kit-to-clip>/scripts/toolbox.py path realesrgan cli)
MODELS=$(python3 <kit-to-clip>/scripts/toolbox.py path realesrgan models)
"$UP" -i small.png -o big.png -n realesrgan-x4plus -s 4 -m "$MODELS"     # -s 2|3|4
```

- **The `-m <models folder>` is required.** Without it the tool exits at once and writes nothing.
- **Good for:** a soft background plate, a low-resolution phone still, screenshots, nets, lines and printed text.
- **It invents texture.** Skin and fabric can look painted (tested: a white shirt came out smooth and plastic-like).
  Check people at 100% before using it, and say "upscaled" if a person's face is shown large.
- **Never use it on a logo or brand artwork.** Use the vector original, or VectorCraft's trace for a PNG-only logo.
- **For a clip:** extract the frames, upscale the folder (`-i in_dir -o out_dir`), then reassemble at the source fps.
  It is slow for long clips, so upscale only the shot that needs it.
- **Tested 2026-10-08:** a 270x270 crop of a padel still became 1080x1080. The net became crisp where bicubic blurred
  it, and the shirt looked smoothed.
