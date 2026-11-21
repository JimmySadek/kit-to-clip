/* Original, token-driven glass illustration. All animation belongs to the seekable timeline. */
window.EXPLAINER_STYLE = {
  name: "glass",
  decorate(art) {
    const wide = window.REEL_FORMAT.canvas[0] > window.REEL_FORMAT.canvas[1];
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "art");
    svg.setAttribute("viewBox", wide ? "0 0 560 200" : "0 0 360 360");
    svg.setAttribute("aria-hidden", "true");
    const panes = wide ? [[46,34,192,132],[184,20,192,132],[322,48,192,132]] : [[28,26,220,150],[72,104,220,150],[110,182,220,150]];
    const centres = panes.map(([x,y,w,h]) => [x + w/2,y + h/2]);
    svg.innerHTML = centres.map(([x,y]) => `<circle class="glass-halo" cx="${x}" cy="${y}" r="46"/>`).join("") +
      `<path class="glass-link" d="M${centres.map(p => p.join(",")).join("L")}"/>` +
      panes.map(([x,y,w,h]) => `<g class="pane"><rect class="glass-pane" x="${x}" y="${y}" width="${w}" height="${h}" rx="16"/><path class="glass-edge" d="M${x+18},${y+9}H${x+w-18}"/><circle class="glass-node" cx="${x+w/2}" cy="${y+h/2}" r="10"/></g>`).join("");
    art.prepend(svg);
    if (art.querySelector("img")) svg.style.cssText = "position:absolute;inset:0;opacity:.3";
  },
  animate(tl, art, sc, R) {
    tl.fromTo(art.querySelectorAll(".pane"), { y: 18, opacity: 0 },
      { y: 0, opacity: 1, duration: R.dur("enter"), stagger: R.stagger()*3, ease: R.ease("enter") }, sc.start + .05);
    const link = art.querySelector(".glass-link"), length = link.getTotalLength();
    tl.fromTo(link, { strokeDasharray: length, strokeDashoffset: length },
      { strokeDashoffset: 0, duration: R.dur("move"), ease: R.ease("move") }, sc.start + .18);
  }
};
