# Blender: heavy 3D (a logo or product in real 3D, lit and rendered)

Blender 5.2 runs here as a separate program (GPL-3.0, fine because we only run it). It is Apple silicon only:
Blender 5 has no Intel Mac build. The install is 907 MB.

## A 3D logo from the brand's SVG (turntable, transparent)

```bash
B=$(python3 <kit-to-clip>/scripts/toolbox.py path blender)
"$B" -b --factory-startup --python <kit-to-clip>/toolbox/helpers/blender_logo.py -- logo.svg out/ \
     --frames 72 --fps 24 --size 1080 --turn 360 --depth 0.12 --tilt 12 --samples 32
```

- **Shapes:** filled shapes are extruded (`--depth` is a share of the width). Open strokes become round tubes.
- **Colours** come from the SVG: the fill, or the stroke when there is no fill. Blender's importer reads fills only;
  the helper fixes strokes by matching SVG `id`s.
- **Looping:** `--turn 360` spins it once over the clip, so it loops. `--turn 30 --frames 48` gives a slow
  "hero" drift instead.
- **Output:** `logo.mov` (ProRes 4444) and `logo.webm` (VP9), both with transparency, plus PNG frames. Place
  `logo.webm` as a `<video>` layer in the HyperFrames composition. Pre-rendered frames are seekable by nature.
- **Get the SVG first:** use the brand's own file. A PNG-only or `.ai` logo goes through VectorCraft (`logo-convert`,
  `image-trace`) first. Never redraw a logo.

## Rules
- **Look at four frames across the turn**, on a contrasting background, before showing it: colour, depth, lighting.
- **Check the brand's guidelines.** Many forbid 3D effects, extrusions or bevels on the logo. Ask ✋ before making
  the logo itself 3D. A 3D *product* or *object* usually needs no such check.
- **Browser 3D or Blender?** Use Three.js inside the engine for light 3D that the video itself controls (cards,
  simple objects). Use Blender when real lighting, materials, bevels or heavy geometry matter.

## Tested 2026-10-08 (M1 Max)
- **The test mark** (ring, tick, wave; outline SVG): 24 frames at 400 px in about 8 s with EEVEE. The colours were
  right after the stroke fix: blue ring, red tick, dark wave. Depth and satin shading read clearly through the turn.
- **First attempt, before the fix:** every part came out white, because the importer drops stroke colours.
