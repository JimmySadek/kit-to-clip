# dotLottie: put a Lottie in the brand's colours

**What it adds:** the LottieFiles player draws a Lottie (`.json` or `.lottie`) on a canvas and can change its colours
(and text) through **slots** and **themes**, without editing the file. Read first: the themes section of the dotLottie
spec (`https://dotlottie.io/spec/2.0/#themes`) and the player's types (`dist/index.d.ts` in the installed package).

1. `python3 <kit-to-clip>/scripts/toolbox.py vendor dotlottie <project>`: copies `vendor/dotlottie.mjs` (an ES
   module) and `vendor/dotlottie-player.wasm`. Also vendor GSAP for the clock.
2. The Lottie needs **slots**: a property with `"sid": "brand_fill"` and a root `"slots"` entry, e.g.
   `"c": {"a":0, "k":[0.55,0.57,0.6,1], "sid":"brand_fill"}` and `"slots": {"brand_fill": {"p": {"a":0, "k":[...]}}}`.
   A stock file without slots: add the `sid` to each fill you want to recolour, or use lottie-web and edit the JSON.

## The seekable pattern

```html
<canvas id="stage" width="900" height="900"></canvas>
<script>   // classic script: exists before the first seek
  let markReady; window.__lottieReady = new Promise((r) => (markReady = r)); window.__lottieMarkReady = (p) => markReady(p);
  window.addEventListener("hf-seek", (e) => {
    const t = e.detail.time;
    e.detail.waitUntil(window.__lottieReady.then((p) => {
      const fr = p.totalFrames / p.duration;
      p.setFrame(Math.min(t * fr, p.totalFrames - 1));     // synchronous: renders and draws now
    }));
  });
  const tl = gsap.timeline({ paused: true });              // sets length, keeps lint happy
  tl.fromTo("#label", { opacity: 0 }, { opacity: 1, duration: 0.4 }, 0);
  window.__timelines["main"] = tl;
</script>
<script type="module">
  import { DotLottie } from "./vendor/dotlottie.mjs";
  DotLottie.setWasmUrl(new URL("vendor/dotlottie-player.wasm", location.href).href);
  const player = new DotLottie({ canvas: document.getElementById("stage"), src: "assets/x.json",
    autoplay: false, loop: false,
    renderConfig: { autoResize: false, devicePixelRatio: 1, freezeOnOffscreen: false } });
  (window.__hfLottie = window.__hfLottie || []).push(player);
  player.addEventListener("load", () => {
    player.setThemeData({ rules: [{ id: "brand_fill", type: "Color", value: [203/255, 27/255, 32/255] }] });
    window.__lottieMarkReady(player);
  });
</script>
```

## Traps found by testing
- **The engine's Lottie adapter cannot seek this player version.** It looks for `setCurrentRawFrameValue` or
  `seek()`, which dotlottie-web 0.81 does not have. Registered on `__hfLottie` alone, every frame froze on frame 0.
  The `hf-seek` listener above is what moves it. Keep the registration too, as the adapter docs ask.
- **The WASM comes from a CDN by default** (jsDelivr, then unpkg). Always call `DotLottie.setWasmUrl` first.
- **Loading is async.** `waitUntil` makes the renderer wait for the WASM, the file and the theme before each frame.
- Theme colours are **0 to 1 RGB**, not hex. The theme `id` is the slot id and is case-sensitive.
- `setColorSlot` / `setTextSlot` / `setSlots` exist too (untested here). Re-texting needs the font inside the Lottie.

## Proof
Tested 2026-10-08 on dotlottie-web 0.81.0, HyperFrames 0.8.77, 1080x1080, 3 s, with a hand-made Lottie: `hyperframes
lint` 0 errors. Snapshots at 0.5, 1.5, 2.5 s, in that order and in reverse (`--no-browser-gpu`), were byte-identical
(md5) at every time. The box pixel read exactly #CB1B20 (grey without the theme). A full render looked the same at 1.5 s
(checked by eye; H.264 shifts the red slightly).
