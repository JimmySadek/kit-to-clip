/* Original input/process/output grammar, without invented data or scientific claims. */
window.EXPLAINER_STYLE = {
  name: "flat-vector",
  decorate(art) {
    const wide = window.REEL_FORMAT.canvas[0] > window.REEL_FORMAT.canvas[1];
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "art"); svg.setAttribute("viewBox", wide ? "0 0 560 200" : "0 0 360 360");
    svg.setAttribute("aria-hidden", "true");
    const nodes = wide ? [[92,100],[280,100],[468,100]] : [[180,60],[180,180],[180,300]];
    const [a,b,c] = nodes;
    const links = wide ? ["M154,100H210M194,86L210,100L194,114", "M350,100H406M390,86L406,100L390,114"] :
      ["M180,104V130M168,118L180,130L192,118", "M180,230V254M168,242L180,254L192,242"];
    svg.innerHTML = links.map(d => `<path class="vector-link" d="${d}"/>`).join("") +
      `<g class="vector-node"><circle class="vector-input" cx="${a[0]}" cy="${a[1]}" r="42"/><circle class="vector-detail" cx="${a[0]}" cy="${a[1]}" r="13"/></g>` +
      `<g class="vector-node"><rect class="vector-process" x="${b[0]-56}" y="${b[1]-44}" width="112" height="88" rx="14"/><path class="vector-detail" d="M${b[0]-20},${b[1]-18}h40v36h-40Z"/></g>` +
      `<g class="vector-node"><circle class="vector-output" cx="${c[0]}" cy="${c[1]}" r="42"/><path class="vector-detail" d="M${c[0]-18},${c[1]}l12,12l26,-28l-7,-6l-20,21l-6,-6Z"/></g>`;
    art.prepend(svg);
    if (art.querySelector("img")) svg.style.cssText = "position:absolute;inset:0;opacity:.3";
  },
  animate(tl, art, sc, R) {
    tl.fromTo(art.querySelectorAll(".vector-node"), { opacity: 0, scale: .8, transformOrigin: "50% 50%" },
      { opacity: 1, scale: 1, duration: R.dur("enter"), stagger: R.stagger()*4, ease: R.ease("enter") }, sc.start + .05);
    art.querySelectorAll(".vector-link").forEach((link,i) => {
      const length = link.getTotalLength();
      tl.fromTo(link, { strokeDasharray: length, strokeDashoffset: length },
        { strokeDashoffset: 0, duration: R.dur("move"), ease: R.ease("move") }, sc.start + .15 + i*R.stagger()*4);
    });
  }
};
