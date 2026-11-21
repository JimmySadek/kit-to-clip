/* Frame-by-frame renderer worker for Kit to Clip Studio players.
   node render.js <job.json>   (written by render.py; never run by hand)

   Opens the self-contained player HTML in Playwright's/HyperFrames' bundled Chromium, calls window.seek(t) for each
   frame (from..to at fps), pipes lossless PNG frames straight to ffmpeg, and optionally renders the offline SFX stem
   via window.SOUND.renderOffline or OfflineAudioContext with window.SCORE_STEM = 'sfx'. */
'use strict';
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const puppeteer = require(process.env.REEL_STUDIO + '/node_modules/puppeteer-core');

const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

function encodeWavInPage(samplesL, samplesR, sr) {
  const n = samplesL.length;
  const buf = new ArrayBuffer(44 + n * 4);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + n * 4, true); str(8, 'WAVE');
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 2, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 4, true); v.setUint16(32, 4, true); v.setUint16(34, 16, true);
  str(36, 'data'); v.setUint32(40, n * 4, true);
  let off = 44;
  for (let i = 0; i < n; i++) {
    const l = Math.max(-1, Math.min(1, samplesL[i] || 0));
    const r = Math.max(-1, Math.min(1, samplesR[i] || 0));
    v.setInt16(off, Math.round(l * 32767), true);
    v.setInt16(off + 2, Math.round(r * 32767), true);
    off += 4;
  }
  return new Uint8Array(buf);
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: process.env.HYPERFRAMES_BROWSER_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: job.width, height: job.height, deviceScaleFactor: 1 });
    await page.setRequestInterception(true);
    const htmlDir = path.dirname(path.resolve(job.html));
    page.on('request', r => {
      const u = r.url();
      if (u.startsWith('file://') || u.startsWith('data:') || u.startsWith('blob:') ||
          /^https:\/\/fonts\.(googleapis|gstatic)\.com\//.test(u)) r.continue();
      else r.abort();
    });
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));

    await page.goto(pathToFileURL(path.resolve(job.html)).href, { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => Promise.race([
      document.fonts ? document.fonts.ready : Promise.resolve(),
      new Promise(r => setTimeout(r, 4000)),
    ]));

    const meta = await page.evaluate(() => ({
      duration: typeof window.DURATION === 'number' && isFinite(window.DURATION) ? window.DURATION : null,
      hasSeek: typeof window.seek === 'function',
      hasCanvas: !!document.querySelector('canvas'),
      hasScore: typeof window.scoreSound === 'function',
      hasSound: typeof window.SOUND === 'object' && !!window.SOUND,
    }));
    if (!meta.hasSeek) throw new Error('the player HTML has no window.seek(t) function');
    if (errors.length) throw new Error('player script error: ' + errors[0]);

    const fullDur = job.duration || meta.duration;
    if (!fullDur || fullDur <= 0) throw new Error('no window.DURATION and no --duration given');
    const fromS = Math.max(0, job.from || 0);
    const toS = Math.min(fullDur, job.to != null ? job.to : fullDur);
    if (toS <= fromS) throw new Error('render window is empty');

    const fps = job.fps || 30;
    const totalFrames = Math.max(1, Math.round((toS - fromS) * fps));

    // Pipe lossless PNG frames directly to ffmpeg, with zero temporary image files on disk.
    const ff = spawn('ffmpeg', [
      '-v', 'error', '-y',
      '-f', 'image2pipe', '-vcodec', 'png', '-framerate', String(fps), '-i', 'pipe:0',
      '-vf', `scale=${job.width}:${job.height}:force_original_aspect_ratio=decrease,pad=${job.width}:${job.height}:(ow-iw)/2:(oh-ih)/2`,
      '-c:v', 'libx264', '-preset', job.preset || 'medium', '-crf', String(job.crf || 16),
      '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
      job.out_video,
    ], { stdio: ['pipe', 'ignore', 'pipe'] });
    let ffErr = '';
    ff.stderr.on('data', d => { ffErr += d.toString(); });

    const writeChunk = chunk => new Promise((resolve, reject) => {
      if (ff.stdin.write(chunk)) resolve();
      else ff.stdin.once('drain', resolve);
      ff.stdin.once('error', reject);
    });

    for (let i = 0; i < totalFrames; i++) {
      const t = fromS + i / fps;
      let png;
      if (meta.hasCanvas && !job.dom_screenshot) {
        const b64 = await page.evaluate(async (t) => {
          await window.seek(t);
          const c = document.querySelector('canvas');
          return c.toDataURL('image/png').split(',')[1];
        }, t);
        png = Buffer.from(b64, 'base64');
      } else {
        await page.evaluate(async (t) => { await window.seek(t); }, t);
        png = await page.screenshot({ type: 'png' });
      }
      await writeChunk(png);
    }
    ff.stdin.end();
    const ffCode = await new Promise(resolve => ff.on('close', resolve));
    if (ffCode !== 0) throw new Error('ffmpeg failed: ' + ffErr.trim());

    // Offline SFX stem rendering (when the player scores sound effects).
    let sfxWritten = false;
    let sfxNote = null;
    if (job.out_sfx && meta.hasScore && meta.hasSound) {
      const sfxRes = await page.evaluate(async (dur, fromS, toS, sr, encodeSrc) => {
        try {
          window.SCORE_STEM = 'sfx';
          let audioBuf = null;
          if (typeof window.SOUND.renderOffline === 'function') {
            audioBuf = await window.SOUND.renderOffline((k) => window.scoreSound(k, 0), dur, { sr });
          } else if (typeof window.SOUND.kit === 'function' && typeof OfflineAudioContext === 'function') {
            const ctx = new OfflineAudioContext(2, Math.max(1, Math.ceil(dur * sr)), sr);
            const k = window.SOUND.kit(ctx);
            window.scoreSound(k, 0);
            audioBuf = await ctx.startRendering();
          }
          if (!audioBuf) return { ok: false, note: 'no SOUND.renderOffline or SOUND.kit' };
          // If SOUND.renderOffline returned an AudioBuffer or {left, right} or Wav bytes, normalize it.
          let chL, chR, rate = sr;
          if (audioBuf instanceof Uint8Array || audioBuf instanceof ArrayBuffer) {
            const bytes = audioBuf instanceof Uint8Array ? audioBuf : new Uint8Array(audioBuf);
            let bin = '';
            for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
            return { ok: true, wav_b64: btoa(bin) };
          }
          if (typeof audioBuf.getChannelData === 'function') {
            rate = audioBuf.sampleRate || sr;
            const s0 = Math.max(0, Math.floor(fromS * rate));
            const s1 = Math.min(audioBuf.length, Math.ceil(toS * rate));
            chL = audioBuf.getChannelData(0).subarray(s0, s1);
            chR = audioBuf.numberOfChannels > 1 ? audioBuf.getChannelData(1).subarray(s0, s1) : chL;
          } else {
            return { ok: false, note: 'unrecognised renderOffline return value' };
          }
          let peak = 0;
          for (let i = 0; i < chL.length; i++) {
            const a = Math.abs(chL[i]), b = Math.abs(chR[i]);
            if (a > peak) peak = a;
            if (b > peak) peak = b;
          }
          if (peak < 1e-6) return { ok: false, note: 'sfx stem is silent' };
          const encodeWav = eval('(' + encodeSrc + ')');
          const bytes = encodeWav(chL, chR, rate);
          let bin = '';
          for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
          return { ok: true, wav_b64: btoa(bin), peak };
        } catch (e) {
          return { ok: false, note: String(e && e.message || e) };
        }
      }, fullDur, fromS, toS, 48000, encodeWavInPage.toString());

      if (sfxRes.ok && sfxRes.wav_b64) {
        fs.writeFileSync(job.out_sfx, Buffer.from(sfxRes.wav_b64, 'base64'));
        sfxWritten = true;
      } else {
        sfxNote = sfxRes.note || 'no sfx stem';
      }
    }

    if (errors.length) throw new Error('player threw during render: ' + errors[0]);
    process.stdout.write(JSON.stringify({
      frames: totalFrames,
      fps,
      duration: Math.round((toS - fromS) * 1000) / 1000,
      width: job.width,
      height: job.height,
      sfx: sfxWritten,
      sfx_note: sfxNote,
    }));
  } finally {
    await browser.close();
  }
})().catch(e => {
  console.error(String(e && e.message || e));
  process.exit(1);
});
