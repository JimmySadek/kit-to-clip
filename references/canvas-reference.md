# Canvas drawings in a Kit to Clip video

Use this guide when a reference drawing or effect is a time-driven Canvas2D sketch: everything is drawn with
`ctx.fillRect`, `ctx.fillText`, paths and so on, as a function of time. The **Canvas bridge**
(`finish/scripts/canvas-bridge.js`) runs that drawing on the existing HyperFrames engine. Preview, render and the finish
checks all seek it to exact times. It is not a renderer, an OCR system or a visual template: it only connects your draw
function to HyperFrames time and records what each draw put on the canvas, so the finish checks can audit it.

WebGL, Three.js and `OffscreenCanvas` are out of scope. For Three.js, use HyperFrames' own `three` adapter guide.
Sub-compositions are not supported: a bridge works only on a canvas in the root composition (see the rules below).

## External drawing files and the compiled snapshot

HyperFrames 0.8.77 combines local classic external scripts at the first local `script[src]` tag. If GSAP is in
the head and a later external drawing file immediately queries its canvas, the bundled drawing can run before
that canvas exists. The original HTML can pass the finish checks while an engine snapshot stays blank.
Either keep external drawing files definition-only and register the bridge inline after the canvas, or put
**all** local classic external scripts after the canvas, in dependency order (GSAP, bridge, drawing). Keep the
paused timeline registration inline in the HTML so lint can see it. This constraint concerns DOM access by
bundled external files, not the order of timeline and bridge registration within one inline block. The inline
example below does not query the canvas from an external file, so it can keep GSAP and the bridge in the head.

Keep matched comparison versions in separate project folders, each with one root `index.html`. A second
top-level composition HTML in the same folder fails engine lint. Inspect the actual engine snapshots before
calling a composition ready; a runtime check of the original HTML does not prove the compiled pixels.

## Set up a composition

1. Copy `finish/scripts/canvas-bridge.js` into the project folder, next to `index.html`.
2. Load local GSAP, then the bridge, as classic scripts. They can be in `<head>` when drawing/DOM registration
   is inline, as below. An external drawing file that queries the canvas follows the external-file rules above.
3. Put the canvas in the root composition and give the root a finite `data-duration`. That sets the render length, because Canvas has no duration
   inference.
4. Register the standard paused root timeline yourself, in the HTML, where `hyperframes lint` can see it. The bridge
   never registers or touches a timeline. A runtime-only registration fails lint with `missing_timeline_registry`.
5. Mark each bridged canvas `data-k2c-canvas`. The checks then fail if it is ever left without a bridge.

```html
<head>
  <script src="vendor/gsap.min.js"></script>
  <script src="canvas-bridge.js"></script>
</head>
<body>
  <div id="root" data-composition-id="intro" data-start="0" data-width="1080" data-height="1920" data-duration="6">
    <canvas id="art" width="1080" height="1920" data-k2c-canvas style="position:absolute;inset:0;width:100%;height:100%"></canvas>
  </div>
  <script>
    window.__timelines["intro"] = gsap.timeline({ paused: true });   // add DOM tweens here if there are any
    KitToClipCanvas.register({
      id: "art",
      canvas: document.getElementById("art"),
      duration: 6,
      ready: document.fonts.ready,
      draw(ctx, t, audit) {
        ctx.fillStyle = "#101820"; ctx.fillRect(0, 0, 1080, 1920);
        const rnd = KitToClipCanvas.seeded(7);                            // made in draw: the same dots on every frame
        ctx.fillStyle = "#2a3a4a";
        for (let i = 0; i < 40; i++) ctx.fillRect(rnd() * 1080, rnd() * 1920 + 30 * t, 8, 8);
        ctx.fillStyle = "#fff"; ctx.font = "bold 96px sans-serif";
        ctx.fillText("Launch day", 160, 900 - 40 * Math.min(t, 1));      // measured automatically
        ctx.beginPath();                                                  // a logo drawn as a path...
        ctx.moveTo(160, 1220); ctx.lineTo(280, 1100); ctx.lineTo(400, 1220); ctx.closePath(); ctx.fill();
        audit.region("logo", 160, 1100, 240, 120, { kind: "logo" });      // ...declared, so the checks can see it
      },
    });
  </script>
</body>
```

