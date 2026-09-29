// Kit to Clip finish: sample how elements really move in a HyperFrames composition, by seeking the running timeline the
// way the renderer does. Shared by the anchors check (when does an anchored element start and stop moving?) and the
// motion trace (motion.json, for sound that follows the picture).
//
// Per element and time: centre, size, opacity and the visible fraction. Visible means seen by a viewer: opacity of the
// element and its parents, times the share of it that is not clipped by an overflow-hidden parent (a headline parked
// inside a text mask is hidden, so its jump while hidden is not motion). The canvas edge is not a clip: an element that
// slides in from outside the frame starts moving when its tween starts.
//
// The renderer draws whole frames, and the runtime's renderSeek snaps any time to the frame grid (30 fps unless the
// composition says otherwise). So this samples exactly the frames a viewer sees, one per 1/fps, seeking a quarter frame
// past each frame's time so floating point can never land it on the frame before. Sampling faster only repeats frames.
//
// Pitfall: puppeteer's waitForFunction runs in an isolated world and cannot see page globals such as window.__timelines.
// hfpage.mjs waits for the player with window.__renderReady and seeks with the player's renderSeek, so this never polls
// page globals from the isolated world.

// Elements matched by `selector`, one sample per frame from 0 to `duration`.
//   members: 0 = only the element itself; N = also its first N descendants (a container whose words move counts as moving)
// Returns [{ label, id, trackName, anchor, declared, scope, frames: [{t, x, y, w, h, o, vis, sx, sy}], act: [[pos, size, vis] per frame] }]
// act = the largest change in the element's subtree since the frame before: px moved, px resized, visibility gained or lost.
export async function sampleMotion(page, { selector, fps = 30, duration, members = 0 }) {
  return page.evaluate(async ({ selector, fps, duration, members }) => {
    const step = 1 / fps;
    const V = window.__reelVisible;
    const isRoot = (a) => a === document.body || a === document.documentElement ||
      (a.hasAttribute("data-composition-id") && !(a.parentElement && a.parentElement.closest("[data-composition-id]")));
    const rows = [...document.querySelectorAll(selector)].filter((el) => !el.closest("script, style, template")).map((el) => ({
      el, label: V.name(el), id: el.id || null, trackName: el.getAttribute("data-track") || null, anchor: el.getAttribute("data-anchor"),
      declared: el.getAttribute("data-at") ?? el.getAttribute("data-start"), scope: el.getAttribute("data-anchor-scope"),
      subtree: [el, ...[...el.querySelectorAll("*")].filter((e) => !e.closest("script, style, template")).slice(0, members)],
      frames: [], act: [], prev: null,
    }));
    const gs = window.gsap;
    const clipOf = (el) => {           // opacity of the parents and the box their overflow-hidden ancestors leave visible
      let o = 1, L = -1e9, T = -1e9, R = 1e9, B = 1e9;
      for (let a = el.parentElement; a && a.nodeType === 1; a = a.parentElement) {
        const cs = getComputedStyle(a);
        if (cs.display === "none") return { o: 0, L: 0, T: 0, R: 0, B: 0 };
        o *= Number(cs.opacity);
        if (isRoot(a)) continue;
        if (/hidden|clip/.test(cs.overflowX) || /hidden|clip/.test(cs.overflowY)) {
          const r = a.getBoundingClientRect();
          L = Math.max(L, r.left); T = Math.max(T, r.top); R = Math.min(R, r.right); B = Math.min(B, r.bottom);
        }
      }
      return { o, L, T, R, B };
    };
    const state = (row) => {
      const c = clipOf(row.el);
      return row.subtree.map((m) => {
        const r = m.getBoundingClientRect();
        let o = c.o;
        for (let a = m; a; a = a.parentElement) {
          const cs = getComputedStyle(a);
          if (cs.display === "none") { o = 0; break; }
          o *= Number(cs.opacity);
          if (a === row.el) break;
        }
        const fx = r.width > 0 ? Math.max(0, Math.min(r.right, c.R) - Math.max(r.left, c.L)) / r.width : (r.left >= c.L && r.left <= c.R ? 1 : 0);
        const fy = r.height > 0 ? Math.max(0, Math.min(r.bottom, c.B) - Math.max(r.top, c.T)) / r.height : (r.top >= c.T && r.top <= c.B ? 1 : 0);
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, o, vis: o * fx * fy };
      });
    };
    const n = Math.ceil(duration * fps - 1e-9);
    for (let i = 0; i < n; i++) {
      const t = i * step;
      await V.seek(t + step / 4);
      for (const row of rows) {
        const cur = state(row), me = cur[0];
        row.frames.push({ t: +t.toFixed(5), x: me.x, y: me.y, w: me.w, h: me.h, o: me.o, vis: me.vis,
          sx: gs ? Number(gs.getProperty(row.el, "scaleX")) : 1, sy: gs ? Number(gs.getProperty(row.el, "scaleY")) : 1 });
        if (row.prev) {
          let pos = 0, size = 0, vis = 0;
          for (let k = 0; k < cur.length; k++) {
            const a = row.prev[k], b = cur[k], seen = Math.min(a.vis, b.vis);
            pos = Math.max(pos, Math.hypot(b.x - a.x, b.y - a.y) * seen);
            size = Math.max(size, Math.hypot(b.w - a.w, b.h - a.h) * seen);
            vis = Math.max(vis, Math.abs(b.vis - a.vis));
          }
          row.act.push([pos, size, vis]);
        } else row.act.push([0, 0, 0]);
        row.prev = cur;
      }
    }
    return rows.map(({ label, id, trackName, anchor, declared, scope, frames, act }) => ({ label, id, trackName, anchor, declared, scope, frames, act }));
  }, { selector, fps, duration, members });
}

// When does an element start and stop moving? Events from its activity series (see sampleMotion).
//   starts: the last still frame before it moves. A tween placed at time T shows its first change one frame later, so
//           this reads T (within one frame) whatever the ease. Hair-trigger on purpose: an ease-in is slow at first.
//   lands:  the first frame it is still again after moving, held for three frames. "Still" here is what an eye can
//           tell: under 0.05 px per frame. An ease-out creeps for the last frames of its tween; that creep is not
//           motion anyone sees, and counting it would make a hit read late by a frame or two.
export const EPS = { starts: { pos: 0.002, size: 0.002, vis: 0.0002 }, lands: { pos: 0.05, size: 0.05, vis: 0.005 } };
export function motionEvents(times, act) {
  const events = [];
  ["pos", "size", "vis"].forEach((ch, c) => {
    const s = act.map((a) => a[c]), go = EPS.starts[ch], rest = EPS.lands[ch];
    const quiet = (i, eps) => i < 0 || i >= s.length || s[i] < eps;
    for (let i = 1; i < s.length; i++) {
      if (s[i] >= go && quiet(i - 1, go)) events.push({ t: times[i - 1], kind: "starts", channel: ch });
      if (s[i] < rest && s[i - 1] >= rest && quiet(i + 1, rest) && quiet(i + 2, rest)) events.push({ t: times[i], kind: "lands", channel: ch });
    }
  });
  return events.sort((a, b) => a.t - b.t);
}
