/* Isometric style: three blocks on an isometric grid that drop in one after another. Heights vary per scene, fixed by
   the scene number, so frames repeat exactly. */
(function () {
  const iso = (x, y, z) => [100 + (x - y) * 26, 120 + (x + y) * 15 - z * 30];
  const block = (ns, gx, gy, h, alt) => {
    const g = document.createElementNS(ns, "g"); g.setAttribute("class", "block");
    const P = (pts) => pts.map((p) => p.join(",")).join(" ");
    const a = iso(gx, gy, h), b = iso(gx + 1, gy, h), c = iso(gx + 1, gy + 1, h), d = iso(gx, gy + 1, h);
    const b0 = iso(gx + 1, gy, 0), c0 = iso(gx + 1, gy + 1, 0), d0 = iso(gx, gy + 1, 0);
    for (const [cls, pts] of [["face-left", [d, c, c0, d0]], ["face-right", [b, c, c0, b0]], ["face-top" + (alt ? " alt" : ""), [a, b, c, d]]]) {
      const poly = document.createElementNS(ns, "polygon"); poly.setAttribute("class", cls); poly.setAttribute("points", P(pts)); g.append(poly);
    }
    return g;
  };
  window.EXPLAINER_STYLE = {
    name: "isometric",
    decorate(art, i, seed) {
      const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
      svg.setAttribute("class", "art"); svg.setAttribute("viewBox", "0 0 200 200");
      let grid = ""; for (let k = -3; k <= 3; k++) { const [x1, y1] = iso(k, -3, 0), [x2, y2] = iso(k, 3, 0), [x3, y3] = iso(-3, k, 0), [x4, y4] = iso(3, k, 0);
        grid += `M${x1} ${y1}L${x2} ${y2}M${x3} ${y3}L${x4} ${y4}`; }
      const g = document.createElementNS(ns, "path"); g.setAttribute("class", "grid"); g.setAttribute("d", grid); svg.append(g);
      const hs = [1 + (seed % 3), 2 + ((seed + 1) % 2), 1 + ((seed + 2) % 3)];
      [[-1, 0], [0, 0], [0, -1]].forEach(([gx, gy], k) => svg.append(block(ns, gx, gy, hs[k] * 0.6, k === 1)));
      art.prepend(svg);
      if (art.querySelector("img")) svg.style.cssText = "position:absolute;inset:0;opacity:.5";
    },
    animate(tl, art, sc, R, u) {
      tl.from(art.querySelectorAll(".block"), { y: -18 * u, opacity: 0, duration: R.dur("enter"), ease: "back.out(1.6)", stagger: R.stagger() * 3 }, sc.start + 0.05);
    },
  };
})();