## API

`KitToClipCanvas.register(options)` returns a handle. It throws a clear error, and changes nothing, when the options
are wrong.

| Option | Meaning |
|---|---|
| `id` | Unique, non-empty name. A second bridge with the same id is refused. |
| `canvas` | The actual `<canvas>` element, inside the root composition (the first `data-composition-id` element). A canvas in a nested or `data-composition-src` composition is refused. Each canvas can have one bridge. |
| `duration` | Finite seconds above 0, no longer than the composition's `data-duration`. The draw time is clamped to `[0, duration]`, so the picture holds after it. |
| `draw(ctx, t, audit)` | A pure function of `t`. The bridge clears the canvas and resets the context state before every call. |
| `labels` | `"audit"` (the default): the canvas shows text or a logo, and the safe check fails if none is recorded. `"none"`: the canvas draws no text or logo. This is taken as said and reported as not inspected. A `"none"` canvas that draws text fails. |
| `ready` | Optional promise, such as fonts or images decoded from local files. The bridge holds HyperFrames' render-ready on it (`__hf.buildReady`). A seek that arrives earlier is held through its `waitUntil` and drawn at its own time once `ready` resolves. If `ready` rejects, every seek fails with `KitToClipCanvas "<id>" not ready: <reason>`, so a render stops. |

Any other option is refused.

Inside `draw`:

- `ctx.fillText` and `ctx.strokeText` are measured as they are drawn (`measureText` bounds through the current
  transform). These are the **measured** labels.
- `audit.region(name, x, y, w, h, { kind: "logo" | "lettering" })` declares the box of path lettering, a logo path or
  a logo image, in the current transform. These are the **declared** labels. They are only as true as the box you
  give: the checks do not look at the pixels inside them.
- Every label box is clipped to the canvas bitmap. A label drawn wholly off the bitmap has no box and counts nowhere.

Handle methods: `frame()` returns a copy of what the last draw recorded (`time`, `seq`, `labels`, `clock`, `error`,
`fingerprint`). `draw(t)` draws now. `dispose()` removes the bridge, its ready hold and, with the last bridge, the
shared `hf-seek` listener. `KitToClipCanvas.list()` lists the live bridges. `KitToClipCanvas.seeded(seed)` returns a
seeded random function: same seed, same numbers. Create it inside `draw`, as in the example, so every frame starts the
sequence afresh. One created outside `draw` keeps advancing from frame to frame, and `check` fails it.

## Rules for the draw function

- Draw from `t` only, with no state kept between draws: no frame counter, no particles stepped each draw, no
  `new Date()`. `finish.py check` seeks every sample a second time, backwards, and fails a bridge whose pixels differ.
  Reading `Math.random`, `Date.now` or `performance.now` during a draw is also recorded and fails `check`. Use
  `KitToClipCanvas.seeded(seed)`, made inside `draw`, for scatter. The HyperFrames renderer makes `performance.now`
  read-only; the bridge leaves a property it cannot patch alone, so that clock is not watched there (the re-seek still
  catches a draw that depends on it).
- Root composition only. HyperFrames gives `hf-seek` the root's time, and the bridge does not convert it to a
  sub-composition's local time, so `register` refuses a canvas in a sub-composition. This is unsupported, not merely
  untested.
- No `requestAnimationFrame` loop and no second drawer on the same canvas. HyperFrames' `hf-seek` (with
  `detail.time`) is the only driver: one shared listener draws every bridge. Anything that paints over the canvas after
  the bridge makes the audit stale, and the checks fail.
