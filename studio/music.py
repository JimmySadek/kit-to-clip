#!/usr/bin/env python3
"""⑤ Music: hyper-local keywords, one cue per story world, 3 takes on the actual picture at matched loudness (-18 LUFS),
and assembling the person's picked takes into one full-length music track.

  python3 music.py cues     <video-folder> [--film film.json]
  python3 music.py audition <video-folder> [--cue <id>] [--picture <mp4>] [--takes 3] [--seed 11]
                                           [--engine ace|score] [--lufs -18] [--film film.json]
  python3 music.py assemble <video-folder> [--out <wav>] [--lufs -18] [--film film.json]

Results land in <video>/.studio/results/music/ (git-ignored):
  music.json                what Room ⑤ Music reads: cues, takes, engine, round, loudness, picture clips, basis
  <cue>-take-<n>.wav        each take levelled to -18 LUFS (true peak <= -3 dBTP)
  <cue>-take-<n>.mp4        when a built picture exists, that take placed on the cue's slice of the picture
  score-full.wav            assembled full-length music track from the person's picks (never chosen by the agent)

The agent cannot hear. Claude never picks a take; `assemble` refuses if any cue has no current human pick.
A new audition round always clears that cue's previous pick so the person must hear the new takes before picking.
ACE-Step is the default engine and never falls back to the built-in synth silently (`--engine score` is explicit only).
Tests may set KIT_TO_CLIP_MUSIC_FAKE to a script that writes deterministic stereo WAVs without ACE-Step.
"""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
SOUND_SCRIPTS = SKILL_ROOT / 'sound' / 'scripts'
FINISH_SCRIPTS = SKILL_ROOT / 'finish' / 'scripts'
ACE_TAKES = SOUND_SCRIPTS / 'ace_takes.py'
SCORE_PY = SOUND_SCRIPTS / 'score.py'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FINISH_SCRIPTS))
import compose  # noqa: E402
from compose import StudioError, ensure_studio_dir, inside, write_atomic  # noqa: E402
import finish as finish_mod  # noqa: E402

SR = 48000
DEFAULT_LUFS = -18.0
DEFAULT_PEAK = -3.0
DEFAULT_BPM = 100
DEFAULT_KEY = 'A minor'
LAYERS = ('Place and people', 'Local genre', 'Local instruments', 'Rhythm and scale', 'Scene energy')
SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
SEED_STEPS = (0, 12, 26)
SCORE_STYLES = ('pulse', 'calm', 'uplift', 'cinematic')


def music_dir(video):
    return ensure_studio_dir(Path(video)) / 'results' / 'music'


def read_music_results(video):
    """music.json, or None before the first audition. Reads only: no folder is made."""
    try:
        m = json.loads((Path(video) / '.studio' / 'results' / 'music' / 'music.json').read_text(encoding='utf-8'))
        return m if isinstance(m, dict) else None
    except (OSError, ValueError):
        return None


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def probe_duration(path):
    r = _run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)])
    if r.returncode:
        return None
    try:
        return round(float(r.stdout.strip()), 3)
    except ValueError:
        return None


def level_audio(src, dst, target_lufs=DEFAULT_LUFS, peak_db=DEFAULT_PEAK):
    """Level any audio file to target_lufs with true-peak ceiling peak_db via finish.master_audio (48 kHz stereo WAV)."""
    try:
        res = finish_mod.master_audio(src, dst, target_lufs, peak_db)
    except RuntimeError as e:
        if 'silent or too quiet' in str(e):
            shutil.copyfile(src, dst)
            return {'lufs': None, 'true_peak': None}
        raise StudioError(f'ffmpeg could not level {src}: {str(e).strip()[:300]}')
    i1, tp1 = res.get('after_lufs'), res.get('after_tp')
    return {'lufs': round(i1, 2) if i1 is not None else None, 'true_peak': round(tp1, 2) if tp1 is not None else None}


def film_length(film):
    parts = film.get('parts') or []
    return float(film.get('length') or (parts[-1]['to'] if parts else 0) or 0)


