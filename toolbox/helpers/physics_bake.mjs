#!/usr/bin/env node
// Bake a 2D physics scene once with Rapier, so a video can play it back seekably.
//
//   node physics_bake.mjs <spec.json> <out.json | out.js> [--rapier <path to rapier.mjs>]
//
// An out path ending in .js writes `window.__physics = {...};` instead, so the page loads it with a <script> tag and
// nothing is fetched at render time.
//
// spec: {width, height, fps, duration, gravity (px/s², down), substeps (default 4), scale (px per metre, default 100),
//        walls: true (floor + left + right walls at the frame edges), bodies: [{shape: "box"|"ball", size (box: side or
//        [w, h]; ball: diameter, px), x, y (centre, px, y down), vx, vy (px/s), angle (radians), spin (rad/s),
//        restitution, friction, density, plus any keys of yours such as color}]}
// out:  {fps, width, height, duration, count, bodies: [{shape, size, ...your keys}],
//        frames: [[{x, y, angle}, ...one per body], ...one per frame]}
//       frames[0] is t = 0; frame i is t = i / fps. Angles are radians, clockwise on screen (CSS rotate()).
//
// Deterministic: a fixed step of 1/fps split into substeps, no clock, no randomness, values rounded. The same spec on
// the same Rapier version gives the same file. Rapier comes from the toolbox (toolbox.py path rapier module) unless
// --rapier or KIT_TO_CLIP_RAPIER names it.
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const args = process.argv.slice(2);
const flag = args.indexOf("--rapier");
const rapierArg = flag >= 0 ? args.splice(flag, 2)[1] : null;
const [specPath, outPath] = args;
if (!specPath || !outPath) {
  console.error("usage: node physics_bake.mjs <spec.json> <out.json|out.js> [--rapier <rapier.mjs>]");
  process.exit(2);
}

function rapierPath() {
  if (rapierArg) return rapierArg;
  if (process.env.KIT_TO_CLIP_RAPIER) return process.env.KIT_TO_CLIP_RAPIER;
  const toolbox = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "scripts", "toolbox.py");
  try {
    return execFileSync("python3", [toolbox, "path", "rapier", "module"], { encoding: "utf8" }).trim();
  } catch {
    console.error("❌ Rapier is not installed: python3 <kit-to-clip>/scripts/toolbox.py install rapier (after a ✋ yes)");
    process.exit(3);
  }
}

const mod = await import(pathToFileURL(resolve(rapierPath())).href);
const RAPIER = mod.default ?? mod;
await RAPIER.init();

const spec = JSON.parse(readFileSync(specPath, "utf8"));
const W = spec.width ?? 1080, H = spec.height ?? 1080, fps = spec.fps ?? 30, duration = spec.duration ?? 3;
const S = spec.scale ?? 100; // px per metre: Rapier is tuned for metre-sized bodies
const substeps = Math.max(1, Math.round(spec.substeps ?? 4));
const m = (px) => px / S;
const round = (v, d) => Math.round(v * 10 ** d) / 10 ** d;

const world = new RAPIER.World({ x: 0, y: m(spec.gravity ?? 1800) });
world.timestep = 1 / fps / substeps;

if (spec.walls !== false) {
  const t = m(200); // thick walls, so fast bodies never tunnel through
  const wall = (cx, cy, hx, hy) =>
    world.createCollider(RAPIER.ColliderDesc.cuboid(hx, hy).setTranslation(cx, cy).setFriction(0.6));
  wall(m(W / 2), m(H) + t, m(W) + t, t); // floor
  wall(-t, m(H / 2) - m(H), t, m(H) * 2); // left, tall enough for bodies dropped from above
  wall(m(W) + t, m(H / 2) - m(H), t, m(H) * 2); // right
}

const bodies = (spec.bodies ?? []).map((b) => {
  const desc = RAPIER.RigidBodyDesc.dynamic()
    .setTranslation(m(b.x ?? W / 2), m(b.y ?? 0))
    .setRotation(b.angle ?? 0)
    .setLinvel(m(b.vx ?? 0), m(b.vy ?? 0))
    .setAngvel(b.spin ?? 0)
    .setCcdEnabled(true);
  const body = world.createRigidBody(desc);
  const size = b.size ?? 80;
  const [w, h] = Array.isArray(size) ? size : [size, size];
  const shape = b.shape === "ball" || b.shape === "circle"
    ? RAPIER.ColliderDesc.ball(m(w / 2))
    : RAPIER.ColliderDesc.cuboid(m(w / 2), m(h / 2));
  shape.setRestitution(b.restitution ?? 0.3).setFriction(b.friction ?? 0.6).setDensity(b.density ?? 1);
  world.createCollider(shape, body);
  return body;
});

const snap = () => bodies.map((body) => {
  const p = body.translation();
  return { x: round(p.x * S, 2), y: round(p.y * S, 2), angle: round(body.rotation(), 4) };
});

const count = Math.round(duration * fps) + 1;
const frames = [snap()];
for (let i = 1; i < count; i++) {
  for (let s = 0; s < substeps; s++) world.step();
  frames.push(snap());
}
world.free();

const PHYSICS = ["x", "y", "vx", "vy", "angle", "spin", "restitution", "friction", "density"];
const looks = (spec.bodies ?? []).map((b) => Object.fromEntries(Object.entries(b).filter(([k]) => !PHYSICS.includes(k))));
const json = JSON.stringify({ fps, width: W, height: H, duration, count, bodies: looks, frames });
writeFileSync(outPath, outPath.endsWith(".js") ? `window.__physics = ${json};\n` : json);
console.log(`✅ baked ${bodies.length} bodies, ${count} frames at ${fps} fps → ${outPath}`);
