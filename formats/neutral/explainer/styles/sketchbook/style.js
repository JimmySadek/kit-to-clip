/* Sketchbook style: a seeded hand-drawn loop (two passes, like a pencil going round twice), a marker underline and an
   arrow, all drawn on. Seeded jitter: the same scene always wobbles the same way. */
(function () {
  const rng = (seed) => () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const loop = (r, cx, cy, rx, ry) => { let d = ""; const a0 = -1.8 + r(); for (let k = 0; k <= 64; k++) { const a = a0 + (k / 64) * (Math.PI * 2 + 0.5),
    j = 1 + (r() - 0.5) * 0.05; d += (k ? "L" : "M") + (cx + rx * j * Math.cos(a)).toFixed(1) + " " + (cy + ry * j * Math.sin(a) + k * 0.06).toFixed(1); } return d; };
  window.EXPLAINER_STYLE = {
    name: "sketchbook",
    decorate(art, i, seed) {
      const r = rng(seed * 131), ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
      svg.setAttribute("class", "art"); svg.setAttribute("viewBox", "0 0 200 200");
      const paths = [["pencil", loop(r, 100, 100, 72, 60), 2.6], ["pencil", loop(r, 101, 99, 70, 58), 1.6],
        ["marker", `M40 168 Q100 ${158 + r() * 8} 160 166`, 7],
        ["pencil", `M150 30 Q175 ${50 + r() * 8} 160 74 M160 74 L150 64 M160 74 L170 66`, 2.2]];
      for (const [cls, d, w] of paths) {
        const p = document.createElementNS(ns, "path");
        p.setAttribute("class", cls + " draw"); p.setAttribute("d", d); p.setAttribute("stroke-width", w); svg.append(p);
      }
      art.prepend(svg);
      if (art.querySelector("img")) svg.style.cssText = "position:absolute;inset:0";
    },
    animate(tl, art, sc, R) {
      art.querySelectorAll(".draw").forEach((p, k) => {
        const L = p.getTotalLength();
        tl.fromTo(p, { strokeDasharray: L, strokeDashoffset: L + 1 }, { strokeDashoffset: 0, duration: R.dur("move"), ease: "power1.inOut" }, sc.start + 0.1 + k * 0.22);
      });
    },
  };
})();