def cues_for_film(film):
    """Resolve one cue per story world (style run group) or explicit cue in film.music.cues.
    Returns list of dicts: {id, name, style, bpm, key, hits, spans: [[a,b],...], duration, layers, pick, wrong}."""
    parts = [p for p in film.get('parts') or [] if isinstance(p, dict)]
    smap = (film.get('styles') or {}).get('map') or {}
    music = film.get('music') if isinstance(film.get('music'), dict) else {}
    stored = music.get('cues') if isinstance(music.get('cues'), dict) else {}
    cat = compose.catalogue()

    # Group contiguous runs by style to discover story worlds in order of appearance.
    runs = []
    for p in parts:
        st = (smap.get(p['id']) or {}).get('style')
        if not st:
            continue
        if runs and runs[-1]['style'] == st:
            runs[-1]['to'] = float(p['to'])
        else:
            runs.append({'style': st, 'from': float(p['from']), 'to': float(p['to'])})

    world_order = []
    for r in runs:
        if r['style'] not in world_order:
            world_order.append(r['style'])
    # Also keep explicit cues defined in film.music.cues (e.g. single-style film with a story flip).
    for cid in stored:
        if cid not in world_order:
            world_order.append(cid)

    total = film_length(film)
    out = []
    for cid in world_order:
        if not SAFE_ID.fullmatch(str(cid)):
            continue
        raw = stored.get(cid) if isinstance(stored.get(cid), dict) else {}
        spans = raw.get('spans')
        if not (isinstance(spans, list) and spans):
            spans = [[r['from'], r['to']] for r in runs if r['style'] == cid]
        if not spans and total > 0:
            spans = [[0.0, total]]
        spans = [[round(float(a), 3), round(float(b), 3)] for a, b in spans if float(b) > float(a)]
        dur = round(sum(b - a for a, b in spans), 3)
        style_id = raw.get('style') or (cid if cid in cat else None)
        style_name = cat.get(style_id, {}).get('name') if style_id else cid
        bpm = int(raw.get('bpm') or DEFAULT_BPM)
        bpm = max(60, min(200, bpm))
        out.append({
            'id': cid,
            'name': raw.get('name') or f'{style_name} world',
            'style': style_id,
            'bpm': bpm,
            'key': str(raw.get('key') or DEFAULT_KEY),
            'hits': str(raw.get('hits') or ''),
            'spans': spans,
            'duration': dur,
            'layers': raw.get('layers') if isinstance(raw.get('layers'), list) else [],
            'pick': raw.get('pick'),
            'pick_round': raw.get('pick_round'),
            'wrong': str(raw.get('wrong') or ''),
        })
    return out


def caption_for(cue, avoid=None):
    """Build the music prompt string from the 5 keyword layers, checking against words to avoid.
    Returns (caption, warnings)."""
    words = []
    for layer in cue.get('layers') or []:
        if not isinstance(layer, dict):
            continue
        for chip in layer.get('chips') or []:
            kw = chip[0] if isinstance(chip, (list, tuple)) and chip else (chip.get('word') if isinstance(chip, dict) else '')
            kw = str(kw or '').strip()
            if kw:
                words.append(kw)
    avoid_words = []
    for item in avoid or []:
        w = item[0] if isinstance(item, (list, tuple)) and item else (item.get('word') if isinstance(item, dict) else str(item))
        w = str(w or '').strip()
        if w:
            avoid_words.append(w)
    warnings = []
    clean = []
    for kw in words:
        hit = next((a for a in avoid_words if re.search(rf'\b{re.escape(a)}\b', kw, re.I)), None)
        if hit:
            warnings.append(f'keyword "{kw}" contains avoided word "{hit}" (skipped in caption)')
        else:
            clean.append(kw)
    if not clean:
        clean = [f'{cue.get("name") or "instrumental"} underscore', f'{cue.get("bpm", DEFAULT_BPM)} BPM', 'instrumental']
    else:
        if not any('instrumental' in w.lower() or 'vocal' in w.lower() for w in clean):
            clean.insert(0, 'instrumental')
    return ', '.join(clean), warnings


def cue_basis(cue, avoid):
    """What a cue's takes were made from, so Room ⑤ can flag out-of-date takes when keywords or BPM change."""
    cap, _ = caption_for(cue, avoid)
    return {'caption': cap, 'bpm': cue['bpm'], 'key': cue['key'], 'spans': cue['spans']}


