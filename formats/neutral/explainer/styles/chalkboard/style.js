/* Fixed hand-drawn paths, no randomness and no replacement of brand colours. */
window.EXPLAINER_STYLE = {
  name: "chalkboard",
  decorate(art) {
    const wide = window.REEL_FORMAT.canvas[0] > window.REEL_FORMAT.canvas[1];
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "art"); svg.setAttribute("viewBox", wide ? "0 0 560 200" : "0 0 360 360");
    svg.setAttribute("aria-hidden", "true");
    const circles = wide ? [[100,100],[460,100]] : [[94,88],[264,272]];
    const ring = ([x,y]) => `M${x+51},${y-4}C${x+55},${y+32} ${x+25},${y+52} ${x-7},${y+48}C${x-43},${y+45} ${x-57},${y+16} ${x-49},${y-16}C${x-42},${y-47} ${x-7},${y-53} ${x+23},${y-44}C${x+46},${y-37} ${x+55},${y-19} ${x+51},${y-4}`;
    const arrow = wide ? "M176,108C236,82 312,116 382,98M362,82L384,98L365,116" : "M126,158C164,174 179,222 207,237M206,214L210,241L185,235";
    svg.innerHTML = circles.map(p => `<path class="chalk-line chalk-draw" d="${ring(p)}"/><path class="chalk-line chalk-echo" transform="translate(2,1)" d="${ring(p)}"/>`).join("") +
      `<path class="chalk-line chalk-arrow chalk-draw" d="${arrow}"/>` +
      circles.map(([x,y]) => `<path class="chalk-note" d="M${x-32},${y+72}q29,6 60,-2M${x-27},${y+78}q22,4 48,-1"/>`).join("");
    art.prepend(svg);
    if (art.querySelector("img")) svg.style.cssText = "position:absolute;inset:0;opacity:.3";
  },
  animate(tl, art, sc, R) {
    art.querySelectorAll(".chalk-draw").forEach((line,i) => {
      const length = line.getTotalLength();
      tl.fromTo(line, { strokeDasharray: length, strokeDashoffset: length },
        { strokeDashoffset: 0, duration: R.dur("move"), ease: R.ease("move") }, sc.start + .05 + i*R.stagger()*3);
    });
    tl.fromTo(art.querySelectorAll(".chalk-echo, .chalk-note"), { opacity: 0 },
      { opacity: .28, duration: R.dur("enter"), ease: R.ease("enter") }, sc.start + .3);
  }
};
