# Motion: real springs, driven by video time

**What it adds:** physical springs (overshoot, settle, "app-like" bounce) from the Motion library. GSAP's
`elastic` and `back` eases only imitate this. Read first: `https://motion.dev/docs/spring.md` and
`https://motion.dev/docs/animate.md`.

1. `python3 <kit-to-clip>/scripts/toolbox.py vendor motion <project>`: copies `vendor/motion.js` (a UMD file, it
   sets `window.Motion`). Load it with a plain `<script src="vendor/motion.js">`. Never from a CDN.
2. Also vendor GSAP: the paused GSAP timeline is the clock HyperFrames seeks.

## The seekable pattern (use this)

`spring({keyframes:[from,to], ...})` returns a generator. `next(ms)` gives the spring's value at any time, in any
order, so a spring becomes a pure function of composition time. A GSAP tween writes a proxy property whose setter
draws the frame, so every seek redraws exactly that time, forwards or backwards.

```js
const { spring } = window.Motion;
function springTrack(from, to, start, opts) {            // start in seconds of composition time
  const gen = spring({ keyframes: [from, to], ...opts });
  return (t) => (t <= start ? from : gen.next((t - start) * 1000).value);
}
const cardX = springTrack(-760, 0, 0.0, { visualDuration: 0.7, bounce: 0.45 });
const pop   = springTrack(0, 1, 1.2, { stiffness: 260, damping: 9, mass: 1 });
function draw(t) {
  card.style.transform = `translateX(${cardX(t)}px)`;
  dot.style.transform  = `scale(${pop(t)})`;
}
let now = 0;
const clock = { get t() { return now; }, set t(v) { now = v; draw(v); } };
const tl = gsap.timeline({ paused: true });
tl.fromTo(clock, { t: 0 }, { t: 3, duration: 3, ease: "none" }, 0);   // 3 = data-duration
draw(0);
window.__timelines["main"] = tl;
```

**Second route (also tested):** `animate(el, {...}, { type: "spring", delay: 1.9, autoplay: false })`, then
`anim.time = t` inside `draw(t)`. Pass the **composition time** and put the start in `delay`.

## Traps found by testing
- **Motion's own clock is the wall clock.** Never let `animate()` autoplay in a video. Always `autoplay: false` and
  set `.time` from the GSAP clock, or use `spring().next()`.
- **Motion hands some properties to the browser (WAAPI).** `opacity` became a native animation that HyperFrames'
  WAAPI adapter also seeks, to composition time. The two agree only when `.time` is the composition time with the
  start in `delay`. Setting `.time = t - start` makes two clocks fight. Transforms like `rotate` ran in JS.
- **Use a property setter, not `onUpdate`, to draw.** It runs on every seek, whatever GSAP does with callbacks.
- `spring()` time is in **milliseconds**; `visualDuration` is in **seconds**. Setting `stiffness`, `damping` or
  `mass` overrides `visualDuration` and `bounce`.
- Size it for the peak: a bouncy `scale` overshoots well past 1 (clearly visible at damping 9), so leave room.

## Proof
Tested 2026-10-08 on motion 14.0.0, HyperFrames 0.8.77, 1080x1080, 3 s: `hyperframes lint` 0 errors. Snapshots at
0.5, 1.5, 2.5 s, taken once in that order and once in reverse (`--no-browser-gpu`), were byte-identical (md5)
at every time. Frames showed the slide, the overshooting pop, the spring bar and the spin. A full
`hyperframes render` looked the same at 1.5 s (checked by eye).
