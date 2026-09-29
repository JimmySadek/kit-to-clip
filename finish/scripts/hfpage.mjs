// Kit to Clip finish: open a HyperFrames composition the way HyperFrames previews and renders it. The project is served on
// localhost with the HyperFrames runtime in index.html's <head>, so data-composition-src sub-compositions load, their
// scripts run and the player knows the real duration. A page opened from file:// without the runtime loads none of
// that and makes checks pass on nothing.
import http from "node:http";
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { findRuntime, loadPuppeteer } from "./engine.mjs";

// a check that could not run, or found a problem, reported after Chrome and the server are closed
export class CheckFailed extends Error { constructor(msg, lines = []) { super(msg); this.lines = lines; } }
export const fail = (msg, lines = []) => { throw new CheckFailed(msg, lines); };

const RUNTIME_URL = "/__reel_finish_hf_runtime.js";
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
  ".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2", ".mp4": "video/mp4", ".webm": "video/webm",
  ".mov": "video/quicktime", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg" };

// serve the project like the HyperFrames file server: runtime injected into index.html, other files as they are.
// `missing` collects every project path the page asked for that is not on disk.
async function serve(proj, runtimePath) {
  const missing = new Set();
  const indexHtml = () => {
    const html = readFileSync(path.join(proj, "index.html"), "utf8")
      .replace(/<script\b[^>]*(hyperframe[.-]runtime|data-hyperframes-preview-runtime)[^>]*>\s*<\/script>/gi, "");
    // __hf.onSwallowed is the runtime's hook for errors it catches and hides (for example a timeline callback that
    // throws while seeking); keep them in window.__reelSwallowed
    const pre = "window.__timelines = window.__timelines || {}; window.__reelSwallowed = [];" +
      "window.__hf = Object.assign(window.__hf || {}, { onSwallowed: function (x) { var e = x && x.error;" +
      " window.__reelSwallowed.push(String(x && x.label) + ': ' + String(e && e.message || e)); } });";
    const tags = `<script>${pre}</script><script src="${RUNTIME_URL}"></script>\n`;
    if (/<\/head>/i.test(html)) return html.replace(/<\/head>/i, tags + "</head>");
    if (/<body/i.test(html)) return html.replace(/<body/i, tags + "<body");
    return tags + html;
  };
  const server = http.createServer((req, res) => {
    let rel;
    try { rel = decodeURIComponent((req.url || "/").split(/[?#]/)[0]).replace(/^\/+/, "") || "index.html"; }
    catch { res.writeHead(400); res.end(); return; }
    if ("/" + rel === RUNTIME_URL) { res.writeHead(200, { "content-type": TYPES[".js"] }); createReadStream(runtimePath).pipe(res); return; }
    if (rel === "index.html") { res.writeHead(200, { "content-type": TYPES[".html"] }); res.end(indexHtml()); return; }
    const file = path.resolve(proj, rel);
    const inside = !path.relative(proj, file).startsWith("..") && !path.isAbsolute(path.relative(proj, file));
    if (!inside || !existsSync(file) || !statSync(file).isFile()) {
      if (rel !== "favicon.ico") missing.add(rel);
      res.writeHead(404); res.end(); return;
    }
    // honour Range like HyperFrames does: without 206 answers, video and audio hold Chrome's six connections open and
    // the page never fires load
    const size = statSync(file).size;
    const headers = { "content-type": TYPES[path.extname(file).toLowerCase()] || "application/octet-stream", "accept-ranges": "bytes" };
    if (size === 0) { res.writeHead(200, { ...headers, "content-length": "0" }); res.end(); return; }
    const m = /^bytes=(\d*)-(\d*)$/.exec((req.headers.range || "").trim());
    let start = 0, end = size - 1, status = 200;
    if (m) {
      start = m[1] !== "" ? Number(m[1]) : Math.max(0, size - Number(m[2]));
      end = m[1] !== "" && m[2] !== "" ? Math.min(Number(m[2]), size - 1) : size - 1;
      if (start > end) { res.writeHead(416, { ...headers, "content-range": `bytes */${size}` }); res.end(); return; }
      status = 206;
      headers["content-range"] = `bytes ${start}-${end}/${size}`;
    }
    headers["content-length"] = String(end - start + 1);
    res.writeHead(status, headers);
    createReadStream(file, { start, end }).on("error", () => res.destroy()).pipe(res);
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const origin = `http://127.0.0.1:${server.address().port}`;
  return { origin, url: `${origin}/index.html`, missing, close: () => new Promise((r) => { server.close(() => r()); server.closeAllConnections(); }) };
}

// Load <proj>/index.html, wait for the HyperFrames player, then run check({ page, state, errors }) and close everything.
//   state:  ready, rootId, timelines, hosts, unmounted, playerDur, declared, duration, size
//   errors: script (uncaught), console (console.error), missing (local 404s), remote (requests off this machine)
// Exits 2 when node packages or the browser are missing. A CheckFailed thrown by check is printed as
// "✗ <label>: ..." with exit 1; otherwise returns what check returns.
export async function withComposition(proj, label, check) {
  const usage = (msg) => { console.error(`${label}: ${msg}`); process.exit(2); };
  if (!existsSync(path.join(proj, "index.html"))) usage(`no index.html in ${proj}`);
  const puppeteer = loadPuppeteer(proj), runtimePath = findRuntime(proj), exe = process.env.HYPERFRAMES_BROWSER_PATH;
  if (!puppeteer || !runtimePath) usage("puppeteer-core or hyperframes not found (in or above the project, or in the engine studio: $REEL_STUDIO, $REEL_STUDIO_HOME or ~/.kit-to-clip)");
  if (!exe || !existsSync(exe)) usage("set HYPERFRAMES_BROWSER_PATH (source env.sh)");

  const server = await serve(proj, runtimePath);
  const browser = await puppeteer.launch({ executablePath: exe, headless: true, args: ["--autoplay-policy=no-user-gesture-required", "--mute-audio"] });
  let result, failed;
  try {
    const page = await browser.newPage();
    const errors = { script: [], console: [], missing: server.missing, remote: [] };
    page.on("pageerror", (e) => errors.script.push(e.message.split("\n")[0]));
    // a local 404 is already in `missing` with its path; Chrome's own line for it adds nothing
    page.on("console", (m) => { if (m.type() === "error" && !m.text().startsWith("Failed to load resource")) errors.console.push(m.text()); });
    page.on("request", (r) => { const u = r.url(); if (/^https?:/.test(u) && !u.startsWith(server.origin)) errors.remote.push(u); });
    // size the viewport to the root composition, then load again (as `hyperframes inspect` does)
    await page.goto(server.url, { waitUntil: "domcontentloaded", timeout: 60000 });
    const size = await page.evaluate(() => {
      const r = document.querySelector("[data-composition-id][data-width][data-height]");
      const w = r ? parseInt(r.getAttribute("data-width"), 10) : 0, h = r ? parseInt(r.getAttribute("data-height"), 10) : 0;
      return { width: w > 0 ? Math.min(w, 4096) : 1920, height: h > 0 ? Math.min(h, 4096) : 1080 };
    });
    await page.setViewport(size);
    for (const list of [errors.script, errors.console, errors.remote]) list.length = 0;
    server.missing.clear();
    await page.goto(server.url, { waitUntil: "load", timeout: 60000 });
    // the runtime sets __renderReady once every timeline (root and sub-compositions) is bound
    const ready = await page.waitForFunction(
      () => window.__renderReady === true && window.__player && typeof window.__player.renderSeek === "function",
      { timeout: 30000, polling: 100 }).then(() => true, () => false);
    await page.evaluate(() => document.fonts.ready);
    const state = await page.evaluate(() => {
      const root = document.querySelector("[data-composition-id]");
      // the renderer's fallback when the timeline reports 0: root data-duration, else the last sub-composition end
      let declared = Number(root && root.getAttribute("data-duration")) || 0;
      const hosts = [...document.querySelectorAll("[data-composition-src]")];
      if (!declared) for (const h of hosts) declared = Math.max(declared, (Number(h.getAttribute("data-start")) || 0) + (Number(h.getAttribute("data-duration")) || 0));
      const p = window.__player;
      return {
        rootId: root ? root.getAttribute("data-composition-id") : null,
        playerDur: p && typeof p.getDuration === "function" ? Number(p.getDuration()) || 0 : 0,
        declared,
        timelines: Object.keys(window.__timelines || {}),
        hosts: hosts.length,
        unmounted: hosts.filter((h) => !h.querySelector("*")).map((h) => h.getAttribute("data-composition-src")),
      };
    });
    Object.assign(state, { ready, size, duration: state.playerDur > 0 ? state.playerDur : state.declared });
    // window.__reelVisible: what a viewer can see (shared by the safe-zone and first-three-seconds checks)
    await page.addScriptTag({ path: fileURLToPath(new URL("./visible.js", import.meta.url)) });
    result = await check({ page, state, errors });
  } catch (e) {
    if (!(e instanceof CheckFailed)) throw e;
    failed = e;
  } finally {
    await browser.close();
    await server.close();
  }
  if (failed) {
    console.log(`✗ ${label}: ${failed.message}`);
    for (const l of failed.lines) console.log("  - " + l);
    process.exit(1);
  }
  return result;
}
