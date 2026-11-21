/* Pixel illustration only. Brand fonts, supplied visuals and logos are never pixelated. */
window.EXPLAINER_STYLE = {
  name: "pixel",
  decorate(art) {
    const wide = window.REEL_FORMAT.canvas[0] > window.REEL_FORMAT.canvas[1];
    const W = wide ? 560 : 360, H = wide ? 200 : 360;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "art"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("aria-hidden", "true");
    let grid = "";
    for (let x=16;x<W;x+=16) grid += `M${x},16V${H-16}`;
    for (let y=16;y<H;y+=16) grid += `M16,${y}H${W-16}`;
    const nodes = wide ? [[64,96],[272,64],[480,128]] : [[64,64],[272,160],[96,288]];
    const route = wide ? "M64,96H160V64H272H384V128H480" : "M64,64H176V160H272V224H96V288";
    svg.innerHTML = `<path class="pixel-grid" d="${grid}"/><path class="pixel-link" d="${route}"/>` +
      nodes.map(([x,y]) => `<g class="pixel-node"><path class="pixel-block" d="M${x-24},${y-32}h48v8h8v48h-8v8h-48v-8h-8v-48h8Z"/><rect class="pixel-inset" x="${x-16}" y="${y-16}" width="32" height="32"/><rect class="pixel-light" x="${x-8}" y="${y-8}" width="16" height="16"/></g>`).join("");
    art.prepend(svg);
    if (art.querySelector("img")) svg.style.cssText = "position:absolute;inset:0;opacity:.3";
  },
  animate(tl, art, sc, R) {
    const link = art.querySelector(".pixel-link"), length = link.getTotalLength();
    tl.fromTo(link, { strokeDasharray: length, strokeDashoffset: length },
      { strokeDashoffset: 0, duration: R.dur("move")*1.4, ease: "steps(12)" }, sc.start + .05);
    tl.fromTo(art.querySelectorAll(".pixel-node"), { opacity: 0, y: -8 },
      { opacity: 1, y: 0, duration: R.dur("enter"), ease: "steps(4)", stagger: R.stagger()*4 }, sc.start + .1);
  }
};
