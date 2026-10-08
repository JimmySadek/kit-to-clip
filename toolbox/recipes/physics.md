# Physics: Rapier 2D, baked once, played back seekably

Things that fall, bounce and pile up. Rapier (Apache-2.0) runs **once, in Node**, and writes every body's position
for every frame. The video only reads that file, so any frame can be drawn in any order. Never simulate in the page.
Read before use: Rapier's JavaScript guide (link on the card) for joints, sensors and more body options.

```
spec.json ──▶ node helpers/physics_bake.mjs ──▶ baked.js (positions per frame) ──▶ page places shapes at round(t·fps)
```

## 1. Describe the scene

```json
{"width": 1080, "height": 1080, "fps": 30, "duration": 4, "gravity": 2400, "substeps": 4, "walls": true,
 "bodies": [{"shape": "box", "size": 150, "x": 300, "y": -120, "vx": 40, "angle": -0.5, "restitution": 0.2,
             "color": "#CB1B20"},
            {"shape": "ball", "size": 120, "x": 620, "y": -270, "restitution": 0.35, "color": "#161212"}]}
```

Pixels, y pointing down, angles in radians. `size` is a box side (or `[w, h]`) or a ball diameter. `walls` adds a
floor and side walls at the frame edges. Extra keys (`color`, `id`) are passed through to the page.

## 2. Bake (once, and again after any change to the spec)

```bash
node <kit-to-clip>/toolbox/helpers/physics_bake.mjs spec.json baked.js   # .js: sets window.__physics
```

It finds Rapier with `toolbox.py path rapier module`. A `.json` output is the same data without the wrapper.

## 3. Play it back (tested)

```html
<script src="baked.js"></script>
<script>
  const P = window.__physics, root = document.getElementById("root");
  const els = P.bodies.map((b) => {
    const [w, h] = Array.isArray(b.size) ? b.size : [b.size, b.size];
    const el = document.createElement("div");
    Object.assign(el.style, { position: "absolute", left: 0, top: 0, width: w + "px", height: h + "px",
      background: b.color, borderRadius: b.shape === "ball" ? "50%" : "0" });
    root.appendChild(el); return { el, w, h };
  });
  function place(t) {
    const i = Math.min(P.count - 1, Math.max(0, Math.round(t * P.fps)));
    P.frames[i].forEach((s, k) => { const { el, w, h } = els[k];
      el.style.transform = `translate(${s.x - w / 2}px, ${s.y - h / 2}px) rotate(${s.angle}rad)`; });
  }
  window.addEventListener("hf-seek", (e) => place(e.detail.time));
  place(window.__hfThreeTime || 0);
</script>
```

Also register a paused GSAP timeline (a caption is enough) and set `data-duration` on the root. Bake at the video's
fps; for another fps, bake again rather than interpolating.

## Traps
- **Load the bake with a `<script>` tag** (`baked.js`), not `fetch()`: nothing may load over the network at render time.
- **Rapier thinks in metres.** The helper uses 100 px per metre (`scale`); pixel-sized bodies in a metre world
  feel like dust in slow motion.
- **Drop bodies from above the frame** (negative `y`), one after another: 150 px apart gave a readable cascade.
- **Check that the pile settles before the end.** In the test, movement fell to 0 px by frame 90 of 120.
- **Same spec + same Rapier version = same file.** Pin the version; a new Rapier can bake a different pile.

## Proof (2026-10-08, Rapier 0.21.0)
12 bodies (boxes and balls in #CB1B20 and #161212) on #F4F1EA, 1080x1080, 4 s at 30 fps.
- Bake: 121 frames in 1.3 s, 56 KB. Baked twice: identical md5 (`c5007aee8fd011cd850079656626e115`).
- `hyperframes lint`: 0 errors. Snapshots at 0.5, 1.5, 2.5 s forward and backward: md5 equal.
- Frames: bodies fall in turn, tumble, and pile against the floor and walls with no overlaps; still from 3 s.
- Render: 4 s in 7 s.
