# PixiJS: thousands of particles, confetti, sparks

Adds a GPU canvas for particle counts that DOM elements cannot carry: 2000 confetti pieces, 3 s at 1080x1080,
rendered in about 5 s. Read before use: https://pixijs.com/llms.txt, the ParticleContainer guide
(https://pixijs.com/8.x/guides/components/scene-objects/particle-container.md) and
`hyperframes-animation/adapters/three.md` (how the engine seeks a canvas).

1. `python3 <kit-to-clip>/scripts/toolbox.py vendor pixi <project>`: copies `vendor/pixi.min.js` (840 KB, global
   `PIXI`). Load it with a plain `<script src>`. The install is 90 MB because npm ships every build; only this file
   goes into the project.
2. Stop Pixi's clock, and compute every particle from time alone: a seeded PRNG for the starting values, a closed
   formula for the motion. Nothing is carried from one frame to the next, so any frame can be drawn first.

```js
const tl = gsap.timeline({ paused: true }); /* HTML tweens */ window.__timelines["<comp-id>"] = tl;
const rnd = mulberry32(20261008);                       // seeded PRNG, never Math.random
const seeds = Array.from({ length: 2000 }, () => ({ born: 0.15 + rnd() * 0.1, vx: ..., vy: ..., k: 1.6 + rnd() * 1.4 }));
function place(p, s, t) {                               // pure function of (seed, t)
  const u = t - s.born; if (u <= 0) { p.alpha = 0; return; }
  const d = (1 - Math.exp(-s.k * u)) / s.k;             // linear drag, closed form
  p.x = 540 + s.vx * d;  p.y = 540 + s.vy * d + (G / s.k) * (u - d);   // plus gravity G
  p.rotation = s.r0 + s.spin * u;  p.scaleX = s.size * Math.cos(s.flip * u);  p.alpha = 1;
}
let renderAt = null, last = 0;
window.addEventListener("hf-seek", (e) => { last = e.detail.time; if (renderAt) renderAt(last); });
window.__hf = window.__hf || {}; window.__hf.buildReady = window.__hf.buildReady || {};
window.__hf.buildReady["pixi"] = (async () => {         // init is async: hold the first capture until it is done
  const app = new PIXI.Application();
  await app.init({ width: 1080, height: 1080, resolution: 1, backgroundAlpha: 0, preference: "webgl",
                   autoStart: false, sharedTicker: false, preserveDrawingBuffer: true, antialias: true });
  app.ticker.stop();
  document.getElementById("stage").appendChild(app.canvas);
  const texture = app.renderer.generateTexture(new PIXI.Graphics().rect(0, 0, 14, 22).fill(0xffffff));
  const box = new PIXI.ParticleContainer({ dynamicProperties: { position: true, rotation: true, vertex: true, color: true } });
  const parts = seeds.map((s, i) => box.addParticle(new PIXI.Particle({ texture, anchorX: 0.5, anchorY: 0.5, tint: 0xCB1B20 })));
  app.stage.addChild(box);
  renderAt = (t) => { seeds.forEach((s, i) => place(parts[i], s, t)); app.render(); };
  renderAt(window.__hfThreeTime ?? last);
})();
```

## Traps
- **`backgroundAlpha: 0` with a `background` colour doubles the colour in WebGL** (#161212 came out #2c2424). For an
  overlay give no background colour. For an opaque canvas use `backgroundAlpha: 1`.
- **Mark every property you change as dynamic** in `ParticleContainer`. Static ones only upload on `container.update()`.
  `addParticle` returns the particle.
- **No `requestAnimationFrame` and no `app.ticker` callbacks.** Lint rejects rAF, and ticker time is wall-clock time.
- Register `hf-seek` before the `await`, so a seek during init is not lost.

## GPU and headless
WebGL works in SwiftShader (`--no-browser-gpu`). PixiJS 8.22 also has `preference: "canvas"` (2D canvas). It drew
the same ParticleContainer scene under SwiftShader, so it is a fallback when WebGL is missing.

## Tested 2026-10-08 (8.22.0, HyperFrames 0.8.77)
- 1080x1080, 3 s, 2000 particles, two confetti bursts in #CB1B20 and #F4F1EA. `hyperframes lint`: 0 errors.
- Snapshots at 0.5, 1.5, 2.5 s and in reverse order (`--no-browser-gpu`): the md5 of every frame matched.
- `hyperframes render` (hardware GPU 5.3 s, software 6.7 s): not black. Frame 0 is empty, then the bursts spread and fall.

## Craft note (review, 2026-10-08)
- **Keep particles off the words.** At the peak of the test burst, 2000 confetti pieces crowded the "Game on" title.
  For real videos, spawn away from the text box, fade particles near it, or launch the burst before the words land.
  Check the busiest frame for readability with `finish.py hook` and your own eyes.
