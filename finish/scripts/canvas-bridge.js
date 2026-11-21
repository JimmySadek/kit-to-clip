// Kit to Clip Canvas bridge: a time-driven Canvas2D drawing on the HyperFrames engine, with an audit trail for the
// finish checks. Copy this file into the project and load it with a classic <script src="canvas-bridge.js">, after
// GSAP and before the composition's own script. Guide: references/canvas-reference.md.
//
//   const scene = KitToClipCanvas.register({
//     id: "intro",                    // unique name
//     canvas: document.getElementById("intro-canvas"),
//     duration: 6,                    // finite seconds, at most the composition root's data-duration (root only)
//     draw(ctx, t, audit) { ... },    // pure: the picture at time t (seconds), from t alone
//     labels: "audit",                // default; "none" = this canvas draws no text or logo (said, not inspected)
//     ready: document.fonts.ready,    // optional: fonts or images the first frame needs; seeks wait for it, a rejection fails them
//   });
//
// The bridge does not register a timeline: the composition keeps the standard one-line paused root timeline
// (window.__timelines["<id>"] = gsap.timeline({ paused: true })) where `hyperframes lint` can see it, and a finite
// data-duration on the composition root, which sets the render length.
//
// How it runs: HyperFrames dispatches "hf-seek" with detail.time on every seek (preview, render, finish checks). One
// shared listener draws every bridge at that time, clamped to [0, duration]. No requestAnimationFrame, no clock.
// detail.time is the root composition's time, so a bridge is only accepted on a canvas of the root composition.
// Before `ready` settles, a seek is held with detail.waitUntil and drawn at its own time once ready; if `ready` rejects
// or the draw throws, the seek's waitUntil promise rejects, so a render stops instead of exporting a blank canvas.
// What it records per draw (scene.frame()): the seek time, a sequence number, every fillText/strokeText run measured
// with measureText and the current transform ("measured"), every audit.region(name, x, y, w, h, { kind }) box for path
// lettering or logos ("declared"), any read of Math.random, Date.now or performance.now during the draw, and the error
// if the draw threw. When the finish checks turn the audit on, it also records a fingerprint of the pixels it drew, and
// for each measured text run how many bitmap pixels it actually changed ("painted") and their box ("ink"): text under a
// closed ctx.clip(), in a transparent colour or off the bitmap paints nothing. Declared regions are taken as said.
(function () {
  "use strict";
  if (window.KitToClipCanvas) return;                   // loaded twice: keep the first registry
  var bridges = new Map(), canvases = new Set(), listening = false, auditing = false;
  var KINDS = { logo: 1, lettering: 1 }, OPTIONS = ["id", "canvas", "duration", "draw", "labels", "ready"];
  var INK = 24;                                         // a pixel is painted when a channel changes by this much (of 255)

  function fingerprint(canvas) {                        // FNV-1a over the RGBA words; finish.py computes the same
    var d = new Uint32Array(canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data.buffer);
    var h = 0x811c9dc5;
    for (var i = 0; i < d.length; i++) { h ^= d[i]; h = Math.imul(h, 0x01000193); }
    return h >>> 0;
  }

  // note any read of obj[key] during a draw; returns how to undo it, or null when the host made the property read-only
  // (the HyperFrames renderer does this to performance.now): such a property is left alone and not watched
  function watch(obj, key, name, clock) {
    var desc = Object.getOwnPropertyDescriptor(obj, key), orig = obj[key];
    if (typeof orig !== "function") return null;
    var w = function () { if (clock.indexOf(name) < 0) clock.push(name); return orig.apply(obj, arguments); };
    try {
      if (!desc) { Object.defineProperty(obj, key, { value: w, writable: true, configurable: true }); return function () { delete obj[key]; }; }
      if (desc.configurable) {
        Object.defineProperty(obj, key, { value: w, writable: true, configurable: true, enumerable: desc.enumerable });
        return function () { Object.defineProperty(obj, key, desc); };
      }
      if (desc.writable) { obj[key] = w; return function () { obj[key] = orig; }; }
    } catch (e) { /* not patchable: leave it alone */ }
    return null;
  }

  function box(m, pts) {                               // canvas-pixel AABB of points under transform m
    var L = Infinity, T = Infinity, R = -Infinity, B = -Infinity;
    for (var i = 0; i < pts.length; i++) {
      var x = m.a * pts[i][0] + m.c * pts[i][1] + m.e, y = m.b * pts[i][0] + m.d * pts[i][1] + m.f;
      L = Math.min(L, x); T = Math.min(T, y); R = Math.max(R, x); B = Math.max(B, y);
    }
    return [L, T, R, B];
  }

  // a canvas-pixel box clipped to the bitmap (what can show at all); null when it lies off the bitmap
  function onBitmap(canvas, r) {
    var L = Math.max(0, r[0]), T = Math.max(0, r[1]), R = Math.min(canvas.width, r[2]), B = Math.min(canvas.height, r[3]);
    return R > L && B > T ? [L, T, R, B] : null;
  }

  // what one native text call changed on the bitmap inside its (clipped) box: painted pixel count and their box
  function paintedBy(ctx, rect, call) {
    var x = Math.floor(rect[0]), y = Math.floor(rect[1]), w = Math.ceil(rect[2]) - x, h = Math.ceil(rect[3]) - y;
    var before = ctx.getImageData(x, y, w, h).data, out = call(), after = ctx.getImageData(x, y, w, h).data;
    var n = 0, L = Infinity, T = Infinity, R = -Infinity, B = -Infinity;
    for (var i = 0; i < after.length; i += 4) {
      if (Math.abs(after[i] - before[i]) < INK && Math.abs(after[i + 1] - before[i + 1]) < INK &&
          Math.abs(after[i + 2] - before[i + 2]) < INK && Math.abs(after[i + 3] - before[i + 3]) < INK) continue;
      var px = (i >> 2) % w, py = ((i >> 2) - px) / w;
      n++; L = Math.min(L, x + px); T = Math.min(T, y + py); R = Math.max(R, x + px + 1); B = Math.max(B, y + py + 1);
    }
    return { out: out, painted: n, ink: n ? [L, T, R, B] : null };
  }

  function textBox(ctx, text, x, y, maxWidth, pad) {
    var m = ctx.measureText(text);
    var l = -m.actualBoundingBoxLeft, r = m.actualBoundingBoxRight;
    if (maxWidth !== undefined && m.width > maxWidth && m.width > 0) { var k = maxWidth / m.width; l *= k; r *= k; }
    var t = -m.actualBoundingBoxAscent - pad, b = m.actualBoundingBoxDescent + pad;
    l -= pad; r += pad;
    return box(ctx.getTransform(), [[x + l, y + t], [x + r, y + t], [x + l, y + b], [x + r, y + b]]);
  }

  // one draw of one bridge at seek time `time`; returns the error it threw, if any
  function render(s, time) {
    var t = Math.min(Math.max(0, Number(time) || 0), s.duration);
    var labels = [], clock = [], ctx = s.ctx;
    var frame = { id: s.id, seq: ++s.seq, time: Number(time) || 0, t: t, labels: labels, clock: clock, error: null, fingerprint: null };
    var rec = function (kind) {
      return function (text, x, y, maxWidth) {
        var s2 = String(text), args = arguments;
        var call = function () { return CanvasRenderingContext2D.prototype[kind].apply(ctx, args); };
        if (!s2.trim()) return call();
        var lab = { source: "measured", kind: "text", text: s2, alpha: ctx.globalAlpha, painted: null, ink: null,
                    rect: onBitmap(s.canvas, textBox(ctx, s2, x, y, maxWidth, kind === "strokeText" ? ctx.lineWidth / 2 : 0)) };
        labels.push(lab);
        if (!auditing) return call();
        if (!lab.rect) { lab.painted = 0; return call(); }
        var p = paintedBy(ctx, lab.rect, call);
        lab.painted = p.painted; lab.ink = p.ink;
        return p.out;
      };
    };
    var audit = Object.freeze({
      region: function (name, x, y, w, h, opts) {
        var kind = (opts && opts.kind) || "lettering";
        if (!KINDS[kind]) throw new TypeError('KitToClipCanvas: audit.region kind must be "logo" or "lettering", not ' + JSON.stringify(kind));
        if (![x, y, w, h].every(Number.isFinite) || !(w > 0) || !(h > 0)) throw new TypeError("KitToClipCanvas: audit.region needs finite x, y and a positive w, h");
        labels.push({ source: "declared", kind: kind, text: String(name), alpha: ctx.globalAlpha, painted: null, ink: null,
          rect: onBitmap(s.canvas, box(ctx.getTransform(), [[x, y], [x + w, y], [x, y + h], [x + w, y + h]])) });
      },
    });
    // every frame starts from a cleared canvas and default state: nothing carries over from the previous seek
    if (typeof ctx.reset === "function") ctx.reset();
    else { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, s.canvas.width, s.canvas.height); }
    var restores = [];
    try {
      ctx.fillText = rec("fillText"); ctx.strokeText = rec("strokeText");
      restores = [watch(Math, "random", "Math.random", clock), watch(Date, "now", "Date.now", clock),
                  watch(performance, "now", "performance.now", clock)];
      ctx.save();
      try { s.draw.call(null, ctx, t, audit); } finally { ctx.restore(); }
    } catch (e) {
      frame.error = String((e && e.stack && e.stack.split("\n")[0]) || e);
      frame.labels = [];
    } finally {
      delete ctx.fillText; delete ctx.strokeText;
      restores.forEach(function (r) { if (r) r(); });
    }
    if (!frame.error && auditing) frame.fingerprint = fingerprint(s.canvas);
    s.frame = frame;
    return frame.error;
  }

  function drawError(s, time, err) {
    return new Error('KitToClipCanvas "' + s.id + '" draw failed at ' + (Number(time) || 0).toFixed(3) + " s: " + err);
  }
  function drawAll(time, waitUntil) {
    bridges.forEach(function (s) {
      if (!s.ready) {                                   // hold the seek until `ready` settles, then draw its own time
        s.pendingTime = time;
        var held = s.gate.then(function () {
          if (bridges.get(s.id) !== s || s.pendingTime !== time) return;     // a later seek draws instead
          var err = render(s, time);
          if (err) throw drawError(s, time, err);
        });
        if (typeof waitUntil === "function") waitUntil(held); else held.catch(function () {});   // already logged
        return;
      }
      var err = render(s, time);
      if (err) {
        var e = drawError(s, time, err);
        if (typeof waitUntil === "function") waitUntil(Promise.reject(e)); else throw e;
      }
    });
  }
  function onSeek(ev) {
    var d = ev && ev.detail;
    drawAll(d && d.time, d && d.waitUntil);
  }
  function listen(on) {
    if (on && !listening) window.addEventListener("hf-seek", onSeek);
    if (!on && listening) window.removeEventListener("hf-seek", onSeek);
    listening = on;
  }

  function register(o) {
    o = o || {};
    var unknown = Object.keys(o).filter(function (k) { return OPTIONS.indexOf(k) < 0; });
    if (unknown.length) throw new TypeError("KitToClipCanvas: unknown option(s) " + unknown.join(", ") + " (known: " + OPTIONS.join(", ") + ")");
    var id = o.id, canvas = o.canvas, duration = o.duration, draw = o.draw;
    if (typeof id !== "string" || !id.trim()) throw new TypeError("KitToClipCanvas: id must be a non-empty string");
    if (bridges.has(id)) throw new Error('KitToClipCanvas: a bridge with id "' + id + '" is already registered');
    if (!(canvas instanceof HTMLCanvasElement)) throw new TypeError("KitToClipCanvas: canvas must be a <canvas> element");
    if (canvases.has(canvas)) throw new Error("KitToClipCanvas: this canvas is already bridged");
    if (typeof duration !== "number" || !isFinite(duration) || !(duration > 0)) throw new TypeError("KitToClipCanvas: duration must be a finite number of seconds above 0, not " + String(duration));
    if (typeof draw !== "function") throw new TypeError("KitToClipCanvas: draw(ctx, t, audit) must be a function");
    var labelsMode = o.labels === undefined ? "audit" : o.labels;
    if (labelsMode !== "audit" && labelsMode !== "none") throw new TypeError('KitToClipCanvas: labels must be "audit" or "none"');
    var comp = canvas.closest("[data-composition-id]");
    var compId = comp && comp.getAttribute("data-composition-id");
    var compDur = comp ? Number(comp.getAttribute("data-duration")) : NaN;
    if (!compId) throw new Error("KitToClipCanvas: the canvas is not inside an element with data-composition-id");
    var outer = comp.parentElement && comp.parentElement.closest("[data-composition-id]");
    if (outer || comp.closest("[data-composition-src]") || comp !== document.querySelector("[data-composition-id]"))
      throw new Error('KitToClipCanvas: the canvas is in sub-composition "' + compId + '", which is not supported: hf-seek ' +
        "gives the root composition's time, so the drawing would run at the wrong time. Put the canvas in the root composition");
    if (!(isFinite(compDur) && compDur > 0)) throw new Error('KitToClipCanvas: composition "' + compId + '" needs a finite data-duration (Canvas has no duration inference)');
    if (duration > compDur + 1e-6) throw new Error("KitToClipCanvas: duration " + duration + " s is longer than the composition's data-duration " + compDur + " s");
    if (o.ready !== undefined && (o.ready === null || typeof o.ready.then !== "function")) throw new TypeError("KitToClipCanvas: ready must be a promise");
    var ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("KitToClipCanvas: the canvas has no 2d context (is it already used for WebGL?)");

    // validated: from here on, side effects
    var s = { id: id, canvas: canvas, ctx: ctx, duration: duration, draw: draw, labels: labelsMode, seq: 0, frame: null,
              ready: o.ready === undefined, gate: null, pendingTime: undefined, readyKey: null };
    bridges.set(id, s); canvases.add(canvas); listen(true);
    var start = function () { return typeof window.__hfThreeTime === "number" ? window.__hfThreeTime : 0; };
    if (!s.ready) {
      s.pendingTime = start();
      // the gate every early seek waits on: it rejects for good when `ready` does, so each held seek fails with it
      s.gate = Promise.resolve(o.ready).then(function () { if (bridges.get(id) === s) s.ready = true; }, function (e) {
        var why = "not ready: " + String(e && e.message || e);
        if (bridges.get(id) === s) {
          s.frame = { id: id, seq: ++s.seq, time: Number(s.pendingTime) || 0, t: 0, labels: [], clock: [], fingerprint: null, error: why };
          console.error('KitToClipCanvas "' + id + '" ' + why);
        }
        throw new Error('KitToClipCanvas "' + id + '" ' + why);
      });
      s.gate.catch(function () {});                       // reported above and through every held seek's waitUntil
      // HyperFrames also holds render-ready on __hf.buildReady (it logs a rejected one and carries on, so the held
      // seeks are what stop a render)
      window.__hf = window.__hf || {};
      window.__hf.buildReady = window.__hf.buildReady || {};
      s.readyKey = "k2c-canvas:" + id;
      window.__hf.buildReady[s.readyKey] = s.gate.then(function () {
        if (bridges.get(id) !== s) return;
        var err = render(s, s.pendingTime);
        if (err) throw drawError(s, s.pendingTime, err);
      });
    } else {
      var err = render(s, start());
      if (err) throw new Error('KitToClipCanvas "' + id + '" draw failed: ' + err);
    }
    return handle(s);
  }

  function copy(f) { return f && JSON.parse(JSON.stringify(f)); }
  function handle(s) {
    return Object.freeze({
      id: s.id, canvas: s.canvas, duration: s.duration, labels: s.labels,
      frame: function () { return copy(s.frame); },        // what the last draw recorded (a copy)
      draw: function (time) { render(s, time); return copy(s.frame); },
      dispose: function () {
        if (bridges.get(s.id) !== s) return;
        bridges.delete(s.id); canvases.delete(s.canvas);
        if (s.readyKey && window.__hf && window.__hf.buildReady) delete window.__hf.buildReady[s.readyKey];
        if (!bridges.size) listen(false);
      },
    });
  }

  // a seeded random source for draws that need scatter: same seed, same numbers. Make it inside draw, so every frame
  // starts the sequence afresh (one made outside draw advances across frames and breaks redraws)
  function seeded(seed) {
    var a = (Number(seed) >>> 0) || 1;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  window.KitToClipCanvas = Object.freeze({
    version: 1,
    register: register,
    list: function () { return Array.from(bridges.values()).map(handle); },
    seeded: seeded,
    // for the finish checks: from now on every draw also fingerprints its pixels; redraws each bridge at its last time
    audit: Object.freeze({ enable: function () {
      auditing = true;
      bridges.forEach(function (s) { if (s.ready && s.frame) render(s, s.frame.time); });
    } }),
  });
})();
