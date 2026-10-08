/* Risograph style: a halftone disc in the accent ink, a misregistered outline in the text ink, a printed grain. The
   offset is fixed per scene (seeded), so a frame never shifts between renders. */
(function () {
  window.EXPLAINER_STYLE = {
    name: "risograph",
    background(bg) {
      bg.innerHTML = '<svg class="grain" xmlns="http://www.w3.org/2000/svg"><filter id="riso"><feTurbulence type="fractalNoise" baseFrequency="1.4" numOctaves="1" seed="3"/>' +
        '<feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1.2 -.2"/></filter><rect width="100%" height="100%" filter="url(#riso)"/></svg>';
    },
    decorate(art, i, seed) {
      const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg"), id = "dots" + seed;
      svg.setAttribute("class", "art"); svg.setAttribute("viewBox", "0 0 200 200");
      svg.innerHTML = `<defs><pattern id="${id}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(${15 + seed * 7})">` +
        `<circle cx="3.5" cy="3.5" r="2.4" fill="var(--reel-accent)"/></pattern></defs>` +
        `<circle class="tone" cx="100" cy="100" r="76" fill="url(#${id})"/>` +
        `<circle class="outline" cx="${103 + (seed % 3)}" cy="${98 - (seed % 2) * 3}" r="76" fill="none" stroke="var(--reel-fg)" stroke-width="3"/>`;
      art.prepend(svg);
      if (art.querySelector("img")) svg.style.cssText = "position:absolute;inset:0;opacity:.6";
    },
    animate(tl, art, sc, R) {
      tl.fromTo(art.querySelector(".tone"), { scale: 0.6, transformOrigin: "50% 50%" }, { scale: 1, duration: R.dur("expressive"), ease: R.ease("expressive") }, sc.start + 0.05);
      const o = art.querySelector(".outline"), L = 2 * Math.PI * 76;
      tl.fromTo(o, { strokeDasharray: L, strokeDashoffset: L }, { strokeDashoffset: 0, duration: R.dur("move"), ease: R.ease("move") }, sc.start + 0.2);
    },
  };
})();
