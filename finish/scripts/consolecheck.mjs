// Kit to Clip console check: open a HyperFrames composition the way HyperFrames previews and renders it (served with
// the runtime, see hfpage.mjs) and fail on problems lint misses: script errors in index.html (e.g. a top-level
// `const top` clashing with window.top) or in any sub-composition, console errors, missing local files, requests that
// leave this machine, a sub-composition that does not load, a root timeline that never registers, zero duration,
// and errors while seeking, including those the runtime catches and hides. Usage: node consolecheck.mjs <project-dir>
import path from "node:path";
import { fail, withComposition } from "./hfpage.mjs";

const proj = path.resolve(process.argv[2] || ".");
const state = await withComposition(proj, "console check", async ({ page, state, errors }) => {
  await new Promise((r) => setTimeout(r, 1500)); // let timers and first frames throw
  const rootOk = state.ready && state.rootId && state.timelines.includes(state.rootId);
  // seek the whole film with the player, every 0.5 s and the last frame; uncaught errors land in errors.script
  const seekErr = rootOk && state.duration > 0 ? await page.evaluate(async (duration) => {
    const seek = async (t) => {
      await window.__player.renderSeek(t);
      if (typeof window.__hfWaitForSeekCompletion === "function") await window.__hfWaitForSeekCompletion();
    };
    try { for (let t = 0; t < duration; t += 0.5) await seek(t); await seek(Math.max(0, duration - 0.001)); return null; }
    catch (e) { return String(e); }
  }, state.duration) : null;
  // errors the runtime caught and hid, for example a timeline callback that throws during a seek (see hfpage.mjs)
  const hidden = await page.evaluate(() => window.__reelSwallowed || []);

  const problems = [
    ...errors.script.map((e) => `script error: ${e}`),
    ...errors.console.map((e) => `console error: ${e}`),
    ...[...errors.missing].map((f) => `missing file: ${path.join(proj, f)}`),
    ...errors.remote.map((u) => `network request at load: ${u}`),
  ];
  if (!state.rootId) problems.push("no element with data-composition-id in index.html");
  else if (!state.timelines.includes(state.rootId)) problems.push(`timeline "${state.rootId}" not registered on window.__timelines (found: ${state.timelines.join(", ") || "none"})`);
  if (!state.ready) problems.push("the HyperFrames player never became ready, so the composition did not load");
  for (const src of state.unmounted) problems.push(`sub-composition did not load: ${src}`);
  if (rootOk && !(state.duration > 0)) problems.push("the composition has zero duration");
  if (seekErr) problems.push(`error while seeking the timeline: ${seekErr}`);
  for (const h of hidden) problems.push(`error hidden by the HyperFrames runtime: ${h}`);
  const seen = [...new Set(problems)];
  if (seen.length) fail(`${seen.length} problem(s)`, seen);
  return state;
});
const dur = state.playerDur > 0 ? `${state.playerDur.toFixed(2)} s` : `timeline 0 s, renders ${state.declared.toFixed(2)} s from data-duration`;
const subs = state.hosts ? `, ${state.hosts} sub-composition(s) loaded` : "";
console.log(`✓ console check: no script errors, all local files load, timeline "${state.rootId}" registered (${dur}${subs}) and seeks cleanly`);
