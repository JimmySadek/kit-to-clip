/* Kit to Clip Studio page. Plain JS, no build step, served by studio.py.
   The film lives in film.json through the server; localStorage keeps only the last room you looked at. */
(function () {
  'use strict';

  const ROOMS = [
    { id: 'start',  num: '⓪', name: 'Start',      you: 'Drop or paste what you have. The Studio opens the right room.' },
    { id: 'story',  num: '①', name: 'Story',      you: 'Pick a story idea, shape the beats, write the script for the voice.' },
    { id: 'styles', num: '②', name: 'Styles',     you: 'Put styles on the story, set the brand per part, choose each join.' },
    { id: 'voice',  num: '③', name: 'Voice',      you: 'Voice each segment, drop the files back, check the word timings.' },
    { id: 'board',  num: '④', name: 'Storyboard', you: 'Look at every panel in its style, comment, then approve.' },
    { id: 'music',  num: '⑤', name: 'Music',      you: 'Check the music keywords, play 3 takes per cue on the picture, pick by ear.' },
    { id: 'finish', num: '⑥', name: 'Finish',     you: 'Choose formats and captions, then watch and hear the finished film.' },
  ];
  const STOPS = [
    ['script', '✋ Script', 'When Kit to Clip wrote the story: your yes on the script.'],
    ['storyboard', '✋ Storyboard', 'One yes covers layout, look, brand and joins, before the film is built.'],
    ['music', '✋ Music pick', 'After the picture is built: 3 takes per cue on the picture, you pick by ear.'],
    ['final', '✋ Final film', 'You watch and hear the finished film once. Listening is part of this yes.'],
  ];
  const ROUTES = [
    ['inspiration', 'An inspiration (a link, a reference film, "something like this")', 'story', '2-3 story ideas in the spirit of the reference, plus styles that match its look'],
    ['idea', 'An idea or a topic', 'story', '2-3 story ideas, then beats and a script'],
    ['script', 'A finished script', 'styles', 'Your script split into story parts, ready to style'],
    ['voice', 'A voice file', 'voice', 'Word timings already on the timeline'],
    ['footage', 'Footage', 'finish', 'Trim, captions, an animated opening or ending'],
  ];
  const KIND_ROOM = { script: 'styles', voice: 'voice', cues: 'music', footage: 'finish', inspiration: 'story', idea: 'story' };
  const LAST_ROOM = 'kit-to-clip-studio-room';

  let film = null, info = {}, lib = { atlas: false, styles: [], families: [], joins: { types: {}, suggest: [] } }, brands = [];
  let filmStamp = 0, writing = 0, writes = 0, pendingReload = false, watching = false, offline = false;
  let lastAnswer = Date.now(), closed = null, poller = null, approvals = {};
  let board = { version: 0, panels: [] }, musicRes = { version: 0, cues: {} }, finishRes = { finish: null, render: null }, resultsStamp = null;
  const ui = { room: 'start', dropped: [], uploads: [], brush: null, openJoin: null, drawer: false, query: '', build: null, otherBrand: false, notYet: null, delPart: null, lastSeg: null, words: {}, voicing: {}, safe: null, cdraft: {} };

  /* ---------- helpers ---------- */
  const $ = (sel, root) => (root || document).querySelector(sel);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sec = t => (Math.round(t * 10) / 10).toFixed(1) + ' s';
  const span = (a, b) => a.toFixed(1) + '–' + b.toFixed(1) + ' s';
  const room = id => ROOMS.find(r => r.id === id) || ROOMS[0];
  const roomLabel = id => room(id).num + ' ' + room(id).name;
  const base = p => String(p || '').split('/').pop();
  const kb = n => (n / 1024).toFixed(1) + ' KB';

  function toast(msg) {
    const t = $('#toast'); t.textContent = msg; t.classList.add('on');
    clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('on'), 2600);
  }
  function copyText(text, label) {
    const done = () => toast('Copied: ' + label);
    const fallback = () => {
      const ta = document.createElement('textarea'); ta.value = text; ta.setAttribute('readonly', '');
      ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select();
      let ok = false; try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      ta.remove(); ok ? done() : toast('Copy was blocked by the browser. Select the text and copy it by hand.');
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, fallback);
    else fallback();
  }

  /* ---------- server ---------- */
  async function getJSON(path) {
    const r = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
    if (!r.ok) throw new Error(path + ': ' + r.status);
    return r.json();
  }
  async function post(path, body, headers) {
    const r = await fetch(path, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: Object.assign({ 'Content-Type': 'application/json' }, headers || {}),
      body: body instanceof Blob ? body : JSON.stringify(body),
    });
    let data = null; try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok) throw new Error((data && data.error) || ('The Studio answered ' + r.status));
    return data;
  }
  /* Replace whole top-level sections of film.json (start, styles, rooms). */
  async function saveSections(sections) {
    Object.assign(film, sections);
    writing++; writes++;
    try {
      const r = await post('/api/film', sections, { 'X-Film-Base': String(filmStamp) });
      filmStamp = r.changed ? 0 : r.film;   // Claude wrote in between: the next poll loads the merged file
      if (r.reopened && r.reopened.length) {
        toast(r.reopened.map(x => x.name + ' is open again: ' + x.changed.join(', ') + ' changed').join('. ') + '.');
        loadApprovals().then(() => render(true));
      }
      return true;
    }
    catch (e) { toast('Not saved: ' + e.message); filmStamp = 0; return false; }   // the next poll reloads the saved file
    finally { writing--; }
  }
  function logEvent(kind, detail) {
    post('/api/event', { kind, room: ui.room, detail: detail || {} }).catch(() => { /* the click still counts in the page */ });
  }
  function markDraft(id) {
    const rooms = Object.assign({}, film.rooms || {});
    if ((rooms[id] || 'empty') === 'empty') { rooms[id] = 'draft'; return { rooms }; }
    return {};
  }

  /* ---------- film structure ---------- */
  function normal(f) {
    f.styles = Object.assign({ shortlist: [], map: {}, joins: {} }, f.styles);
    f.styles.map = asIsWithoutBrand(f.styles.map, f.brand);
    return f;
  }
  /* No brand: every part is as is, whatever the map, a preset or Claude wrote. */
  function asIsWithoutBrand(map, brand) {
    if (brand && brand.name) return map;
    const out = {};
    Object.entries(map || {}).forEach(([k, m]) => { out[k] = m && typeof m === 'object' ? Object.assign({}, m, { brand: 'as-is' }) : m; });
    return out;
  }
  const parts = () => film.parts || [];
  const length = () => film.length || (parts().length ? parts()[parts().length - 1].to : 0) || 1;
  const pct = t => (t / length() * 100).toFixed(3) + '%';
  const cols = items => items.map(x => Math.max(0.01, x.to - x.from).toFixed(2) + 'fr').join(' ');
  const styleOf = id => lib.styles.find(s => s.id === id);
  const styleName = id => (styleOf(id) || { name: id }).name;
  function styleShort(id) {
    const words = styleName(id).split(/\s+/).filter(w => !/^\d/.test(w));
    return words[0] || styleName(id);
  }
  const SWATCH = ['#9aa1a6', '#8fc0ff', '#7fb08a', '#e59a6a', '#c9a6e8', '#e8d07a', '#7fc9c4', '#e89aa6'];
  function styleColor(id) {
    const order = [...(film.styles && film.styles.shortlist || [])];
    Object.values(film.styles && film.styles.map || {}).forEach(m => { if (!order.includes(m.style)) order.push(m.style); });
    const i = order.indexOf(id);
    return SWATCH[(i < 0 ? 0 : i) % SWATCH.length];
  }
  const mapOf = pid => (film.styles && film.styles.map || {})[pid];
  function runs() {
    const out = [];
    parts().forEach(p => {
      const st = (mapOf(p.id) || {}).style || null, last = out[out.length - 1];
      if (last && last.style === st) { last.to = p.to; last.parts.push(p.id); }
      else out.push({ style: st, from: p.from, to: p.to, parts: [p.id] });
    });
    const seen = {};
    out.forEach(r => { if (r.style) { r.returns = !!seen[r.style]; seen[r.style] = true; } });
    return out;
  }
  function suggest(from, to) {
    const facts = { from_family: (styleOf(from) || {}).family, to_family: (styleOf(to) || {}).family };
    for (const rule of lib.joins.suggest || []) {
      if (Object.entries(rule.when || {}).every(([k, v]) => facts[k] === v)) return rule.order;
    }
    return Object.keys(lib.joins.types || {});
  }
  /* Joins come from the map: one wherever two neighbouring parts have different styles. */
  function joinsList() {
    const out = [], ps = parts(), picks = film.styles && film.styles.joins || {};
    for (let i = 1; i < ps.length; i++) {
      const a = mapOf(ps[i - 1].id), b = mapOf(ps[i].id);
      if (!a || !b || a.style === b.style) continue;
      const opts = suggest(a.style, b.style), pick = picks[ps[i].id] && picks[ps[i].id].type;
      out.push({ at: ps[i].from, part: ps[i].id, from: a.style, to: b.style, opts,
        pick: lib.joins.types[pick] ? pick : opts[0], chosen: !!lib.joins.types[pick] });
    }
    return out;
  }
  const joinName = type => (lib.joins.types[type] || { name: type }).name;

  /* ---------- top: rooms, ribbon ---------- */
  function roomState(id) {
    const st = (film.rooms || {})[id] || 'empty';
    if (id === 'board') {
      if (approvals.storyboard && approvals.storyboard.state === 'approved') return 'done';
      if (st === 'empty' && board && board.panels && board.panels.length) return 'draft';
    } else if (id === 'music') {
      if (approvals.music && approvals.music.state === 'approved') return 'done';
      if (st === 'empty' && musicRes && musicRes.cues && Object.keys(musicRes.cues).length) return 'draft';
    } else if (id === 'finish') {
      if (approvals.final && approvals.final.state === 'approved') return 'done';
      if (st === 'empty' && ((finishRes.finish && finishRes.finish.video) || (finishRes.render && finishRes.render.picture))) return 'draft';
    }
    return st;
  }
  function renderTop() {
    $('#filmTitle').textContent = film.title || 'Untitled film';
    const fr = film.frame || {};
    $('#filmMeta').textContent = [film.about, film.length ? film.length + ' s' : '', fr.width ? fr.width + '×' + fr.height : ''].filter(Boolean).join(', ');
    document.title = (film.title ? film.title + ' · ' : '') + 'Kit to Clip Studio';
    $('#rooms').innerHTML = ROOMS.map(r => {
      const st = roomState(r.id);
      const cls = st === 'done' ? 'approved' : st;
      return '<button class="room-tab" data-act="go" data-room="' + r.id + '"' + (ui.room === r.id ? ' aria-current="page"' : '') +
        ' title="' + esc(r.you) + '"><span class="room-num">' + r.num + '</span><span class="room-name">' + r.name + '</span>' +
        '<span class="room-state"><span class="dot ' + cls + '"></span><span class="state-' + cls + '">' + esc(st) + '</span></span></button>';
    }).join('');
    renderRibbon();
  }
  function ticks() {
    const L = length(), step = L > 90 ? 20 : L > 40 ? 10 : 5, t = [];
    for (let x = 0; x < L - step / 2; x += step) t.push(x);
    t.push(L);
    return '<div class="ticks">' + t.map(x => '<span style="left:' + pct(x) + '">' + (x === L ? sec(x) : x + 's') + '</span>').join('') + '</div>';
  }
  function renderRibbon() {
    const ps = parts();
    if (!ps.length) {
      $('#ribbon').innerHTML = '<span class="ribbon-label">Story</span><span class="ribbon-label">No story parts yet. Claude adds them to film.json from your script.</span>';
      return;
    }
    const rn = runs(), js = joinsList();
    $('#ribbon').innerHTML =
      '<span class="ribbon-label">Story</span><div class="lane parts" style="grid-template-columns:' + cols(ps) + '">' +
        ps.map((p, i) => '<button class="seg" data-act="go" data-room="styles" title="' + esc(p.name + ', ' + span(p.from, p.to)) + '"><span class="t">' + (i + 1) + ' ' + esc(p.name) + '</span></button>').join('') + '</div>' +
      '<span class="ribbon-label">Style</span><div class="lane style" style="grid-template-columns:' + cols(rn) + '">' +
        rn.map(r => r.style
          ? '<button class="seg" data-act="go" data-room="styles" style="background:' + styleColor(r.style) + '" title="' + esc(styleName(r.style)) + '"><span class="lg">' + esc(styleName(r.style)) + '</span><span class="sm">' + esc(styleShort(r.style)) + '</span></button>'
          : '<button class="seg" data-act="go" data-room="styles" style="background:var(--well-2);color:var(--well-ink-2);font-weight:500" title="No style yet"><span class="lg">No style yet</span><span class="sm">None</span></button>').join('') +
        '<div class="joins-over">' + js.map(j => '<button class="join-pin" data-act="join" data-part="' + esc(j.part) + '" style="left:' + pct(j.at) + '" title="Join at ' + sec(j.at) + ': ' + esc(joinName(j.pick)) + '" aria-label="Join at ' + sec(j.at) + '"></button>').join('') + '</div></div>' +
      '<span class="ribbon-label">Music cues</span><div class="lane cues" style="grid-template-columns:' + cols(rn) + '">' +
        rn.map(r => {
          const cid = r.style, c = cid ? cueOf(cid) : null;
          if (!cid) return '<span class="seg later">No style yet</span>';
          const lbl = (c && c.name ? c.name : styleShort(cid) + ' world') + (r.returns ? ' returns' : '') + (c && c.bpm ? ', ' + c.bpm + ' beats a minute' : '');
          return '<button class="seg' + (r.returns ? ' returns' : '') + '" data-act="go" data-room="music" title="' + esc(lbl) + '"><span>' + esc(lbl) + '</span></button>';
        }).join('') + '</div>' +
      '<span></span>' + ticks();
  }

  /* ---------- rooms ---------- */
  function head(id, side) {
    const r = room(id);
    return '<div class="room-head"><div><h1 class="room-title"><span class="n">' + r.num + '</span>' + r.name + '</h1>' +
      '<p class="room-you">' + esc(r.you) + '</p></div>' + (side ? '<div class="head-side">' + side + '</div>' : '') + '</div>' +
      (r.phase ? '<div class="later-strip"><b>Coming in Phase ' + r.phase + '.</b> Nothing here is saved. Work on this room in chat as before.</div>' : '');
  }

  function detect() {
    for (const f of ui.dropped) {
      const k = { voice: 'A voice file', footage: 'Footage', inspiration: 'An inspiration image', script: 'A script file' }[f.kind];
      if (k) return [f.kind, k + ': ' + base(f.path)];
    }
    const t = ((film.start || {}).pasted || '').trim();
    if (!t) return null;
    if (/^https?:\/\//i.test(t) || /youtu|vimeo|instagram|tiktok/i.test(t)) return ['inspiration', 'A link to an inspiration'];
    const sentences = (t.match(/[.!?](\s|$)/g) || []).length;
    if (t.length > 280 || sentences >= 4 || t.split('\n').length > 4) return ['script', 'A script (' + t.split(/\s+/).length + ' words)'];
    return ['idea', 'An idea or a topic'];
  }
  function detectHtml(d) {
    if (!d) return '';
    const to = ROUTES.find(r => r[0] === d[0])[2];
    return '<div class="detect">Found: <b>' + esc(d[1]) + '</b>. Opens at <b>' + roomLabel(to) + '</b>. <button class="btn small" data-act="go" data-room="' + to + '">Open ' + room(to).name + '</button></div>';
  }
  function roomStart() {
    const d = detect(), inputs = film.inputs || [];
    const max = info.max_upload ? Math.round(info.max_upload / 1048576) + ' MB' : '500 MB';
    return head('start') +
      '<div class="two"><div>' +
        '<div class="drop" id="drop"><div class="block-h">Drop or paste anything</div>' +
        '<p class="sub" style="margin:0">An idea, a link, a script, a voice file, footage or a brand. The Studio reads it and opens the right room.</p>' +
        '<textarea id="paste" data-field="paste" placeholder="Paste here, or drop files on this box. Try a link, one line of an idea, or a full script.">' + esc((film.start || {}).pasted || '') + '</textarea>' +
        '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><label class="btn ghost small file-pick">Choose files<input type="file" id="filePick" multiple></label>' +
        '<span class="hint">Dropped files are copied into <b>inputs/</b> in the video folder, up to ' + max + ' each.</span></div>' +
        (ui.uploads.length ? '<ul class="uploads">' + ui.uploads.map(u => '<li class="' + (u.bad ? 'bad' : '') + '">' + esc(u.text) + '</li>').join('') + '</ul>' : '') +
        '<div id="detectBox">' + detectHtml(d) + '</div>' +
        '</div></div>' +
        '<div class="block"><h2>This film already has</h2>' +
        (inputs.length
          ? '<p class="sub">From film.json. Files stay where they are; nothing here is asked again.</p><ul class="have">' + inputs.map(h => {
              const to = KIND_ROOM[h.kind];
              return '<li><span>✅</span><span>' + esc(h.note || base(h.path)) + ' <span class="kind">' + esc(h.kind) + '</span><br><span class="file" title="' + esc(h.path) + '">' + esc(base(h.path)) + '</span></span>' +
                (to ? '<button class="btn ghost small" data-act="go" data-room="' + to + '">' + room(to).name + '</button>' : '<span></span>') + '</li>';
            }).join('') + '</ul>'
          : '<p class="sub" style="margin:0">Nothing yet. Drop or paste what you have.</p>') +
        '</div>' + brandBlock() +
      '</div>' +
      '<div class="block" style="margin-top:16px"><h2>What you bring decides where the Studio opens</h2>' +
      '<table class="route"><thead><tr><th>You bring</th><th>Opens at</th><th>You get</th></tr></thead><tbody>' +
      ROUTES.map(r => '<tr' + (d && d[0] === r[0] ? ' class="hit"' : '') + '><td>' + esc(r[1]) + '</td><td><button class="btn ghost small" data-act="go" data-room="' + r[2] + '">' + roomLabel(r[2]) + '</button></td><td>' + esc(r[3]) + '</td></tr>').join('') +
      '</tbody></table></div>';
  }

  /* ---------- the film's brand: picked here, used per part in Styles ---------- */
  function brandBlock() {
    const b = film.brand, opts = brands.slice();
    if (b && b.skill && !opts.some(o => o.skill === b.skill)) opts.push({ skill: b.skill, name: b.name, from_film: true });
    const sel = ui.otherBrand || (b && b.other) ? 'other' : b ? b.skill : '';
    const opt = (key, label, sub, on) => '<button class="brand-opt" data-act="pickbrand" data-skill="' + esc(key) + '" aria-pressed="' + on + '"><strong>' + esc(label) + '</strong>' + (sub ? '<span>' + esc(sub) + '</span>' : '') + '</button>';
    const other = sel === 'other';
    return '<div class="block" id="brandBlock" tabindex="-1" style="margin-top:16px"><h2>Brand</h2>' +
      '<p class="sub">The film\'s one brand. In the Styles room each part then uses it fully, for colours only, or not at all.</p>' +
      '<div class="brand-opts">' + opt('', 'No brand', 'Every style as it is', sel === '') +
        opts.map(o => opt(o.skill, o.name, o.skill + (o.from_film ? ', named in film.json' : o.pack ? ', has a video pack' : ''), sel === o.skill)).join('') +
        '<button class="brand-opt" data-act="otherbrand" aria-pressed="' + other + '"><strong>Another brand</strong><span>Claude asks you for its guide</span></button></div>' +
      (other ? '<div class="other-brand"><input type="text" id="otherBrand" maxlength="120" aria-label="The brand\'s name" placeholder="The brand\'s name" value="' + esc(b && b.other ? b.name : '') + '"><button class="btn small" data-act="saveother">Use this brand</button></div>' : '') +
      (opts.length ? '' : '<p class="hint" style="margin:8px 0 0">No brand skill was found on this computer. Pick Another brand, or keep No brand.</p>') +
      '</div>';
  }
  async function setBrand(brand) {
    const sections = { brand };
    if (!brand) {                                    // no brand: every part keeps its style as it is
      film.styles.map = asIsWithoutBrand(film.styles.map, null); sections.styles = film.styles;
    }
    ui.otherBrand = false;
    if (!await saveSections(sections)) return;     // the error toast stays; the poll reloads the saved brand
    logEvent('brand-pick', { brand: brand ? (brand.skill || brand.name) : null, other: !!(brand && brand.other) });
    render(true);
    const f = brand && brand.other ? $('[data-act="otherbrand"]') : $('[data-act="pickbrand"][data-skill="' + (brand ? CSS.escape(brand.skill) : '') + '"]');
    if (f) f.focus();
    toast(brand ? 'Brand: ' + brand.name + '.' : 'No brand. Every part stays as is.');
  }
  function openBrand() {
    if (ui.room !== 'start') go('start');
    const el = $('#brandBlock'); if (el) { el.scrollIntoView({ block: 'center' }); el.focus({ preventScroll: true }); }
  }
  const brandRef = () => film.brand && film.brand.skill ? 'the ' + film.brand.skill + ' brand skill' : 'its brand guide (ask me for it)';

  /* ---------- ② Styles ---------- */
  const NO_ATLAS = 'Live preview needs the private style folder (one line in ~/.config/kit-to-clip/config.json).';
  const brandModes = () => film.brand && film.brand.name ? ['brand', 'palette', 'as-is'] : ['as-is'];
  function brandLabel(mode) {
    const name = film.brand && film.brand.name;
    if (mode === 'brand') return { lg: name || 'Brand', sm: (name || 'B').split(/\s+/).map(w => w[0]).join('').slice(0, 3), line: 'Branded with ' + (name || 'the brand') + ', from ' + brandRef() + ': colours, fonts, logo.' };
    if (mode === 'palette') return { lg: 'Palette only', sm: 'Pal', line: 'Brand colours only. The style keeps its own fonts and look.' };
    return { lg: 'As is', sm: 'As is', line: 'The style exactly as it is. No brand.' };
  }
  const brandClass = mode => mode === 'as-is' ? 'asis' : mode;
  const shortlist = () => (film.styles && film.styles.shortlist) || [];
  function preview(id) {
    const s = styleOf(id) || { name: id, family: '' };
    if (!lib.atlas || !styleOf(id)) {
      return '<div class="preview"><div class="no-preview"><b>' + esc(s.name) + '</b><span>' + esc(s.family) + '</span><span>' + esc(NO_ATLAS) + '</span></div></div>';
    }
    const src = '/preview/' + encodeURIComponent(id);
    return '<div class="preview"><iframe sandbox="allow-scripts" title="' + esc(s.name) + ', live preview" ' +
      'data-src="' + src + '" tabindex="-1"></iframe></div>';
  }
  function styleCard(id, used) {
    const s = styleOf(id) || { name: id, family: '', look: [] };
    return '<div class="card-wrap"><div class="style-card" role="button" tabindex="0" draggable="true" data-act="brush" data-style="' + esc(id) + '" aria-pressed="' + (ui.brush === id) + '" aria-label="' + esc(s.name) + ': pick to paint">' +
      preview(id) +
      '<span class="nm"><strong>' + esc(s.name) + '</strong><span class="used"' + (used[id] ? '' : ' hidden') + '>on the film</span></span>' +
      '<span class="line">' + esc((s.look || []).slice(0, 4).join(', ')) + '</span></div>' +
      '<span class="card-meta">' +
      (lib.atlas && styleOf(id) ? '<button class="linkish" data-act="demo" data-style="' + esc(id) + '">Play the demo</button>' : '<span></span>') +
      '<button class="linkish drop-style" data-act="unshort" data-style="' + esc(id) + '" title="Take ' + esc(s.name) + ' off the shortlist" aria-label="Take ' + esc(s.name) + ' off the shortlist">×</button></span></div>';
  }
  function usedStyles() {
    const used = {};
    parts().forEach(p => { const m = mapOf(p.id); if (m) used[m.style] = true; });
    return used;
  }
  function shortlistHtml() {
    const used = usedStyles();
    const ids = shortlist();
    return '<h2>Shortlist</h2><p class="sub">Drag a style onto a story part below. Or click a style, then click the parts to paint it. Point at a style to see it move.</p>' +
      '<div class="shortlist">' + (ids.length ? ids.map(id => styleCard(id, used)).join('') : '<p class="hint shortlist-empty">No styles yet. Browse all ' + lib.styles.length + ' and add a few.</p>') + '</div>' +
      '<div style="margin-top:10px"><button class="btn ghost small" data-act="drawer" aria-expanded="' + ui.drawer + '">' + (ui.drawer ? 'Close the library' : 'Browse all ' + lib.styles.length + ' styles') + '</button></div>' +
      (ui.drawer ? drawerHtml() : '');
  }
  function drawerHtml() {
    const fams = lib.families.length ? lib.families : [...new Set(lib.styles.map(s => s.family))];
    return '<div class="drawer" id="drawer"><div class="drawer-top"><input type="search" id="libSearch" placeholder="Search by name, look, motion or subject: chalk, neon, history…" aria-label="Search the styles" value="' + esc(ui.query) + '"><span class="hint" id="libCount"></span></div>' +
      fams.map(f => {
        const ss = lib.styles.filter(s => s.family === f).sort((a, b) => (a.order || 0) - (b.order || 0));
        if (!ss.length) return '';
        return '<section data-family="' + esc(f) + '"><h3 class="family">' + esc(f) + ' <span>' + ss.length + '</span></h3><div class="lib">' + ss.map(s => {
          const on = shortlist().includes(s.id);
          const tags = [].concat(s.look || [], s.motion || [], s.explains || [], s.fit || []);
          return '<article class="lib-card" data-id="' + esc(s.id) + '" data-text="' + esc((s.name + ' ' + s.family + ' ' + tags.join(' ')).toLowerCase()) + '">' +
            preview(s.id) + '<strong>' + esc(s.name) + '</strong><span class="tags">' + esc((s.look || []).slice(0, 5).join(', ')) + '</span>' +
            (on ? '<span class="used">On the shortlist</span>' : '<button class="btn ghost small" data-act="short" data-style="' + esc(s.id) + '">Add to shortlist</button>') + '</article>';
        }).join('') + '</div></section>';
      }).join('') + '</div>';
  }
  function filterDrawer() {
    const q = ui.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let n = 0;
    document.querySelectorAll('.lib-card').forEach(c => { const hit = q.every(w => c.dataset.text.includes(w)); c.hidden = !hit; if (hit) n++; });
    document.querySelectorAll('#drawer section').forEach(s => { s.hidden = !s.querySelector('.lib-card:not([hidden])'); });
    const el = $('#libCount'); if (el) el.textContent = n + ' of ' + lib.styles.length;
    watchPreviews();
  }
  function mapHtml() {
    const ps = parts(), js = joinsList(), open = js.find(j => j.part === ui.openJoin);
    if (!ps.length) return '<h2>Mix and match on the story</h2><p class="hint">No story parts yet. Claude adds them to film.json from your script.</p>';
    const presets = Object.entries(film.presets || {});
    const current = JSON.stringify(film.styles.map || {});
    return '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px"><h2 style="margin:0">Mix and match on the story</h2>' +
      '<div class="presets">' + (presets.length ? '<span class="hint">Start from</span>' : '') +
        presets.map(([k, p]) => '<button class="btn ghost small" data-act="preset" data-k="' + esc(k) + '" aria-pressed="' + (JSON.stringify(asIsWithoutBrand(p.map, film.brand)) === current) + '">' + esc(p.label || k) + '</button>').join('') +
        '<button class="btn ghost small" data-act="clear">Clear map</button></div></div>' +
      '<div class="timeline"><div class="tl">' +
        '<span class="tl-label">Story</span><div class="lane story" style="grid-template-columns:' + cols(ps) + '">' + ps.map((p, i) => '<div class="cell" title="' + esc((i + 1) + ' ' + p.name + ', ' + span(p.from, p.to)) + '"><b>' + (i + 1) + '<span class="pname"> ' + esc(p.name) + '</span></b><span>' + span(p.from, p.to) + '</span></div>').join('') + '</div>' +
        '<span class="tl-label">Style<br><span style="font-size:11px">drop here</span></span><div class="lane stylel" style="grid-template-columns:' + cols(ps) + '">' + ps.map((p, i) => {
          const m = mapOf(p.id), hint = ui.brush ? 'Click to paint ' + styleName(ui.brush) + ' here' : 'Drag a style here, or pick one above first';
          return m
            ? '<button class="cell" data-act="paint" data-part="' + esc(p.id) + '" style="background:' + styleColor(m.style) + '" title="' + esc(styleName(m.style) + '. ' + hint) + '" aria-label="Part ' + (i + 1) + ': ' + esc(styleName(m.style)) + '"><span class="lg">' + esc(styleName(m.style)) + '</span><span class="sm">' + esc(styleShort(m.style)) + '</span></button>'
            : '<button class="cell empty" data-act="paint" data-part="' + esc(p.id) + '" title="' + esc('No style yet. ' + hint) + '" aria-label="Part ' + (i + 1) + ': no style yet"><span class="lg">No style yet</span><span class="sm">None</span></button>';
        }).join('') + '</div>' +
        '<button class="tl-label lane-link" data-act="brandpick" title="Choose the film\'s brand in the Start room">Brand<br><span style="font-size:11px">' + (film.brand && film.brand.name ? esc(film.brand.name) + ', click to change' : 'none, click to set') + '</span></button><div class="lane brandl" style="grid-template-columns:' + cols(ps) + '">' + ps.map((p, i) => {
          const m = mapOf(p.id);
          if (!m) return '<span class="cell"></span>';
          const b = brandLabel(m.brand), only = brandModes().length === 1;
          return '<button class="cell" data-act="brandmode" data-part="' + esc(p.id) + '"' + (only ? ' disabled' : '') + ' title="' + esc(b.line + (only ? '' : ' Click to change.')) + '" aria-label="Part ' + (i + 1) + ' brand: ' + esc(b.lg) + '"><span class="brand-chip ' + brandClass(m.brand) + '"><span class="lg">' + esc(b.lg) + '</span><span class="sm">' + esc(b.sm) + '</span></span></button>';
        }).join('') + '</div>' +
        '<span class="tl-label">Joins ◆</span><div class="lane joinl">' + (js.length ? js.map((j, k) => '<button class="join-btn' + (j.at / length() > 0.85 ? ' end' : '') + '" data-act="join" data-part="' + esc(j.part) + '" aria-expanded="' + (ui.openJoin === j.part) + '" style="left:' + pct(j.at) + ';top:' + (k % 2 ? 72 : 28) + '%" title="Join at ' + sec(j.at) + '"><i></i>' + esc(joinName(j.pick)) + '</button>').join('')
          : '<span class="hint" style="color:var(--well-ink-2)">' + (Object.keys(film.styles.map || {}).length ? 'One style on the whole film, so there is no join.' : 'Joins appear where the style changes.') + '</span>') + '</div>' +
      '</div>' +
      (open ? joinPop(open) : '') +
      '<p class="map-read" id="mapRead">Reading the map: ' + readMap() + '</p></div>' +
      '<p class="hint" style="margin:10px 0 0">' + (film.brand && film.brand.name
        ? 'Brand: <b>' + esc(film.brand.name) + '</b> applies ' + esc(brandRef()) + '. <b>Palette only</b> uses brand colours only. <b>As is</b> keeps the style untouched. '
        : 'This film has no brand, so every part stays as is. Choose one with the Brand label. ') + 'Click a ◆ to choose how one style turns into the next.</p>';
  }
  function joinPop(j) {
    return '<div class="join-pop"><h3>Join at ' + sec(j.at) + ': ' + esc(styleName(j.from)) + ' to ' + esc(styleName(j.to)) + '</h3><div class="join-opts">' +
      j.opts.map((o, i) => '<button class="join-opt" data-act="pickjoin" data-part="' + esc(j.part) + '" data-j="' + esc(o) + '" aria-pressed="' + (j.pick === o) + '"><div class="look join-look join-' + esc(o) + '"></div><strong>' + esc(joinName(o)) + '</strong><span>' + esc((lib.joins.types[o] || {}).line || '') + '</span>' + (i === 0 ? '<em>Suggested first for these two styles</em>' : '') + '</button>').join('') +
      '</div></div>';
  }
  function readMap() {
    const rn = runs(), js = joinsList();
    if (!rn.some(r => r.style)) return 'no style on the story yet.';
    let k = 0;
    return rn.map(r => {
      if (!r.style) return '<b>No style yet</b> ' + span(r.from, r.to) + ', ';
      const b = [...new Set(r.parts.map(p => brandLabel(mapOf(p).brand).lg))].join(' and ');
      const j = js[k] && js[k].at === r.to ? js[k++] : null;
      return '<b>' + esc(styleName(r.style)) + '</b> ' + span(r.from, r.to) + ' (' + esc(b) + ')' + (j ? ', ◆ ' + esc(joinName(j.pick)) + ', ' : '');
    }).join('').replace(/, $/, '') + '. ' + (js.length === 0 ? 'No switch.' : js.length === 1 ? 'One switch.' : js.length + ' switches.');
  }
  function roomStyles() {
    return head('styles', '<span class="stop-note">✋ Styles, brand and joins are approved together with the storyboard: one yes, in the Storyboard room or in chat.</span>') +
      '<div class="block" id="shortBlock">' + shortlistHtml() + '</div>' +
      '<div class="block" id="mapBlock">' + mapHtml() + '</div>';
  }
  /* Redraw only the map (and the ribbon and request), so the live previews keep running. */
  function renderMap() {
    renderTop();
    const box = $('#mapBlock'); if (box) box.innerHTML = mapHtml();
    const used = usedStyles();                     // the cards stay (their previews keep running); only the badges follow the map
    document.querySelectorAll('.style-card').forEach(c => {
      c.setAttribute('aria-pressed', String(ui.brush === c.dataset.style));
      const badge = c.querySelector('.used'); if (badge) badge.hidden = !used[c.dataset.style];
    });
    refreshPrompt();
  }
  function renderShortlist() {
    const box = $('#shortBlock'); if (box) { box.innerHTML = shortlistHtml(); filterDrawer(); }
    renderMap();
  }
  async function saveStyles(kind, detail) {
    film.styles = Object.assign({ shortlist: [], map: {}, joins: {} }, film.styles);
    await saveSections(Object.assign({ styles: film.styles }, markDraft('styles')));
    if (kind) logEvent(kind, detail);
  }
  function paint(pid, id) {
    const map = Object.assign({}, film.styles.map), old = map[pid];
    map[pid] = { style: id, brand: old && brandModes().includes(old.brand) ? old.brand : 'as-is' };
    film.styles.map = map;
    if (!shortlist().includes(id)) film.styles.shortlist = shortlist().concat([id]);
    renderMap();
    saveStyles('map', { part: pid, style: id });
  }

  /* Live previews: each card is a sandboxed frame that draws the style's hero frame with the style's own code. A frame
     loads only while its card is on screen, two load at a time, and library frames unload when they scroll away.
     Styles are written for frame-by-frame renders (often 100+ ms a frame), so only the card under the pointer or
     the keyboard moves; "Play the demo" shows the full motion. */
  const MAX_LOADING = 2, seen = new Set(), queue = [], loading = new Set();
  let hot = null;
  const io = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
    entries.forEach(e => {
      const f = e.target;
      if (e.isIntersecting) { seen.add(f); if (!f.dataset.loaded && !queue.includes(f)) queue.push(f); }
      else { seen.delete(f); if (f.closest('.lib-card')) unload(f); }
    });
    pump(); schedule();
  }, { rootMargin: '200px 0px' }) : null;
  function watchPreviews() {
    if (!io) { document.querySelectorAll('.preview iframe[data-src]').forEach(f => { f.src = f.dataset.src; f.dataset.loaded = '1'; }); return; }
    io.disconnect(); seen.clear(); queue.length = 0;
    [...loading].forEach(f => { if (!f.isConnected) loading.delete(f); });
    document.querySelectorAll('.preview iframe[data-src]').forEach(f => { if (!f.closest('[hidden]')) io.observe(f); });
  }
  function pump() {
    while (loading.size < MAX_LOADING && queue.length) {
      const f = queue.shift();
      if (!f.isConnected || !seen.has(f) || f.dataset.loaded) continue;
      loading.add(f); f.dataset.loaded = '1'; f.src = f.dataset.src;
      setTimeout(() => loaded(f), 4000);            // a frame that never answers frees its place
    }
  }
  function loaded(f) { if (loading.delete(f)) pump(); }
  function unload(f) {
    if (!f.dataset.loaded) return;
    loading.delete(f); delete f.dataset.loaded; delete f.dataset.ready; f.dataset.playing = '0';
    f.src = 'about:blank'; pump();
  }
  document.addEventListener('load', e => { if (e.target.matches && e.target.matches('.preview iframe')) loaded(e.target); }, true);
  function schedule() {
    document.querySelectorAll('.preview iframe[data-src]').forEach(f => {
      const play = f === hot && seen.has(f) && !!f.dataset.ready && !f.closest('[hidden]');
      f.dataset.playing = play ? '1' : '0';
      if (f.contentWindow && f.dataset.ready) f.contentWindow.postMessage({ k2c: play ? 'play' : 'pause' }, '*');
    });
  }
  window.addEventListener('message', e => {
    if (!e.data || e.data.k2c !== 'ready') return;
    const f = [...document.querySelectorAll('.preview iframe')].find(x => x.contentWindow === e.source);
    if (f) { f.dataset.ready = '1'; loaded(f); schedule(); }
  });
  function heat(el) {
    const card = el && el.closest && el.closest('.card-wrap, .lib-card'), f = card ? card.querySelector('.preview iframe') : null;
    if (f !== hot) { hot = f; schedule(); }
  }
  document.addEventListener('mouseover', e => heat(e.target));
  document.addEventListener('focusin', e => heat(e.target));
  document.addEventListener('mouseleave', () => heat(null));
  function openDemo(id) {
    const s = styleOf(id) || { name: id };
    $('#modal').innerHTML = '<div class="modal-box" role="dialog" aria-modal="true" aria-label="' + esc(s.name) + ' demo"><div class="modal-head"><b>' + esc(s.name) + '</b>' +
      '<span class="hint" style="color:var(--well-ink-2)">The style\'s own demo, running in a sealed frame.</span><button class="btn ghost small" data-act="close-demo">Close</button></div>' +
      '<div class="preview"><iframe sandbox="allow-scripts" title="' + esc(s.name) + ' demo" src="/preview/' + encodeURIComponent(id) + '?demo=1"></iframe></div></div>';
    $('#modal').hidden = false; $('[data-act="close-demo"]').focus();
  }
  function closeDemo() { const m = $('#modal'); if (!m.hidden) { m.hidden = true; m.innerHTML = ''; } }

  async function copyBuildPrompt(btn) {
    btn.disabled = true; const label = btn.textContent; btn.textContent = 'Composing…';
    try {
      const r = await post('/api/prompt', {});
      ui.build = { bytes: r.bytes, styles: r.styles.length, joins: r.joins, warnings: r.warnings || [] };
      copyText(r.text, 'the build prompt, ' + kb(r.bytes) + ', ' + r.styles.length + ' style' + (r.styles.length === 1 ? '' : 's') + ', ' + r.joins + ' join' + (r.joins === 1 ? '' : 's'));
      logEvent('copy-build-prompt', { bytes: r.bytes, styles: r.styles, joins: r.joins });
    } catch (e) {
      ui.build = { error: e.message };
      toast('No build prompt yet: ' + e.message);
    } finally { btn.disabled = false; btn.textContent = label; renderRail(); }
  }

  /* ---------- ① Story: edit the parts; the style map and joins follow (page/parts.js) ---------- */
  function partsHtml() {
    const ps = parts();
    if (!ps.length) return '<p class="hint" style="margin:0">No story parts yet. Claude writes them from your script.</p>';
    const field = (p, f, label, rows) => '<label class="pr-field"><span>' + label + '</span><textarea rows="' + rows + '" data-pfield="' + f + '" data-part="' + esc(p.id) + '">' + esc(p[f]) + '</textarea></label>';
    return '<ol class="part-rows">' + ps.map((p, i) => {
      const m = mapOf(p.id), last = i === ps.length - 1, del = ui.delPart === p.id;
      return '<li class="part-row" data-part="' + esc(p.id) + '"><div class="pr-head"><b class="pr-n">' + (i + 1) + '</b>' +
        '<input type="text" class="pr-name" maxlength="120" data-pfield="name" data-part="' + esc(p.id) + '" value="' + esc(p.name) + '" aria-label="Part ' + (i + 1) + ' name">' +
        '<span class="pr-time">' + sec(p.from) + ' to ' + (last ? sec(p.to)
          : '<input type="number" class="pr-end" step="0.1" min="' + (p.from + PARTS.MIN).toFixed(1) + '" max="' + (ps[i + 1].to - PARTS.MIN).toFixed(1) + '" value="' + p.to + '" data-boundary="' + i + '" aria-label="Part ' + (i + 1) + ' ends at, in seconds"> s') + '</span>' +
        '<span class="ptag">' + esc(m ? styleName(m.style) : 'No style yet') + '</span>' +
        '<span class="pr-acts"><button class="btn ghost small" data-act="splitpart" data-part="' + esc(p.id) + '" title="Cut this part in two at its middle. Both halves keep its style.">Split</button>' +
        (last ? '' : '<button class="btn ghost small" data-act="mergepart" data-part="' + esc(p.id) + '" title="Join this part with the next. The first style stays.">Merge with next</button>') +
        (ps.length > 1 ? '<button class="btn ghost small' + (del ? ' danger' : '') + '" data-act="delpart" data-part="' + esc(p.id) + '">' + (del ? 'Delete part ' + (i + 1) + '?' : 'Delete') + '</button>' : '') +
        '</span></div><div class="pr-body">' + field(p, 'words', 'Words', 2) + field(p, 'picture', 'Picture', 2) + field(p, 'sound', 'Sound', 1) + '</div></li>';
    }).join('') + '</ol>';
  }
  const story = () => Object.assign({ ideas: [], picked: null, beats: [] }, film.story);
  const script = () => Object.assign({ model: '', voice: '', segments: [] }, film.script);
  function ideasHtml() {
    const st = story();
    if (!st.ideas.length) return '<p class="hint" style="margin:0">No ideas yet. Copy the request: Claude writes 2-3 story ideas from what you brought.</p>';
    return '<div class="ideas">' + st.ideas.map(i => '<button class="idea" data-act="pickidea" data-id="' + esc(i.id) + '" aria-pressed="' + (st.picked === i.id) + '">' +
      '<strong>' + esc(i.title) + '</strong><span>' + esc(i.line) + '</span>' + (i.why ? '<em>' + esc(i.why) + '</em>' : '') + '</button>').join('') + '</div>';
  }
  function beatsHtml() {
    const b = story().beats;
    return '<ol class="beats">' + b.map((x, i) => '<li><input type="text" maxlength="2000" data-beat="' + i + '" value="' + esc(x.text) + '" aria-label="Beat ' + (i + 1) + '">' +
      '<button class="linkish" data-act="delbeat" data-i="' + i + '" aria-label="Remove beat ' + (i + 1) + '">×</button></li>').join('') + '</ol>' +
      '<button class="btn ghost small" data-act="addbeat">Add a beat</button>';
  }
  function segNotes(g) {
    const c = SCRIPT.check(g);
    return '≈ ' + SCRIPT.estimate(g.text).toFixed(1) + ' s' + (c.length ? '<span class="seg-warn">⚠️ ' + c.map(esc).join(' ') + '</span>' : '');
  }
  function scriptHtml() {
    const sc = script(), total = sc.segments.reduce((t, g) => t + SCRIPT.estimate(g.text), 0);
    return '<div class="script-meta"><label>Model <input type="text" maxlength="200" data-sfield="model" value="' + esc(sc.model) + '" placeholder="e.g. Gemini Flash TTS"></label>' +
      '<label>Voice <input type="text" maxlength="200" data-sfield="voice" value="' + esc(sc.voice) + '" placeholder="the voice name in AI Studio"></label></div>' +
      '<div class="tag-palette" role="group" aria-label="Insert a tag where the cursor is">' + SCRIPT.TAGS.map(t => '<button class="btn ghost small" data-act="tag" data-tag="' + esc(t) + '">' + esc(t) + '</button>').join('') + '</div>' +
      '<ol class="segs">' + sc.segments.map((g, i) => '<li class="seg-row" data-seg="' + esc(g.id) + '"><div class="seg-head"><b>' + esc(g.id) + '</b>' +
        '<input type="text" maxlength="300" class="seg-style" data-seg="' + esc(g.id) + '" data-segf="style" value="' + esc(g.style) + '" placeholder="Style line: short, e.g. calm documentary narrator, reflective" aria-label="Style line for ' + esc(g.id) + '">' +
        '<button class="linkish" data-act="delseg" data-seg="' + esc(g.id) + '" aria-label="Remove ' + esc(g.id) + '">×</button></div>' +
        '<textarea rows="3" maxlength="5000" data-seg="' + esc(g.id) + '" data-segf="text" aria-label="Words for ' + esc(g.id) + '">' + esc(g.text) + '</textarea>' +
        '<div class="seg-notes" id="notes-' + esc(g.id) + '">' + segNotes(g) + '</div></li>').join('') + '</ol>' +
      '<div class="seg-foot"><button class="btn ghost small" data-act="addseg">Add a segment</button><span class="hint" id="scriptTotal">' +
      (sc.segments.length ? 'All segments ≈ ' + total.toFixed(1) + ' s' + (film.length ? ' (the film is ' + film.length + ' s)' : '') : '') + '</span></div>';
  }
  function cleanCopy() { return script().segments.map(g => SCRIPT.clean(g.text)).filter(Boolean).join('\n'); }
  function roomStory() {
    const st = story();
    return head('story') +
      '<div class="block"><h2>Story ideas</h2><p class="sub">Pick one. Claude writes the beats and the script from it.</p>' + ideasHtml() + '</div>' +
      '<div class="block"><h2>Beats</h2><p class="sub">The story in a few lines, in order.' + (st.picked ? '' : ' Pick an idea first, or write your own.') + '</p>' + beatsHtml() + '</div>' +
      '<div class="block"><h2>Script for the voice</h2><p class="sub">Only spoken words. One segment per tone, a short Style line, pauses as tags, one CAPITAL word for stress, never square brackets.</p>' + scriptHtml() + '</div>' +
      '<div class="block"><h2>Clean copy</h2><p class="sub">The words without tags, for captions.</p><pre class="clean-copy" id="cleanCopy">' + esc(cleanCopy() || 'No script yet.') + '</pre>' +
        '<button class="btn ghost small" data-act="copyclean">Copy clean copy</button></div>' +
      '<div class="block"><h2>Story parts</h2><p class="sub">Edit the words, picture and sound, move where a part ends, split, merge or delete. ' +
      'The style map and the joins follow, and both are saved together.</p>' + partsHtml() + '</div>' + approveHtml('script');
  }
  function saveStory(st, action) {
    film.story = st;
    saveSections(Object.assign({ story: st }, markDraft('story')));
    logEvent('story', { action });
  }
  /* The script saves as a whole; square brackets turn into tags first, so none ever reaches film.json. */
  function saveScript(sc, action, redraw) {
    const notes = [];
    sc.segments = sc.segments.map(g => {
      const a = SCRIPT.fixBrackets(g.text), b = SCRIPT.fixBrackets(g.style);
      notes.push(...a.notes, ...b.notes);
      return Object.assign({}, g, { text: a.text, style: b.text });
    });
    if (notes.length) { toast('Square brackets fixed: ' + notes.join('; ') + '.'); redraw = true; }
    film.script = sc;
    saveSections(Object.assign({ script: sc }, markDraft('story')));
    logEvent('script', { action });
    if (redraw) render(true);
    else { const el = $('#cleanCopy'); if (el) el.textContent = cleanCopy() || 'No script yet.'; refreshPrompt(); }
  }
  /* One edit: parts and styles go to film.json in one request, never one without the other. */
  function editParts(how, action, id, ...args) {
    let out;
    try { out = PARTS[how](film.parts || [], film.styles, id, ...args); }
    catch (e) { toast(e.message); render(true); return; }
    film.parts = out.parts; film.styles = Object.assign({}, film.styles, out.styles);
    ui.delPart = null;
    saveSections(Object.assign({ parts: film.parts, styles: film.styles }, markDraft('story')));
    logEvent('parts', { action, part: id });
    if (how === 'edit') { renderTop(); refreshPrompt(); }      // the box already shows the text: keep the focus where it is
    else render(true);
  }
  /* ③ Voice: copy each segment to AI Studio, drop the takes back, see each word's time. */
  const AI_STUDIO = 'https://aistudio.google.com/generate-speech';
  const VOICE_ROUTES = [['ai-studio', 'Gemini in AI Studio', 'Your Google account. You run each segment there and download it.'],
    ['own', 'Your own recording', 'Record each segment and drop it on its row.'],
    ['kokoro', 'Kokoro, free and local', 'Claude makes the takes on this Mac.'],
    ['none', 'No voice', 'Captions and music carry the film.']];
  const voiceOf = () => Object.assign({ route: 'ai-studio', takes: {} }, film.voice);
  function takeKey(t) { return t.words_file + '@' + (t.at || ''); }
  function loadWords(seg, t) {
    const k = takeKey(t);
    if (ui.words[seg] && ui.words[seg].key === k) return ui.words[seg].doc;
    if (!ui.words[seg] || ui.words[seg].key !== k) {
      ui.words[seg] = { key: k, doc: null };
      getJSON('/voice/' + encodeURIComponent(base(t.words_file))).then(doc => {
        if (ui.words[seg] && ui.words[seg].key === k) { ui.words[seg].doc = doc; if (ui.room === 'voice') render(true); }
      }).catch(() => {});
    }
    return null;
  }
  function wordLine(doc) {
    const len = Math.max(doc.length || 0, ...doc.words.map(w => w.end || 0), 0.1);
    return '<div class="wtl" aria-hidden="true">' + doc.words.map(w => '<span class="w' + (w.flag ? ' flag' : '') + '" style="left:' + (100 * w.start / len).toFixed(2) + '%;width:' + Math.max(0.4, 100 * (w.end - w.start) / len).toFixed(2) + '%" title="' + esc(w.text + ' ' + w.start.toFixed(2) + ' s' + (w.flag ? ': ' + w.flag : '')) + '"></span>').join('') +
      '</div><div class="wtl-scale"><span>0 s</span><span>' + len.toFixed(1) + ' s</span></div>' +
      '<p class="wlist">' + doc.words.map(w => w.flag ? '<mark title="' + esc(w.flag) + '">' + esc(w.text) + '</mark>' : esc(w.text)).join(' ') + '</p>';
  }
  function takeHtml(g, t) {
    if (ui.voicing[g.id]) return '<p class="take-state">⏳ Sending ' + esc(ui.voicing[g.id]) + '…</p>';
    if (!t) return '';
    const stale = t.clean != null && t.clean !== SCRIPT.clean(g.text);
    let out = '<div class="take"><audio controls preload="none" src="/voice/' + esc(encodeURIComponent(base(t.file))) + '"></audio>';
    if (t.state === 'timing') out += '<p class="take-state">⏳ Finding each word\'s time in ' + esc(base(t.file)) + '…</p>';
    else if (t.state === 'failed') out += '<p class="take-state bad">❌ ' + esc(t.error || 'The timing failed.') + '</p>';
    else if (t.state === 'timed') {
      out += '<p class="take-state">' + (t.flagged ? '⚠️ ' + t.flagged + ' of ' + t.words + ' words need a check (marked below).' : '✅ All ' + t.words + ' words found.') + '</p>';
      const doc = loadWords(g.id, t);
      out += doc ? wordLine(doc) : '<p class="hint">Loading the words…</p>';
    }
    if (stale) out += '<p class="take-state bad">⚠️ The script for this segment changed after this take. Voice it again, or ask Claude whether the take still fits.</p>';
    return out + '</div>';
  }
  function copyBtn(what, text, label) {
    return '<button class="btn ghost small" data-act="copyvoice" data-text="' + esc(text) + '" data-what="' + esc(what) + '"' + (text ? '' : ' disabled') + '>' + esc(label) + '</button>';
  }
  function roomVoice() {
    const sc = script(), v = voiceOf(), takes = v.takes || {}, route = v.route || 'ai-studio';
    const routes = '<div class="vroutes" role="radiogroup" aria-label="How the voice is made">' + VOICE_ROUTES.map(r =>
      '<button class="vroute" role="radio" data-act="vroute" data-route="' + r[0] + '" aria-checked="' + (route === r[0]) + '"><strong>' + esc(r[1]) + '</strong><span>' + esc(r[2]) + '</span></button>').join('') + '</div>';
    if (!sc.segments.length) return head('voice') + '<div class="block"><h2>How the voice is made</h2>' + routes + '</div>' +
      '<div class="block"><p class="hint" style="margin:0">No script yet. Write it in ① Story first; each segment becomes one take here.</p></div>';
    if (route === 'none') return head('voice') + '<div class="block"><h2>How the voice is made</h2>' + routes + '</div>' +
      '<div class="block"><p class="hint" style="margin:0">No voice for this film. The script stays as captions; Claude times the parts by the music.</p></div>';
    const done = sc.segments.filter(g => (takes[g.id] || {}).state === 'timed').length;
    const steps = route === 'ai-studio'
      ? '<ol class="vsteps"><li><b>Copy</b> each segment below into AI Studio\'s speech page: <a href="' + AI_STUDIO + '" target="_blank" rel="noopener noreferrer">Open AI Studio ↗</a> <span class="hint">(⚠️ field names not checked on the live page yet)</span></li>' +
        '<li><b>Run, listen, download</b> each one as <code>seg-01.wav</code>, <code>seg-02.wav</code> … Not happy? Change the Style line and run it again.</li>' +
        '<li><b>Drop the files</b> here. Each word gets its time; words the voice did not say are marked.</li></ol>'
      : route === 'kokoro' ? '<p class="hint" style="margin:0">Copy the request: Claude voices each segment with Kokoro on this Mac and times it here. Kokoro needs your ✋ yes if it is not installed yet.</p>'
      : '<p class="hint" style="margin:0">Record each segment, then drop the files here (name them <code>seg-01</code>, <code>seg-02</code> … or drop each on its row).</p>';
    return head('voice') +
      '<div class="block"><h2>How the voice is made</h2>' + routes + steps + '</div>' +
      '<div class="block"><div class="vdrop" data-vdrop="all" tabindex="0"><b>Drop all takes here</b><span>Files named seg-01, seg-02 … go to their segment.</span></div>' +
      '<p class="hint">' + done + ' of ' + sc.segments.length + ' segments timed.' + (sc.model || sc.voice ? ' Model: ' + esc(sc.model || 'not set') + '. Voice: ' + esc(sc.voice || 'not set') + '.' : '') + '</p>' +
      '<ol class="vsegs">' + sc.segments.map(g => {
        const t = takes[g.id];
        return '<li class="vseg" data-vdrop="' + esc(g.id) + '"><div class="vseg-head"><b>' + esc(g.id) + '</b><span class="vstyle">' + esc(g.style || 'Style: empty') + '</span>' +
          '<span class="vcopy">' + copyBtn('model', sc.model, 'Model') + copyBtn('voice', sc.voice, 'Voice') + copyBtn('Style line', g.style, 'Style') + copyBtn('text', g.text, 'Text') + '</span></div>' +
          '<p class="vtext">' + esc(g.text) + '</p>' +
          '<div class="vseg-drop"><label class="btn ghost small">' + (t ? 'Replace the take' : 'Add the take') + '<input type="file" accept="audio/*,.wav,.mp3,.m4a,.aif,.aiff,.flac,.ogg" data-vseg="' + esc(g.id) + '" hidden></label>' +
          '<span class="hint">or drop the file on this row</span></div>' + takeHtml(g, t) + '</li>';
      }).join('') + '</ol></div>';
  }
  const SEG_NAME = /seg[-_ ]?0*(\d{1,3})/i;
  async function uploadTake(seg, f) {
    ui.voicing[seg] = f.name; if (ui.room === 'voice') render(true);
    writing++;
    try {
      await post('/api/voice?seg=' + encodeURIComponent(seg), f, { 'Content-Type': 'application/octet-stream', 'X-File-Name': encodeURIComponent(f.name) });
      toast(f.name + ' is ' + seg + '. Finding each word\'s time…');
    } catch (err) { toast('❌ ' + f.name + ': ' + err.message); }
    finally { delete ui.voicing[seg]; writing--; filmStamp = 0; }     // the server wrote film.json: the next poll loads it
    reloadFilm().catch(() => {});
  }
  function dropTakes(seg, files) {
    const segs = script().segments.map(g => g.id);
    for (const f of files) {
      let id = seg;
      if (seg === 'all') { const m = f.name.match(SEG_NAME); id = m ? 'seg-' + String(Number(m[1])).padStart(2, '0') : null; }
      if (!id || !segs.includes(id)) { toast(f.name + ': name it seg-01, seg-02 … or drop it on its segment.'); continue; }
      uploadTake(id, f);
    }
  }
  /* ---------- ④ storyboard: the panels board.py drew, checked against the film as it is now ---------- */
  async function loadBoard() {
    try { board = await getJSON('/api/board'); } catch (e) { board = { version: 0, panels: [] }; }
    if (!Array.isArray(board.panels)) board.panels = [];
    if (!Array.isArray(board.comments)) board.comments = [];
  }
  const openComments = id => board.comments.filter(c => c.open && (!id || c.panel === id));
  /* What each panel was drawn from must match the film now; the same rule board.py uses (compose.mapped_parts). */
  function panelBasis() {
    const out = {}, js = joinsList(), branded = !!(film.brand && film.brand.name);
    parts().forEach(p => {
      const j = js.find(x => x.part === p.id), m = mapOf(p.id);
      if (j) out['join-' + p.id] = { at: j.at, from: j.from, to: j.to, type: j.pick };
      out[p.id] = m ? { from: p.from, to: p.to, style: m.style, brand: branded ? (m.brand || 'as-is') : 'as-is', picture: p.picture || '', words: p.words || '' } : null;
    });
    return out;
  }
  const BASIS_WORDS = { at: 'time', from: 'time', to: 'time', style: 'style', brand: 'brand', picture: 'picture', words: 'words', type: 'join type' };
  function staleWhy(panel, now) {
    if (!now) return ['no style on this part now'];
    const b = panel.basis || {}, why = [];
    Object.keys(now).forEach(k => {
      if (JSON.stringify(b[k]) === JSON.stringify(now[k])) return;
      const w = panel.kind === 'join' && (k === 'from' || k === 'to') ? 'styles' : BASIS_WORDS[k] || k;
      if (!why.includes(w)) why.push(w);
    });
    return why;
  }
  function safeBox(lay) {
    const name = ui.safe, s = name && lay.safe && lay.safe[name], [w, h] = lay.canvas || [1920, 1080];
    if (!s) return '';
    const pc = (v, of) => (100 * v / of).toFixed(2) + '%';
    return '<span class="safe-box" style="left:' + pc(s.left, w) + ';top:' + pc(s.top, h) + ';right:' + pc(w - s.right, w) + ';bottom:' + pc(h - s.bottom, h) + '"></span>';
  }
  function boardRibbon(ps, js) {
    const total = film.length || (ps.length ? ps[ps.length - 1].to : 0) || 1;
    return '<div class="bribbon" aria-label="The panels on the film\'s time line">' + ps.map((p, i) => {
      const m = mapOf(p.id);
      return '<button class="bseg" data-act="seepanel" data-id="' + esc(p.id) + '" style="left:' + (100 * p.from / total).toFixed(2) + '%;width:' + (100 * (p.to - p.from) / total).toFixed(2) + '%" title="' +
        esc((i + 1) + ' ' + p.name + ', ' + span(p.from, p.to) + (m ? ', ' + styleName(m.style) : '')) + '">' + (i + 1) + '</button>';
    }).join('') + js.map(j => '<button class="bjoin" data-act="seepanel" data-id="join-' + esc(j.part) + '" style="left:' + (100 * j.at / total).toFixed(2) + '%" title="' + esc(joinName(j.pick) + ' at ' + sec(j.at)) + '">◆</button>').join('') + '</div>';
  }
  function panelCard(panel, i, now, lay) {
    const why = staleWhy(panel, now), join = panel.kind === 'join', ver = board.version;
    const title = join ? '◆ ' + esc(joinName(panel.type)) : (i + 1) + ' ' + esc(panel.name || panel.part);
    const when = join ? sec(panel.at) : span(panel.from, panel.to);
    const tags = join ? '<span class="ptag">' + esc(styleName(panel.from_style)) + ' to ' + esc(styleName(panel.to_style)) + '</span>'
      : '<span class="ptag">' + esc(styleName(panel.style)) + '</span><span class="ptag">' + esc(brandLabel(panel.brand).lg) + '</span>';
    return '<article class="panel bpanel' + (join ? ' is-join' : '') + (why.length ? ' is-stale' : '') + '" id="panel-' + esc(panel.id) + '">' +
      '<figure class="bshot" style="aspect-ratio:' + (lay.canvas || [16, 9]).join(' / ') + '"><img src="/board/' + encodeURIComponent(panel.file) + '?v=' + ver + '-' + (panel.version || 1) + '" alt="' + esc((join ? 'Join panel: ' : 'Panel ' + (i + 1) + ': ') + (join ? joinName(panel.type) : panel.name || panel.part)) + '" loading="lazy">' + safeBox(lay) + '</figure>' +
      '<div class="meta"><b>' + title + '</b><span>' + when + '</span></div>' +
      '<div class="tags">' + tags + '<span class="pver" title="This panel was drawn ' + (panel.version || 1) + ' time' + (panel.version > 1 ? 's' : '') + '">v' + (panel.version || 1) + '</span></div>' +
      (join ? '' : '<p class="what">' + esc(panel.picture || '') + '</p>') +
      (why.length ? '<p class="bstale">⚠️ Out of date: ' + esc(why.join(', ')) + ' changed since it was drawn. Claude redraws it.</p>' : '') +
      (panel.note ? '<p class="bnote">ℹ️ ' + esc(panel.note) + '</p>' : '') +
      commentsHtml(panel) + '</article>';
  }
  function commentsHtml(panel) {
    const open = openComments(panel.id), done = board.comments.filter(c => c.panel === panel.id && !c.open).length;
    return '<div class="bcomments">' + open.map(c => '<p class="bcomment">💬 ' + esc(c.text) + ' <span>Waiting for Claude to redraw.</span></p>').join('') +
      (done ? '<p class="bdone">✅ ' + done + ' earlier comment' + (done > 1 ? 's' : '') + ' answered by a redraw.</p>' : '') +
      '<textarea data-comment="' + esc(panel.id) + '" rows="2" maxlength="4000" aria-label="Comment on panel ' + esc(panel.id) + '" placeholder="Comment on this panel">' + esc(ui.cdraft[panel.id] || '') + '</textarea>' +
      '<button class="btn small" data-act="sendcomment" data-id="' + esc(panel.id) + '">Send comment</button></div>';
  }
  function roomBoard() {
    const ps = parts(), js = joinsList(), now = panelBasis(), lay = board.layout || { canvas: [1920, 1080], safe: {} };
    if (!board.panels.length) {
      const items = [];
      ps.forEach((p, i) => {
        const j = js.find(x => x.part === p.id);
        if (j) items.push('<article class="panel is-join"><div class="look join-look join-' + esc(j.pick) + '"></div><div class="meta"><b>◆ ' + esc(joinName(j.pick)) + '</b><span>' + sec(j.at) + '</span></div><p class="what">' + esc(styleName(j.from)) + ' to ' + esc(styleName(j.to)) + '.</p></article>');
        const m = mapOf(p.id);
        items.push('<article class="panel"><div class="meta"><b>' + (i + 1) + ' ' + esc(p.name) + '</b><span>' + span(p.from, p.to) + '</span></div>' +
          '<div class="tags"><span class="ptag">' + esc(m ? styleName(m.style) : 'No style yet') + '</span></div><p class="what">' + esc(p.picture) + '</p><p class="snd">Sound: ' + esc(p.sound) + '</p></article>');
      });
      return head('board') + '<p class="hint">No panels drawn yet. This is the plan as text. Copy the request: Claude draws one rough panel per part and one per join, in each style\'s own code.</p>' +
        (items.length ? '<div class="panels">' + items.join('') + '</div>' : '<div class="empty-room">No story parts yet.</div>') + approveHtml('storyboard');
    }
    const have = new Set(board.panels.map(p => p.id)), want = Object.keys(now);
    const missing = want.filter(id => !have.has(id)), gone = board.panels.filter(p => !(p.id in now));
    const stale = board.panels.filter(p => p.id in now && staleWhy(p, now[p.id]).length);
    const order = id => { const k = ps.findIndex(p => p.id === id.replace(/^join-/, '')); return k * 2 + (id.startsWith('join-') ? 0 : 1); };
    const cards = board.panels.filter(p => p.id in now).sort((a, b) => order(a.id) - order(b.id))
      .map(p => panelCard(p, ps.findIndex(x => x.id === p.part), now[p.id], lay));
    const joins = board.panels.filter(p => p.kind === 'join').length, safes = Object.keys(lay.safe || {});
    const redrawn = Array.isArray(board.redrawn) ? ' Last drawing: ' + board.redrawn.join(', ') + ' only.' : '';
    return head('board') +
      '<div class="bhead"><div><h2>Storyboard v' + board.version + '</h2><p class="sub">' + board.panels.length + ' panels: ' + (board.panels.length - joins) + ' part' + (board.panels.length - joins === 1 ? '' : 's') + ', ' + joins + ' join' + (joins === 1 ? '' : 's') +
        '. Drawn ' + esc(day(board.made)) + '.' + esc(redrawn) + '</p></div>' +
        (safes.length ? '<div class="safe-pick" role="group" aria-label="Safe box"><span>Safe box</span>' + ['', ...safes].map(k => '<button class="btn ghost small" data-act="safebox" data-k="' + esc(k) + '" aria-pressed="' + ((ui.safe || '') === k) + '">' + (k ? esc(k) : 'Off') + '</button>').join('') + '</div>' : '') + '</div>' +
      boardRibbon(ps, js) +
      (stale.length || missing.length || gone.length ? '<div class="bwarn">⚠️ ' + [stale.length ? stale.length + ' panel' + (stale.length > 1 ? 's are' : ' is') + ' out of date' : '',
        missing.length ? 'not drawn yet: ' + missing.join(', ') : '', gone.length ? 'no longer in the film: ' + gone.map(p => p.id).join(', ') : ''].filter(Boolean).join('; ') +
        '. Copy the request: Claude redraws only those.</div>' : '') +
      '<div class="panels bpanels">' + cards.join('') + '</div>' +
      '<p class="hint">' + esc(lay.note || '') + '</p>' + approveHtml('storyboard');
  }
  /* ---------- ⑤ Music: hyper-local keywords, cue map, 3 takes on the picture, pick by ear ---------- */
  const MUSIC_LAYERS = ['Place and people', 'Local genre', 'Local instruments', 'Rhythm and scale', 'Scene energy'];
  async function loadMusic() {
    try { musicRes = await getJSON('/api/music'); } catch (e) { musicRes = { version: 0, cues: {} }; }
    if (!musicRes || typeof musicRes.cues !== 'object') musicRes = { version: 0, cues: {} };
  }
  function musicObj() {
    const m = film.music && typeof film.music === 'object' ? film.music : {};
    return { cues: Object.assign({}, m.cues), avoid: Array.isArray(m.avoid) ? m.avoid.map(x => Array.isArray(x) ? x.slice() : [String(x), '']) : [] };
  }
  function cueWorlds() {
    const rn = runs(), out = [];
    rn.forEach(r => { if (r.style && !out.includes(r.style)) out.push(r.style); });
    Object.keys((film.music && film.music.cues) || {}).forEach(id => { if (!out.includes(id)) out.push(id); });
    return out;
  }
  function defaultLayers() { return MUSIC_LAYERS.map(layer => ({ layer, chips: [] })); }
  function cueOf(id) {
    const stored = ((film.music && film.music.cues) || {})[id];
    const baseName = styleOf(id) ? styleName(id) + ' world' : id;
    if (!stored || typeof stored !== 'object') {
      return { name: baseName, style: styleOf(id) ? id : null, bpm: 100, key: 'A minor', hits: '', layers: defaultLayers(), pick: null, wrong: '' };
    }
    const layers = Array.isArray(stored.layers) && stored.layers.length
      ? stored.layers.map(L => ({ layer: L.layer || '', chips: Array.isArray(L.chips) ? L.chips.map(c => Array.isArray(c) ? c.slice() : [String(c), '']) : [] }))
      : defaultLayers();
    return Object.assign({ name: baseName, style: styleOf(id) ? id : null, bpm: 100, key: 'A minor', hits: '', pick: null, wrong: '' }, stored, { layers });
  }
  function cueSpans(id) {
    const stored = ((film.music && film.music.cues) || {})[id];
    if (stored && Array.isArray(stored.spans) && stored.spans.length) return stored.spans;
    const rn = runs().filter(r => r.style === id);
    return rn.length ? rn.map(r => [r.from, r.to]) : [[0, length()]];
  }
  function avoidMatch(keyword, avoidList) {
    const kw = String(keyword || '').trim();
    if (!kw) return null;
    for (const item of avoidList || []) {
      const w = String((Array.isArray(item) ? item[0] : item) || '').trim();
      if (!w) continue;
      const rx = new RegExp('\\b' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'i');
      if (rx.test(kw)) return { word: w, reason: (Array.isArray(item) && item[1]) ? String(item[1]) : '' };
    }
    return null;
  }
  function cueCaption(c, avoidList) {
    const words = [];
    (c.layers || []).forEach(L => (L.chips || []).forEach(ch => {
      const kw = ch[0] && String(ch[0]).trim();
      if (kw && !avoidMatch(kw, avoidList)) words.push(kw);
    }));
    return words.join(', ');
  }
  function cueEffectiveCaption(c, avoidList) {
    const words = [];
    (c.layers || []).forEach(L => (L.chips || []).forEach(ch => {
      const kw = ch[0] && String(ch[0]).trim();
      if (kw && !avoidMatch(kw, avoidList)) words.push(kw);
    }));
    if (!words.length) return (c.name || 'instrumental') + ' underscore, ' + (c.bpm || 100) + ' BPM, instrumental';
    if (!words.some(w => /instrumental|vocal/i.test(w))) words.unshift('instrumental');
    return words.join(', ');
  }
  function cuePickMatches(w, c) {
    if (!c.pick) return false;
    const cm = (musicRes && musicRes.cues || {})[w];
    if (!cm || !Array.isArray(cm.takes) || !cm.takes.length) return false;
    const curRound = Number(cm.round || musicRes.version || 1);
    return c.pick_round != null && Number(c.pick_round) === curRound;
  }
  function allCuesPicked() {
    const ws = cueWorlds();
    return ws.length > 0 && ws.every(w => cuePickMatches(w, cueOf(w)));
  }
  function engineTag(t) {
    const eng = String(t.engine || '');
    if (t.is_guide || eng.startsWith('score')) {
      return '<span class="take-engine">Synth guide</span>';
    }
    if (eng === 'ace-step') return '<span class="take-engine">Generated music</span>';
    if (t.engine_label && !/ace-step/i.test(t.engine_label)) return '<span class="take-engine">' + esc(t.engine_label) + '</span>';
    if (eng) return '<span class="take-engine">' + esc(eng) + '</span>';
    return '<span class="take-engine">Engine unknown</span>';
  }
  function saveMusic(m, action, detail, redraw) {
    film.music = m;
    saveSections(Object.assign({ music: m }, markDraft('music')));
    logEvent('music', Object.assign({ action }, detail || {}));
    if (redraw) render(true); else { renderTop(); refreshPrompt(); }
  }
  function mutateCue(id, fn, action, redraw) {
    const m = musicObj();
    const c = cueOf(id);
    fn(c, m);
    m.cues[id] = c;
    saveMusic(m, action, { cue: id }, redraw);
  }
  function musicHasGuide(resCues) {
    if (musicRes && musicRes.assembled && musicRes.assembled.is_guide) return true;
    return Object.values(resCues || {}).some(cm => cm && Array.isArray(cm.takes) && cm.takes.length > 0 &&
      (cm.is_guide || cm.takes.some(t => t.is_guide || String(t.engine || '').startsWith('score'))));
  }
  function roomMusic() {
    const rn = runs(), worlds = cueWorlds(), m = musicObj(), resCues = (musicRes && musicRes.cues) || {};
    const cuemap = rn.length
      ? '<div class="cuemap"><div class="tl">' +
          '<span class="tl-label">Style</span><div class="lane style" style="grid-template-columns:' + cols(rn) + '">' + rn.map(r => r.style
            ? '<span class="seg" style="background:' + styleColor(r.style) + '">' + esc(styleName(r.style)) + '</span>'
            : '<span class="seg later">No style yet</span>').join('') + '</div>' +
          '<span class="tl-label">Cue</span><div class="lane cues" style="grid-template-columns:' + cols(rn) + '">' + rn.map(r => {
            if (!r.style) return '<span class="seg later">No style yet</span>';
            const c = cueOf(r.style);
            return '<span class="seg' + (r.returns ? ' returns' : '') + '">' + esc(c.name) + (r.returns ? ' returns' : '') + ', ' + c.bpm + ' beats a minute</span>';
          }).join('') + '</div><span></span>' + ticks() + '</div></div>'
      : '';
    const worldsHtml = worlds.length ? worlds.map(w => {
      const c = cueOf(w), spans = cueSpans(w), times = spans.map(sp => span(sp[0], sp[1])).join(' and ');
      const cm = resCues[w], hasTakes = cm && Array.isArray(cm.takes) && cm.takes.length > 0;
      const effCap = cueEffectiveCaption(c, m.avoid);
      const basisStale = hasTakes && cm.basis && (cm.basis.bpm !== Number(c.bpm) || cm.basis.key !== c.key || cm.basis.caption !== effCap);
      const avoidedHits = [];
      const layersHtml = c.layers.map((L, li) => '<div class="layer"><span class="layer-name">' + esc(L.layer) + '</span><div class="chips">' +
        L.chips.map((ch, ci) => {
          const hit = avoidMatch(ch[0], m.avoid);
          if (hit) avoidedHits.push(ch[0]);
          const note = hit
            ? '<small class="avoid-note">⚠️ On "Words to avoid" (' + esc(hit.word) + '), skipped when making takes.</small>'
            : (ch[1] ? '<small>' + esc(ch[1]) + '</small>' : '');
          return '<span class="chip' + (hit ? ' chip-avoided' : '') + '"' + (hit ? ' data-avoided="true"' : '') + '><b>' + esc(ch[0]) + '</b>' +
            '<button class="linkish x" data-act="mchip-del" data-w="' + esc(w) + '" data-l="' + li + '" data-c="' + ci + '" title="Remove this keyword" aria-label="Remove ' + esc(ch[0]) + '">×</button>' +
            note + '</span>';
        }).join('') +
        '<input class="chip-add" data-mfield="chip-add" data-w="' + esc(w) + '" data-l="' + li + '" placeholder="Add a keyword" aria-label="Add a keyword to ' + esc(L.layer) + '"></div></div>').join('');
      const curRound = hasTakes ? Number(cm.round || musicRes.version || 1) : 0;
      const pickIsCurrent = hasTakes && cuePickMatches(w, c);
      const takesHtml = hasTakes
        ? '<div class="takes">' + cm.takes.map(t => {
            const picked = pickIsCurrent && Number(c.pick) === Number(t.n);
            const media = t.video
              ? '<video controls preload="metadata" src="/music/' + encodeURIComponent(t.video) + '?v=' + (musicRes.version || 1) + '"></video>'
              : '<audio controls preload="metadata" src="/music/' + encodeURIComponent(t.audio) + '?v=' + (musicRes.version || 1) + '"></audio>';
            const volOk = t.lufs == null || Math.abs(t.lufs - (musicRes.lufs || -18)) <= 1.2;
            const metaParts = [Number(t.duration || 0).toFixed(1) + ' s'];
            if (t.video) metaParts.push('on picture');
            if (t.lufs != null) metaParts.push(volOk ? 'volume matched' : 'volume check needed');
            return '<div class="mtake"' + (picked ? ' aria-current="true"' : '') + '>' +
              '<div class="take-top"><b>Take ' + t.n + '</b>' + engineTag(t) + '<span>' + metaParts.join(', ') + '</span></div>' +
              media +
              (picked ? '<span class="state-approved">✓ You picked this take</span>' : '<button class="btn ghost small" data-act="mpick" data-w="' + esc(w) + '" data-t="' + t.n + '">I pick this take</button>') +
              '</div>';
          }).join('') + '</div>'
        : '<div class="takes-empty"><p class="hint" style="margin:0">No takes made yet for this cue. Copy the request: Claude makes 3 takes with the music generator on this computer, placed on the picture at matched volume.</p></div>';
      return '<section class="cue-world" data-cue="' + esc(w) + '"><div class="cue-head">' +
        '<span class="swatch" style="background:' + styleColor(w) + ';width:14px;height:14px"></span>' +
        '<div><h3>' + esc(c.name) + '</h3><span class="when">' + esc(styleName(w)) + ', ' + times + (curRound > 1 ? ' · Round ' + curRound : '') + '</span></div>' +
        '<div class="cue-ctrl"><label title="How fast the music feels, in beats a minute">Speed (beats a minute) <input type="number" min="40" max="240" data-mfield="bpm" data-w="' + esc(w) + '" value="' + esc(c.bpm) + '"></label>' +
        '<label title="Musical key and mood, such as D minor or G major">Musical key <input type="text" maxlength="40" data-mfield="key" data-w="' + esc(w) + '" value="' + esc(c.key) + '"></label></div></div>' +
        '<div class="cue-hits"><label>Moments to match <input type="text" maxlength="500" data-mfield="hits" data-w="' + esc(w) + '" value="' + esc(c.hits) + '" placeholder="Where the music must stop, hit or enter (seconds)"></label></div>' +
        '<div class="layers">' + layersHtml + '</div>' +
        (avoidedHits.length ? '<div class="bwarn" style="margin:0 14px 10px">⚠️ Highlighted keyword' + (avoidedHits.length > 1 ? 's are' : ' is') + ' on your "Words to avoid" list and will be skipped: ' + avoidedHits.map(esc).join(', ') + '.</div>' : '') +
        (basisStale ? '<div class="bwarn" style="margin:0 14px 10px">⚠️ Keywords, speed or musical key changed since these takes were made. Copy the request for a fresh round.</div>' : '') +
        takesHtml +
        '<div class="wrong"><label for="wrong-' + esc(w) + '" class="hint">None fits? Say what is wrong:</label>' +
        '<input id="wrong-' + esc(w) + '" data-mfield="wrong" data-w="' + esc(w) + '" placeholder="For example: too slow, wrong percussion" value="' + esc(c.wrong || '') + '"></div></section>';
    }).join('') : '<div class="block"><p class="hint" style="margin:0">No story worlds yet. Put styles on the story parts in ② Styles first, and one cue appears per story world.</p></div>';
    const asm = musicRes && musicRes.assembled
      ? '<div class="block"><h2>Assembled music track</h2><p class="sub">Your picked takes extended and stitched across the whole film (' + Number(musicRes.assembled.duration || 0).toFixed(1) + ' s, volume matched). Unheard by the agent.</p>' +
        '<audio controls preload="metadata" style="width:100%" src="/music/' + encodeURIComponent(musicRes.assembled.file) + '?v=' + (musicRes.version || 1) + '"></audio></div>'
      : '';
    return head('music', '<span class="stop-note">✋ You pick by ear. Claude never picks for you. Takes are unheard by the agent.</span>') +
      (musicHasGuide(resCues) ? '<div class="bwarn" style="margin:0 0 12px">⚠️ Temporary synth guide: some takes' + (musicRes && musicRes.assembled && musicRes.assembled.is_guide ? ' and the assembled track' : '') + ' are guide music only, not final music. Ask Claude for real music takes before the finished film.</div>' : '') +
      '<p class="say">These are the keywords we suggest, and why.</p>' +
      '<p class="sub" style="color:var(--ink-2);margin:0 0 12px">One cue per story world. Delete, add or swap any keyword. The cue map follows the style map in ② Styles.</p>' +
      cuemap + (cuemap ? '<div style="height:16px"></div>' : '') + worldsHtml +
      '<div class="block"><h2>Words to avoid</h2><p class="sub">Some words pull the music toward another culture or a cliché. Claude asks of each word: "which culture does this suggest first?" This is a judgement, not a tested filter.</p>' +
      '<div class="avoid">' + m.avoid.map((a, i) => '<span class="chip"><b>' + esc(a[0]) + '</b><button class="linkish x" data-act="mavoid-del" data-i="' + i + '" title="Remove" aria-label="Remove ' + esc(a[0]) + '">×</button>' + (a[1] ? '<small>' + esc(a[1]) + '</small>' : '') + '</span>').join('') +
      '<input class="chip-add" data-mfield="avoid-add" placeholder="Add a word to avoid" aria-label="Add a word to avoid"></div></div>' +
      asm + approveHtml('music');
  }

  /* ---------- ⑥ Finish: formats, captions, volume check, final watch, ✋ Final film ---------- */
  const SOUND_LAYER_LABELS = { voice: 'voice', sfx: 'sound effects', music: 'music' };
  async function loadFinish() {
    try { finishRes = await getJSON('/api/finish'); } catch (e) { finishRes = { finish: null, render: null }; }
    if (!finishRes || typeof finishRes !== 'object') finishRes = { finish: null, render: null };
  }
  function finishCfg() {
    const f = film.finish && typeof film.finish === 'object' ? film.finish : {};
    return {
      formats: Object.assign({ wide: true, tall: false, square: false }, f.formats),
      captions: f.captions || 'burned',
      lufs: f.lufs != null ? f.lufs : -14,
    };
  }
  function saveFinish(f, action) {
    film.finish = f;
    saveSections(Object.assign({ finish: f }, markDraft('finish')));
    logEvent('finish', { action, captions: f.captions, formats: f.formats });
    render(true);
  }
  function roomFinish() {
    const cfg = finishCfg(), fr = film.frame || { width: 1280, height: 720 };
    const fin = finishRes.finish, ren = finishRes.render;
    const fmt = (k, name, note) => '<label class="opt"><input type="checkbox" data-ffield="format" data-k="' + k + '"' + (cfg.formats[k] ? ' checked' : '') + '><span><b>' + name + '</b><small>' + note + '</small></span></label>';
    const cap = (k, name, note) => '<label class="opt"><input type="radio" name="cap" data-ffield="captions" value="' + k + '"' + (cfg.captions === k ? ' checked' : '') + '><span><b>' + name + '</b><small>' + note + '</small></span></label>';
    let screen;
    if (fin && fin.video) {
      const stale = fin.basis && (fin.basis.captions !== cfg.captions || JSON.stringify(fin.basis.formats) !== JSON.stringify(cfg.formats) || fin.basis.lufs !== cfg.lufs);
      screen = '<div class="screen has-video"><video controls preload="metadata" src="/finish/' + encodeURIComponent(fin.video) + '?v=' + (fin.version || 1) + '"></video></div>' +
        '<p class="hint" style="margin:6px 0 0">Final v' + esc(fin.version) + ' · ' + esc(fin.width) + '×' + esc(fin.height) + ' · ' + Number(fin.duration || 0).toFixed(1) + ' s · ' + (fin.bytes ? (fin.bytes / 1048576).toFixed(1) + ' MB' : '') +
        (fin.captions_srt ? ' · <a href="/finish/' + encodeURIComponent(fin.captions_srt) + '" target="_blank" rel="noopener">Download captions (.srt)</a> (' + fin.captions_count + ' lines)' : '') + '</p>' +
        (fin.music_is_guide ? '<div class="bwarn" style="margin-top:8px">⚠️ Temporary guide music: this film still uses a temporary synth guide track, not final music. Make real takes in Room ⑤ Music before approving.</div>' : '') +
        (stale ? '<div class="bwarn" style="margin-top:8px">⚠️ Your format or caption choices changed since v' + esc(fin.version) + '. Copy the request to rebuild the finished film.</div>' : '');
    } else if (ren && ren.picture) {
      screen = '<div class="screen has-video"><video controls preload="metadata" src="/render/' + encodeURIComponent(ren.picture) + '?v=' + (ren.version || 1) + '"></video></div>' +
        '<p class="hint" style="margin:6px 0 0">Silent picture preview v' + esc(ren.version) + ' (' + esc(ren.width) + '×' + esc(ren.height) + ', ' + Number(ren.duration || 0).toFixed(1) + ' s). Copy the request to mix in voice, sound effects, music and captions.</p>';
    } else {
      screen = '<div class="screen"><div><b>Final watch</b>The finished film plays here once picture, sound and captions are put together.</div></div>';
    }
    const loud = fin && fin.loudness;
    const finWarnings = fin ? (fin.warnings || []).filter(w => !(fin.music_is_guide && /^Temporary guide music/.test(String(w)))) : [];
    const layerNames = fin ? (fin.stems || []).map(k => SOUND_LAYER_LABELS[k] || k) : [];
    const targetLevel = fin && fin.target_lufs != null ? fin.target_lufs : -14;
    const volOk = loud && loud.after_lufs != null && Math.abs(loud.after_lufs - targetLevel) <= 1.0 && (loud.after_tp == null || loud.after_tp <= -1.0);
    const soundHtml = fin
      ? '<p class="sub" style="margin:0 0 6px">Sound layers: <b>' + esc(layerNames.join(', ') || 'silent') + '</b>' + (fin.ducked ? ' · music lowers automatically under the voice' : '') + '.</p>' +
        (loud && loud.after_lufs != null ? '<p class="hint" style="margin:0 0 6px">Volume: <b>' + (volOk ? 'ready for web playback (level on target, no clipping)' : 'needs a check before export') + '</b>.</p>' : '') +
        (finWarnings.length ? '<div class="bwarn" style="margin:6px 0">' + finWarnings.map(w => '⚠️ ' + esc(w)).join('<br>') + '</div>' : '') +
        '<p class="hint" style="margin:0"><b>Unheard by the agent:</b> automatic checks cannot judge taste. Watch and listen once before approving.</p>'
      : '<p class="sub" style="margin:0">Voice, sound effects and the chosen music, with the music lowered under the voice and levelled for web playback.</p>';
    return head('finish', '<span class="stop-note">Posting or sending the film always needs a separate yes in chat.</span>') +
      '<div class="two"><div>' +
      '<div class="block"><h2>Formats</h2><p class="sub">Each platform gets its own folder after your final film yes.</p><div class="opts">' +
        fmt('wide', '16:9, ' + fr.width + '×' + fr.height, 'YouTube, LinkedIn, web. The film is built in this shape.') +
        fmt('tall', '9:16', 'Instagram and TikTok. ⚠️ Every scene must be laid out again, not cropped or stretched.') +
        fmt('square', '1:1', 'Feeds. Needs a layout check per scene.') + '</div></div>' +
      '<div class="block"><h2>Captions</h2><p class="sub">Made from your clean script and the word timings from Room ③ Voice (timed on this computer).</p><div class="opts">' +
        cap('burned', 'Burned into the picture', 'Always visible. Good for silent autoplay.') +
        cap('srt', 'Separate .srt file', 'The platform shows them; viewers can turn them off.') +
        cap('off', 'No captions', '') + '</div></div>' +
      '<div class="block"><h2>Sound and volume</h2>' + soundHtml + '</div>' +
      '</div><div>' + screen + approveHtml('final') +
      '<p class="hint">No render yes is needed: rendering is local, and you judge the finished film here once.</p></div></div>';
  }

  /* ---------- ✋ stops: the server says what Claude asks; a click logs a stamped yes, nothing else ---------- */
  async function loadApprovals() {
    try { approvals = Object.fromEntries((await getJSON('/api/approvals')).stops.map(r => [r.stop, r])); }
    catch (e) { approvals = {}; }
  }
  const day = at => at ? String(at).slice(0, 10) : '';
  function approveHtml(stop, wide) {
    const r = approvals[stop] || { state: 'none' }, name = STOPS.find(x => x[0] === stop)[1];
    let body;
    if (r.state === 'asked') {
      body = '<span class="approve-act"><button class="btn yes" data-act="approve" data-stop="' + stop + '" data-asked="' + esc(r.asked) + '">✋ Yes, ' + esc(r.asked) + '</button>' +
        '<button class="btn ghost small" data-act="notyet" data-stop="' + stop + '" aria-expanded="' + (ui.notYet === stop) + '">Not yet</button></span>';
      if (ui.notYet === stop) body += '<span class="notyet-box"><textarea id="notYetNote" rows="2" maxlength="4000" aria-label="What should change first" placeholder="What should change first?"></textarea>' +
        '<button class="btn small" data-act="sendnotyet" data-stop="' + stop + '" data-asked="' + esc(r.asked) + '">Send to Claude</button></span>';
    } else if (r.state === 'clicked') {
      body = '<span class="approve-state ok">✅ Your yes on ' + esc(r.asked) + ' is logged. Claude records it next.</span>';
    } else if (r.state === 'approved') {
      body = '<span class="approve-state ok">✅ Approved: ' + esc(r.asked || name) + (r.via === 'studio' ? ', clicked here' : ', said in chat') + (r.at ? ' on ' + day(r.at) : '') + '.</span>';
    } else if (r.state === 'outdated') {
      body = '<span class="approve-state open">⚠️ ' + (r.music_outdated
        ? 'New music takes were made after Claude asked about ' + esc(r.asked) + '. Listen to the new takes; Claude asks again.'
        : 'The panels were drawn again (v' + esc(r.board) + ') after Claude asked about ' + esc(r.asked) + '. Claude asks again.') + '</span>';
    } else if (r.state === 'reopened') {
      body = '<span class="approve-state open">⚠️ Open again: ' + esc((r.changed || []).join(', ')) + ' changed after your yes' + (r.asked ? ' on ' + esc(r.asked) : '') + '. Claude asks again.</span>';
    } else {
      body = '<span class="approve-state">⏳ Claude asks for this yes when it is ready. No button until then.</span>';
    }
    return wide ? body : '<div class="approve-bar" data-stop="' + stop + '"><p><b>' + name + ':</b> ' + esc(STOPS.find(x => x[0] === stop)[2]) +
      ' Click once Claude asks, or say it in chat.</p>' + body + '</div>';
  }
  async function approve(el) {
    el.disabled = true;
    try {
      await post('/api/approve', { stop: el.dataset.stop, asked: el.dataset.asked, room: ui.room });
      toast('Your yes on ' + el.dataset.asked + ' is logged. Claude records it next.');
    } catch (e) { toast('Not logged: ' + e.message); }
    await loadApprovals(); render(true); renderStopsIfOpen();
  }

  /* ---------- the request for Claude, per room ---------- */
  function filmLine() {
    const fr = film.frame || {};
    return 'Film: "' + (film.title || 'Untitled') + '"' + (film.about ? ' (' + film.about + ')' : '') + '. ' +
      (film.length ? film.length + ' s' : 'length not set') + (fr.width ? ', ' + fr.width + '×' + fr.height : '') + '.\n' +
      'Video folder: ' + (info.folder || 'the one this Studio was opened from') + '\n' +
      'First run: studio.py events "' + (info.folder || '<video folder>') + '" --since <the last event you read>, so you know what I clicked.';
  }
  function brandLine() {
    const b = film.brand;
    if (!b || !b.name) return 'none. Every part stays as is.';
    return b.skill ? b.name + ' (the ' + b.skill + ' brand skill).' : b.name + ', another brand. Ask me for its brand guide before the storyboard.';
  }
  const PROMPTS = {
    start() {
      const d = detect(), pasted = ((film.start || {}).pasted || '').trim(), inputs = film.inputs || [];
      return 'Kit to Clip Studio request, room ⓪ Start\n\n' + filmLine() + '\n\nWhat I brought (film.json inputs; files stay where they are):\n' +
        (inputs.length ? inputs.map(i => '- ' + (i.note || i.kind) + ': ' + i.path).join('\n') : '- nothing yet') + '\n' +
        (pasted ? '\nI pasted this (' + (d ? d[1] : 'not sure what it is') + '):\n"""\n' + pasted + '\n"""\n' : '') +
        '\nBrand: ' + brandLine() + '\n' +
        '\nPlease:\n1. Read what I brought and list, in one short list, what you found and what is missing.\n' +
        '2. Fill in everything you can in film.json (title, length, frame, story parts with times). Do not ask me again for anything listed above.\n' +
        '3. Tell me which room to open next' + (d ? ' (the Studio suggests ' + roomLabel(ROUTES.find(r => r[0] === d[0])[2]) + ')' : '') + '.';
    },
    styles() {
      const js = joinsList(), out = [];
      parts().forEach((p, i) => {
        const j = js.find(x => x.part === p.id), m = mapOf(p.id);
        if (j) out.push('  ◆ ' + sec(j.at) + ' join: ' + joinName(j.pick) + ' (' + styleName(j.from) + ' to ' + styleName(j.to) + ')');
        out.push('  ' + (i + 1) + '. ' + p.name + ', ' + span(p.from, p.to) + ': ' + (m ? styleName(m.style) + ' [library:' + m.style + '], ' + brandLabel(m.brand).lg : 'no style yet'));
      });
      const b = film.brand && film.brand.name;
      return 'Kit to Clip Studio request, room ② Styles\n\n' + filmLine() + '\n\nStyle map, ' + (js.length ? js.length + ' join' + (js.length > 1 ? 's' : '') : 'no join') + ':\n' + out.join('\n') +
        '\n\nBrand: ' + brandLine() + '\nBrand modes: ' + (b ? '"' + b + '" = apply ' + brandRef() + ' (colours, fonts, logo). "Palette only" = brand colours only, the style keeps its own fonts. ' : '') + '"As is" = no brand.\n' +
        'Shortlist: ' + (shortlist().map(styleName).join(', ') || 'empty') +
        '\n\nPlease:\n1. Tell me if any style, brand mode or join fights the story. Suggest a better one only where it really helps.\n' +
        '2. Then make the storyboard: one rough frame per story part and one per join, at their times, drawn with each style\'s own code. The build prompt (studio/compose.py, or the one I copied) holds every style\'s code.\n' +
        '3. Stop for my storyboard yes. It covers layout, look, brand and joins together. Do not build the film before that yes.';
    },
    story() {
      const ps = parts(), st = story(), sc = script(), idea = st.ideas.find(i => i.id === st.picked);
      const rules = 'Follow references/story-and-voice.md: only spoken words, one segment per tone with a short Style line, <short pause> and <long pause> tags, one CAPITAL word for stress, never square brackets.';
      let ask;
      if (sc.segments.length) ask = '1. Check my script against the voice rules and tell me what to fix. Do not rewrite segments I did not ask about.\n' +
        '2. Split it into story parts with times, or update the parts to match it. Keep the style map for parts that stay.\n3. Then ask for my ✋ script yes (studio.py ask … script "script v<n>").';
      else if (st.beats.length) ask = '1. Write the script for the voice from these beats, in film.json script.segments. ' + rules + '\n2. Then ask for my ✋ script yes.';
      else if (idea) ask = '1. Write 5-8 beats for the idea I picked, in film.json story.beats.\n2. Stop there so I can edit them.';
      else if (st.ideas.length) ask = '1. I have not picked an idea yet. Answer my questions about them, nothing else.';
      else ask = '1. Write 2-3 story ideas from what I brought, in film.json story.ideas (id, title, one line, why it fits).\n2. Stop there so I can pick one.';
      return 'Kit to Clip Studio request, room ① Story\n\n' + filmLine() + '\n' +
        (idea ? '\nPicked idea: ' + idea.title + '. ' + (idea.line || '') + '\n' : '') +
        (st.beats.length ? '\nBeats:\n' + st.beats.map((b, i) => '  ' + (i + 1) + '. ' + b.text).join('\n') + '\n' : '') +
        (sc.segments.length ? '\nScript (' + sc.segments.length + ' segments' + (sc.voice ? ', voice ' + sc.voice : '') + '):\n' + sc.segments.map(g => '  ' + g.id + ' [Style: ' + (g.style || 'empty') + ']\n  ' + g.text).join('\n') + '\n' : '') +
        '\nStory parts (' + ps.length + '):\n' + (ps.length ? ps.map((p, i) => '  ' + (i + 1) + '. ' + p.name + ', ' + span(p.from, p.to) + ': "' + (p.words || '') + '"').join('\n') : '  none yet') +
        '\n\nPlease:\n' + ask;
    },
    voice() {
      const sc = script(), v = voiceOf(), takes = v.takes || {}, route = v.route || 'ai-studio';
      const rows = sc.segments.map(g => { const t = takes[g.id]; return '  ' + g.id + ': ' + (!t ? 'no take yet' : t.state === 'timed' ? t.words + ' words, ' + (t.flagged || 0) + ' flagged' : t.state); }).join('\n');
      const flagged = sc.segments.map(g => { const d = ui.words[g.id] && ui.words[g.id].doc; return d ? d.words.filter(w => w.flag).map(w => '  ' + g.id + ' "' + w.text + '": ' + w.flag).join('\n') : ''; }).filter(Boolean).join('\n');
      let ask;
      if (!sc.segments.length) ask = '1. There is no script yet. Help me write it in the Story room first.';
      else if (route === 'none') ask = '1. This film has no voice. Time the story parts by the music and keep the script as captions.';
      else if (route === 'kokoro') ask = '1. Voice each segment with the local Kokoro voice (ask for my ✋ yes first if it is not installed). Save each as seg-NN.wav.\n' +
        '2. Time each one with studio.py voice <video folder> --seg seg-NN --file <the wav>.\n3. Tell me which words were flagged.';
      else if (flagged) ask = '1. Look at the flagged words. Tell me which are only spelling (fine as they are) and which segments I should voice again.\n2. Then fit the story parts to the take times.';
      else if (sc.segments.every(g => (takes[g.id] || {}).state === 'timed')) ask = '1. Fit the story parts to the take times (each part starts on its first word).\n2. Tell me the film length this gives.';
      else ask = '1. Help me voice the missing segments: which voice fits, and is each Style line short and clear?';
      return 'Kit to Clip Studio request, room ③ Voice\n\n' + filmLine() + '\n\nVoice: ' + (VOICE_ROUTES.find(r => r[0] === route) || VOICE_ROUTES[0])[1] +
        (sc.voice ? ', voice ' + sc.voice : '') + (sc.model ? ', model ' + sc.model : '') + '\nTakes:\n' + (rows || '  none') +
        (flagged ? '\n\nFlagged words:\n' + flagged : '') + '\n\nPlease:\n' + ask;
    },
    board() {
      const now = panelBasis(), drawn = board.panels.length;
      const stale = board.panels.filter(p => p.id in now && staleWhy(p, now[p.id]).length);
      const missing = Object.keys(now).filter(id => !board.panels.some(p => p.id === id));
      const nostyle = parts().filter(p => !mapOf(p.id)).map(p => p.name || p.id);
      const talk = openComments();
      const redo = [...new Set(stale.map(p => p.id).concat(missing, talk.map(c => c.panel)))];
      let ask;
      if (nostyle.length) ask = '1. These parts have no style yet: ' + nostyle.join(', ') + '. Help me pick them in the Styles room first.';
      else if (!drawn) ask = '1. Draw the storyboard: source scripts/env.sh, then run python3 studio/board.py <video folder>. It draws one rough panel per part and one per join, at their times, with each style\'s own code.\n' +
        '2. Tell me the board version and anything it noted.\n3. Then ask for my ✋ storyboard yes (studio.py ask <video folder> storyboard "storyboard v<version>").';
      else if (redo.length) ask = (talk.length ? '1. Read my comments above. Change only what they ask for.\n2. ' : '1. ') + 'Redraw only these panels, one at a time: ' + redo.map(id => 'python3 studio/board.py <video folder> --panel ' + id).join('; ') + '.\n' +
        (talk.length ? '3. ' : '2. ') + 'Then ask for my ✋ storyboard yes on the new board version.';
      else ask = '1. Tell me if any panel fights the story. Change nothing yet.\n2. Ask for my ✋ storyboard yes on "storyboard v' + board.version + '" when the board is ready.';
      return 'Kit to Clip Studio request, room ④ Storyboard\n\n' + filmLine() + '\n\n' +
        (drawn ? 'Board: v' + board.version + ', ' + drawn + ' panels in .studio/results/board/' + (stale.length ? '\nOut of date: ' + stale.map(p => p.id + ' (' + staleWhy(p, now[p.id]).join(', ') + ')').join(', ') : '') +
          (missing.length ? '\nNot drawn yet: ' + missing.join(', ') : '') +
          (talk.length ? '\nMy comments (studio.py events, kind comment):\n' + talk.map(c => '  ' + c.panel + ' (drawn v' + c.panel_version + '): "' + c.text + '"').join('\n') : '') : 'Board: none drawn yet') +
        '\nThe storyboard yes covers layout, look, brand and joins together. Do not build the film before it.\n\nPlease:\n' + ask;
    },
    music() {
      const worlds = cueWorlds(), m = musicObj();
      const body = worlds.map(w => {
        const c = cueOf(w), times = cueSpans(w).map(sp => span(sp[0], sp[1])).join(' and '), cap = cueCaption(c, m.avoid);
        return '\n' + c.name + ' (' + styleName(w) + ', ' + times + ', ' + c.bpm + ' beats per minute, musical key ' + c.key + ')' +
          (cap ? '\n  Keywords: ' + cap : '\n  Keywords: none yet (please write 5 layers in film.json music.cues.' + w + ', with a reason for each)') +
          (c.hits ? '\n  Moments to match: ' + c.hits : '') +
          (cuePickMatches(w, c) ? '\n  My pick: take ' + c.pick : '') +
          (c.wrong ? '\n  What is wrong with the last round: ' + c.wrong : '');
      }).join('\n');
      const needsKw = worlds.some(w => !cueCaption(cueOf(w), m.avoid));
      let ask;
      if (!worlds.length) ask = '1. Put styles on the story parts in ② Styles first, then suggest hyper-local keywords per story world.';
      else if (needsKw) ask = '1. Follow references/music-keywords.md: write 5-layer hyper-local keywords (Place and people, Local genre, Local instruments, Rhythm and scale, Scene energy) and words to avoid in film.json music, with a reason for each.\n2. Stop so I can edit any chip before you generate takes.';
      else if (allCuesPicked()) ask = '1. Extend my picked takes to full length: python3 studio/music.py assemble <video folder>. Do not make a new song and do not change my picks.\n2. Ask for my ✋ music pick yes (studio.py ask <video folder> music "music pick v1").';
      else ask = '1. Make 3 different takes per cue on the built picture at matched volume: python3 studio/music.py audition <video folder> (or --cue <id> for one cue).\n2. If I wrote what is wrong, update the keywords and avoid list in film.json first and show me the change.\n3. Never pick for me. Tell me the takes are ready in Room ⑤ Music (unheard by you) and ask for my ✋ music pick yes once I pick by ear.';
      return 'Kit to Clip Studio request, room ⑤ Music\n\n' + filmLine() + '\n\nOne cue per story world:' + (body || '\n  none yet') +
        '\n\nWords to avoid: ' + (m.avoid.length ? m.avoid.map(a => a[0]).join(', ') : 'none yet') + '\n\nPlease:\n' + ask;
    },
    finish() {
      const cfg = finishCfg(), fr = film.frame || { width: 1280, height: 720 };
      const list = [cfg.formats.wide && ('16:9 (' + fr.width + '×' + fr.height + ')'),
        cfg.formats.tall && '9:16 (re-lay out every scene)', cfg.formats.square && '1:1 (check layout per scene)'].filter(Boolean);
      const capName = { burned: 'burned into the picture', srt: 'separate .srt file', off: 'none' }[cfg.captions];
      const fin = finishRes.finish, ren = finishRes.render;
      let ask;
      if (!ren) ask = '1. Render the built player frame by frame (no separate render yes needed): source scripts/env.sh && python3 studio/render.py <video folder>.\n' +
        '2. Mix voice, sound effects and the music I picked (lower the music under the voice, level for web playback) and build captions (' + capName + '): python3 studio/mix.py <video folder>.\n' +
        '3. Tell me whether the volume check passed (labelled unheard by you) and ask for my ✋ final film yes (studio.py ask <video folder> final "final v1").';
      else if (!fin) ask = '1. Mix voice, sound effects and the picked music (lower the music under the voice, level for web playback) and build captions (' + capName + '): python3 studio/mix.py <video folder>.\n' +
        '2. Show the finished film in Room ⑥ Finish and ask for my ✋ final film yes (studio.py ask <video folder> final "final v1").';
      else ask = '1. Check if my format/caption choices changed since final v' + fin.version + '; if so re-run python3 studio/mix.py <video folder>.\n' +
        '2. After my ✋ final film yes, export each chosen format with finish/scripts/finish.py finish into its own platform folder.\n' +
        '3. Never post or send anything without a separate yes from me in chat.';
      return 'Kit to Clip Studio request, room ⑥ Finish\n\n' + filmLine() + '\n\nFormats: ' + (list.length ? list.join('; ') : 'none chosen') +
        '\nCaptions: ' + capName + '\nSound: music lowered under the voice, levelled for web playback' +
        (fin ? '\nCurrent finish: v' + fin.version + ' (' + fin.width + '×' + fin.height + ', ' + Number(fin.duration || 0).toFixed(1) + ' s)' : '') +
        (fin && fin.music_is_guide ? '\nNote: current build uses temporary guide music, not final music.' : '') +
        '\n\nPlease:\n' + ask;
    },
    later() {
      const r = room(ui.room);
      return 'Kit to Clip Studio request, room ' + r.num + ' ' + r.name + '\n\n' + filmLine();
    },
  };
  const promptFor = () => (PROMPTS[ui.room] || PROMPTS.later)();

  function renderRail() {
    const text = promptFor();
    $('#rail').innerHTML = '<div class="rail-head"><h2>Request for Claude</h2><p>This room\'s request as plain text. Paste it into your Claude Code chat. It also works in Codex or claude.ai.</p></div>' +
      '<pre class="prompt-text" id="promptText">' + esc(text) + '</pre>' +
      '<div class="rail-actions"><button class="btn" data-act="copyprompt">Copy prompt</button>' +
      (ui.room === 'styles' ? '<button class="btn ghost" data-act="buildprompt" title="The long prompt for a fresh build session: the film, the style map, the stops and every chosen style\'s code.">Copy build prompt</button>' +
        '<span class="count" id="buildInfo">' + (ui.build ? (ui.build.error ? '⚠️ ' + esc(ui.build.error) : 'Build prompt: ' + kb(ui.build.bytes) + ', ' + ui.build.styles + ' style' + (ui.build.styles === 1 ? '' : 's') + ', ' + ui.build.joins + ' join' + (ui.build.joins === 1 ? '' : 's') + (ui.build.warnings.length ? '. ⚠️ ' + esc(ui.build.warnings.join(' ')) : '')) : 'Also saved as .studio/prompt.txt in the video folder.') + '</span>' : '') +
      (watching
        ? '<button class="btn ask-on" data-act="ask" title="Claude is watching this Studio and starts on the request without you typing.">Ask Claude to do this</button>'
        : '<button class="btn later" disabled title="Works only while Claude runs studio.py wait in the background. Ask Claude to start it.">Ask Claude to do this <span class="later-tag">Off</span></button>') +
      '<span class="count" id="promptCount">' + text.length.toLocaleString('en') + ' characters</span></div>';
  }
  function refreshPrompt() {
    const el = $('#promptText'); if (!el) return;
    el.textContent = promptFor(); $('#promptCount').textContent = el.textContent.length.toLocaleString('en') + ' characters';
  }

  function renderStops() {
    $('#stopsPanel').innerHTML = '<h2>✋ Approval stops</h2><p class="hint" style="margin:0 0 10px">Kit to Clip stops at each of these and waits for your yes. Click it here once Claude asks, or say it in chat. The Studio never approves for you.</p>' +
      '<table><tbody>' + STOPS.map(s => '<tr data-stop="' + s[0] + '"><td>' + s[1] + '</td><td>' + esc(s[2]) + '<div class="stop-act">' + approveHtml(s[0], true) + '</div></td></tr>').join('') + '</tbody></table>' +
      '<p class="hint" style="margin:0">No yes is needed to render: rendering is local, and you judge the result.</p>';
  }
  function renderStopsIfOpen() { if (!$('#stopsPanel').hidden) renderStops(); }

  /* ---------- render ---------- */
  const RENDER = { start: roomStart, story: roomStory, styles: roomStyles, voice: roomVoice, board: roomBoard, music: roomMusic, finish: roomFinish };
  function render(keepScroll) {
    const y = window.scrollY;
    renderTop();
    $('#room').innerHTML = RENDER[ui.room]();
    renderRail();
    measureTop();
    if (ui.room === 'styles') filterDrawer();
    if (keepScroll) window.scrollTo(0, y);
  }
  function measureTop() { document.documentElement.style.setProperty('--top-h', $('.top').offsetHeight + 'px'); }
  window.addEventListener('resize', measureTop);
  function go(id) {
    ui.room = room(id).id;
    try { localStorage.setItem(LAST_ROOM, ui.room); } catch (e) { /* storage blocked: fine */ }
    if (location.hash !== '#' + ui.room) history.replaceState(null, '', '#' + ui.room);
    render(); window.scrollTo(0, 0); $('#room').focus({ preventScroll: true });
  }

  /* ---------- refresh: Claude changed film.json ---------- */
  const typing = () => { const a = document.activeElement; return !!(a && a.matches('textarea, input[type="text"], input[type="search"], input[type="number"], input:not([type])')); };
  let reloading = null;                    // one reload at a time: leaving a box and clicking Reload both ask for one
  function reloadFilm() {
    if (!reloading) {
      pendingReload = false;
      const seen = writes;
      reloading = (async () => {
        const r = await fetch('/api/film', { cache: 'no-store', credentials: 'same-origin' });
        if (!r.ok) throw new Error('/api/film: ' + r.status);
        const next = normal(JSON.parse(await r.text()));   // a half-written file throws here; the stamp stays, so the next poll retries
        film = next;
        filmStamp = writes === seen ? r.headers.get('X-Film-Stamp') : 0;   // a click saved meanwhile: load again after it
        $('#reloadBar').hidden = true;
        await Promise.all([loadApprovals(), loadBoard(), loadMusic(), loadFinish()]);
        render(true); renderStopsIfOpen();
      })().finally(() => { reloading = null; });
    }
    return reloading;
  }
  /* A planned stop (studio.py stop, or 4 hours without use) is calm news: the work is saved. Only a server that
     vanished without saying so gets the warning. */
  function idleWords() {
    const s = info.idle || 14400, h = Math.round(s / 3600);
    return s >= 3600 ? h + ' hour' + (h === 1 ? '' : 's') : Math.round(s) + ' seconds';
  }
  function showClosed(why) {
    if (closed) return;
    closed = why; clearInterval(poller);
    const bar = $('#reloadBar'); bar.classList.remove('offline'); bar.classList.add('closed');
    bar.innerHTML = '<span><b>The Studio is closed' + (why === 'idle' ? ' after ' + idleWords() + ' without use' : '') + '.</b> ' +
      'Everything you did is saved in film.json. To go on, ask Claude to open the Studio again.</span>';
    bar.hidden = false;
    document.body.dataset.closed = why;
  }
  async function poll() {
    if (closed) return;
    try {
      const s = await getJSON('/api/stamp');
      lastAnswer = Date.now();
      if (s.closing) return showClosed(s.closing);
      if (offline) { offline = false; $('#reloadBar').hidden = true; }
      if (s.watching !== watching) { watching = s.watching; renderRail(); }
      if (s.results !== resultsStamp) {                  // board.py, music.py, render.py or mix.py wrote results: show them
        resultsStamp = s.results;                        // not awaited: the film check below must use this stamp at once
        Promise.all([loadApprovals(), loadBoard(), loadMusic(), loadFinish()]).then(() => {
          if (['board', 'music', 'finish'].includes(ui.room) && !typing()) render(true);
          else renderTop();
          renderStopsIfOpen();
          renderRail();
        });
      }
      if (writing || s.film === String(filmStamp)) return;
      if (typing()) {
        if (pendingReload) return;
        pendingReload = true;
        const bar = $('#reloadBar'); bar.classList.remove('offline');
        bar.innerHTML = 'Claude updated the film. <button class="btn small" data-act="reload">Reload</button>'; bar.hidden = false;
      } else await reloadFilm();
    } catch (e) {
      if (closed) return;
      if (info.idle && Date.now() - lastAnswer >= info.idle * 1000) return showClosed('idle');   // the page slept past the idle stop
      if (!offline) {
        offline = true; const bar = $('#reloadBar'); bar.classList.add('offline');
        bar.textContent = 'The Studio server is not answering. Ask Claude to run studio.py open again.'; bar.hidden = false;
      }
    }
  }

  /* ---------- clicks ---------- */
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-act]');
    if (!el) { if (!e.target.closest('#stopsPanel')) closeStops(); return; }
    const a = el.dataset.act;
    if (a !== 'stops' && !el.closest('#stopsPanel')) closeStops();
    switch (a) {
      case 'go': go(el.dataset.room); break;
      case 'stops': { const p = $('#stopsPanel'), open = p.hidden; renderStops(); p.hidden = !open; el.setAttribute('aria-expanded', String(open)); break; }
      case 'reload': reloadFilm().catch(() => {}); break;
      case 'copyprompt': {
        const text = promptFor();
        copyText(text, roomLabel(ui.room) + ' request (' + text.length.toLocaleString('en') + ' characters)');
        logEvent('copy-prompt', { chars: text.length }); break;
      }
      case 'pickbrand': {
        const o = brands.find(x => x.skill === el.dataset.skill) || (film.brand && film.brand.skill === el.dataset.skill ? film.brand : null);
        if (el.dataset.skill && !o) { toast('That brand is no longer listed. Reload the page.'); break; }
        setBrand(o ? { name: o.name, skill: o.skill } : null); break;
      }
      case 'otherbrand': ui.otherBrand = true; render(true); { const i = $('#otherBrand'); if (i) i.focus(); } break;
      case 'saveother': {
        const name = ($('#otherBrand') || {}).value || '';
        if (!name.trim()) { toast('Type the brand\'s name first.'); break; }
        setBrand({ name: name.trim(), skill: null, other: true }); break;
      }
      case 'brandpick': openBrand(); break;
      case 'brush': ui.brush = ui.brush === el.dataset.style ? null : el.dataset.style; renderMap(); if (ui.brush) toast('Now click the story parts to paint ' + styleName(ui.brush) + '.'); break;
      case 'paint': if (ui.brush) paint(el.dataset.part, ui.brush); else toast('Pick a style in the shortlist first, or drag one here.'); break;
      case 'brandmode': {
        const order = brandModes(), m = Object.assign({}, mapOf(el.dataset.part));
        m.brand = order[(order.indexOf(m.brand) + 1) % order.length];
        film.styles.map = Object.assign({}, film.styles.map, { [el.dataset.part]: m });
        renderMap(); saveStyles('brand', { part: el.dataset.part, brand: m.brand }); break;
      }
      case 'preset': {
        const p = film.presets[el.dataset.k];
        film.styles.map = asIsWithoutBrand(JSON.parse(JSON.stringify(p.map || {})), film.brand); film.styles.joins = JSON.parse(JSON.stringify(p.joins || {}));
        ui.openJoin = null; renderShortlist(); saveStyles('preset', { preset: el.dataset.k }); break;
      }
      case 'clear': film.styles.map = {}; film.styles.joins = {}; ui.openJoin = null; renderMap(); saveStyles('preset', { preset: 'clear' }); toast('Map cleared. Paint a style onto the story parts.'); break;
      case 'join':
        ui.openJoin = ui.openJoin === el.dataset.part && ui.room === 'styles' ? null : el.dataset.part;
        if (ui.room !== 'styles') go('styles'); else renderMap();
        break;
      case 'pickjoin': {
        const joins = Object.assign({}, film.styles.joins), old = joins[el.dataset.part] || {};
        joins[el.dataset.part] = { type: el.dataset.j, note: old.note || '' };
        film.styles.joins = joins; renderMap(); saveStyles('join', { part: el.dataset.part, type: el.dataset.j });
        toast('Join set: ' + joinName(el.dataset.j) + '.'); break;
      }
      case 'drawer': ui.drawer = !ui.drawer; renderShortlist(); if (ui.drawer) { const s = $('#libSearch'); if (s) s.focus(); } break;
      case 'short':
        if (!shortlist().includes(el.dataset.style)) film.styles.shortlist = shortlist().concat([el.dataset.style]);
        renderShortlist(); saveStyles('shortlist', { add: el.dataset.style }); break;
      case 'unshort':
        film.styles.shortlist = shortlist().filter(id => id !== el.dataset.style);
        if (ui.brush === el.dataset.style) ui.brush = null;
        renderShortlist(); saveStyles('shortlist', { remove: el.dataset.style }); break;
      case 'demo': openDemo(el.dataset.style); break;
      case 'close-demo': closeDemo(); break;
      case 'buildprompt': copyBuildPrompt(el); break;
      case 'approve': approve(el); break;
      case 'vroute': {
        const r = el.dataset.route;
        film.voice = Object.assign({}, voiceOf(), { route: r }); render(true); refreshPrompt();
        writing++;
        post('/api/voice-route', { route: r }).catch(err => toast('Not saved: ' + err.message)).finally(() => { writing--; filmStamp = 0; });
        break;
      }
      case 'copyvoice': copyText(el.dataset.text, el.dataset.what); break;
      case 'sendcomment': {
        const box = document.querySelector('[data-comment="' + el.dataset.id + '"]'), text = ((box || {}).value || '').trim();
        if (!text) { toast('Write the comment first.'); if (box) box.focus(); break; }
        el.disabled = true;
        post('/api/event', { kind: 'comment', room: 'board', detail: { panel: el.dataset.id, text } })
          .then(() => loadBoard()).then(() => { delete ui.cdraft[el.dataset.id]; render(true); toast('Sent to Claude: your comment on ' + el.dataset.id + '.'); },
            err => { el.disabled = false; toast('Not sent: ' + err.message); });
        break;
      }
      case 'safebox': ui.safe = el.dataset.k || null; render(true); break;
      case 'seepanel': { const x = document.getElementById('panel-' + el.dataset.id); if (x) { x.scrollIntoView({ behavior: 'smooth', block: 'center' }); x.classList.add('flash'); setTimeout(() => x.classList.remove('flash'), 1200); } break; }
      case 'pickidea': { const st = story(); st.picked = st.picked === el.dataset.id ? null : el.dataset.id; saveStory(st, 'pick'); render(true); break; }
      case 'addbeat': { const st = story(); st.beats = st.beats.concat([{ id: 'b' + (st.beats.reduce((m, b) => Math.max(m, parseInt(String(b.id).slice(1), 10) || 0), 0) + 1), text: '' }]); saveStory(st, 'add-beat'); render(true); { const x = $('[data-beat="' + (st.beats.length - 1) + '"]'); if (x) x.focus(); } break; }
      case 'delbeat': { const st = story(); st.beats = st.beats.filter((_, i) => i !== Number(el.dataset.i)); saveStory(st, 'delete-beat'); render(true); break; }
      case 'addseg': { const sc = script(); sc.segments = sc.segments.concat([{ id: SCRIPT.newId(sc.segments), style: (sc.segments[sc.segments.length - 1] || {}).style || '', text: '' }]); saveScript(sc, 'add-segment', true); break; }
      case 'delseg': { const sc = script(); sc.segments = sc.segments.filter(g => g.id !== el.dataset.seg); saveScript(sc, 'delete-segment', true); break; }
      case 'tag': {
        const ta = ui.lastSeg && $('textarea[data-seg="' + CSS.escape(ui.lastSeg) + '"]');
        if (!ta) { toast('Click into a segment first, then pick a tag.'); break; }
        const a = ta.selectionStart, b = ta.selectionEnd, tag = el.dataset.tag, before = ta.value.slice(0, a), pad = before && !/\s$/.test(before) ? ' ' : '';
        ta.value = before + pad + tag + ' ' + ta.value.slice(b);
        const sc = script(); sc.segments = sc.segments.map(g => g.id === ta.dataset.seg ? Object.assign({}, g, { text: ta.value }) : g);
        saveScript(sc, 'tag', false);
        ta.focus(); ta.selectionStart = ta.selectionEnd = a + pad.length + tag.length + 1;
        const n = $('#notes-' + CSS.escape(ta.dataset.seg)); if (n) n.innerHTML = segNotes(sc.segments.find(g => g.id === ta.dataset.seg));
        break;
      }
      case 'copyclean': { const t = cleanCopy(); if (t) copyText(t, 'clean copy (' + t.length + ' characters)'); break; }
      case 'splitpart': editParts('split', 'split', el.dataset.part); break;
      case 'mergepart': editParts('merge', 'merge', el.dataset.part); break;
      case 'delpart':
        if (ui.delPart === el.dataset.part) editParts('remove', 'delete', el.dataset.part);
        else { ui.delPart = el.dataset.part; render(true); }
        break;
      case 'notyet': ui.notYet = ui.notYet === el.dataset.stop ? null : el.dataset.stop; render(true); renderStopsIfOpen(); { const n = $('#notYetNote'); if (n) n.focus(); } break;
      case 'sendnotyet': {
        const note = (($('#notYetNote') || {}).value || '').trim();
        post('/api/event', { kind: 'not-yet', room: ui.room, detail: { stop: el.dataset.stop, asked: el.dataset.asked, note } })
          .then(() => { ui.notYet = null; render(true); renderStopsIfOpen(); toast('Sent to Claude: not yet' + (note ? ', with your note.' : '.')); },
            err => toast('Not sent: ' + err.message));
        break;
      }
      case 'mchip-del': {
        mutateCue(el.dataset.w, c => {
          const L = c.layers[Number(el.dataset.l)];
          if (L) { const gone = L.chips.splice(Number(el.dataset.c), 1)[0]; if (gone) toast('Removed "' + gone[0] + '".'); }
        }, 'remove-keyword', true);
        break;
      }
      case 'mavoid-del': {
        const m = musicObj(), gone = m.avoid.splice(Number(el.dataset.i), 1)[0];
        saveMusic(m, 'remove-avoid', { word: gone ? gone[0] : '' }, true);
        break;
      }
      case 'mpick': {
        const takeN = Number(el.dataset.t), cm = (musicRes && musicRes.cues || {})[el.dataset.w];
        const round = Number((cm && cm.round) || (musicRes && musicRes.version) || 1);
        mutateCue(el.dataset.w, c => { c.pick = takeN; c.pick_round = round; }, 'pick-take', true);
        toast('Picked take ' + takeN + ' for ' + cueOf(el.dataset.w).name + '.');
        break;
      }
      case 'ask': {
        const text = promptFor();
        post('/api/event', { kind: 'ask', room: ui.room, detail: { chars: text.length, request: text } })
          .then(() => toast('Sent to Claude. It starts on the request in a moment.'), err => toast('Not sent: ' + err.message));
        break;
      }
    }
  });
  function closeStops() { const p = $('#stopsPanel'); if (!p.hidden) { p.hidden = true; const b = $('[data-act="stops"]'); if (b) b.setAttribute('aria-expanded', 'false'); } }
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeStops(); closeDemo(); }
    if (e.key === 'Enter' && e.target.id === 'otherBrand') { e.preventDefault(); $('[data-act="saveother"]').click(); }
    if (e.key === 'Enter' && e.target.matches('.chip-add')) { e.preventDefault(); e.target.blur(); }
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[role="button"][data-act]')) { e.preventDefault(); e.target.click(); }
  });

  /* ---------- typing: the paste box saves when you leave it ---------- */
  document.addEventListener('input', e => {
    if (e.target.id === 'libSearch') { ui.query = e.target.value; filterDrawer(); return; }
    if (e.target.dataset.comment) { ui.cdraft[e.target.dataset.comment] = e.target.value; return; }
    if (e.target.dataset.segf === 'text') {           // live estimate and checks, no redraw while typing
      const g = { id: e.target.dataset.seg, text: e.target.value, style: ($('input[data-seg="' + CSS.escape(e.target.dataset.seg) + '"]') || {}).value };
      const n = $('#notes-' + CSS.escape(g.id)); if (n) n.innerHTML = segNotes(g);
      return;
    }
    if (e.target.dataset.field !== 'paste') return;
    film.start = Object.assign({}, film.start, { pasted: e.target.value });
    const box = $('#detectBox'); if (box) box.innerHTML = detectHtml(detect());
    refreshPrompt();
  });
  document.addEventListener('change', e => {
    const t = e.target;
    if (t.dataset.mfield) {
      const f = t.dataset.mfield, w = t.dataset.w;
      if (f === 'chip-add') {
        const val = t.value.trim();
        if (val) mutateCue(w, c => { const L = c.layers[Number(t.dataset.l)]; if (L) L.chips.push([val, 'Your keyword.']); }, 'add-keyword', true);
        t.value = '';
        return;
      }
      if (f === 'avoid-add') {
        const val = t.value.trim();
        if (val) { const m = musicObj(); m.avoid.push([val, 'Your word to avoid.']); saveMusic(m, 'add-avoid', { word: val }, true); }
        t.value = '';
        return;
      }
      if (f === 'bpm') {
        const n = Math.max(40, Math.min(240, Math.round(Number(t.value) || 100)));
        mutateCue(w, c => { c.bpm = n; }, 'edit-bpm', false); return;
      }
      if (f === 'key' || f === 'hits' || f === 'wrong') {
        mutateCue(w, c => { c[f] = t.value.trim(); }, 'edit-' + f, false); return;
      }
    }
    if (t.dataset.ffield) {
      const cfg = finishCfg();
      if (t.dataset.ffield === 'format') cfg.formats[t.dataset.k] = !!t.checked;
      else if (t.dataset.ffield === 'captions') cfg.captions = t.value;
      saveFinish(cfg, 'edit-' + t.dataset.ffield);
      return;
    }
    if (t.dataset.beat != null) { const st = story(); st.beats = st.beats.map((b, i) => i === Number(t.dataset.beat) ? Object.assign({}, b, { text: t.value }) : b); saveStory(st, 'edit-beat'); return; }
    if (t.dataset.sfield) { const sc = script(); sc[t.dataset.sfield] = t.value; saveScript(sc, 'edit-' + t.dataset.sfield, false); return; }
    if (t.dataset.segf) { const sc = script(); sc.segments = sc.segments.map(g => g.id === t.dataset.seg ? Object.assign({}, g, { [t.dataset.segf]: t.value }) : g); saveScript(sc, 'edit-segment', false); return; }
    if (t.dataset.pfield) { editParts('edit', 'edit-' + t.dataset.pfield, t.dataset.part, t.dataset.pfield, t.value); return; }
    if (t.dataset.boundary != null) { editParts('move', 'move', Number(t.dataset.boundary), t.value); return; }
    if (t.dataset.field === 'paste') {
      const d = detect(), start = Object.assign({}, film.start, { pasted: t.value, found: d ? d[0] : null, opens: d ? ROUTES.find(r => r[0] === d[0])[2] : null });
      saveSections(Object.assign({ start }, markDraft('start')));
      logEvent('paste', { chars: t.value.length, found: start.found });
      if (pendingReload && !typing()) reloadFilm().catch(() => {});
    } else if (t.id === 'filePick') { upload([...t.files]); t.value = ''; }
    else if (t.dataset.vseg) { dropTakes(t.dataset.vseg, [...t.files]); t.value = ''; }
  });
  document.addEventListener('focusin', e => { if (e.target.dataset && e.target.dataset.segf === 'text') ui.lastSeg = e.target.dataset.seg; });
  document.addEventListener('focusout', () => { setTimeout(() => { if (pendingReload && !typing()) reloadFilm().catch(() => {}); }, 0); });

  /* ---------- files: dropped into inputs/ through the server ---------- */
  async function upload(files) {
    if (!files.length) return;
    for (const f of files) {
      if (info.max_upload && f.size > info.max_upload) {
        ui.uploads.push({ bad: true, text: '⚠️ ' + f.name + ' is over ' + Math.round(info.max_upload / 1048576) + ' MB. Copy it into ' + info.inputs + ' by hand, then tell Claude.' });
        continue;
      }
      ui.uploads.push({ text: '⏳ ' + f.name + ' (' + kb(f.size) + ')' });
      if (ui.room === 'start') render(true);
      const row = ui.uploads[ui.uploads.length - 1];
      writing++;
      try {
        const r = await post('/api/upload', f, { 'Content-Type': 'application/octet-stream', 'X-File-Name': encodeURIComponent(f.name) });
        row.text = '✅ ' + r.path + ' (' + r.kind + ')';
        ui.dropped.unshift({ kind: r.kind, path: r.path });
        film.inputs = (film.inputs || []).concat([{ kind: r.kind, path: r.path, note: 'Dropped in the Studio' }]);
      } catch (err) { row.bad = true; row.text = '❌ ' + f.name + ': ' + err.message; }
      finally { writing--; }
    }
    const d = detect();
    if (d) await saveSections(Object.assign({ start: Object.assign({}, film.start, { found: d[0], opens: ROUTES.find(r => r[0] === d[0])[2] }) }, markDraft('start')));
    filmStamp = 0;            // the server also wrote film.json (inputs): pick up its copy on the next poll
    if (ui.room === 'start') render(true);
  }
  document.addEventListener('dragstart', e => {
    const c = e.target.closest && e.target.closest('.style-card');
    if (c) { e.dataTransfer.setData('text/x-style', c.dataset.style); e.dataTransfer.effectAllowed = 'copy'; }
  });
  document.addEventListener('dragover', e => {
    const cell = e.target.closest && e.target.closest('[data-act="paint"]');
    if (cell && [...e.dataTransfer.types].includes('text/x-style')) { e.preventDefault(); cell.classList.add('drop-ok'); return; }
    const box = e.target.closest && e.target.closest('#drop, [data-vdrop]');
    if (box && [...e.dataTransfer.types].includes('Files')) { e.preventDefault(); box.classList.add('over'); }
  });
  document.addEventListener('dragleave', e => { const cell = e.target.closest && e.target.closest('[data-act="paint"]'); if (cell) cell.classList.remove('drop-ok'); });
  document.addEventListener('dragleave', e => { const box = e.target.closest && e.target.closest('#drop, [data-vdrop]'); if (box) box.classList.remove('over'); });
  document.addEventListener('drop', e => {
    const cell = e.target.closest && e.target.closest('[data-act="paint"]'), st = e.dataTransfer.getData('text/x-style');
    if (cell && st) { e.preventDefault(); paint(cell.dataset.part, st); toast(styleName(st) + ' on part ' + (parts().findIndex(p => p.id === cell.dataset.part) + 1) + '.'); return; }
    const vbox = e.target.closest && e.target.closest('[data-vdrop]');
    if (vbox && e.dataTransfer.files.length) { e.preventDefault(); vbox.classList.remove('over'); dropTakes(vbox.dataset.vdrop, [...e.dataTransfer.files]); return; }
    const box = e.target.closest && e.target.closest('#drop');
    if (box && e.dataTransfer.files.length) { e.preventDefault(); box.classList.remove('over'); upload([...e.dataTransfer.files]); }
  });

  /* ---------- start ---------- */
  async function boot() {
    try {
      [info, lib] = await Promise.all([getJSON('/api/info'), getJSON('/api/styles')]);
      brands = await getJSON('/api/brands').then(r => r.brands || [], () => []);   // no list: No brand and Another brand still work
      const r = await fetch('/api/film', { cache: 'no-store', credentials: 'same-origin' });
      if (!r.ok) throw new Error((await r.json()).error);
      filmStamp = r.headers.get('X-Film-Stamp');
      film = normal(await r.json());
      const st0 = await getJSON('/api/stamp').catch(() => null);
      if (st0) { resultsStamp = st0.results; watching = !!st0.watching; }
      await Promise.all([loadApprovals(), loadBoard(), loadMusic(), loadFinish()]);
    } catch (e) {
      $('#room').innerHTML = '<div class="empty-room">The Studio could not open the film: ' + esc(e.message) + '</div>';
      return;
    }
    let first = location.hash.slice(1);
    if (!ROOMS.some(r => r.id === first)) { try { first = localStorage.getItem(LAST_ROOM); } catch (e) { first = null; } }
    if (!ROOMS.some(r => r.id === first)) first = (film.start || {}).opens || 'start';
    ui.room = room(first).id;
    render();
    logEvent('open', { room: ui.room });
    poller = setInterval(poll, 1000);
  }
  window.addEventListener('hashchange', () => { const id = location.hash.slice(1); if (ROOMS.some(r => r.id === id) && id !== ui.room) go(id); });
  boot();
})();
