/* Story part edits for the Studio's Story room. Pure functions: each takes the film's parts and styles and returns new
   copies, so the page saves both in one request and tests run them in Node. Parts stay back to back (no gaps), the
   style map and the join picks only name parts that exist.

     edit      a part's name, words, picture or sound          the map: nothing
     move      the boundary after part i to a new time         both neighbours change
     split     a part in two at a time (its middle by default) both halves keep its style and brand mode
     merge     a part with the next one                        the first part's style stays; a join between them goes
     remove    a part                                          its map entry and join pick go; the part before takes
                                                               its time (the part after, when it is the first) */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PARTS = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const MIN = 0.1;                                   // the shortest part, in seconds
  const FIELDS = ['name', 'words', 'picture', 'sound'];
  const round = t => Math.round(t * 1000) / 1000;
  const copy = x => JSON.parse(JSON.stringify(x));

  function start(parts, styles) {
    const s = copy(styles || {});
    s.map = s.map || {}; s.joins = s.joins || {};
    return { parts: copy(parts || []), styles: s };
  }
  function at(parts, id) {
    const i = parts.findIndex(p => p.id === id);
    if (i < 0) throw new Error('no part ' + id);
    return i;
  }
  /* Only parts that exist may hold a map entry or a join pick. */
  function tidy(out) {
    const ids = new Set(out.parts.map(p => p.id));
    for (const k of Object.keys(out.styles.map)) if (!ids.has(k)) delete out.styles.map[k];
    for (const k of Object.keys(out.styles.joins)) if (!ids.has(k)) delete out.styles.joins[k];
    return out;
  }
  function newId(parts) {
    let n = parts.reduce((m, p) => Math.max(m, parseInt(String(p.id).replace(/^\D+/, ''), 10) || 0), 0) + 1;
    while (parts.some(p => p.id === 'p' + n)) n++;
    return 'p' + n;
  }

  function edit(parts, styles, id, field, value) {
    if (!FIELDS.includes(field)) throw new Error(field + ' is not a part field you can edit');
    const out = start(parts, styles);
    out.parts[at(out.parts, id)][field] = String(value);
    return out;
  }

  function move(parts, styles, i, t) {
    const out = start(parts, styles), a = out.parts[i], b = out.parts[i + 1];
    if (!a || !b) throw new Error('no boundary after part ' + (i + 1));
    t = round(Number(t));
    if (!(t >= a.from + MIN && t <= b.to - MIN)) throw new Error('the time must stay between ' + round(a.from + MIN) + ' and ' + round(b.to - MIN) + ' s');
    a.to = t; b.from = t;
    return out;
  }

  function split(parts, styles, id, t) {
    const out = start(parts, styles), i = at(out.parts, id), p = out.parts[i];
    t = round(t == null ? (p.from + p.to) / 2 : Number(t));
    if (!(t >= p.from + MIN && t <= p.to - MIN)) throw new Error('the split must fall inside the part, at least ' + MIN + ' s from each end');
    const id2 = newId(out.parts);
    const second = { id: id2, name: (p.name || 'Part') + ' 2', from: t, to: p.to, words: '', picture: p.picture || '', sound: '' };
    p.to = t;
    out.parts.splice(i + 1, 0, second);
    if (out.styles.map[id]) out.styles.map[id2] = copy(out.styles.map[id]);
    return out;
  }

  function merge(parts, styles, id) {
    const out = start(parts, styles), i = at(out.parts, id), a = out.parts[i], b = out.parts[i + 1];
    if (!b) throw new Error('the last part has no next part to merge with');
    a.to = b.to;
    for (const f of ['words', 'picture', 'sound']) {
      const x = (a[f] || '').trim(), y = (b[f] || '').trim();
      a[f] = x && y ? x + ' ' + y : x || y;
    }
    out.parts.splice(i + 1, 1);
    return tidy(out);
  }

  function remove(parts, styles, id) {
    const out = start(parts, styles), i = at(out.parts, id), p = out.parts[i];
    if (out.parts.length < 2) throw new Error('a film keeps at least one part');
    if (i > 0) out.parts[i - 1].to = p.to; else out.parts[1].from = p.from;
    out.parts.splice(i, 1);
    return tidy(out);
  }

  /* What the server also checks: unique ids, from < to, back to back, map and joins naming real parts. */
  function problems(parts, styles) {
    const out = [], ids = new Set();
    parts.forEach((p, i) => {
      if (ids.has(p.id)) out.push('two parts are called ' + p.id);
      ids.add(p.id);
      if (!(p.from < p.to)) out.push(p.id + ' ends before it starts');
      if (i && Math.abs(parts[i - 1].to - p.from) > 1e-6) out.push(p.id + ' does not start where ' + parts[i - 1].id + ' ends');
    });
    for (const k of Object.keys((styles || {}).map || {})) if (!ids.has(k)) out.push('the map names a missing part ' + k);
    for (const k of Object.keys((styles || {}).joins || {})) if (!ids.has(k)) out.push('a join names a missing part ' + k);
    return out;
  }

  return { edit, move, split, merge, remove, problems, MIN };
});
