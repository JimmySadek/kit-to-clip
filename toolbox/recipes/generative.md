# Generative art: p5.js + p5.brush (painted, watercolour, pencil)

Two powers work together: `p5` (the canvas) and `p5-brush` (the brushes, watercolour fills, hatching). Read before
use: the p5.brush README (link on its card). It covers the p5 2.x build, which is the one we vendor.

**Licence.** p5.js is LGPL-2.1. We may use it only as an **unmodified, separate file**: `toolbox.py vendor p5 <project>`
copies `vendor/p5.min.js` with `p5-LICENSE.txt` and credits them in `CREDITS.md`. Never edit, re-bundle or inline
p5's code. p5.min.js bundles libtess (SGI-B-2.0, permissive) but drops its notice, so `libtess-LICENSE.txt` is
vendored too. p5.brush is MIT (its licence file is vendored).

```bash
python3 <kit-to-clip>/scripts/toolbox.py vendor p5 <project>
python3 <kit-to-clip>/scripts/toolbox.py vendor p5-brush <project>   # load order: gsap, p5.min.js, p5.brush.js
```

## The seekable pattern (tested)

Every seek repaints the whole frame from time `t`. Nothing is kept from the frame drawn before.

```js
const state = { t: 0 }; let resolveReady; const ready = new Promise((r) => (resolveReady = r));
window.__hf = window.__hf || {}; window.__hf.buildReady = window.__hf.buildReady || {};
window.__hf.buildReady["paint"] = ready;
const sketch = new p5((p) => {
  p.setup = () => { p.pixelDensity(1); p.createCanvas(1080, 1080, p.WEBGL); p.noLoop();
                    brush.scaleBrushes(2.5); resolveReady(); };          // scaleBrushes ONCE, here
  p.draw = () => paint(p, state.t);                                        // brush flushes after draw()
}, document.getElementById("paint"));
window.addEventListener("hf-seek", (e) => {
  const t = e.detail.time;
  e.detail.waitUntil(ready.then(() => { state.t = t; return sketch.redraw(); }));
});
function paint(p, t) {
  p.background(PAPER);
  brush.noStroke(); brush.noHatch(); brush.noFill();                       // reset p5.brush's own buffers
  brush.wash(PAPER, 255); brush.rect(-540, -540, 1080, 1080); brush.noWash();
  // ...seeded layers, below
}
```

Still register a paused GSAP timeline on `window.__timelines[<id>]` (a caption is enough), and set `data-duration`
on the root.

## Making strokes build up

- **Layers that appear:** give each layer its own seed (`p.randomSeed(100 + k); p.noiseSeed(100 + k)`) right
  before it is drawn, and grow only its opacity with `t` (`brush.fill(RED, 140 * ramp)`). Its shape never changes.
- **Lines that draw on:** cut the path into fixed segments (40 for a ring, 16 for a line). At time `t`, draw the
  finished segments in full and the current one partly, each with its own seed (`p.randomSeed(1000 + i)`). Finished
  segments stay identical; only the tip moves. Never redraw one long stroke with a growing end: its pressure and
  texture stretch, so the whole line shimmers.
- **Geometry** (ring points, wobble) comes from a small seeded generator (mulberry32), never `Math.random`.

## Traps found by testing (2026-10-08, p5 2.3.4, p5.brush 2.2.3)
- **`brush.scaleBrushes()` multiplies.** Called inside `paint`, brushes grew with every seek (huge blobs by the third
  frame) and the result depended on seek order. Call it once in `setup`.
- **`brush.clip()` does nothing** in 2.2.3 (the README documents it, the source is a stub). Use segments.
- **Without the reset wash, a frame depended on what was drawn before it** (1 pixel, 1 level, but a different md5).
  The full-frame paper wash makes p5.brush re-read the whole canvas. With it, forward and backward seeks match.
- **Draw only inside `p.draw`** (via `redraw()`). p5.brush composites its strokes after `draw()` returns.
- **WEBGL puts (0, 0) at the centre**, for brush coordinates too. Charcoal shows a small bead at each segment joint;
  fewer, longer segments or the `2B` pencil look smoother.
- **GPU renders are not bit-identical.** On this Mac the default render used the GPU: two renders differed in 115 of
  120 frames (PSNR about 54 dB, invisible). With `--no-browser-gpu` (SwiftShader) two renders matched in every frame.
  Use `--no-browser-gpu` when stills and the video must match exactly.

## Proof (2026-10-08)
1080x1080, 4 s: five watercolour washes in #CB1B20, a 2B pencil ring and three charcoal lines in #161212 on #F4F1EA.
- `hyperframes lint`: 0 errors. Snapshots at 0.5, 1.5, 2.5 s forward and backward (`--no-browser-gpu`): md5 equal.
- Frames: washes deepen, the ring draws on clockwise, lines draw left to right, caption fades in at 2.6 s.
- Render time for 4 s: 12 s with the GPU, 99 s with `--no-browser-gpu`. Say so before a long software render.
