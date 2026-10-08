/* Cut-paper style: three wobbly paper layers per scene (seeded, so every frame is repeatable), paper grain with a fixed
   turbulence seed, and the headline on a slightly turned paper strip. */
(function () {
  const rng = (seed) => () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const blob = (r, cx, cy, rad, n) => { let d = ""; for (let k = 0; k <= n; k++) { const a = (k / n) * Math.PI * 2, rr = rad * (0.86 + 0.28 * r());
    d += (k ? "L" : "M") + (cx + Math.cos(a) * rr).toFixed(1) + " " + (cy + Math.sin(a) * rr).toFixed(1); } return d + "Z"; };
  window.EXPLAINER_STYLE = {
    name: "cut-paper",
    background(bg) {
      bg.innerHTML = '<svg class="grain" xmlns="http://www.w3.org/2000/svg"><filter id="paper"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="7"/>' +
        '<feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .9 0"/></filter><rect width="100%" height="100%" filter="url(#paper)"/></svg>';
    },
    decorate(art, i, seed) {
      const r = rng(seed * 977), ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
      svg.setAttribute("class", "art"); svg.setAttribute("viewBox", "0 0 200 200");
      const fills = ["var(--reel-surface)", "var(--reel-accent)", "var(--reel-fg)"];
      [78, 58, 30].forEach((rad, k) => {
        const p = document.createElementNS(ns, "path");
        p.setAttribute("class", "layer"); p.setAttribute("d", blob(r, 100 + (r() - 0.5) * 20, 100 + (r() - 0.5) * 20, rad, 9));
        p.setAttribute("fill", fills[k]); svg.append(p);
      });
      art.prepend(svg);
      if (art.querySelector("img")) svg.style.cssText = "position:absolute;inset:0";
      const h = art.parentElement.querySelector(".scene-headline");
      h.style.transform = `rotate(${((r() - 0.5) * 3).toFixed(2)}deg)`;
    },
    animate(tl, art, sc, R, u) {
      tl.from(art.querySelectorAll(".layer"), { y: 12 * u, opacity: 0, duration: R.dur("enter"), ease: R.ease("enter"), stagger: R.stagger() * 3 }, sc.start + 0.05);
    },
  };
})();
