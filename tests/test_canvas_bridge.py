"""Canvas bridge: time-driven Canvas2D drawings on the existing HyperFrames engine, and honest Canvas audits in finish.py.

Behaviour tests on tiny synthetic fixtures (geometry and text only), run in the installed engine's headless Chrome through
the existing finish probes (hfpage.mjs). The engine is found the way env.sh finds it; a missing engine, browser or node
is an error, never a skip.

  python3 -m unittest discover -s tests -p test_canvas_bridge.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO if (REPO / "SKILL.md").is_file() else REPO / "addons" / "kit-to-clip"  # public repo = the skill / workshop
SCRIPTS = SKILL / "finish" / "scripts"
FINISH = SCRIPTS / "finish.py"
BRIDGE = SCRIPTS / "canvas-bridge.js"
HFPAGE = SCRIPTS / "hfpage.mjs"
ENV_SH = SKILL / "scripts" / "env.sh"

# 1080x1920 page, canvas backing store at half resolution: label boxes must be mapped from canvas pixels to the page
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><script src="vendor/gsap.min.js"></script>{bridge_tag}
<style>html, body {{ width: 1080px; height: 1920px; margin: 0; overflow: hidden; background: #111; }}
#root {{ position: relative; width: 100%; height: 100%; }}
canvas {{ position: absolute; left: 0; top: 0; width: 1080px; height: 1920px; }}</style></head>
<body><div id="root" data-composition-id="t" data-start="0" data-width="1080" data-height="1920" data-duration="{dur}">
{body}
</div><script>{js}</script></body></html>
"""
CANVAS = '<canvas id="c" width="540" height="960" data-k2c-canvas></canvas>'
BRIDGE_TAG = '<script src="canvas-bridge.js"></script>'

# a moving square, a moving measured label and a declared logo region drawn as a path; everything inside TikTok's box
GOOD_DRAW = """
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.fillStyle = "#1d2b53"; ctx.fillRect(0, 0, 540, 960);
    ctx.fillStyle = "#ff004d"; ctx.fillRect(80 + 120 * t, 200, 60, 60);
    ctx.fillStyle = "#ffffff"; ctx.font = "bold 48px sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    ctx.fillText(LABEL, 90 + 40 * t, LABEL_Y);
    ctx.save(); ctx.translate(200, 520); ctx.beginPath(); ctx.arc(30, 30, 30, 0, Math.PI * 2); ctx.fill();
    audit.region("mark", 0, 0, 60, 60, { kind: "logo" }); ctx.restore();
"""


ROOT_TL = 'window.__timelines["t"] = gsap.timeline({ paused: true });'   # the standard registration, visible to lint
FLIP_DRAW = 'ctx.fillStyle = t < 0.5 ? "#ff0000" : "#0000ff"; ctx.fillRect(0, 0, 160, 90);'

# a sub-composition file with its own bridge: red before its local 0.5 s, blue after
SUB_SCENE = """<template id="scene-template">
<div data-composition-id="scene" data-start="0" data-duration="1" data-width="1080" data-height="1920">
<canvas id="sub-c" width="540" height="960" data-k2c-canvas style="position:absolute;inset:0;width:100%;height:100%"></canvas>
<script>
window.__timelines["scene"] = gsap.timeline({ paused: true });
KitToClipCanvas.register({ id: "sub", canvas: document.getElementById("sub-c"), duration: 1, labels: "none",
  draw(ctx, t) { ctx.fillStyle = t < 0.5 ? "#ff0000" : "#0000ff"; ctx.fillRect(0, 0, 540, 960); } });
</script>
</div>
</template>
"""


def scene_js(label="HELLO", label_y=400, draw=GOOD_DRAW, extra_opts="", before="", after="", root=True):
    return ((ROOT_TL + "\n" if root else "") + f'const LABEL = {json.dumps(label)}, LABEL_Y = {label_y};\nconst canvas = document.getElementById("c");\n{before}\n'
            f'KitToClipCanvas.register({{ id: "scene", canvas, duration: 2, ready: document.fonts.ready{extra_opts},\n'
            f'  draw(ctx, t, audit) {{ {draw} }} }});\n{after}')


