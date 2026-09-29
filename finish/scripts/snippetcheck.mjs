// Kit to Clip snippet check: open a live snippet folder (finish.py snippet) as a plain web page, the way a website
// would embed it: no HyperFrames runtime, no local server. Fails on script errors, requests that leave the machine,
// no timeline, a timeline that does not advance, or motion that keeps playing when the viewer asks for reduced motion.
// Usage: node snippetcheck.mjs <snippet-dir>
import path from "node:path";
import { existsSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { loadPuppeteer } from "./engine.mjs";

const dir = path.resolve(process.argv[2] || ".");
const index = path.join(dir, "index.html");
if (!existsSync(index)) { console.error(`snippet check: no index.html in ${dir}`); process.exit(2); }
const puppeteer = loadPuppeteer(dir), exe = process.env.HYPERFRAMES_BROWSER_PATH;
if (!puppeteer || !exe || !existsSync(exe)) { console.error("snippet check: puppeteer-core or Chrome not found (source env.sh)"); process.exit(2); }

const browser = await puppeteer.launch({ executablePath: exe, headless: true, args: ["--allow-file-access-from-files"] });
const bad = [], good = [];
try {
  for (const reduced of [false, true]) {
    const page = await browser.newPage();
    const errs = [], remote = [];
    page.on("pageerror", (e) => errs.push(e.message.split("\n")[0]));
    page.on("request", (r) => { if (/^https?:/.test(r.url())) remote.push(r.url()); });
    await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: reduced ? "reduce" : "no-preference" }]);
    await page.goto(pathToFileURL(index).href, { waitUntil: "load", timeout: 60000 });
    await page.waitForFunction(() => window.__reelSnippet, { timeout: 5000 }).catch(() => {});
    const times = async () => page.evaluate(() => Object.values(window.__timelines || {}).map((t) => t.totalTime()));
    const a = await times();
    await new Promise((r) => setTimeout(r, 700));
    const b = await times();
    const label = reduced ? "reduced motion" : "playing";
    if (errs.length) bad.push(`${label}: script errors: ${errs.join("; ")}`);
    if (remote.length) bad.push(`${label}: requests off this machine: ${remote.slice(0, 3).join(", ")}`);
    if (!a.length) bad.push(`${label}: no timeline registered in window.__timelines`);
    const advanced = b.some((t, i) => t > (a[i] ?? 0) + 0.2);
    if (!reduced && a.length && !advanced) bad.push("the timeline does not advance: the snippet does not play");
    if (reduced && advanced) bad.push("it keeps moving when the viewer asks for reduced motion");
    if (!reduced && advanced) good.push(`plays and loops (${a.length} timeline(s))`);
    if (reduced && a.length && !advanced) good.push("holds still for reduced motion");
    await page.close();
  }
} finally {
  await browser.close();
}
if (bad.length) {
  console.log(`✗ snippet check: ${bad.length} problem(s) in ${dir}`);
  for (const b of bad) console.log("  - " + b);
  process.exit(1);
}
console.log(`✓ snippet check: ${good.join("; ")} (${dir})`);
