/* Clean style: an accent ring that draws on, a dot that lands. Deterministic (no randomness). */
window.EXPLAINER_STYLE = {
  name: "clean",
  decorate(art, i) {
    const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "art"); svg.setAttribute("viewBox", "0 0 200 200");
    const ring = document.createElementNS(ns, "circle");
    ring.setAttribute("class", "ring draw"); ring.setAttribute("cx", 100); ring.setAttribute("cy", 100); ring.setAttribute("r", 70);
    ring.setAttribute("stroke-width", 9); ring.setAttribute("transform", `rotate(${-90 + i * 40} 100 100)`);
    const dot = document.createElementNS(ns, "circle");
    dot.setAttribute("class", "dot"); dot.setAttribute("cx", 100); dot.setAttribute("cy", 100); dot.setAttribute("r", 16);
    svg.append(ring, dot);
    art.prepend(svg);
    if (art.querySelector("img")) svg.style.cssText = "position:absolute;inset:0;opacity:.35";
  },
  animate(tl, art, sc, R) {
    const ring = art.querySelector(".ring"), dot = art.querySelector(".dot"), L = 2 * Math.PI * 70;
    tl.fromTo(ring, { strokeDasharray: L, strokeDashoffset: L }, { strokeDashoffset: 0, duration: R.dur("expressive") * 1.4, ease: R.ease("move") }, sc.start + 0.05);
    tl.fromTo(dot, { scale: 0, transformOrigin: "50% 50%" }, { scale: 1, duration: R.dur("enter"), ease: "back.out(2)" }, sc.start + 0.35);
  },
};
