// Kit to Clip first-three-seconds check (the hook): load a HyperFrames composition the way HyperFrames renders it and
// step through its opening. People decide in the first seconds, often with the sound off, so it fails when:
//   - the first frame shows nothing but background (visible elements covering less than 2% of the canvas together),
//   - no readable text or logo is on screen by --by seconds (text ink at least 2.5% of the canvas height; a logo
//     counts), so a muted viewer has no reason to stay,
//   - nothing moves in the first second (every visible element keeps the same position, size and opacity).
// Like the other checks it fails, never passes, when it cannot check (player not ready, script errors, zero duration).
// Usage: node hookcheck.mjs <project-dir> [bySeconds]
import path from "node:path";
import { fail, withComposition } from "./hfpage.mjs";

const proj = path.resolve(process.argv[2] || ".");
const by = Number(process.argv[3] || 3);
if (!(by > 0)) { console.error("hook check: --by must be a positive number of seconds"); process.exit(2); }

const r = await withComposition(proj, "hook check", async ({ page, state, errors }) => {
  const subErrs = errors.console.filter((e) => e.startsWith("[HyperFrames] composition script error"));
  const errs = [...new Set([...errors.script, ...subErrs])].map((e) => `script error: ${e}`);
  if (!state.ready) fail("the HyperFrames player never became ready, so the opening was not checked", errs);
  if (errs.length) fail("the page threw script errors while loading (run finish.py check)", errs);
  if (!(state.duration > 0)) fail("the composition has zero duration, so there is no opening to check");
  const end = Math.min(by, state.duration);
  return page.evaluate(async ({ end, W, H }) => {
    const V = window.__reelVisible;
    const minText = H * 0.025, minArea = W * H * 0.02;
    // everything drawn: leaf-ish elements with a box, not the root or full-canvas background layers of the root itself
    const drawn = () => [...document.querySelectorAll("body *")].filter((el) => {
      if (el.closest("script, style, template, audio")) return false;
      if (el.matches("[data-composition-id]")) return false;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) return false;
      const cs = getComputedStyle(el);
      const paints = ["IMG", "VIDEO", "CANVAS", "svg"].includes(el.tagName) || el instanceof SVGElement ||
        cs.backgroundImage !== "none" || (cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== "transparent") ||
        [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) || parseFloat(cs.borderTopWidth) > 0;
      return paints;
    });
    const seen = (el) => { const r = el.getBoundingClientRect(); return V.seenRect(el, { L: r.left, T: r.top, R: r.right, B: r.bottom }, W, H); };
    const snapshot = () => drawn().map((el) => {
      const v = seen(el); if (!v) return null;
      const cs = getComputedStyle(el);
      return `${V.name(el)}|${Math.round(v.L)},${Math.round(v.T)},${Math.round(v.R)},${Math.round(v.B)}|${(+cs.opacity).toFixed(2)}|${cs.transform}|${cs.clipPath}`;
    }).filter(Boolean).join("\n");

    await V.seek(0);
    // everything drawn at 0 s, together: a headline split into word spans counts as the headline
    const shown = drawn().map((el) => ({ el, v: seen(el) })).filter((x) => x.v)
      .map((x) => ({ name: V.name(x.el), area: (x.v.R - x.v.L) * (x.v.B - x.v.T) })).sort((a, b) => b.area - a.area);
    const total = shown.reduce((s, x) => s + x.area, 0);
    const opening = total >= minArea ? shown : [];
    const s0 = snapshot();
    let moved = null, readable = null, readableText = "";
    for (let t = 0; t <= end + 1e-6; t = +(t + 0.1).toFixed(3)) {
      await V.seek(Math.min(t, end));
      if (moved === null && t > 0 && t <= 1.0 + 1e-6 && snapshot() !== s0) moved = t;
      if (readable === null) for (const el of V.candidates()) {
        const q = V.inkRect(el); if (!(q.R > q.L && q.B > q.T)) continue;
        const v = V.seenRect(el, q, W, H); if (!v) continue;
        const logo = ["IMG", "svg"].includes(el.tagName);
        if (logo || v.B - v.T >= minText) { readable = t; readableText = (el.textContent || el.getAttribute("src") || "").trim().replace(/\s+/g, " ").slice(0, 40); break; }
      }
      if (readable !== null && (moved !== null || t > 1.0)) break;
    }
    return { opening: opening.slice(0, 3), openingCount: opening.length, moved, readable, readableText };
  }, { end, W: state.size.width, H: state.size.height });
});

const lines = [], bad = [];
if (r.openingCount) lines.push(`first frame shows ${r.openingCount} element(s), e.g. ${r.opening.map((o) => o.name).join(", ")}`);
else bad.push("the first frame shows only background: open on the subject, a photo or the title");
if (r.readable !== null) lines.push(`readable muted by ${r.readable.toFixed(1)} s ("${r.readableText}")`);
else bad.push(`no readable text or logo by ${by} s: a muted viewer gets no reason to stay (show the promise or the brand early)`);
if (r.moved !== null) lines.push(`moves by ${r.moved.toFixed(1)} s`);
else bad.push("nothing moves in the first second: start the motion at once");
if (bad.length) {
  console.log(`✗ hook check: ${bad.length} problem(s) in the first ${by} s`);
  for (const b of bad) console.log("  - " + b);
  for (const l of lines) console.log("  ✓ " + l);
  process.exit(1);
}
console.log(`✓ hook check: ${lines.join("; ")}`);