def find_picture(video, explicit=None):
    if explicit:
        p = Path(explicit).expanduser()
        p = p if p.is_absolute() else Path(video) / p
        if not p.is_file():
            raise StudioError(f'picture video not found: {p}')
        return p
    default = Path(video) / '.studio' / 'results' / 'render' / 'picture.mp4'
    return default if default.is_file() else None


def mux_on_picture(picture, audio, dst, start_s, duration_s):
    """Place an audition take onto the cue's slice of the built picture, so the person watches and listens together."""
    r = _run([
        'ffmpeg', '-v', 'error', '-y',
        '-ss', f'{start_s:.3f}', '-t', f'{duration_s:.3f}', '-i', str(picture),
        '-i', str(audio),
        '-map', '0:v:0', '-map', '1:a:0',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart',
        str(dst),
    ])
    if r.returncode:
        raise StudioError(f'could not place take on picture: {r.stderr.strip()[:300]}')


def bars_for(seconds, bpm):
    """Minimum whole 4/4 bars covering at least `seconds` (clamped to ACE-Step's 10..600 s range)."""
    bar_s = 4.0 * 60.0 / bpm
    bars = max(4, math.ceil(seconds / bar_s))
    while bars * bar_s < 10.0:
        bars += 1
    return bars


def _score_style_for(caption, bpm, idx):
    low = caption.lower()
    if any(k in low for k in ('noir', 'tension', 'cinema', 'orchestra', 'dramatic', 'dark')):
        order = ('cinematic', 'calm', 'pulse', 'uplift')
    elif any(k in low for k in ('bright', 'happy', 'festival', 'keynote', 'hope', 'major', 'shaabi')):
        order = ('uplift', 'pulse', 'calm', 'cinematic')
    elif bpm < 95:
        order = ('calm', 'cinematic', 'uplift', 'pulse')
    else:
        order = ('pulse', 'uplift', 'calm', 'cinematic')
    return order[idx % len(order)]


def _generate_one_take(engine, caption, cue, take_idx, seed, target_s, work_dir):
    """Make one raw WAV take of at least target_s seconds.
    Returns (wav_path, used_engine, engine_label, is_guide).
    ACE-Step is the default and never silently falls back to the built-in synth (score.py)."""
    raw_wav = work_dir / f'raw-{cue["id"]}-{take_idx}-s{seed}.wav'
    fake = os.environ.get('KIT_TO_CLIP_MUSIC_FAKE')
    if fake and engine != 'score':
        cmd = shlex.split(fake) + [str(raw_wav), '--duration', f'{target_s:.3f}', '--seed', str(seed),
                                   '--bpm', str(cue['bpm']), '--caption', caption]
        r = _run(cmd, timeout=120)
        if r.returncode or not raw_wav.is_file():
            raise StudioError(f'fake music generator failed: {(r.stderr or r.stdout).strip()[:300]}')
        return raw_wav, 'fake', 'Test audio', False

    bars = bars_for(target_s, cue['bpm'])
    if engine == 'ace':
        ace_dir = work_dir / f'ace-{cue["id"]}-s{seed}'
        r = _run([
            sys.executable, str(ACE_TAKES), caption,
            '--bpm', str(cue['bpm']), '--key', cue['key'], '--bars', str(bars),
            '--takes', '1', '--seed', str(seed), '--lufs', str(DEFAULT_LUFS),
            '--out', str(ace_dir),
        ], timeout=1800)
        if r.returncode == 0 and (ace_dir / 'music.wav').is_file():
            shutil.copyfile(ace_dir / 'music.wav', raw_wav)
            return raw_wav, 'ace-step', 'ACE-Step', False
        if r.returncode == 3:
            raise StudioError(
                'ACE-Step is not installed, so no music takes were made. '
                'Install it with `toolbox.py install ace-step` after a ✋ yes (first run downloads ~9.4 GB). '
                'The built-in synth is never used automatically; pass `--engine score` only if the person explicitly asks for a temporary guide track.'
            )
        detail = (r.stderr or r.stdout).strip()[:300]
        raise StudioError(
            f'ACE-Step failed (exit {r.returncode}): {detail}. '
            'No takes were made; the built-in synth is never used as a silent fallback.'
        )

    if engine == 'score':
        sc_dir = work_dir / f'score-{cue["id"]}-s{seed}'
        style = _score_style_for(caption, cue['bpm'], take_idx)
        r = _run([
            sys.executable, str(SCORE_PY), 'make',
            '--style', style, '--bpm', str(cue['bpm']), '--key', cue['key'],
            '--bars', str(bars), '--seed', str(seed), '--out', str(sc_dir),
        ], timeout=120)
        if r.returncode or not (sc_dir / 'music.wav').is_file():
            raise StudioError(f'score.py failed: {(r.stderr or r.stdout).strip()[:300]}')
        shutil.copyfile(sc_dir / 'music.wav', raw_wav)
        return raw_wav, f'score:{style}', 'Temporary synth guide', True

    raise StudioError(f'unknown music engine "{engine}" (use "ace" or explicitly "score" for a temporary guide track)')


