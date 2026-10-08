# Paper Shaders: living gradient backgrounds in brand colours

Adds GPU shader backgrounds: mesh gradients, grain gradients, liquid metal, noise, waves. They are drawn in WebGL2,
coloured with the brand's own hex values. Read before use: https://shaders.paper.design/llms.txt (the parameters of each
shader) and `hyperframes-animation/adapters/three.md` (how the engine seeks a canvas).

1. `python3 <kit-to-clip>/scripts/toolbox.py vendor paper-shaders <project>`. It copies 40 small ES module files to
   `vendor/paper-shaders/`. The package is not one bundle, so keep the folder whole and import `index.js`.
2. Stop its clock and draw from composition time. `speed` 0 means no animation loop. `setFrame(ms)` draws at once.

```html
<div id="shader" style="position:absolute;inset:0;width:1080px;height:1080px" data-safe-ignore></div>
<script>  /* classic script: GSAP timeline for the HTML layers, plus a hold until the shader can draw */
  window.__timelines["<comp-id>"] = tl;
  window.__hf = window.__hf || {}; window.__hf.buildReady = window.__hf.buildReady || {};
  window.__hf.buildReady["paper-shader"] = new Promise((r) => { window.__shaderReady = r; });
</script>
<script type="module">
  import { ShaderMount, meshGradientFragmentShader, getShaderColorFromString, ShaderFitOptions } from "./vendor/paper-shaders/index.js";
  const el = document.getElementById("shader"), colors = ["#161212", "#CB1B20", "#161212", "#F4F1EA"];
  const uniforms = { u_colors: colors.map(getShaderColorFromString), u_colorsCount: colors.length,
    u_distortion: 0.8, u_swirl: 0.35, u_grainMixer: 0.15, u_grainOverlay: 0.08,
    u_fit: ShaderFitOptions.cover, u_scale: 1, u_rotation: 0, u_offsetX: 0, u_offsetY: 0,
    u_originX: 0.5, u_originY: 0.5, u_worldWidth: 0, u_worldHeight: 0 };
  // (parent, shader, uniforms, WebGL attributes, speed 0, frame 0, minPixelRatio 1, maxPixelCount = frame size)
  const mount = new ShaderMount(el, meshGradientFragmentShader, uniforms, { preserveDrawingBuffer: true }, 0, 0, 1, 1080 * 1080);
  const renderAt = (t) => mount.setFrame(t * 1000);          // frame is in ms; multiply t to go faster
  window.addEventListener("hf-seek", (e) => renderAt(e.detail.time));
  const ro = new ResizeObserver(() => { if (mount.canvasElement.width > 0) {
    ro.disconnect(); renderAt(window.__hfThreeTime || 0); window.__shaderReady(); } });
  ro.observe(el);
</script>
```

## Traps
- **The vanilla package takes raw `u_*` uniforms, not the React props.** Colours go through `getShaderColorFromString`.
  Pass every sizing uniform (`u_fit`, `u_scale`, `u_origin*`, `u_world*`...) too. Each shader's uniforms are listed
  in `vendor/paper-shaders/shaders/<name>.js` and on the docs page.
- **No `requestAnimationFrame` in the composition.** `hyperframes lint` rejects it (`requestanimationframe_in_composition`).
- **The canvas is sized later, by a ResizeObserver.** Draw after it fires (our observer runs right after the library's),
  and hold the first capture with `window.__hf.buildReady`.
- **`minPixelRatio` defaults to 2** (a 2160 px canvas for a 1080 px video). Set 1, and `maxPixelCount` to width x height.
- **WebGL2 only.** Without it the constructor throws "WebGL is not supported". Use the CSS gradient fallback then.
- `hf-seek` is sent by the engine's `three` adapter on every seek, also when the page has no Three.js.

## GPU and headless
WebGL2 works in SwiftShader (`--no-browser-gpu`), so the software and hardware paths both draw the shader.

## Tested 2026-10-08 (0.0.81, HyperFrames 0.8.77)
- 1080x1080, 3 s mesh gradient in #161212, #CB1B20, #F4F1EA with grain. `hyperframes lint`: 0 errors.
- Snapshots at 0.5, 1.5, 2.5 s and again in reverse order (`--no-browser-gpu`): the md5 of every frame matched,
  grain included. The gradient visibly flows between the three times.
- `hyperframes render` (hardware GPU, 5.2 s) and `--no-browser-gpu` (7.1 s): not black, average brightness 58 to 85.