PROBE = r"""
const { withComposition } = await import(process.env.K2C_HFPAGE_URL);
const [proj, mode] = process.argv.slice(2);
const HASH = (c) => { const d = new Uint32Array(c.getContext("2d").getImageData(0, 0, c.width, c.height).data.buffer);
  let h = 0x811c9dc5; for (let i = 0; i < d.length; i++) { h ^= d[i]; h = Math.imul(h, 0x01000193); } return h >>> 0; };
const out = await withComposition(proj, "probe", async ({ page, state, errors }) => {
  if (mode === "aba") {
    const res = await page.evaluate(async (hashSrc) => {
      const hash = (0, eval)(hashSrc), c = document.getElementById("c"), V = window.__reelVisible;
      const b = window.KitToClipCanvas.list()[0];
      const at = async (t) => { await V.seek(t); return { t, runtime: window.__hfThreeTime, hash: hash(c), frame: b.frame() }; };
      return [await at(0.5), await at(1.5), await at(0.5)];
    }, HASH.toString());
    return { res, errors: { script: errors.script, console: errors.console } };
  }
  if (mode === "audited") {        // the finish audit's view: fingerprints and painted-pixel evidence on, then one seek
    const res = await page.evaluate(async () => {
      window.KitToClipCanvas.audit.enable();
      await window.__reelVisible.seek(0.5);
      const c = document.getElementById("c");
      return { width: c.width, height: c.height, frame: window.KitToClipCanvas.list()[0].frame() };
    });
    return { res, errors: { script: errors.script, console: errors.console } };
  }
  if (mode === "nested") {
    const res = await page.evaluate(() => {
      const draw = (ctx, t) => { ctx.fillRect(0, 0, 10 + t, 10); };
      try { window.KitToClipCanvas.register({ id: "inner", canvas: document.getElementById("inner-c"), duration: 1, draw }); return null; }
      catch (e) { return `${e.name}: ${e.message}`; }
    });
    return { res, registered: await page.evaluate(() => window.KitToClipCanvas.list().length) };
  }
  if (mode === "api") {
    const client = await page.createCDPSession();
    const count = async () => {
      const { result } = await client.send("Runtime.evaluate", { expression: "window" });
      const { listeners } = await client.send("DOMDebugger.getEventListeners", { objectId: result.objectId });
      return listeners.filter((l) => l.type === "hf-seek").length;
    };
    const base = await count();
    const refusals = await page.evaluate(() => {
      const c1 = document.getElementById("c1");
      const draw = (ctx, t) => { ctx.fillRect(0, 0, 10 + t, 10); };
      const tryReg = (o) => { try { window.KitToClipCanvas.register(o); return null; } catch (e) { return `${e.name}: ${e.message}`; } };
      const out = {};
      for (const [k, d] of [["nan", NaN], ["inf", Infinity], ["zero", 0], ["neg", -1], ["string", "2"], ["missing", undefined]])
        out["duration_" + k] = tryReg({ id: "bad", canvas: c1, duration: d, draw });
      out.no_draw = tryReg({ id: "bad", canvas: c1, duration: 1 });
      out.not_canvas = tryReg({ id: "bad", canvas: document.body, duration: 1, draw });
      out.longer_than_root = tryReg({ id: "bad", canvas: c1, duration: 5, draw });
      out.unknown_option = tryReg({ id: "bad", canvas: c1, duration: 1, draw, timeline: "create" });
      out.registered = window.KitToClipCanvas.list().length;
      return out;
    });
    const afterRefusals = await count();
    const regs = await page.evaluate(() => {
      const [c1, c2, c3] = ["c1", "c2", "c3"].map((id) => document.getElementById(id));
      const draw = (ctx, t) => { ctx.fillRect(0, 0, 10 + t, 10); };
      const tryReg = (o) => { try { window.KitToClipCanvas.register(o); return null; } catch (e) { return `${e.name}: ${e.message}`; } };
      const out = {};
      out.first = tryReg({ id: "a", canvas: c1, duration: 1, draw });
      out.dup_id = tryReg({ id: "a", canvas: c2, duration: 1, draw });
      out.dup_canvas = tryReg({ id: "b", canvas: c1, duration: 1, draw });
      out.second = tryReg({ id: "b", canvas: c2, duration: 1, draw });
      out.ids = window.KitToClipCanvas.list().map((b) => b.id);
      out.root_timeline_kept = window.__timelines.t === window.__ownRoot;
      return out;
    });
    const withTwo = await count();
    await page.evaluate(() => window.KitToClipCanvas.list().forEach((b) => b.dispose()));
    const afterDispose = await count();
    const reuse = await page.evaluate(() => {
      window.KitToClipCanvas.register({ id: "a", canvas: document.getElementById("c1"), duration: 1, draw: (ctx) => ctx.fillRect(0, 0, 1, 1) });
      const n = window.KitToClipCanvas.list().length;
      window.KitToClipCanvas.list().forEach((b) => b.dispose());
      return n;
    });
    return { base, afterRefusals, withTwo, afterDispose, refusals, regs, reuse };
  }
  throw new Error("unknown probe mode " + mode);
});
console.log("@@probe " + JSON.stringify(out));
"""