def trim_with_fade(src, dst, duration_s, fade_out=0.35):
    """Trim or pad stereo WAV to exact duration_s with a smooth tail fade."""
    fade_start = max(0.0, duration_s - fade_out)
    af = f'apad=whole_dur={duration_s:.3f},atrim=0:{duration_s:.3f},afade=t=out:st={fade_start:.3f}:d={min(fade_out, duration_s):.3f}'
    r = _run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-ac', '2', '-ar', str(SR),
              '-af', af, '-c:a', 'pcm_s16le', str(dst)])
    if r.returncode:
        raise StudioError(f'could not trim take: {r.stderr.strip()[:300]}')


def _clear_stale_picks(video, film_name, cue_ids):
    """Clear previous picks in film.json for cues that just got a new round of takes, so nobody approves unheard music."""
    film_path = Path(video) / film_name
    try:
        film = json.loads(film_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    m = film.get('music')
    cues = m.get('cues') if isinstance(m, dict) else None
    if not isinstance(cues, dict):
        return []
    cleared = []
    for cid in cue_ids:
        entry = cues.get(cid)
        if isinstance(entry, dict) and (entry.get('pick') is not None or entry.get('pick_round') is not None):
            entry['pick'] = None
            entry.pop('pick_round', None)
            cleared.append(cid)
    if cleared:
        write_atomic(film_path, json.dumps(film, indent=2, ensure_ascii=False) + '\n')
    return cleared


def audition(video, film_name='film.json', cue_id=None, picture=None, n_takes=3, seed=None,
             engine='ace', lufs=DEFAULT_LUFS, preview_max_s=30.0):
    """Generate `n_takes` different takes per cue, level to `lufs`, and place on the built picture when available.
    Clears any previous human pick for the auditioned cue(s) so the person must hear the new round before picking."""
    video = Path(video).resolve()
    film = compose.load_film(video, film_name)
    cues = cues_for_film(film)
    if not cues:
        raise StudioError('no story worlds or cues found yet: put styles on the story parts or define film.music.cues')
    if cue_id:
        cues = [c for c in cues if c['id'] == cue_id]
        if not cues:
            raise StudioError(f'no cue "{cue_id}" in this film')
    if engine == 'score':
        print('⚠️ Using temporary synth guide (score.py) as explicitly requested; not final music.', file=sys.stderr)
    avoid = ((film.get('music') or {}).get('avoid') or [])
    pic = find_picture(video, picture)
    out_dir = music_dir(video)
    out_dir.mkdir(parents=True, exist_ok=True)
    prev = read_music_results(video) or {'version': 0, 'cues': {}}
    results_cues = dict(prev.get('cues') or {})
    steps = list(SEED_STEPS) + [SEED_STEPS[-1] + 12 * i for i in range(1, max(1, n_takes - len(SEED_STEPS) + 1))]

    with tempfile.TemporaryDirectory(prefix='k2c-music-') as tmp:
        work = Path(tmp)
        for ci, cue in enumerate(cues):
            prev_cue = results_cues.get(cue['id']) if isinstance(results_cues.get(cue['id']), dict) else {}
            cue_round = int(prev_cue.get('round') or 0) + 1
            base_seed = int(seed) if seed is not None else (11 + (cue_round - 1) * 40)
            seeds = [base_seed + s for s in steps[:n_takes]]
            caption, warns = caption_for(cue, avoid)
            first_span = cue['spans'][0] if cue['spans'] else [0.0, 20.0]
            span_len = max(2.0, first_span[1] - first_span[0])
            aud_len = round(min(span_len, preview_max_s) if preview_max_s else span_len, 3)
            takes_out = []
            cue_engine = None
            cue_engine_label = None
            cue_is_guide = False
            for ti, sd in enumerate(seeds, 1):
                cue_seed = sd + ci * 100
                raw_wav, used_engine, engine_label, is_guide = _generate_one_take(
                    engine, caption, cue, ti - 1, cue_seed, aud_len, work
                )
                cue_engine = used_engine
                cue_engine_label = engine_label
                cue_is_guide = cue_is_guide or is_guide
                trimmed = work / f'trim-{cue["id"]}-{ti}.wav'
                trim_with_fade(raw_wav, trimmed, aud_len)
                wav_name = f'{cue["id"]}-take-{ti}.wav'
                wav_path = out_dir / wav_name
                stats = level_audio(trimmed, wav_path, target_lufs=lufs)
                item = {
                    'n': ti,
                    'round': cue_round,
                    'seed': cue_seed,
                    'engine': used_engine,
                    'engine_label': engine_label,
                    'is_guide': is_guide,
                    'audio': wav_name,
                    'duration': probe_duration(wav_path) or aud_len,
                    'lufs': stats.get('lufs'),
                    'true_peak': stats.get('true_peak'),
                }
                if pic is not None:
                    mp4_name = f'{cue["id"]}-take-{ti}.mp4'
                    mux_on_picture(pic, wav_path, out_dir / mp4_name, first_span[0], aud_len)
                    item['video'] = mp4_name
                takes_out.append(item)
            results_cues[cue['id']] = {
                'id': cue['id'],
                'name': cue['name'],
                'round': cue_round,
                'engine': cue_engine,
                'engine_label': cue_engine_label,
                'is_guide': cue_is_guide,
                'caption': caption,
                'warnings': warns,
                'bpm': cue['bpm'],
                'key': cue['key'],
                'span': first_span,
                'duration': aud_len,
                'on_picture': pic is not None,
                'basis': cue_basis(cue, avoid),
                'takes': takes_out,
                'made': now_iso(),
            }

    auditioned_ids = [c['id'] for c in cues]
    cleared_picks = _clear_stale_picks(video, film_name, auditioned_ids)
    prev_asm = prev.get('assembled')
    if isinstance(prev_asm, dict):
        asm_picks = prev_asm.get('picks') if isinstance(prev_asm.get('picks'), dict) else {}
        if any(cid in asm_picks for cid in auditioned_ids) or not asm_picks:
            asm_file = prev_asm.get('file')
            if isinstance(asm_file, str) and asm_file:
                cand = Path(asm_file) if os.path.isabs(asm_file) else (out_dir / asm_file)
                if cand.is_file() and inside(cand, out_dir):
                    cand.unlink(missing_ok=True)
            prev_asm = None
    if prev_asm is None:
        (out_dir / 'score-full.wav').unlink(missing_ok=True)

    manifest = {
        'version': int(prev.get('version') or 0) + 1,
        'made': now_iso(),
        'film': film_name,
        'lufs': lufs,
        'unheard': True,
        'cleared_picks': cleared_picks,
        'cues': results_cues,
        'assembled': prev_asm,
    }
    write_atomic(out_dir / 'music.json', json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    return manifest


def extend_to_duration(src, dst, duration_s, fade_in=0.25, fade_out=0.6):
    """Extend a picked take (smooth crossfade loop if shorter than duration_s, never a new song) and trim cleanly."""
    cur = probe_duration(src) or duration_s
    if cur >= duration_s - 0.05:
        fade_st = max(0.0, duration_s - fade_out)
        af = (f'apad=whole_dur={duration_s:.3f},atrim=0:{duration_s:.3f},'
              f'afade=t=in:st=0:d={min(fade_in, duration_s / 3):.3f},'
              f'afade=t=out:st={fade_st:.3f}:d={min(fade_out, duration_s / 3):.3f}')
        r = _run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-ac', '2', '-ar', str(SR),
                  '-af', af, '-c:a', 'pcm_s16le', str(dst)])
        if r.returncode:
            raise StudioError(f'could not trim picked take: {r.stderr.strip()[:300]}')
        return
    # Loop with a crossfade overlap so extending the chosen take never clicks or cuts abruptly.
    xf = min(1.0, cur * 0.2)
    step = max(0.5, cur - xf)
    copies = max(2, math.ceil((duration_s + xf) / step))
    inputs = []
    for _ in range(copies):
        inputs.extend(['-i', str(src)])
    fc_parts = []
    prev_lbl = '0:a'
    for idx in range(1, copies):
        nxt_lbl = f'x{idx}'
        fc_parts.append(f'[{prev_lbl}][{idx}:a]acrossfade=d={xf:.3f}:c1=tri:c2=tri[{nxt_lbl}]')
        prev_lbl = nxt_lbl
    fade_st = max(0.0, duration_s - fade_out)
    fc_parts.append(
        f'[{prev_lbl}]atrim=0:{duration_s:.3f},'
        f'afade=t=in:st=0:d={min(fade_in, duration_s / 3):.3f},'
        f'afade=t=out:st={fade_st:.3f}:d={min(fade_out, duration_s / 3):.3f}[out]'
    )
    r = _run(['ffmpeg', '-v', 'error', '-y', *inputs, '-filter_complex', ';'.join(fc_parts),
              '-map', '[out]', '-ac', '2', '-ar', str(SR), '-c:a', 'pcm_s16le', str(dst)])
    if r.returncode:
        raise StudioError(f'could not extend picked take: {r.stderr.strip()[:300]}')


