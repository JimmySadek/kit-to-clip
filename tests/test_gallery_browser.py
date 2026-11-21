"""Real browser checks. Source scripts/env.sh first; uses the installed bundled headless shell."""
import functools
import base64
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO if (REPO / 'SKILL.md').exists() else REPO / 'addons/kit-to-clip'

SCRIPT = r'''
const assert = require('node:assert/strict');
const puppeteer = require(process.env.REEL_STUDIO + '/node_modules/puppeteer-core');
(async () => {
  const browser = await puppeteer.launch({executablePath: process.env.HYPERFRAMES_BROWSER_PATH, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage']});
  try {
    const page = await browser.newPage();
    const remote = [], errors = [];
    await page.setRequestInterception(true);
    page.on('request', request => {
      if (!request.url().startsWith(process.env.GALLERY_URL)) {
        remote.push(request.url()); request.abort();
      } else request.continue();
    });
    page.on('pageerror', error => errors.push(String(error)));
    await page.setViewport({width: 1440, height: 1000});
    await page.goto(process.env.GALLERY_URL, {waitUntil: 'networkidle0'});
    assert.equal(await page.$$eval('.sample', els => els.length), 15);
    assert.match(await page.$eval('#results', el => el.textContent), /15 of 86/);
    assert.equal(await page.$eval('#grid', el => getComputedStyle(el).gridTemplateColumns.split(' ').length), 3);
    assert.equal(await page.$$eval('.sample a', els => els.length), 30);
    assert.match(await page.$eval('.sample .kind', el => el.textContent), /Neutral demo/);
    assert.match(await page.$eval('.sample .kind', el => el.textContent), /Local reference study/);
    assert.equal(await page.$$eval('video[src^="https:"], img[src^="https:"]', els => els.length), 0);
    await page.click('#more');
    assert.equal(await page.$$eval('.sample', els => els.length), 30);
    await page.click('#all');
    assert.equal(await page.$$eval('.sample', els => els.length), 86);
    await page.type('#search', 'pixel');
    const matched = await page.$$eval('.sample', els => els.length);
    assert.ok(matched > 0 && matched < 86);
    assert.ok(await page.$('.reason'));
    await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {value: undefined, configurable: true}));
    await page.click('.sample .copy');
    assert.equal(await page.$eval('#copy-fallback', el => el.hidden), false);
    const request = await page.$eval('#request-text', el => el.value);
    assert.match(request, /library:/);
    assert.match(request, /original look/);
    assert.doesNotMatch(request, /choose the brand first/);
    await page.click('#close-copy');
    await page.$eval('#search', el => { el.value = ''; el.dispatchEvent(new Event('input')); });
    await page.click('[data-category="saved"]');
    assert.equal(await page.$$eval('.sample', els => els.length), 1);
    assert.match(await page.$eval('.sample', el => el.textContent), /previous-brand/);
    assert.match(await page.$eval('.sample', el => el.textContent), /Draft/);
    await page.click('.sample .copy');
    assert.match(await page.$eval('#request-text', el => el.value), /still a draft/);
    await page.click('#close-copy');
    await page.click('[data-category="legacy"]');
    assert.ok(await page.$('.sample'));
    await page.setViewport({width: 390, height: 844});
    await page.select('#category', 'library');
    assert.equal(await page.$eval('#grid', el => getComputedStyle(el).gridTemplateColumns.split(' ').length), 1);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.click('#new-direction');
    assert.match(await page.$eval('#request-text', el => el.value), /new video direction/);
    await page.goto(process.env.GALLERY_URL + 'branded/', {waitUntil:'networkidle0'});
    assert.match(await page.$eval('.sample .kind', el => el.textContent), /Your brand/);
    assert.match(await page.$eval('.sample .kind', el => el.textContent), /Local reference study/);
    assert.deepEqual(errors, []);
    assert.deepEqual(remote, []);
    console.log(JSON.stringify({desktop_columns:3, phone_columns:1, initial:15, all:86, remote_requests:remote.length,
      copy_request:true, drafts:true, new_direction:true, errors}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
'''


class GalleryBrowserTests(unittest.TestCase):
    def test_discovery_controls_and_copy_requests_without_remote_requests(self):
        engine = os.environ.get('REEL_STUDIO')
        chrome = os.environ.get('HYPERFRAMES_BROWSER_PATH')
        if not engine or not chrome:
            self.skipTest('Source Kit to Clip scripts/env.sh to run the actual browser test')
        self.assertNotIn('/Applications/Google Chrome.app', chrome)
        spec = importlib.util.spec_from_file_location('gallery_browser', SKILL / 'scripts/gallery.py')
        gallery = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gallery)
        with tempfile.TemporaryDirectory(prefix='kit-gallery-browser-') as tmp:
            base = Path(tmp)
            style = base / 'styles' / 'draft'
            style.mkdir(parents=True)
            (style / 'style.json').write_text(json.dumps({'slug':'draft', 'title':'My paper', 'status':'draft',
                'brand':'previous-brand', 'kind':'reference', 'tags':['paper']}))
            items = gallery.catalog(base, styles_root=base / 'styles')
            out = base / 'gallery'
            (base/'poster.png').write_bytes(base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aDz4AAAAASUVORK5CYII='))
            manifest=base/'samples.json'
            manifest.write_text(json.dumps({'schema':1,'samples':[{'id':'library:flat-space',
                'kind':'neutral-demo','poster':'poster.png'}]}))
            gallery.build(out, items, samples=manifest)
            branded=base/'brand-samples.json'
            branded.write_text(json.dumps({'schema':1,'samples':[{'id':'library:flat-space',
                'kind':'brand','brand':'acme','poster':'poster.png'}]}))
            gallery.build(out/'branded',items,brand='acme',samples=branded)
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
            with http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    result = subprocess.run(['node', '-e', SCRIPT], text=True, capture_output=True,
                        env={**os.environ, 'GALLERY_URL':f'http://127.0.0.1:{server.server_port}/'}, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(json.loads(result.stdout)['remote_requests'], 0)
                finally:
                    server.shutdown()
                    thread.join()


if __name__ == '__main__':
    unittest.main()
