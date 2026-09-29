// Kit to Clip motion trace: record how the elements of a HyperFrames composition really move, frame by frame, so sound
// can follow the picture. The composition is loaded the way HyperFrames renders it and the timeline is sampled once per
// frame (motion.mjs). Output: motion.json.
//
//   node trace.mjs <project-dir> [--fps 30] [--select "<css>"] [--out motion.json]
//
// Tracked elements: every element with data-anchor or data-track, plus anything --select matches. An element is named by
// its data-track value, else its id, else el<N>. Two elements with the same name are an error, never a silent overwrite.
//
// motion.json: { fps, duration, width, height, ids: [name...], frames: [ { t, <name>: { x, y, w, h, o, vis, sx, sy } } ] }
//   x, y      centre of the element in canvas pixels
//   w, h      its size in pixels
//   o         opacity of the element and its parents multiplied together
//   vis       o times the share of the element a viewer can see: a parent with overflow hidden (a text mask) clips it.
//             Speed x visibility is what moves the eye: a headline parked in a mask jumps between two hidden positions
//             and would otherwise read as thousands of px/s of motion.
//   sx, sy    scale, when the composition uses GSAP (1 otherwise): a line that draws by scaling shows nothing in x or y
import path from "node:path";
import { writeFileSync } from "node:fs";
import { fail, withComposition } from "./hfpage.mjs";
import { sampleMotion } from "./motion.mjs";

const args = process.argv.slice(2);
const flag = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : dflt; };
const proj = path.resolve(args[0] && !args[0].startsWith("--") ? args[0] : ".");
const fps = Number(flag("--fps", 30));
const out = path.resolve(flag("--out", path.join(proj, "motion.json")));
const selector = ["[data-anchor]", "[data-track]", flag("--select", "")].filter(Boolean).join(", ");
if (!(fps > 0)) { console.error("trace: --fps must be a positive number"); process.exit(2); }

const result = await withComposition(proj, "trace", async ({ page, state, errors }) => {
  const subErrs = errors.console.filter((e) => e.startsWith("[HyperFrames] composition script error"));
  const errs = [...new Set([...errors.script, ...subErrs])].map((e) => `script error: ${e}`);
  if (!state.ready) fail("the HyperFrames player never became ready, so nothing was traced", errs);
  if (errs.length) fail("the page threw script errors while loading (run finish.py check)", errs);
  if (!(state.duration > 0)) fail("the composition has zero duration, so there is nothing to trace");
  const rows = await sampleMotion(page, { selector, fps, duration: state.duration, members: 0 });
  if (!rows.length) fail("no element to trace: mark the elements that move with data-track (or data-anchor), or pass --select");
  return { duration: state.duration, size: state.size, rows };
});

const names = [], seen = new Set();
result.rows.forEach((r, i) => {
  const name = r.trackName || r.id || `el${i}`;
  if (seen.has(name)) { console.error(`trace: two tracked elements are named "${name}". Give each its own id or data-track.`); process.exit(1); }
  seen.add(name); names.push(name);
});
const n = result.rows[0].frames.length;
const frames = [];
for (let k = 0; k < n; k++) {
  const row = { t: result.rows[0].frames[k].t };
  result.rows.forEach((r, i) => { const { t, ...f } = r.frames[k]; row[names[i]] = f; });
  frames.push(row);
}
writeFileSync(out, JSON.stringify({ fps, duration: result.duration, width: result.size.width, height: result.size.height, ids: names, frames }));
console.log(`✓ trace: ${names.length} element(s), ${n} frames at ${fps} fps, ${result.duration.toFixed(2)} s -> ${out}`);