def engine_env(cwd):
    """The environment env.sh gives engine commands, plus a private TMPDIR so browser profiles stay in our temp dir."""
    r = subprocess.run(["bash", "-c", 'source "$1" >/dev/null 2>&1; env -0', "_", str(ENV_SH)], cwd=cwd, capture_output=True)
    env = dict(kv.split("=", 1) for kv in r.stdout.decode().split("\0") if "=" in kv)
    studio = Path(env.get("REEL_STUDIO", ""))
    need = [studio / "node_modules" / p for p in ("gsap/dist/gsap.min.js", "puppeteer-core/package.json", "hyperframes/package.json")]
    missing = [str(p) for p in need if not p.is_file()]
    browser = env.get("HYPERFRAMES_BROWSER_PATH", "")
    if missing or not env.get("REEL_STUDIO"):
        raise RuntimeError(f"requirement unavailable: engine packages not found after env.sh (REEL_STUDIO={studio}): {missing}")
    if not browser or not Path(browser).is_file() or "/Applications/Google Chrome.app" in browser:
        raise RuntimeError(f"requirement unavailable: no engine headless browser after env.sh (HYPERFRAMES_BROWSER_PATH={browser!r})")
    if not shutil.which("node", path=env.get("PATH")):
        raise RuntimeError("requirement unavailable: node is not on the engine PATH after env.sh")
    return env, studio


class CanvasBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="k2c-canvas-tests-"))
        try:
            cls.env, cls.studio = engine_env(cls.base)
        except Exception:
            shutil.rmtree(cls.base, ignore_errors=True)
            raise
        (cls.base / "tmp").mkdir()
        cls.env["TMPDIR"] = str(cls.base / "tmp")
        cls.env["K2C_HFPAGE_URL"] = HFPAGE.as_uri()
        cls.gsap = cls.studio / "node_modules" / "gsap" / "dist" / "gsap.min.js"
        cls.probe = cls.base / "probe-script" / "probe.mjs"
        cls.probe.parent.mkdir()
        cls.probe.write_text(PROBE)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    # ------------------------------------------------------------ helpers
    def project(self, name, js, body=CANVAS, bridge=True, dur=2):
        d = self.base / "proj" / name
        if d.exists():
            return d
        (d / "vendor").mkdir(parents=True)
        shutil.copy2(self.gsap, d / "vendor" / "gsap.min.js")
        if bridge and BRIDGE.is_file():          # before the bridge exists the page simply lacks it: behaviour fails, not setup
            shutil.copy2(BRIDGE, d / "canvas-bridge.js")
        (d / "index.html").write_text(PAGE.format(bridge_tag=BRIDGE_TAG if bridge else "", dur=dur, body=body, js=js))
        return d

    def fin(self, *args):
        r = subprocess.run([sys.executable, str(FINISH), *args], capture_output=True, text=True, cwd=self.base, env=self.env, timeout=300)
        return r.returncode, r.stdout + r.stderr

    def run_probe(self, proj, mode):
        r = subprocess.run(["node", str(self.probe), str(proj), mode], capture_output=True, text=True, cwd=self.base, env=self.env, timeout=300)
        line = next((ln for ln in r.stdout.splitlines() if ln.startswith("@@probe ")), None)
        self.assertIsNotNone(line, f"probe produced no result (exit {r.returncode}):\n{r.stdout}\n{r.stderr}")
        return json.loads(line[len("@@probe "):])

    def assertRun(self, got, code, *texts, absent=()):
        rc, out = got
        self.assertEqual(rc, code, f"exit {rc}, wanted {code}:\n{out}")
        for t in texts:
            self.assertIn(t, out, f"wanted {t!r} in:\n{out}")
        for t in absent:
            self.assertNotIn(t, out, f"did not want {t!r} in:\n{out}")

    # ------------------------------------------------------------ seeking
    def test_seek_a_b_a_is_identical_and_metadata_describes_the_sampled_frame(self):
        res = self.run_probe(self.project("good", scene_js()), "aba")
        a1, b, a2 = res["res"]
        self.assertEqual(res["errors"], {"script": [], "console": []})
        self.assertEqual(a1["hash"], a2["hash"], "seeking back to 0.5 s must redraw exactly the same pixels")
        self.assertNotEqual(a1["hash"], b["hash"], "1.5 s must differ from 0.5 s (the square and the label move)")
        for row in (a1, b, a2):
            f = row["frame"]
            self.assertAlmostEqual(row["runtime"], row["t"], places=6)
            self.assertAlmostEqual(f["time"], row["t"], places=6, msg="frame metadata must be for the sampled time")
            self.assertIsNone(f["error"])
        self.assertLess(a1["frame"]["seq"], b["frame"]["seq"])
        self.assertLess(b["frame"]["seq"], a2["frame"]["seq"])
        lab = lambda f, name: next(x for x in f["labels"] if x["text"] == name)
        hello_a, hello_b = lab(a1["frame"], "HELLO"), lab(b["frame"], "HELLO")
        self.assertEqual(hello_a["source"], "measured")
        self.assertAlmostEqual(hello_b["rect"][0] - hello_a["rect"][0], 40, delta=1.0, msg="label box follows the draw at each time")
        self.assertLess(hello_a["rect"][1], 400)
        self.assertGreaterEqual(hello_a["rect"][3], 395)
        mark = lab(a1["frame"], "mark")
        self.assertEqual((mark["source"], mark["kind"]), ("declared", "logo"))
        self.assertEqual([round(v) for v in mark["rect"]], [200, 520, 260, 580])
        self.assertEqual(a1["frame"]["labels"], a2["frame"]["labels"])

    # ------------------------------------------------------------ the gates on a valid Canvas
    def test_valid_canvas_passes_console_safe_and_hook(self):
        p = self.project("good", scene_js())
        self.assertRun(self.fin("check", "--project", str(p)), 0, "✓ console check", "✓ canvas audit")
        self.assertRun(self.fin("safe", "--project", str(p), "--platform", "tiktok"), 0, "✓ safe check (canvas)", "stay inside",
                       "1 measured text", "1 declared region")
        self.assertRun(self.fin("hook", "--project", str(p)), 0, "✓ hook check", "canvas text \"HELLO\"", "canvas pixels")

    def test_the_guide_example_runs_and_passes(self):
        guide = (SKILL / "references" / "canvas-reference.md").read_text()
        html = guide.split("```html\n", 1)[1].split("```", 1)[0]
        d = self.base / "proj" / "guide"
        (d / "vendor").mkdir(parents=True)
        shutil.copy2(self.gsap, d / "vendor" / "gsap.min.js")
        shutil.copy2(BRIDGE, d / "canvas-bridge.js")
        (d / "index.html").write_text("<!doctype html>\n<html lang=\"en\">\n" + html + "</html>\n")
        self.assertRun(self.fin("check", "--project", str(d)), 0, "✓ console check", "✓ canvas audit", "redrawn identically")
        self.assertRun(self.fin("safe", "--project", str(d), "--platform", "tiktok"), 0, "1 measured text", "1 declared region")
        self.assertRun(self.fin("hook", "--project", str(d)), 0, 'canvas text "Launch day"')

    def test_label_outside_the_safe_box_fails(self):
        p = self.project("bottom", scene_js(label="BOTTOM", label_y=900))
        self.assertRun(self.fin("safe", "--project", str(p), "--platform", "tiktok"), 1, "✗ safe check (canvas)", "BOTTOM", "bottom by")

    # ------------------------------------------------------------ audits that must fail
    def test_marked_canvas_without_a_bridge_fails(self):
        js = 'window.__timelines["t"] = gsap.timeline({ paused: true }); const c = document.getElementById("c").getContext("2d");' \
             ' c.fillStyle = "#fff"; c.font = "bold 48px sans-serif"; c.fillText("HELLO", 90, 400);'
        p = self.project("missing", js)
        self.assertRun(self.fin("safe", "--project", str(p), "--platform", "tiktok"), 1, "no Canvas bridge is registered")
        self.assertRun(self.fin("check", "--project", str(p)), 1, "no Canvas bridge is registered")

    def test_empty_audit_fails(self):
        draw = 'ctx.fillStyle = "#1d2b53"; ctx.fillRect(0, 0, 540, 960); ctx.fillStyle = "#ff004d"; ctx.fillRect(80 + 120 * t, 200, 60, 60);'
        p = self.project("empty", scene_js(draw=draw))
        self.assertRun(self.fin("safe", "--project", str(p), "--platform", "tiktok"), 1, "empty audit", absent=("✓ safe check",))

    def test_stale_audit_from_a_swallowed_seek_fails(self):
        before = 'window.addEventListener("hf-seek", (e) => e.stopImmediatePropagation());'
        p = self.project("stale-time", scene_js(before=before))
        self.assertRun(self.fin("safe", "--project", str(p), "--platform", "tiktok"), 1, "stale")
        self.assertRun(self.fin("check", "--project", str(p)), 1, "stale")

    def test_stale_audit_from_pixels_drawn_after_the_audited_draw_fails(self):
        after = ('window.addEventListener("hf-seek", (e) => { const x = canvas.getContext("2d"); x.setTransform(1, 0, 0, 1, 0, 0);'
                 ' x.fillStyle = "#0f0"; x.fillRect(0, 0, 40 + 100 * e.detail.time, 40); });')
        p = self.project("stale-pixels", scene_js(after=after))
        self.assertRun(self.fin("safe", "--project", str(p), "--platform", "tiktok"), 1, "stale", "pixels changed")

    def test_draw_exception_is_surfaced(self):
        draw = GOOD_DRAW + '\n if (t > 1) throw new Error("boom at " + t.toFixed(2));'
        p = self.project("throws", scene_js(draw=draw))
        self.assertRun(self.fin("check", "--project", str(p)), 1, "boom")
        self.assertRun(self.fin("safe", "--project", str(p), "--platform", "tiktok"), 1, "draw failed", "boom")

    def test_draw_that_keeps_state_or_reads_new_date_fails_the_re_seek(self):
        # n++ is state carried between draws; new Date() is a clock the watch does not see: both pass a single forward pass
        stateful = self.project("stateful", scene_js(draw=GOOD_DRAW + '\n n++; ctx.fillRect(10 * (n % 40), 900, 20, 20);', before="let n = 0;"))
        a1, _, a2 = self.run_probe(stateful, "aba")["res"]
        self.assertNotEqual(a1["hash"], a2["hash"], "fixture: the stateful draw really differs on A/B/A")
        self.assertRun(self.fin("check", "--project", str(stateful)), 1, "drew different pixels", "re-seek", absent=("✓ canvas audit",))
        dated = self.project("new-date", scene_js(draw=GOOD_DRAW + '\n ctx.fillRect(new Date().getMilliseconds() / 4, 900, 20, 20);'))
        self.assertRun(self.fin("check", "--project", str(dated)), 1, "drew different pixels", absent=("✓ canvas audit",))
        # a pure draw with scatter from a seeded source made anew per draw, and a bridge held after its duration, still pass
        seeded = GOOD_DRAW + '\n const rnd = KitToClipCanvas.seeded(7); for (let i = 0; i < 20; i++) ctx.fillRect(rnd() * 500, 600 + rnd() * 200, 6, 6);'
        held = self.project("seeded-held", scene_js(draw=seeded), dur=3)
        self.assertRun(self.fin("check", "--project", str(held)), 0, "✓ canvas audit", "redrawn identically")

    def test_ready_is_waited_for_and_a_rejected_ready_fails_the_checks(self):
        late = self.project("late-ready", scene_js(extra_opts=".then(() => new Promise((r) => setTimeout(r, 1500)))"))
        self.assertRun(self.fin("check", "--project", str(late)), 0, "✓ canvas audit")
        self.assertRun(self.fin("safe", "--project", str(late), "--platform", "tiktok"), 0, "✓ safe check (canvas)")
        bad = self.project("rejected-ready", scene_js(extra_opts='.then(() => Promise.reject(new Error("font file missing")))'))
        self.assertRun(self.fin("check", "--project", str(bad)), 1, "not ready", "font file missing", absent=("✓ canvas audit",))
        self.assertRun(self.fin("safe", "--project", str(bad), "--platform", "tiktok"), 1, "font file missing", absent=("✓ safe check (canvas)",))

    def test_wall_clock_or_unseeded_random_fails(self):
        draw = GOOD_DRAW + '\n ctx.fillRect(Math.random() * 10, 0, 4, 4);'
        p = self.project("random", scene_js(draw=draw))
        self.assertRun(self.fin("check", "--project", str(p)), 1, "not reproducible", "Math.random")

    def test_blank_canvas_opening_fails_the_hook(self):
        draw = 'ctx.clearRect(0, 0, 540, 960); if (t >= 1.5) { ctx.fillStyle = "#fff"; ctx.font = "bold 48px sans-serif"; ctx.fillText("LATE", 90, 400); }'
        p = self.project("blank-open", scene_js(draw=draw))
        self.assertRun(self.fin("hook", "--project", str(p)), 1, "only background")

    def test_text_hidden_by_a_clip_or_a_transparent_fill_is_not_readable(self):
        # an opening with a moving shape, so only the readable-text verdict is in question
        opening = 'ctx.fillStyle = "#1d2b53"; ctx.fillRect(0, 0, 540, 960); ctx.fillStyle = "#ff004d"; ctx.fillRect(80 + 120 * t, 200, 300, 300);'
        hidden = {
            "clipped": 'ctx.save(); ctx.beginPath(); ctx.rect(0, 0, 0, 0); ctx.clip(); ctx.fillStyle = "#fff"; ctx.font = "bold 96px sans-serif";'
                       ' ctx.fillText("HIDDEN", 90, 700); ctx.restore();',
            "transparent": 'ctx.fillStyle = "rgba(255,255,255,0)"; ctx.font = "bold 96px sans-serif"; ctx.fillText("HIDDEN", 90, 700);',
        }
        for name, text in hidden.items():
            with self.subTest(name):
                p = self.project("hidden-" + name, scene_js(draw=opening + text))
                self.assertRun(self.fin("hook", "--project", str(p)), 1, "no readable text or logo by 3", absent=('canvas text "HIDDEN"',))
                self.assertRun(self.fin("safe", "--project", str(p), "--platform", "tiktok"), 1, "empty audit", absent=("✓ safe check",))
        # a reveal that is open shows the same text: readable
        shown = opening + 'ctx.save(); ctx.beginPath(); ctx.rect(0, 0, 540, 960); ctx.clip(); ctx.fillStyle = "#fff"; ctx.font = "bold 96px sans-serif";' \
                          ' ctx.fillText("SHOWN", 90, 700); ctx.restore();'
        self.assertRun(self.fin("hook", "--project", str(self.project("shown", scene_js(draw=shown)))), 0, 'canvas text "SHOWN"')

    def test_label_boxes_stay_on_the_canvas_bitmap(self):
        # a small canvas in the middle of the page: text drawn above its bitmap would map onto visible page pixels
        small = '<canvas id="c" width="270" height="480" data-k2c-canvas style="left:405px;top:720px;width:270px;height:480px"></canvas>'
        base = 'ctx.fillStyle = "#1d2b53"; ctx.fillRect(0, 0, 270, 480); ctx.fillStyle = "#ff004d"; ctx.fillRect(20 + 20 * t, 270, 230, 200);' \
               ' ctx.fillStyle = "#fff"; ctx.font = "bold 96px sans-serif";'
        off = self.project("off-bitmap", scene_js(draw=base + ' ctx.fillText("ABOVE", 10, -200);'), body=small)
        self.assertRun(self.fin("hook", "--project", str(off)), 1, "no readable text or logo by 3", "first frame shows content",
                       absent=('canvas text "ABOVE"',))
        part = self.project("part-bitmap", scene_js(draw=base + ' ctx.fillText("EDGEWISE", 150, 120); audit.region("mark", 200, 400, 200, 200, { kind: "logo" });'), body=small)
        r = self.run_probe(part, "audited")["res"]
        for lab in r["frame"]["labels"]:
            x0, y0, x1, y1 = lab["rect"]
            self.assertGreaterEqual(x0, 0, lab)
            self.assertGreaterEqual(y0, 0, lab)
            self.assertLessEqual(x1, r["width"], f"{lab['text']} box must end at the bitmap's right edge")
            self.assertLessEqual(y1, r["height"], f"{lab['text']} box must end at the bitmap's bottom edge")
        text = next(x for x in r["frame"]["labels"] if x["text"] == "EDGEWISE")
        self.assertGreater(text["painted"], 0)
        self.assertLessEqual(text["ink"][2], r["width"])
        mark = next(x for x in r["frame"]["labels"] if x["text"] == "mark")
        self.assertIsNone(mark["painted"], "a declared region is taken as said, not pixel-checked")

    def test_rotated_or_scaled_label_is_placed_by_its_transformed_box(self):
        # inside the safe box unrotated; rotated 90 degrees about its start, the word runs down past TikTok's bottom margin
        turned = GOOD_DRAW + '\n ctx.save(); ctx.translate(300, 500); ctx.rotate(Math.PI / 2); ctx.scale(1.5, 1.5); ctx.fillText("SIDEWAYS", 0, 0); ctx.restore();'
        p = self.project("rotated", scene_js(draw=turned))
        self.assertRun(self.fin("safe", "--project", str(p), "--platform", "tiktok"), 1, "SIDEWAYS", "bottom by")

    def test_declared_no_labels(self):
        shapes = 'ctx.fillStyle = "#1d2b53"; ctx.fillRect(0, 0, 540, 960); ctx.fillStyle = "#ff004d"; ctx.fillRect(80 + 120 * t, 200, 60, 60);'
        dom = CANVAS + '<div id="cap" style="position:absolute;left:200px;top:700px;font:bold 64px Helvetica;color:#fff">Caption</div>'
        ok = self.project("none-ok", scene_js(draw=shapes, extra_opts=', labels: "none"'), body=dom)
        self.assertRun(self.fin("safe", "--project", str(ok), "--platform", "tiktok"), 0, "stay inside", "declares no text or logo")
        liar = self.project("none-liar", scene_js(extra_opts=', labels: "none"'), body=dom)
        self.assertRun(self.fin("safe", "--project", str(liar), "--platform", "tiktok"), 1, "declares no text or logo", "HELLO")

    # ------------------------------------------------------------ API contract
    def test_api_refuses_bad_registrations_and_leaks_no_listeners(self):
        body = ''.join(f'<canvas id="c{i}" width="40" height="40"></canvas>' for i in (1, 2, 3))
        js = 'window.__ownRoot = gsap.timeline({ paused: true }).to("#c1", { x: 10, duration: 2 }); window.__timelines["t"] = window.__ownRoot;'
        r = self.run_probe(self.project("api", js, body=body), "api")
        ref = r["refusals"]
        for k in ("nan", "inf", "zero", "neg", "string", "missing"):
            self.assertIsNotNone(ref["duration_" + k], f"duration {k} must be refused")
            self.assertIn("duration", ref["duration_" + k])
        self.assertIn("draw", ref["no_draw"])
        self.assertIn("canvas", ref["not_canvas"])
        self.assertIn("data-duration", ref["longer_than_root"])
        self.assertIn("timeline", ref["unknown_option"])
        self.assertEqual(ref["registered"], 0)
        self.assertEqual(r["afterRefusals"], r["base"], "a refused registration must not add a listener")
        regs = r["regs"]
        self.assertIsNone(regs["first"])
        self.assertIn("already registered", regs["dup_id"])
        self.assertIn("already", regs["dup_canvas"])
        self.assertIsNone(regs["second"])
        self.assertEqual(regs["ids"], ["a", "b"])
        self.assertTrue(regs["root_timeline_kept"], "the bridge never touches the author's root timeline")
        self.assertEqual(r["withTwo"], r["base"] + 1, "all bridges share one hf-seek listener")
        self.assertEqual(r["afterDispose"], r["base"], "disposing every bridge removes its listener")
        self.assertEqual(r["reuse"], 1)

    # ------------------------------------------------------------ sub-compositions are not supported
    def test_canvas_in_a_sub_composition_is_refused(self):
        inner = ('<div id="inner" data-composition-id="inner" data-start="1" data-duration="1" data-width="1080" data-height="1920">'
                 '<canvas id="inner-c" width="40" height="40" data-k2c-canvas></canvas></div>')
        r = self.run_probe(self.project("nested", ROOT_TL, body=CANVAS + inner), "nested")
        self.assertIsNotNone(r["res"], "a canvas in a nested composition must be refused")
        self.assertIn("sub-composition", r["res"])
        self.assertEqual(r["registered"], 0)
        # a composition loaded from its own file: its bridge would get the root's seek time, so it is refused and check fails
        d = self.project("sub-src", ROOT_TL, body=CANVAS.replace("data-k2c-canvas", "") +
                         '<div id="host" data-composition-id="scene" data-composition-src="scene.html" data-start="1" data-duration="1"></div>')
        (d / "scene.html").write_text(SUB_SCENE)
        self.assertRun(self.fin("check", "--project", str(d)), 1, "sub-composition", absent=("✓ canvas audit",))

    # ------------------------------------------------------------ legacy controls stay strict
    def test_non_canvas_and_unbridged_controls_stay_strict(self):
        no_text = self.project("dom-no-text", 'window.__timelines["t"] = gsap.timeline({ paused: true });', bridge=False,
                               body='<div style="position:absolute;left:200px;top:600px;width:300px;height:300px;background:#e33"></div>')
        self.assertRun(self.fin("safe", "--project", str(no_text), "--platform", "tiktok"), 1, "no visible text or logo", absent=("canvas",))
        raw = ('window.__timelines["t"] = gsap.timeline({ paused: true }); const x = document.getElementById("c").getContext("2d");'
               ' x.fillStyle = "#fff"; x.font = "bold 48px sans-serif"; x.fillText("HELLO", 90, 400);')
        unbridged = self.project("raw-canvas", raw, body='<canvas id="c" width="540" height="960"></canvas>', bridge=False)
        self.assertRun(self.fin("safe", "--project", str(unbridged), "--platform", "tiktok"), 1, "no visible text or logo")
        self.assertRun(self.fin("hook", "--project", str(unbridged)), 1, "no readable text or logo by 3")
        no_root = self.project("bridge-no-root", scene_js(root=False))
        self.assertRun(self.fin("check", "--project", str(no_root)), 1, "not registered on window.__timelines")

    # ------------------------------------------------------------ the real renderer
    def render(self, name, opts="", draw=FLIP_DRAW):
        """Render a 1 s 320x180 page whose whole frame is one bridged canvas; returns (exit code, log, rgb_at)."""
        page = PAGE.replace("1080px", "320px").replace("1920px", "180px").replace('data-width="1080" data-height="1920"', 'data-width="320" data-height="180"')
        d = self.base / "proj" / name
        (d / "vendor").mkdir(parents=True)
        shutil.copy2(self.gsap, d / "vendor" / "gsap.min.js")
        if BRIDGE.is_file():
            shutil.copy2(BRIDGE, d / "canvas-bridge.js")
        js = (ROOT_TL + f' KitToClipCanvas.register({{ id: "flip", canvas: document.getElementById("c"), duration: 1, labels: "none"{opts},'
              f' draw(ctx, t) {{ {draw} }} }});')
        (d / "index.html").write_text(page.format(bridge_tag=BRIDGE_TAG, dur=1, body='<canvas id="c" width="160" height="90" data-k2c-canvas></canvas>', js=js))
        out = self.base / (name + ".mp4")
        hf = self.studio / "node_modules" / ".bin" / "hyperframes"
        r = subprocess.run([str(hf), "render", str(d), "--output", str(out), "--quality", "draft", "--workers", "1"],
                           capture_output=True, text=True, cwd=self.base, env=self.env, timeout=600)

        def rgb_at(sec):
            px = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(sec), "-i", str(out), "-frames:v", "1", "-vf", "scale=1:1",
                                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, env=self.env).stdout
            return tuple(px[:3])
        return r.returncode, r.stdout + r.stderr, rgb_at, d

    def assertRedThenBlue(self, rgb_at, early_at=0.2):
        early, late = rgb_at(early_at), rgb_at(0.8)
        self.assertGreater(early[0], 150, f"{early_at} s should be red, got {early}")
        self.assertLess(early[2], 90, f"{early_at} s should be red, got {early}")
        self.assertGreater(late[2], 150, f"0.8 s should be blue, got {late}")
        self.assertLess(late[0], 90, f"0.8 s should be blue, got {late}")

    def test_engine_render_draws_the_canvas_at_each_frame_time(self):
        rc, log, rgb_at, d = self.render("render")
        self.assertEqual(rc, 0, log[-4000:])
        self.assertNotIn("PAGEERROR", log, "the bridge must draw under the renderer's pinned clocks")
        hf = self.studio / "node_modules" / ".bin" / "hyperframes"
        lint = subprocess.run([str(hf), "lint", str(d), "--json"], capture_output=True, text=True, cwd=self.base, env=self.env, timeout=120)
        self.assertTrue(json.loads(lint.stdout)["ok"], lint.stdout)
        self.assertRedThenBlue(rgb_at)

    def test_engine_render_holds_for_a_delayed_ready_and_draws_the_first_frame(self):
        # the asset arrives after the page loads: frame 0 must wait for it and show the drawing, not a blank canvas
        rc, log, rgb_at, _ = self.render("render-late", opts=', ready: new Promise((r) => setTimeout(r, 1500))')
        self.assertEqual(rc, 0, log[-4000:])
        self.assertRedThenBlue(rgb_at, early_at=0.0)

    def test_engine_render_fails_when_ready_rejects(self):
        rc, log, rgb_at, _ = self.render("render-rejected", opts=', ready: new Promise((_, no) => setTimeout(() => no(new Error("logo.png is missing")), 300))')
        self.assertNotEqual(rc, 0, "a render must not export a blank canvas when its asset failed:\n" + log[-4000:])
        self.assertIn("logo.png is missing", log)
        self.assertIn('KitToClipCanvas "flip"', log)

    def test_engine_render_fails_when_a_draw_throws(self):
        rc, log, rgb_at, _ = self.render("render-throws", draw='if (t >= 0.5) throw new Error("bad frame"); ' + FLIP_DRAW)
        self.assertNotEqual(rc, 0, "a render must stop when a frame cannot be drawn:\n" + log[-4000:])
        self.assertIn('KitToClipCanvas "flip" draw failed at', log)
        self.assertIn("bad frame", log)


if __name__ == "__main__":
    unittest.main()
