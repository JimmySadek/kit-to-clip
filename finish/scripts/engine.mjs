// Kit to Clip finish: find the HyperFrames engine packages (puppeteer-core, hyperframes) for the node checks.
// Looks in node_modules in or above the project, then above the current folder, then in the engine studio
// ($REEL_STUDIO, $REEL_STUDIO_HOME, the studio these skills were installed from, ~/.kit-to-clip), so a project
// outside the studio folder is still checked.
import { createRequire } from "node:module";
import { existsSync, realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import os from "node:os";
import path from "node:path";

function* roots(proj) {
  for (const start of [proj, process.cwd()]) {
    for (let dir = path.resolve(start); ; dir = path.dirname(dir)) {
      yield dir;
      if (path.dirname(dir) === dir) break;
    }
  }
  // this file is <studio>/.claude/skills/kit-to-clip/finish/scripts/engine.mjs in an installed studio
  const own = path.resolve(path.dirname(realpathSync(fileURLToPath(import.meta.url))), "../../../../..");
  for (const s of [process.env.REEL_STUDIO, process.env.REEL_STUDIO_HOME, own, path.join(os.homedir(), ".kit-to-clip")]) {
    if (s) yield path.resolve(s);
  }
}

// folder of an installed package, or null
export function findPackage(name, proj) {
  for (const dir of roots(proj)) {
    const pkg = path.join(dir, "node_modules", name, "package.json");
    if (existsSync(pkg)) return path.dirname(pkg);
  }
  return null;
}

export function loadPuppeteer(proj) {
  const dir = findPackage("puppeteer-core", proj);
  return dir ? createRequire(path.join(dir, "package.json"))("puppeteer-core") : null;
}

// the runtime HyperFrames injects into index.html when it previews and renders
export function findRuntime(proj) {
  const dir = findPackage("hyperframes", proj);
  if (!dir) return null;
  return ["hyperframe.runtime.iife.js", "hyperframe-runtime.js"].map((f) => path.join(dir, "dist", f)).find(existsSync) || null;
}
