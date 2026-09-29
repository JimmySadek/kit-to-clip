// Kit to Clip anchors check, the part that needs the browser: when does each element with data-anchor really start and
// stop moving? The composition is loaded the way HyperFrames renders it and every frame of the timeline is sampled
// (motion.mjs). What a data-at or data-start attribute says is only reported: the timeline is what plays.
// It fails, never passes, when it cannot check (player not ready, script errors, zero duration).
// Prints one line "@@anchors {json}" for finish.py, which compares the events with each anchor.
// Usage: node anchorscheck.mjs <project-dir> [fps]
import path from "node:path";
import { fail, withComposition } from "./hfpage.mjs";
import { motionEvents, sampleMotion } from "./motion.mjs";

const proj = path.resolve(process.argv[2] || ".");
const fps = Number(process.argv[3] || 30);
if (!(fps > 0)) { console.error("anchors check: fps must be a positive number"); process.exit(2); }

const out = await withComposition(proj, "anchors check", async ({ page, state, errors }) => {
  const subErrs = errors.console.filter((e) => e.startsWith("[HyperFrames] composition script error"));
  const errs = [...new Set([...errors.script, ...subErrs])].map((e) => `script error: ${e}`);
  if (!state.ready) fail("the HyperFrames player never became ready, so the timeline was not checked", errs);
  if (errs.length) fail("the page threw script errors while loading (run finish.py check)", errs);
  if (!(state.duration > 0)) fail("the composition has zero duration, so there is no timeline to sample");
  const rows = await sampleMotion(page, { selector: "[data-anchor]", fps, duration: state.duration, members: 12 });
  return { duration: state.duration, fps, rows: rows.map((r) => ({
    label: r.label, anchor: r.anchor, declared: r.declared, scope: r.scope,
    events: motionEvents(r.frames.map((f) => f.t), r.act).map((e) => ({ ...e, t: +e.t.toFixed(4) })) })) };
});
console.log("@@anchors " + JSON.stringify(out));
