/* The storyboard worker: draws each panel in the bundled headless browser with the style's own code.
   node board.js <job.json>   (written by board.py; never run by hand)
   A part panel is one frame of its style. A join panel is the old style's last moment and the new style's first,
   split on a diagonal. Each panel is a PNG next to board.json. Prints {notes: {id: text}} for panels drawn with a
   fallback (a style that threw, or fonts that did not load in time). */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const puppeteer = require(process.env.REEL_STUDIO + '/node_modules/puppeteer-core');

const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

/* In the page: draw one style at a point (0..1) of its explainer, or of its hero loop when it has none. */
async function frameAt(page, t, under) {
  return page.evaluate(async (t, under, PW, PH) => {
    const style = (window.STYLES || [])[0], canvas = document.querySelector('canvas');
    if (!style || !window.H) throw new Error('the style did not register');
    if (!window.__fonts) {
      window.__fonts = Promise.race([Promise.resolve(H.loadFonts ? H.loadFonts(style) : 0).catch(() => 0),
        new Promise(r => setTimeout(() => r('late'), 4000))]);
    }
    const fonts = await window.__fonts;
    const demo = typeof style.explainer === 'function';
    const length = demo ? (style.explainerDuration || 15) : (style.duration || 6);
    // The explainer runs with the style as `this`, so an explainer that calls this.draw gets the hero frame.
    const shown = demo ? Object.assign(Object.create(style), { draw: (...a) => style.explainer.apply(style, a) }) : style;
    let note = fonts === 'late' ? 'fonts did not load in time' : '';
    try { H.render(shown, canvas, (demo ? 0 : (style.frameT || 0)) + t * length); }
    catch (e) { H.render(style, canvas, style.frameT || 0); note = 'its explainer threw, so this is the hero frame'; }
    if (under) {                                     // a join: the old style's frame on the left of a diagonal
      const img = new Image(); img.src = under; await img.decode();
      const ctx = canvas.getContext('2d');
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(PW * 0.62, 0); ctx.lineTo(PW * 0.38, PH); ctx.lineTo(0, PH); ctx.closePath();
      ctx.clip(); ctx.drawImage(img, 0, 0, PW, PH); ctx.restore();
      ctx.save(); ctx.strokeStyle = 'rgba(255,255,255,.85)'; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(PW * 0.62, 0); ctx.lineTo(PW * 0.38, PH); ctx.stroke(); ctx.restore();
    }
    return { url: canvas.toDataURL('image/png'), note };
  }, t, under || null, job.width, job.height);
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.HYPERFRAMES_BROWSER_PATH, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const notes = {};
  try {
    const pages = {};
    for (const [id, html] of Object.entries(job.pages)) {
      const page = await browser.newPage();
      await page.setRequestInterception(true);
      page.on('request', r => (/^https:\/\/fonts\.(googleapis|gstatic)\.com\//.test(r.url()) || r.url().startsWith('data:') ? r.continue() : r.abort()));
      const errors = [];
      page.on('pageerror', e => errors.push(String(e)));
      await page.setContent(html, { waitUntil: 'domcontentloaded' });
      if (errors.length) throw new Error(id + ': ' + errors[0]);
      pages[id] = page;
    }
    for (const p of job.panels) {
      let shot;
      if (p.kind === 'join') {
        const a = await frameAt(pages[p.draw.a.style], p.draw.a.t);
        shot = await frameAt(pages[p.draw.b.style], p.draw.b.t, a.url);
        shot.note = [a.note, shot.note].filter(Boolean).join('; ');
      } else shot = await frameAt(pages[p.draw.style], p.draw.t);
      fs.writeFileSync(path.join(job.out, p.id + '.png'), Buffer.from(shot.url.split(',')[1], 'base64'));
      if (shot.note) notes[p.id] = shot.note;
    }
  } finally { await browser.close(); }
  process.stdout.write(JSON.stringify({ notes }));
})().catch(e => { console.error(String(e && e.message || e)); process.exit(1); });