def assemble(video, film_name='film.json', out_path=None, lufs=DEFAULT_LUFS):
    """Extend each cue's human-picked take across all its film spans into one full-length music WAV.
    Refuses if any cue has no pick (Claude never picks music for the person)."""
    video = Path(video).resolve()
    film = compose.load_film(video, film_name)
    cues = cues_for_film(film)
    if not cues:
        raise StudioError('no cues found in this film')
    manifest = read_music_results(video)
    if not manifest or not manifest.get('cues'):
        raise StudioError('no music takes yet: run music.py audition first')
    out_dir = music_dir(video)
    missing = [c['id'] for c in cues if not c.get('pick')]
    if missing:
        raise StudioError('no take picked yet for: ' + ', '.join(missing) + '. The person picks by ear first')

    total = film_length(film)
    if total <= 0:
        total = max((b for c in cues for _, b in c['spans']), default=0)
    if total <= 0:
        raise StudioError('the film has no length yet')

    segments = []
    engines = {}
    guide_cues = []
    with tempfile.TemporaryDirectory(prefix='k2c-asm-') as tmp:
        work = Path(tmp)
        for cue in cues:
            cm = (manifest.get('cues') or {}).get(cue['id'])
            if not cm:
                raise StudioError(f'no audition takes for cue "{cue["id"]}" yet')
            cur_round = int(cm.get('round') or 1)
            if cue.get('pick_round') is None:
                raise StudioError(
                    f'cue "{cue["id"]}": pick has no round number (latest takes are round {cur_round}); '
                    'listen to the latest takes and pick again'
                )
            if int(cue['pick_round']) != cur_round:
                raise StudioError(
                    f'cue "{cue["id"]}": pick is from round {cue["pick_round"]}, '
                    f'but the latest takes are round {cur_round}; listen to the new takes and pick again'
                )
            pick_n = int(cue['pick'])
            take = next((t for t in cm.get('takes') or [] if int(t.get('n', -1)) == pick_n), None)
            if not take:
                raise StudioError(f'cue "{cue["id"]}": take {pick_n} is not in music.json')
            take_wav = out_dir / take['audio']
            if not take_wav.is_file():
                raise StudioError(f'cue "{cue["id"]}": missing take file {take_wav}')
            eng = str(take.get('engine') or cm.get('engine') or '')
            engines[cue['id']] = eng
            if bool(take.get('is_guide') or eng.startswith('score')):
                guide_cues.append(cue['id'])
            for si, (a, b) in enumerate(cue['spans']):
                seg_wav = work / f'{cue["id"]}-{si}.wav'
                extend_to_duration(take_wav, seg_wav, b - a)
                segments.append((a, seg_wav))

        dst = Path(out_path).expanduser() if out_path else (out_dir / 'score-full.wav')
        if not dst.is_absolute():
            dst = video / dst
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Place every span at its exact millisecond offset on a silent bed of exact film length.
        inputs = ['-f', 'lavfi', '-i', f'anullsrc=r={SR}:cl=stereo:d={total:.3f}']
        fc = []
        mix_labels = ['[0:a]']
        for idx, (start_s, seg_wav) in enumerate(segments, 1):
            inputs.extend(['-i', str(seg_wav)])
            ms = max(0, int(round(start_s * 1000)))
            fc.append(f'[{idx}:a]adelay={ms}|{ms}[s{idx}]')
            mix_labels.append(f'[s{idx}]')
        fc.append(f'{"".join(mix_labels)}amix=inputs={len(mix_labels)}:normalize=0:duration=first,atrim=0:{total:.3f}[mix]')
        raw_full = work / 'raw-full.wav'
        r = _run(['ffmpeg', '-v', 'error', '-y', *inputs, '-filter_complex', ';'.join(fc),
                  '-map', '[mix]', '-ac', '2', '-ar', str(SR), '-c:a', 'pcm_s16le', str(raw_full)])
        if r.returncode:
            raise StudioError(f'could not assemble music track: {r.stderr.strip()[:300]}')
        stats = level_audio(raw_full, dst, target_lufs=lufs)

    assembled = {
        'file': dst.name if dst.parent == out_dir else str(dst),
        'duration': probe_duration(dst) or round(total, 3),
        'lufs': stats.get('lufs'),
        'true_peak': stats.get('true_peak'),
        'picks': {c['id']: int(c['pick']) for c in cues},
        'rounds': {c['id']: int((manifest['cues'][c['id']]).get('round') or 1) for c in cues},
        'engines': engines,
        'guide_cues': guide_cues,
        'is_guide': bool(guide_cues),
        'made': now_iso(),
        'unheard': True,
    }
    manifest['assembled'] = assembled
    manifest['version'] = int(manifest.get('version') or 0) + 1
    write_atomic(out_dir / 'music.json', json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    return assembled


def main(argv=None):
    ap = argparse.ArgumentParser(description='Kit to Clip Studio music: keywords, 3 takes on the picture, assembly.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('cues', help='list resolved cues and captions from film.json')
    p.add_argument('video')
    p.add_argument('--film', default='film.json')

    p = sub.add_parser('audition', help='make 3 takes per cue, levelled to -18 LUFS, on the picture when available')
    p.add_argument('video')
    p.add_argument('--film', default='film.json')
    p.add_argument('--cue', help='audition only this cue id')
    p.add_argument('--picture', help='rendered picture mp4 (default .studio/results/render/picture.mp4 if present)')
    p.add_argument('--takes', type=int, default=3)
    p.add_argument('--seed', type=int, default=None, help='starting seed (default advances automatically on each round)')
    p.add_argument('--engine', choices=('ace', 'score'), default='ace',
                   help='ace (ACE-Step, default; never falls back silently) or score (explicit temporary synth guide only)')
    p.add_argument('--lufs', type=float, default=DEFAULT_LUFS)
    p.add_argument('--preview-max', type=float, default=30.0, help='max seconds per audition clip (0 = full cue)')

    p = sub.add_parser('assemble', help='extend each picked take into one full-length music track')
    p.add_argument('video')
    p.add_argument('--film', default='film.json')
    p.add_argument('--out', help='output WAV (default .studio/results/music/score-full.wav)')
    p.add_argument('--lufs', type=float, default=DEFAULT_LUFS)

    a = ap.parse_args(argv)
    try:
        if a.cmd == 'cues':
            film = compose.load_film(a.video, a.film)
            avoid = ((film.get('music') or {}).get('avoid') or [])
            out = []
            for c in cues_for_film(film):
                cap, warns = caption_for(c, avoid)
                out.append({**c, 'caption': cap, 'warnings': warns})
            print(json.dumps(out, indent=2, ensure_ascii=False))
        elif a.cmd == 'audition':
            m = audition(a.video, a.film, a.cue, a.picture, a.takes, a.seed, a.engine, a.lufs, a.preview_max)
            print(json.dumps({'version': m['version'], 'cues': list(m['cues']), 'unheard': True}, ensure_ascii=False))
        elif a.cmd == 'assemble':
            res = assemble(a.video, a.film, a.out, a.lufs)
            print(json.dumps(res, ensure_ascii=False))
        return 0
    except StudioError as e:
        print(f'❌ {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
