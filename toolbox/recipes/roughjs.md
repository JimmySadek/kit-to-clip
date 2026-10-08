# Rough.js: hand-drawn shapes that draw on

Rough.js turns rectangles, circles, curves and lines into sketchy SVG paths, with hachure, cross-hatch or zigzag
fills. MIT. Read before use: the Rough.js wiki (link on the card) for every shape and option.

```bash
python3 <kit-to-clip>/scripts/toolbox.py vendor roughjs <project>   # vendor/rough.js (global `rough`) + licence
```

## The seekable pattern (tested)

Rough draws once, at page load. GSAP then draws the paths on with `stroke-dashoffset` on a paused timeline, so any
time seeks exactly.

```js
const rc = rough.svg(svg);
const base = { stroke: INK, strokeWidth: 5, roughness: 1.6, bowing: 1.2 };
const box = rc.rectangle(130, 300, 360, 260, { ...base, seed: 11, fill: RED, fillStyle: "hachure", hachureGap: 18 });
svg.appendChild(box);

// One <path> per subpath, so each outline pass and each hachure line draws on by itself.
const parts = [];
for (const path of [...box.querySelectorAll("path")]) {
  for (const d of path.getAttribute("d").split(/(?=M)/).filter((s) => s.trim())) {
    const p = path.cloneNode(); p.setAttribute("d", d); p.setAttribute("stroke-linecap", "round");
    path.before(p); parts.push({ el: p, fill: path.getAttribute("stroke") !== INK });
  }
  path.remove();
}
const tl = gsap.timeline({ paused: true });
const drawOn = (els, at, dur, stagger) => {
  for (const el of els) {
    const len = el.getTotalLength();
    gsap.set(el, { attr: { "stroke-dasharray": `${len} ${len + 2}` }, strokeDashoffset: len + 1 });
  }
  tl.to(els, { strokeDashoffset: 0, duration: dur, ease: "power1.inOut", stagger }, at);
};
drawOn(parts.filter((s) => !s.fill).map((s) => s.el), 0.2, 0.7, 0.12);   // outline (Rough draws it twice)
drawOn(parts.filter((s) => s.fill).map((s) => s.el), 0.8, 0.18, 0.03);   // hachure, line by line
window.__timelines["<composition id>"] = tl;                              // after every tween is added
```

An arrow is `rc.curve([...points])` for the shaft plus `rc.linearPath([a, tip, b])` for the head, drawn after it.

## Traps found by testing (2026-10-08, Rough.js 4.6.6)
- **Always pass `seed`** (any number above 0) to every shape. Without it Rough uses `Math.random`: two separate page
  loads gave different wobble (different md5 at 3.6 s). A render runs several Chrome workers, each loading the page,
  so unseeded shapes would jump between chunks of the video.
- **Start the dash offset at `len + 1`, not `len`.** With `len`, a zero-length dash sits at the start of every path
  and round caps paint it as a dot: rows of dots showed before any line was drawn.
- **Rough draws each outline twice** (two slightly different passes, as a hand would). Stagger them a little.
- **A hachure fill is one path with many subpaths** (`M ... M ...`). Split it, or the whole fill draws on as one
  line. Fill paths carry the fill colour as their `stroke`; that is how to tell them from outlines.
- Build all paths before registering the timeline; `getTotalLength()` works synchronously after `appendChild`.

## Proof (2026-10-08)
1080x1080, 4 s on #F4F1EA: a hachured rectangle, a cross-hatched circle (fills #CB1B20, ink #161212), then a curved
arrow from one to the other.
- `hyperframes lint`: 0 errors. Snapshots at 0.5, 1.5, 2.5 s forward and backward: md5 equal.
- Frames: outlines draw on, hachure fills line by line, the arrow head lands last; the wobble is identical between
  runs. Render: 4 s in 7 s, and two renders matched in every frame.
