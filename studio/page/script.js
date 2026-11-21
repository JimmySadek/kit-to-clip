/* The script for the voice, in the form Gemini TTS reads best (references/story-and-voice.md). Pure functions, shared
   by the Story room and the tests: the clean copy for captions, a time estimate, the checks, and the fix that turns
   square brackets into tags before anything is saved. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SCRIPT = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const TAGS = ['<short pause>', '<long pause>', '<breath>', '<sigh>', '<chuckle>', '<laugh>', '<whisper>'];
  const WORDS_PER_SECOND = 2.6;                      // a calm narrator, about 155 words a minute
  const PAUSE = { 'short pause': 0.4, 'long pause': 1.0 };

  /* Spoken words only: tags out, spaces tidied. Captions use this. */
  function clean(text) {
    return String(text || '').replace(/<[^<>]*>/g, ' ').replace(/\s+([,.!?;:])/g, '$1').replace(/\s+/g, ' ').trim();
  }
  function words(text) {
    return clean(text).split(' ').filter(w => /[\p{L}\p{N}]/u.test(w));
  }
  /* Seconds, roughly: words at a calm pace, plus each pause tag, '...' and '--'. */
  function estimate(text) {
    const t = String(text || '');
    let s = words(t).length / WORDS_PER_SECOND;
    for (const m of t.matchAll(/<([^<>]*)>/g)) s += PAUSE[m[1].trim().toLowerCase()] || 0;
    s += (t.match(/\.\.\./g) || []).length * 0.3 + (t.match(/--/g) || []).length * 0.2;
    return Math.round(s * 10) / 10;
  }
  /* Square brackets can be read aloud. A direction like [Tone: calm] belongs in the Style line, so it goes; anything
     else becomes a tag. Returns the fixed text and what changed. */
  function fixBrackets(text) {
    const notes = [];
    let out = String(text || '').replace(/\[([^\[\]]*)\]/g, (m, inner) => {
      if (/:/.test(inner) || inner.trim().split(/\s+/).length > 3) { notes.push('removed "' + m + '": put directions in the Style line'); return ''; }
      notes.push('"' + m + '" became <' + inner.trim() + '>');
      return '<' + inner.trim() + '>';
    });
    if (/[\[\]]/.test(out)) { out = out.replace(/[\[\]]/g, ''); notes.push('removed a lone square bracket'); }
    return { text: out.replace(/ {2,}/g, ' '), notes };
  }
  /* What to look at in one segment, as short sentences. */
  function check(seg) {
    const out = [], t = String(seg.text || ''), style = String(seg.style || '');
    if (/[\[\]]/.test(t + style)) out.push('Square brackets can be read aloud. Use a tag like <short pause>.');
    // Short capitals (IDA, CT, AI) are usually names, so only words of 4 letters or more count as stress.
    const caps = words(t).map(w => w.replace(/[^\p{L}]/gu, '')).filter(w => w.length > 3 && w === w.toUpperCase() && /\p{Lu}/u.test(w));
    if (caps.length > 1) out.push('More than one CAPITAL word (' + caps.join(', ') + '). Stress one word.');
    if (/[*_#`]/.test(t)) out.push('No asterisks or markdown: the text is read word for word.');
    if (style.split(/\s+/).filter(Boolean).length > 12) out.push('Keep the Style line short, under about 12 words.');
    for (const m of t.matchAll(/<([^<>]*)>/g)) if (!TAGS.includes('<' + m[1].trim().toLowerCase() + '>')) out.push('<' + m[1] + '> is not in the tag list; check it is a sound or a pause.');
    return out;
  }
  function newId(segments) {
    let n = (segments || []).length + 1;
    const id = k => 'seg-' + String(k).padStart(2, '0');
    while ((segments || []).some(s => s.id === id(n))) n++;
    return id(n);
  }
  return { TAGS, clean, words, estimate, fixBrackets, check, newId };
});
