// Kit to Clip finish: what a viewer can see in a HyperFrames composition, measured in the page (shared by the safe-zone
// and first-three-seconds checks; hfpage.mjs injects it as window.__reelVisible).
// Counts elements with their own visible text (HTML, and SVG <text>), plus logo images and logo SVGs. Footage, stills
// and ink drawings are exempt, as is anything inside #cam, #frame or [data-safe-ignore]. Measures the real text ink
// (Range client rects), not the element's full-width box, and only the part inside the canvas and clipping parents.
window.__reelVisible = (function () {
  const isLogo = (el) => /logo/i.test([el.id, el.getAttribute("class"), el.getAttribute("src"), el.getAttribute("alt"), el.getAttribute("aria-label")].join(" "));
  const candidates = () => [...document.querySelectorAll("body *")].filter((el) => {
    if (el.closest("#cam, #frame, [data-safe-ignore], script, style, template, video, audio")) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === "img") return isLogo(el);
    if (tag === "svg") return isLogo(el);
    if (el instanceof SVGElement) return tag === "text" && el.textContent.trim() !== "";
    return [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  });
  const inkRect = (el) => {
    if (!(el instanceof HTMLElement) || el.tagName === "IMG") { const r = el.getBoundingClientRect(); return { L: r.left, T: r.top, R: r.right, B: r.bottom }; }
    const range = document.createRange(); let L = 1e9, T = 1e9, R = -1e9, B = -1e9;
    for (const n of el.childNodes) if (n.nodeType === 3 && n.textContent.trim()) {
      range.selectNodeContents(n);
      for (const q of range.getClientRects()) { L = Math.min(L, q.left); T = Math.min(T, q.top); R = Math.max(R, q.right); B = Math.max(B, q.bottom); }
    }
    return { L, T, R, B };
  };
  // the part a viewer can see: not hidden, not transparent, not collapsed by clip-path, inside clipping parents and the canvas
  const seenRect = (el, q, W, H) => {
    let { L, T, R, B } = q, o = 1;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === "none") return null;
      if (e === el && cs.visibility !== "visible") return null;
      o *= Number(cs.opacity);
      const m = /inset\(([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%/.exec(cs.clipPath || "");
      if (m && (+m[2] + +m[4] >= 99.5 || +m[1] + +m[3] >= 99.5)) return null;
      if (e !== el && e !== document.body && e !== document.documentElement) {
        const cx = /hidden|clip/.test(cs.overflowX), cy = /hidden|clip/.test(cs.overflowY);
        if (cx || cy) {
          const r = e.getBoundingClientRect();
          if (cx) { L = Math.max(L, r.left); R = Math.min(R, r.right); }
          if (cy) { T = Math.max(T, r.top); B = Math.min(B, r.bottom); }
        }
      }
    }
    if (o <= 0.05) return null;
    L = Math.max(L, 0); T = Math.max(T, 0); R = Math.min(R, W); B = Math.min(B, H);
    return R > L && B > T ? { L, T, R, B } : null;
  };
  const name = (el) => {
    const base = el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}${[...el.classList].map((c) => "." + c).join("")}`;
    const comp = el.closest("[data-composition-id]");
    return comp ? `${base} in ${comp.getAttribute("data-composition-id")}` : base;
  };
  const seek = async (t) => {
    await window.__player.renderSeek(t);
    if (typeof window.__hfWaitForSeekCompletion === "function") await window.__hfWaitForSeekCompletion();
  };
  return { isLogo, candidates, inkRect, seenRect, name, seek };
})();