- No network: inline or bundle images and fonts, and wait for them with `ready`.
- A draw that throws, or a `ready` that rejects, fails the seek through HyperFrames' `waitUntil`, and `finish.py check`
  reports it. With HyperFrames 0.8.77, a render whose draw throws stops with `KitToClipCanvas "<id>" draw failed at
  <t> s`, and one whose `ready` rejects stops with `KitToClipCanvas "<id>" not ready: <reason>`. A throw during
  registration (a refused option, a sub-composition canvas) only shows as a page error in the render log (the render
  carries on), so run `finish.py check`.

## What the finish checks do with a Canvas

`check`, `safe` and `hook` first run their normal DOM checks unchanged. When an HTML file in the project mentions the
bridge, they also run a Canvas audit in the same headless engine browser:

- **Fresh audit.** At every sampled time, each bridge's last record must be for that seek: its time equals the time
  the runtime published, and the pixels on the canvas still match the fingerprint taken right after that draw. If
  there is no record, a record from another time, pixels changed by something else, or a draw error, the check fails.
  This also applies to a marked canvas without a bridge, or a page where the bridge is not loaded. It never falls back
  to a pass.
- **`check`** samples every 0.5 s and the last frame, then seeks the same times again in reverse (all but the last,
  which the runtime would not re-dispatch). It fails when a re-seek draws different pixels, and on clock or random
  reads. It does not check that the bridges recorded any labels: an empty audit is not flagged here.
- **`safe`** places every visible label on the page through the canvas's on-screen box. Visible means a declared
  region, or measured text whose draw changed canvas pixels; text under a closed clip or in a transparent colour is
  skipped. It uses the whole measured box, even when a clip shows only part of the text, clips it to what a viewer can
  see, and fails when a label leaves the platform's safe box. A bridge with `labels: "audit"` that recorded no visible
  label at any sample fails as an **empty audit**. If the page has no DOM text, the canvas labels
  are what is checked; if there are no canvas labels either, the DOM failure stands.
- **`hook`** measures the opening on the canvas pixels: the share of the frame, in cells of about 1%, that holds
  anything other than the canvas's dominant colour. Other drawn elements count by the hook check's usual rule. A
  blank or flat-filled canvas is not content, even though its element box would satisfy the DOM rule. Readable text
  can be measured text whose painted pixels span at least 2.5% of the frame height, a declared lettering box that size,
  or a declared logo. A declared region is reported as taken as said. Motion is any pixel change in the first second.
  The hook does not flag an empty audit by itself; without readable text by `--by` it fails as usual.

## Coverage limits (say these when reporting)

- Canvas pixels are never read as text. Only `fillText`/`strokeText` runs and declared regions are labels. Lettering
  drawn as paths, images or glyph atlases is invisible to the checks until it is declared. Arbitrary source code is not
  inspected for labels it might draw.
- "Painted" is pixel evidence, not readability. A measured run counts when its own draw changed pixels inside its
  box by at least 24 of 255 in a channel, after the native clip, transform, colour and compositing. That catches a
  closed clip, a transparent colour and text off the bitmap; `globalAlpha` at or below 0.05 also skips a label. It
  does not see text painted and then covered later in the same draw, low-contrast text that still clears the
  threshold, or whether the words can be read. Declared regions are never pixel-checked.
- Label boxes are mapped through the canvas's on-screen bounding box. A CSS-rotated canvas is reported as a note, and
  its rotation is not modelled.
- Canvases without a bridge are listed as not inspected.
- The live snippet (`finish.py snippet`) plays timelines without HyperFrames, so no `hf-seek` is sent and a bridged
  canvas stays on its first frame there. Deliver rendered loop exports instead.
- Tested on synthetic fixtures in a root composition with HyperFrames 0.8.77, including renders with a delayed
  `ready`, a rejected `ready` and a throwing draw. Sub-compositions are unsupported and refused (tested for a nested
  and a `data-composition-src` composition).
