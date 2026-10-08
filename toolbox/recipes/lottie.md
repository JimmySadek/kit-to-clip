# Lottie: play one in a video, deliver one for a website or app

## Play a Lottie inside a video
1. `python3 <kit-to-clip>/scripts/toolbox.py vendor lottie-web <project>`: copies `vendor/lottie.min.js` and credits it.
   Never load the player from a CDN, because renders run offline.
2. Copy the `.json` into `assets/`. Load it with `lottie.loadAnimation({container, renderer: "svg", loop: false,
   autoplay: false, path: "assets/x.json"})` and push the animation onto `window.__hfLottie`. The engine's adapter
   (`hyperframes-animation/adapters/lottie.md`) seeks it by composition time.
3. **Also register a paused GSAP timeline on `window.__timelines[<composition id>]`, even when the scene is only a
   Lottie.** Otherwise `hyperframes lint` reports an error. The render still works, but the checks before a render
   offer must pass.

## Deliver a Lottie (capability `lottie-export`)
- **Who makes it:** EffectCraft (`recipes/effectcraft.md`). The Kit to Clip HTML engine cannot export Lottie itself.
  Build the motion as vector layers there, from the brand's SVG.
- **Before handing it over, play it back.** Put it in a one-scene project as above, render it, and put three stills
  next to EffectCraft's own frames at the same times. They must match. (Tested 2026-10-08: they matched at 0.5, 1.0
  and 1.5 s.)
- **What Lottie cannot hold:** tapered strokes, blur and glow effects, video, live text in custom fonts (convert text
  to shapes). Keep a Lottie to vector shapes, fills, strokes, trims, transforms and masks.
- **Deliver:**
  - the `.json`
  - a `.lottie` (dotLottie) when the site uses the dotLottie player
  - a static SVG or PNG poster for people who turn motion off (`reduced-motion`)
  - a WebM as a fallback
- **Size:** a logo draw-on is a few KB. Above 200 KB, look for embedded pictures (`data:image`) and remove them.
