// Kit to Clip safe-zone check: load a HyperFrames composition the way HyperFrames previews and renders it (served on
// localhost with the HyperFrames runtime in <head>, so data-composition-src sub-compositions mount and the real
// duration is known), seek through the timeline with the player's renderSeek, and fail when visible text or a logo
// leaves the platform safe box. Measures the real text ink (Range client rects), not the element's full-width box,
// and only the part a viewer can see (inside the canvas and any overflow-clipping parent).
// It fails, never passes, when it cannot check: player not ready, root timeline missing, a sub-composition that did
// not mount, script errors at load, zero duration, or no visible text or logo at any sampled time.
// Usage: node safecheck.mjs <project-dir> <x0,y0,x1,y1> [stepSeconds]
import path from "node:path";
import { fail, withComposition } from "./hfpage.mjs";

const proj = path.resolve(process.argv[2] || ".");
const box = (process.argv[3] || "").split(",").map(Number);
const step = Number(process.argv[4] || 0.2);
if (box.length !== 4 || box.some(isNaN)) { console.error("safe check: box must be x0,y0,x1,y1"); process.exit(2); }
if (!(step > 0)) { console.error("safe check: step must be a positive number of seconds"); process.exit(2); }

const result = await withComposition(proj, "safe check", async ({ page, state, errors }) => {
  // the runtime catches a sub-composition's script error and only logs it, so count those logs too
  const subErrs = errors.console.filter((e) => e.startsWith("[HyperFrames] composition script error"));
  const errs = [...new Set([...errors.script, ...subErrs])].map((e) => `script error: ${e}`);
  if (!state.ready) fail("the HyperFrames player never became ready, so the composition was not loaded and nothing was checked",
    [...errs, `timelines registered: ${state.timelines.join(", ") || "none"}`]);
  if (!state.rootId) fail("no element with data-composition-id in index.html; not a HyperFrames composition");
  if (!state.timelines.includes(state.rootId)) fail(`no timeline registered for the root composition "${state.rootId}"`,
    [`timelines registered: ${state.timelines.join(", ") || "none"}`, ...errs]);
  if (state.unmounted.length) fail(`${state.unmounted.length} sub-composition(s) did not mount, so their text was not checked`,
    [...state.unmounted, ...errs]);
  if (errs.length) fail("the page threw script errors while loading, so parts of it may not have built (run finish.py check)", errs);
  const { duration, size } = state;
  if (!(duration > 0)) fail("the composition has zero duration, so there was no timeline to step through");

  const result = await page.evaluate(async ({ box, step, duration, W, H }) => {
    const [x0, y0, x1, y1] = box, TOL = 2;
    const { candidates, inkRect, name, seek } = window.__reelVisible;
    const seenRect = (el, q) => window.__reelVisible.seenRect(el, q, W, H);
    const found = new Map(), checked = new Set();
    let samples = 0;
    for (let i = 0; ; i++) {
      const t = Math.min(+(i * step).toFixed(4), Math.max(0, duration - 0.001));
      await seek(t);
      samples++;
      for (const el of candidates()) {
        const q = inkRect(el);
        if (!(q.R > q.L && q.B > q.T)) continue;
        const v = seenRect(el, q);
        if (!v) continue;
        checked.add(el);
        const over = { left: x0 - v.L, top: y0 - v.T, right: v.R - x1, bottom: v.B - y1 };
        const worst = Math.max(...Object.values(over));
        if (worst <= TOL) continue;
        const text = (el.textContent || el.getAttribute("src") || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 40);
        const k = `${name(el)} "${text}"`, prev = found.get(k);
        const side = Object.keys(over).filter((s) => over[s] > TOL).join("+");
        const at = +t.toFixed(2), rect = [v.L, v.T, v.R, v.B].map(Math.round);
        if (!prev) found.set(k, { first: at, last: at, over: Math.round(worst), side, rect });
        else { prev.last = at; if (worst > prev.over) Object.assign(prev, { over: Math.round(worst), side, rect }); }
      }
      if (t >= duration - 0.001) break;
    }
    return { checked: checked.size, samples, issues: [...found.entries()].map(([k, v]) => ({ el: k, ...v })) };
  }, { box, step, duration, W: size.width, H: size.height });
  if (result.checked === 0) fail(`found no visible text or logo at any of ${result.samples} sampled times in ${duration.toFixed(1)} s, so nothing was checked. ` +
    "If this video really has no text or logo, say the safe check does not apply instead of reporting a pass.");
  return Object.assign(result, { duration, hosts: state.hosts, size });
});

const scope = `${result.size.width}x${result.size.height}, ${result.duration.toFixed(1)} s, ${result.samples} samples every ${step} s` +
  (result.hosts ? `, ${result.hosts} sub-composition(s) mounted` : "");
if (result.issues.length) {
  console.log(`✗ safe check: ${result.issues.length} element(s) leave the safe box [${box}] (${scope})`);
  for (const i of result.issues) console.log(`  - ${i.el} ${i.side} by ${i.over}px at ${i.first}-${i.last} s, seen box [${i.rect}]`);
  process.exit(1);
}
console.log(`✓ safe check: ${result.checked} text/logo elements stay inside [${box}] (${scope})`);
