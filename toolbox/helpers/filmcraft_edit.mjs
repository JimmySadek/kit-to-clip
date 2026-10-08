#!/usr/bin/env node
// Frame-exact edits with FilmCraft, from a plain edit list: segments of the source clip in order, each at its own speed,
// with frame holds between them. Exports an H.264 file (exact range, bitrate, loudness) and, if asked, an FCPXML timeline
// an editor can open and re-cut by hand.
//   node filmcraft_edit.mjs <filmcraft-cli> <spec.json>
// spec: {"clip": "/abs/source.mp4", "out": "/abs/out.mp4", "fcpxml": "/abs/out.fcpxml" (optional),
//        "edits": [{"from": 0, "to": 1.6667}, {"hold": 2.4}, {"from": 1.6667, "to": 3.5, "speed": 1.3093}, ...],
//        "bitrateKbps": 8000, "loudnessLufs": -14}
// A hold freezes the first frame of the segment that follows it. Times are source seconds. Recipe: toolbox/recipes/filmcraft.md
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";

const [cli, specPath] = process.argv.slice(2);
if (!cli || !specPath) {
  console.error("usage: node filmcraft_edit.mjs <filmcraft-cli> <spec.json>");
  process.exit(2);
}
const spec = JSON.parse(readFileSync(specPath, "utf8"));
const TICK = 254016000000;                       // FilmCraft ticks per second
const tk = (s) => Math.round(s * TICK);

const proc = spawn(cli, ["--empty", "mcp"], { stdio: ["pipe", "pipe", "inherit"] });
let id = 0, buf = "";
const waits = new Map();
proc.stdout.on("data", (d) => {
  buf += d;
  let i;
  while ((i = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, i);
    buf = buf.slice(i + 1);
    try { const m = JSON.parse(line); waits.get(m.id)?.(m); waits.delete(m.id); } catch { /* not a message */ }
  }
});
const rpc = (method, params) => new Promise((res) => { const n = ++id; waits.set(n, res); proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: n, method, params }) + "\n"); });
async function tool(name, args) {
  const r = await rpc("tools/call", { name, arguments: args });
  const text = (r.result?.content || []).map((c) => c.text || "").join("");
  let json; try { json = JSON.parse(text); } catch { json = text; }
  if (r.result?.isError) throw new Error(`${name} ${JSON.stringify(args).slice(0, 120)}: ${text.slice(0, 300)}`);
  return json;
}
const run = (id_, params) => tool("command_run", { id: id_, params });
const clips = async () => (await tool("sequence_inspect", {})).video[0].items;

try {
  await rpc("initialize", { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "kit-to-clip", version: "1" } });
  proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");
  const imported = await tool("media_import", { text: spec.clip });
  const item = imported.items?.[0];
  if (!item) throw new Error(`could not import ${spec.clip}: ${JSON.stringify(imported.errors)}`);
  await run("project.select", { items: [item] });
  await run("file.newSequenceFromClip", { items: [item] });

  // 1. cut the untouched source at every segment boundary (sequence time == source time before any edit)
  const segs = spec.edits.filter((e) => e.hold === undefined);
  const cuts = [...new Set(segs.flatMap((s) => [s.from, s.to]))].filter((t) => t > 0).sort((a, b) => a - b);
  for (const t of cuts) await run("timeline.razor", { time: tk(t), track: "V1" });
  const pieces = await clips();
  const pieceAt = (t) => pieces.find((c) => Math.abs(c.sourceIn / TICK - t) < 0.5 / 30);
  // which source pieces we keep, in order, and which get a hold in front of them
  const plan = [];
  let holdNext = null;
  for (const e of spec.edits) {
    if (e.hold !== undefined) { holdNext = e.hold; continue; }
    const piece = pieceAt(e.from);
    if (!piece) throw new Error(`no piece starts at ${e.from} s`);
    plan.push({ clip: piece.clip, speed: e.speed || 1, hold: holdNext, from: e.from, to: e.to });
    holdNext = null;
  }
  // 2. holds first, last first, at the exact start tick of their piece (after a speed change starts land between frames)
  for (const p of [...plan].reverse()) {
    if (!p.hold) continue;
    const c = (await clips()).find((x) => x.clip === p.clip);
    await run("clip.insertFrameHoldSegment", { clip: p.clip, time: c.start, seconds: p.hold });
  }
  // 3. speed ramps: select the piece first, ripple the rest of the timeline
  for (const p of plan) {
    if (p.speed === 1) continue;
    await run("timeline.select", { clips: [p.clip] });
    await run("clip.speedDuration", { clips: [p.clip], speed: Math.round(p.speed * 10000) / 100, ripple: true });
  }
  // 4. the kept length: segments at their speed plus the holds (FilmCraft keeps the old sequence length, so set the range)
  const total = plan.reduce((sum, p) => sum + (p.to - p.from) / p.speed + (p.hold || 0), 0);
  const firstStart = plan[0].from;
  if (firstStart > 0) throw new Error("the first segment must start at 0 s (trim the clip first)");
  const exp = await run("file.exportMedia", { path: spec.out, format: "h264", range: "custom", startSeconds: 0, endSeconds: Math.round(total * 1000) / 1000,
    bitrateKbps: spec.bitrateKbps || 8000, bitrateMode: "vbr1Pass", ...(spec.loudnessLufs ? { loudnessLufs: spec.loudnessLufs } : {}), wait: true });
  if (spec.fcpxml) await run("file.exportFcpxml", { path: spec.fcpxml });
  console.log(JSON.stringify({ ok: true, out: spec.out, seconds: Math.round(total * 1000) / 1000, frames: exp?.result?.frames,
    fcpxml: spec.fcpxml || null, plan: plan.map((p) => ({ from: p.from, to: p.to, speed: p.speed, hold: p.hold })) }));
  proc.stdin.end();
  setTimeout(() => process.exit(0), 300);
} catch (error) {
  console.error(`filmcraft_edit: ${error.message}`);
  proc.kill();
  process.exit(1);
}
