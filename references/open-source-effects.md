# Open-source effects: borrowing a look from a public project

A video here is code, so it can borrow a visual effect someone else published: watercolour brush strokes (for example
`p5.brush`), particle orbs, a shader, a generative pattern. The person gives a project link ("use the brush from this
repo"), or you suggest one when a style calls for a texture the brand's own files do not have. Done well it gives a
look no template has. Done carelessly it breaks the render, the licence or the brand.

```
link ─▶ ✋ licence ─▶ make it seekable ─▶ brand colours ─▶ stills at 3 times, twice ─▶ credits ─▶ use it
```

## 1. Licence first (✋ before any code is copied)

Open the project's licence file and say what it is in one line.

| Licence | Use |
|---|---|
| MIT, Apache-2.0, BSD, ISC, CC0, Unlicense | Fine. Keep the copyright notice in the credits (step 5) |
| MPL, LGPL | Fine as a separate, unchanged file loaded by the page; say so |
| GPL, AGPL, CC BY-NC, "non-commercial", or no licence at all | Do not use. No licence means all rights reserved. Offer another project or our own version of the idea |

Ask ✋ **Use this project** / **Find another** with the licence named. The code goes into the video project only
(`effects/<project-name>/` inside it, which a saved style keeps; `vendor/` is not kept), never into the Kit to Clip
engine or a brand pack.

## 2. Make it seekable

The video engine draws each frame from its time alone: frame 90 must look the same whether it is rendered first,
last, or twice. Most sketches assume a live screen instead. Change three things:

- **Time comes from the engine.** Stop the sketch's own loop (in p5: `noLoop()`) and draw the frame for the engine's
  time. Follow the engine's adapter for the runtime: `hyperframes-animation` → `adapters/` (`three.md` for WebGL and
  canvas layers that listen for the `hf-seek` event, `typegpu.md` for WebGPU). For effects that build up over time
  (brush strokes, trails), redraw from the start up to that time; never rely on the previous frame still being there.
- **Randomness is seeded.** Replace `Math.random()` and unseeded `random()` with a seeded generator (in p5:
  `randomSeed(n)` and `noiseSeed(n)` before each redraw). The seed goes into the recipe so the next video can repeat it.
- **Nothing loads at render time.** Copy the library file and any textures into the project; no CDN links, no fetches.

## 3. Brand colours

Feed the effect the brand's role colours from the bridged tokens (`--reel-bg`, `--reel-accent`, ... read with
`getComputedStyle`), never the hex values from the project's demo. One accent rule still holds: a colourful effect
is the scene's accent, so the rest of the scene stays quiet. A motif-like shape from the effect must not look like
someone else's mark.

## 4. Prove it renders the same

Take stills of three moments (start, middle, end) with `npx hyperframes snapshot --describe false`, then the same three
again. The pairs must match. If they differ, something still reads a clock, an unseeded random or the previous frame:
fix that before showing anything. Then the usual checks (lint, check, finish `check`, `safe`, `hook`), and ✋ stills.

Heavy effects slow the render. If one still takes more than a few seconds, lower the particle count or the canvas
resolution before the full render, and say how long the render will take.

## 5. Credits

Write `CREDITS.md` in the project: the project name, link, licence, copyright line, what was changed. Saving a style
keeps it with the template. Credits never go on screen unless the licence asks for it (CC BY does: then add a small
end-card line, and say so before the render).

## Status

Written from the engine's determinism rules (`hyperframes-core/references/determinism-rules.md`). No effect has been
built through this guide yet: the first one is the test. Record what worked here.
