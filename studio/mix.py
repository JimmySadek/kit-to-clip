#!/usr/bin/env python3
"""⑥ Finish: mix voice + effects + picked music (music ducked 12-15 LU under voice, mastered to -14 LUFS),
generate captions (.srt and safe-area burned-in .ass) from Parakeet word times + clean copy, and assemble final.mp4.

  python3 mix.py <video-folder> [--picture <mp4>] [--voice <wav>] [--sfx <wav>] [--music <wav>]
                                [--captions burned|srt|off] [--lufs -14] [--duck-db 13.5] [--film film.json]

Outputs land in <video>/.studio/results/finish/ (git-ignored):
  mix.m4a          mastered audio (-14 LUFS, true peak <= -1.0 dBTP)
  captions.srt     SubRip captions when voice words or timed lines exist
  final.mp4        finished video for the ✋ Final film watch in Room ⑥ Finish
  finish.json      loudness measurements, caption info, formats, basis, unheard=true

The agent cannot hear. Every mix is labelled unheard until the person watches and listens at ✋ Final film.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
FINISH_PY = SKILL_ROOT / 'finish' / 'scripts' / 'finish.py'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FINISH_PY.parent))
import approvals  # noqa: E402
import compose  # noqa: E402
from compose import StudioError, ensure_studio_dir, inside, write_atomic  # noqa: E402
import finish as finish_mod  # noqa: E402
import music as music_mod  # noqa: E402

SR = 48000
DEFAULT_LUFS = -14.0
DEFAULT_PEAK = -1.0
DEFAULT_DUCK_DB = 13.5
TIMED_RE = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)\s*\|\s*(.+?)\s*$')


def finish_dir(video):
    return ensure_studio_dir(Path(video)) / 'results' / 'finish'


def read_finish(video):
    """finish.json, or None before the first finish. Reads only: no folder is made."""
    try:
        f = json.loads((Path(video) / '.studio' / 'results' / 'finish' / 'finish.json').read_text(encoding='utf-8'))
        return f if isinstance(f, dict) else None
    except (OSError, ValueError):
        return None


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def probe(path):
    r = _run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate:format=duration,size',
              '-of', 'json', str(path)])
    if r.returncode:
        raise StudioError(f'ffprobe could not read {path}')
    d = json.loads(r.stdout)
    v = next((s for s in d.get('streams') or [] if s.get('codec_type') == 'video'), {})
    return {
        'width': v.get('width'),
        'height': v.get('height'),
        'duration': float(d['format'].get('duration') or 0),
        'bytes': int(d['format'].get('size') or 0),
    }


def _fmt_srt_time(s):
    ms = max(0, int(round(s * 1000)))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    sec, msec = divmod(rem, 1000)
    return f'{h:02d}:{m:02d}:{sec:02d},{msec:03d}'


def _fmt_ass_time(s):
    cs = max(0, int(round(s * 100)))
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    sec, csec = divmod(rem, 100)
    return f'{h:d}:{m:02d}:{sec:02d}.{csec:02d}'


def group_words_to_cues(words, max_chars=42, max_words=8, pause_break=0.45):
    """Turn Parakeet word-level timestamps [{text, start, end}] into readable subtitle cues."""
    cues = []
    cur = []
    cur_len = 0

    def flush():
        nonlocal cur, cur_len
        if not cur:
            return
        start = float(cur[0]['start'])
        end = max(float(cur[-1]['end']), start + 0.65)
        text = ' '.join(w['text'].strip() for w in cur if str(w.get('text', '')).strip())
        if text:
            cues.append({'start': round(start, 3), 'end': round(end, 3), 'text': text})
        cur, cur_len = [], 0

    for w in words:
        txt = str(w.get('text') or '').strip()
        if not txt:
            continue
        if cur:
            gap = float(w.get('start', 0)) - float(cur[-1].get('end', 0))
            if gap >= pause_break or len(cur) >= max_words or (cur_len + 1 + len(txt) > max_chars):
                flush()
        cur.append(w)
        cur_len += (1 if cur_len else 0) + len(txt)
        if re.search(r'[.!?]["\']?$', txt) and len(cur) >= 2:
            flush()
    flush()

    # Never overlap neighbouring cues.
    for i in range(len(cues) - 1):
        if cues[i]['end'] > cues[i + 1]['start'] - 0.04:
            cues[i]['end'] = round(max(cues[i]['start'] + 0.2, cues[i + 1]['start'] - 0.04), 3)
    return cues


def write_srt(cues, path):
    blocks = []
    for i, c in enumerate(cues, 1):
        blocks.append(f'{i}\n{_fmt_srt_time(c["start"])} --> {_fmt_srt_time(c["end"])}\n{c["text"]}\n')
    write_atomic(path, '\n'.join(blocks))


def write_ass(cues, path, width=1280, height=720):
    """Clean, high-contrast bottom safe-area ASS subtitles (readable on phones, inside YouTube/web safe zone)."""
    font_size = max(24, int(round(height * 0.046)))
    margin_v = max(36, int(round(height * 0.11)))
    margin_h = max(48, int(round(width * 0.07)))
    header = (
        '[Script Info]\n'
        'ScriptType: v4.00+\n'
        f'PlayResX: {width}\n'
        f'PlayResY: {height}\n'
        'WrapStyle: 0\n\n'
        '[V4+ Styles]\n'
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
        'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
        'Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f'Style: Default,Helvetica Neue,{font_size},&H00FFFFFF,&H000000FF,&H00121816,&HA0121816,'
        f'-1,0,0,0,100,100,0,0,3,2,0,2,{margin_h},{margin_h},{margin_v},1\n\n'
        '[Events]\n'
        'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    )
    lines = [header]
    for c in cues:
        txt = c['text'].replace('\\', '\\\\').replace('{', r'\{').replace('}', r'\}').replace('\n', r'\N')
        lines.append(f'Dialogue: 0,{_fmt_ass_time(c["start"])},{_fmt_ass_time(c["end"])},Default,,0,0,0,,{txt}\n')
    write_atomic(path, ''.join(lines))


def collect_voice_and_words(video, film, work_dir, explicit_voice=None):
    """Resolve the film-time voice track WAV (or None) and subtitle cues + caption source label."""
    video = Path(video).resolve()
    voice_wav = None
    words = []
    source = 'none'

    # 1. Explicit voice WAV argument.
    if explicit_voice:
        p = Path(explicit_voice).expanduser()
        p = p if p.is_absolute() else video / p
        if not p.is_file():
            raise StudioError(f'voice audio not found: {p}')
        voice_wav = p

    # 2. Segment takes from Room ③ Voice (voice.takes + voice/<seg>.words.json).
    vsec = film.get('voice') if isinstance(film.get('voice'), dict) else {}
    takes = vsec.get('takes') if isinstance(vsec.get('takes'), dict) else {}
    segs = ((film.get('script') or {}).get('segments') or [])
    seg_files = []
    cursor = 0.0
    for g in segs:
        if not isinstance(g, dict):
            continue
        sid = g.get('id')
        t = takes.get(sid) if isinstance(takes.get(sid), dict) else None
        if not t or not t.get('file'):
            continue
        audio_p = video / t['file']
        if not audio_p.is_file():
            continue
        slot = g.get('slot')
        offset = float(slot[0]) if isinstance(slot, (list, tuple)) and slot else cursor
        dur = probe(audio_p)['duration']
        seg_files.append((offset, audio_p))
        if t.get('words_file') and (video / t['words_file']).is_file():
            try:
                wdoc = json.loads((video / t['words_file']).read_text(encoding='utf-8'))
                for w in wdoc.get('words') or []:
                    words.append({
                        'text': w.get('text', ''),
                        'start': round(offset + float(w.get('start', 0)), 3),
                        'end': round(offset + float(w.get('end', 0)), 3),
                    })
                source = 'parakeet'
            except (OSError, ValueError):
                pass
        cursor = max(cursor, offset + dur + 0.35)

    if voice_wav is None and seg_files:
        # Stitch segment takes at their offsets into one stereo 48 kHz WAV.
        total_v = max(off + probe(p)['duration'] for off, p in seg_files) + 0.2
        inputs = ['-f', 'lavfi', '-i', f'anullsrc=r={SR}:cl=stereo:d={total_v:.3f}']
        fc = []
        labels = ['[0:a]']
        for idx, (off, p) in enumerate(seg_files, 1):
            inputs.extend(['-i', str(p)])
            ms = max(0, int(round(off * 1000)))
            fc.append(f'[{idx}:a]aformat=sample_rates={SR}:channel_layouts=stereo,adelay={ms}|{ms}[v{idx}]')
            labels.append(f'[v{idx}]')
        fc.append(f'{"".join(labels)}amix=inputs={len(labels)}:normalize=0:duration=first[vout]')
        stitched = work_dir / 'voice-stitched.wav'
        r = _run(['ffmpeg', '-v', 'error', '-y', *inputs, '-filter_complex', ';'.join(fc),
                  '-map', '[vout]', '-ac', '2', '-ar', str(SR), '-c:a', 'pcm_s16le', str(stitched)])
        if r.returncode:
            raise StudioError(f'could not assemble voice segments: {r.stderr.strip()[:300]}')
        voice_wav = stitched

    # 3. Single pre-placed voice input in film.json inputs (e.g. a complete voiceover WAV).
    if voice_wav is None:
        for inp in film.get('inputs') or []:
            if isinstance(inp, dict) and inp.get('kind') == 'voice' and inp.get('path'):
                p = compose.expand(inp['path'], video)
                if p and p.is_file():
                    voice_wav = p
                    break

    # 4. Subtitle cues: Parakeet words -> timed script file -> film.parts words.
    cues = []
    if words:
        cues = group_words_to_cues(words)
    else:
        for inp in film.get('inputs') or []:
            if isinstance(inp, dict) and inp.get('kind') == 'script' and inp.get('path'):
                p = compose.expand(inp['path'], video)
                if p and p.is_file():
                    try:
                        for line in p.read_text(encoding='utf-8').splitlines():
                            m = TIMED_RE.match(line)
                            if m:
                                cues.append({'start': float(m.group(1)), 'end': float(m.group(2)), 'text': m.group(3).strip()})
                        if cues:
                            source = 'timed-script'
                            break
                    except (OSError, UnicodeDecodeError):
                        pass
    if not cues:
        for part in film.get('parts') or []:
            if isinstance(part, dict) and (part.get('words') or '').strip():
                cues.append({'start': float(part['from']), 'end': float(part['to']), 'text': part['words'].strip()})
        if cues:
            source = 'parts'
    return voice_wav, cues, source


def mix_stems(out_wav, duration_s, voice_wav=None, sfx_wav=None, music_wav=None, duck_db=DEFAULT_DUCK_DB):
    """Combine voice, effects and music into one 48 kHz stereo pre-master WAV.
    When both voice and music exist, music is ducked smoothly under voice by duck_db (12-15 LU)."""
    stems = []
    inputs = ['-f', 'lavfi', '-i', f'anullsrc=r={SR}:cl=stereo:d={duration_s:.3f}']
    fc = []
    mix_inputs = ['[0:a]']

    v_idx = s_idx = m_idx = None
    idx = 1
    if voice_wav is not None:
        inputs.extend(['-i', str(voice_wav)])
        v_idx = idx
        idx += 1
        stems.append('voice')
    if sfx_wav is not None:
        inputs.extend(['-i', str(sfx_wav)])
        s_idx = idx
        idx += 1
        stems.append('sfx')
    if music_wav is not None:
        inputs.extend(['-i', str(music_wav)])
        m_idx = idx
        idx += 1
        stems.append('music')

    if not stems:
        # Silent film: write clean silence matching duration.
        r = _run(['ffmpeg', '-v', 'error', '-y', *inputs, '-t', f'{duration_s:.3f}',
                  '-ac', '2', '-ar', str(SR), '-c:a', 'pcm_s16le', str(out_wav)])
        if r.returncode:
            raise StudioError(f'could not write silent track: {r.stderr.strip()[:300]}')
        return stems

    if v_idx is not None:
        # Keep voice clean and forward; split a sidechain feed when music is present.
        if m_idx is not None:
            fc.append(f'[{v_idx}:a]aformat=sample_rates={SR}:channel_layouts=stereo,apad=whole_dur={duration_s:.3f},'
                      f'atrim=0:{duration_s:.3f},asplit=2[vmain][vsc]')
            mix_inputs.append('[vmain]')
        else:
            fc.append(f'[{v_idx}:a]aformat=sample_rates={SR}:channel_layouts=stereo,apad=whole_dur={duration_s:.3f},'
                      f'atrim=0:{duration_s:.3f}[vmain]')
            mix_inputs.append('[vmain]')

    if s_idx is not None:
        fc.append(f'[{s_idx}:a]aformat=sample_rates={SR}:channel_layouts=stereo,apad=whole_dur={duration_s:.3f},'
                  f'atrim=0:{duration_s:.3f},volume=-4dB[sfx]')
        mix_inputs.append('[sfx]')

    if m_idx is not None:
        if v_idx is not None:
            # Music sits comfortably under voice and ducks smoothly during speech (~12-15 dB).
            # Base bed at -6 dB plus sidechain compression (~8 dB additional dip during speech).
            base_bed = -max(3.0, min(10.0, duck_db * 0.45))
            ratio = max(4.0, min(12.0, duck_db * 0.6))
            fc.append(f'[{m_idx}:a]aformat=sample_rates={SR}:channel_layouts=stereo,apad=whole_dur={duration_s:.3f},'
                      f'atrim=0:{duration_s:.3f},volume={base_bed:.1f}dB[mprep]')
            fc.append(f'[mprep][vsc]sidechaincompress=threshold=0.02:ratio={ratio:.1f}:attack=80:release=450:makeup=1[mduck]')
            mix_inputs.append('[mduck]')
        else:
            fc.append(f'[{m_idx}:a]aformat=sample_rates={SR}:channel_layouts=stereo,apad=whole_dur={duration_s:.3f},'
                      f'atrim=0:{duration_s:.3f}[mduck]')
            mix_inputs.append('[mduck]')

    fc.append(f'{"".join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0:duration=first,atrim=0:{duration_s:.3f}[out]')
    r = _run(['ffmpeg', '-v', 'error', '-y', *inputs, '-filter_complex', ';'.join(fc),
              '-map', '[out]', '-ac', '2', '-ar', str(SR), '-c:a', 'pcm_s16le', str(out_wav)])
    if r.returncode:
        raise StudioError(f'audio mix failed: {r.stderr.strip()[:300]}')
    return stems


def _guide_info_from_manifest(mres, asm):
    """Determine (is_guide, guide_cues) from an assembled record and music.json takes."""
    if not isinstance(asm, dict):
        return False, []
    if 'is_guide' in asm or 'guide_cues' in asm:
        gc = [str(c) for c in (asm.get('guide_cues') or [])]
        return bool(asm.get('is_guide') or gc), gc
    cues_res = mres.get('cues') if isinstance(mres, dict) and isinstance(mres.get('cues'), dict) else {}
    picks = asm.get('picks') if isinstance(asm.get('picks'), dict) else {}
    gc = []
    for cid, pick_n in picks.items():
        cm = cues_res.get(cid)
        if not isinstance(cm, dict):
            continue
        take = next((t for t in cm.get('takes') or [] if isinstance(t, dict) and int(t.get('n', -1)) == int(pick_n)), None)
        eng = str((take or {}).get('engine') or cm.get('engine') or '')
        if (take and take.get('is_guide')) or cm.get('is_guide') or eng.startswith('score'):
            gc.append(cid)
    return bool(gc), gc


def _resolve_music_track(video, film, explicit_music=None):
    """Resolve the music WAV for mix.py: (path, is_guide, guide_cues, source), source 'studio', 'outside' or None.
    Refuses to mix if Studio music takes exist without a current assembled track matching the latest round and picks,
    and refuses a music file in the Music room folder that no takes or picks explain."""
    mdir = video / '.studio' / 'results' / 'music'
    mres = music_mod.read_music_results(video)
    if explicit_music:
        p = Path(explicit_music).expanduser()
        p = p if p.is_absolute() else video / p
        if not p.is_file():
            raise StudioError(f'music file not found: {p}')
        asm = mres.get('assembled') if isinstance(mres, dict) else None
        same_as_assembled = False
        if isinstance(asm, dict) and asm.get('file'):
            asm_p = Path(asm['file']) if os.path.isabs(str(asm['file'])) else (mdir / str(asm['file']))
            same_as_assembled = asm_p.resolve() == p.resolve()
        if not same_as_assembled:
            # A music file from outside the Music room: no picks to check, so it is labelled as outside music.
            return p, False, [], 'outside'
        # The Music room's own assembled track, passed by hand: it gets the same pick checks as without --music.

    res_cues = mres.get('cues') if isinstance(mres, dict) and isinstance(mres.get('cues'), dict) else {}
    if res_cues:
        asm = mres.get('assembled') if isinstance(mres.get('assembled'), dict) else None
        if not asm or not asm.get('file'):
            raise StudioError(
                'no current assembled music track: audition takes exist (or a new round ran). '
                'Listen, pick one take per cue, and run `studio/music.py assemble` before mixing.'
            )
        asm_file = str(asm['file'])
        asm_path = Path(asm_file) if os.path.isabs(asm_file) else (mdir / asm_file)
        if not asm_path.is_file():
            raise StudioError(
                f'assembled music file not found at {asm_path}: run `studio/music.py assemble` before mixing.'
            )
        cues = music_mod.cues_for_film(film)
        asm_picks = asm.get('picks') if isinstance(asm.get('picks'), dict) else {}
        asm_rounds = asm.get('rounds') if isinstance(asm.get('rounds'), dict) else {}
        for cue in cues:
            cid = cue['id']
            cm = res_cues.get(cid)
            if not isinstance(cm, dict) or not cm.get('takes'):
                raise StudioError(
                    f'cue "{cid}" has no audition takes yet: audition, pick a take, and re-run `studio/music.py assemble` before mixing.'
                )
            cur_round = int(cm.get('round') or 1)
            pick = cue.get('pick')
            pick_round = cue.get('pick_round')
            if pick is None or pick_round is None or int(pick_round) != cur_round:
                raise StudioError(
                    f'cue "{cid}" has no pick for round {cur_round}: listen, pick a take, and run `studio/music.py assemble` before mixing.'
                )
            if asm_picks.get(cid) != int(pick) or asm_rounds.get(cid) != cur_round:
                raise StudioError(
                    f'assembled music track is out of date for cue "{cid}": run `studio/music.py assemble` before mixing.'
                )
        is_guide, guide_cues = _guide_info_from_manifest(mres, asm)
        return asm_path, is_guide, guide_cues, 'studio'

    if (mdir / 'score-full.wav').is_file():
        raise StudioError(
            'a music file is in the Music room folder, but the Music room has no takes or picks for it. '
            'Make takes and pick them (`studio/music.py audition`, then `assemble`), '
            'or pass the file with --music to use it as outside music.'
        )
    return None, False, [], None


def _require_music_yes(video, film):
    """The final film is built only after the person's ✋ Music yes is recorded and still covers the music."""
    row = approvals.status(video, film).get('music') or {}
    state = row.get('state')
    if state == 'approved':
        return
    if state == 'clicked':
        raise StudioError('your ✋ Music yes in the Studio is not recorded yet: run '
                          '`studio/studio.py approvals <video-folder> --record`, then mix again.')
    if state == 'reopened':
        raise StudioError('the ✋ Music yes no longer counts: ' + ', '.join(row.get('changed') or ['the music'])
                          + ' changed after it. Ask for the Music yes again before building the final film.')
    if state == 'outdated':
        raise StudioError('the ✋ Music question is out of date: new takes were made after it was asked. '
                          'Ask for the Music yes again on the current picks before building the final film.')
    raise StudioError('the final film waits for the ✋ Music yes: play the picked music in the Music room, '
                      'then record the yes (a click in the Studio or `studio/studio.py yes`) before mixing.')


def finish_film(video, film_name='film.json', picture=None, voice=None, sfx=None, music=None,
                captions=None, lufs=None, duck_db=DEFAULT_DUCK_DB):
    """Mix stems, master to -14 LUFS, build captions and assemble .studio/results/finish/final.mp4."""
    video = Path(video).resolve()
    film = json.loads((video / film_name).read_text(encoding='utf-8')) if (video / film_name).is_file() else {}
    fcfg = film.get('finish') if isinstance(film.get('finish'), dict) else {}
    cap_mode = captions or fcfg.get('captions') or 'burned'
    if cap_mode not in ('burned', 'srt', 'off'):
        raise StudioError(f'captions must be burned, srt or off (got "{cap_mode}")')
    target_lufs = float(lufs if lufs is not None else fcfg.get('lufs') or DEFAULT_LUFS)

    # Locate picture.
    if picture:
        pic = Path(picture).expanduser()
        pic = pic if pic.is_absolute() else video / pic
    else:
        pic = video / '.studio' / 'results' / 'render' / 'picture.mp4'
    if not pic.is_file():
        raise StudioError(f'no rendered picture found at {pic}: run studio/render.py first (or pass --picture)')
    pic_info = probe(pic)
    dur = pic_info['duration']
    w, h = int(pic_info['width'] or 1280), int(pic_info['height'] or 720)

    # Locate optional SFX and validated assembled music stems.
    sfx_p = None
    if sfx:
        p = Path(sfx).expanduser()
        sfx_p = p if p.is_absolute() else video / p
        if not sfx_p.is_file():
            raise StudioError(f'sfx file not found: {sfx_p}')
    elif (video / '.studio' / 'results' / 'render' / 'sfx.wav').is_file():
        sfx_p = video / '.studio' / 'results' / 'render' / 'sfx.wav'

    music_p, music_is_guide, music_guide_cues, music_source = _resolve_music_track(video, film, explicit_music=music)
    if music_p is not None:
        _require_music_yes(video, film)

    out = finish_dir(video)
    out.mkdir(parents=True, exist_ok=True)
    final_mp4 = out / 'final.mp4'
    mix_m4a = out / 'mix.m4a'
    srt_path = out / 'captions.srt'

    with tempfile.TemporaryDirectory(prefix='k2c-mix-') as tmp:
        work = Path(tmp)
        voice_p, cues, cap_source = collect_voice_and_words(video, film, work, explicit_voice=voice)
        pre_wav = work / 'pre-master.wav'
        stems = mix_stems(pre_wav, dur, voice_wav=voice_p, sfx_wav=sfx_p, music_wav=music_p, duck_db=duck_db)

        loud = None
        has_audio = bool(stems)
        if has_audio:
            try:
                loud = finish_mod.master_audio(pre_wav, mix_m4a, target_lufs, DEFAULT_PEAK)
            except RuntimeError:
                # Quiet/near-silent mix: encode as-is without failing.
                r = _run(['ffmpeg', '-v', 'error', '-y', '-i', str(pre_wav), '-c:a', finish_mod.AAC, '-b:a', '256k', str(mix_m4a)])
                if r.returncode:
                    raise StudioError(f'could not encode audio: {r.stderr.strip()[:300]}')
                loud = {'after_lufs': None, 'after_tp': None, 'after_lra': None, 'warnings': ['audio is silent or very quiet']}

        srt_written = False
        ass_path = None
        if cap_mode != 'off' and cues:
            write_srt(cues, srt_path)
            srt_written = True
            if cap_mode == 'burned':
                ass_path = work / 'captions.ass'
                write_ass(cues, ass_path, width=w, height=h)
        elif srt_path.exists():
            srt_path.unlink()

        # Assemble final.mp4 (burn captions when requested, else stream-copy video).
        cmd = ['ffmpeg', '-v', 'error', '-y', '-i', str(pic)]
        if has_audio:
            cmd.extend(['-i', str(mix_m4a), '-map', '0:v:0', '-map', '1:a:0'])
        else:
            cmd.extend(['-map', '0:v:0'])
        if ass_path is not None:
            # Escape special characters for ffmpeg filter path.
            esc = str(ass_path).replace('\\', '\\\\').replace(':', r'\:').replace("'", r"\'")
            cmd.extend(['-vf', f"ass='{esc}'", '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p'])
        else:
            cmd.extend(['-c:v', 'copy'])
        if has_audio:
            cmd.extend(['-c:a', 'copy', '-shortest'])
        cmd.extend(['-movflags', '+faststart', str(final_mp4)])
        r = _run(cmd)
        if r.returncode:
            raise StudioError(f'final assembly failed: {r.stderr.strip()[:350]}')

    out_info = probe(final_mp4)
    old = read_finish(video) or {'version': 0}
    formats = fcfg.get('formats') if isinstance(fcfg.get('formats'), dict) else {'wide': True, 'tall': False, 'square': False}
    warnings = list((loud or {}).get('warnings') or [])
    if music_is_guide:
        warnings.append('Temporary guide music: this film uses a temporary synth guide track, not final music. '
                        'Make real music takes before approving the final film.')
    if music_source == 'outside':
        warnings.append('Outside music: this film uses a music file passed by hand, not takes picked in the Music room.')
    if formats.get('tall'):
        warnings.append('9:16 selected: re-lay out scenes for vertical rather than cropping or stretching 16:9')
    if formats.get('square'):
        warnings.append('1:1 selected: check layout per scene rather than cropping 16:9')
    doc = {
        'version': int(old.get('version') or 0) + 1,
        'made': now_iso(),
        'film': film_name,
        'video': final_mp4.name,
        'audio': mix_m4a.name if has_audio else None,
        'stems': stems,
        'music_source': music_source,
        'music_is_guide': music_is_guide,
        'music_guide_cues': music_guide_cues,
        'ducked': bool(voice_p and music_p),
        'duck_setting_db': duck_db if (voice_p and music_p) else None,
        'loudness': loud,
        'target_lufs': target_lufs,
        'captions_mode': cap_mode,
        'captions_srt': srt_path.name if srt_written else None,
        'captions_count': len(cues) if srt_written else 0,
        'captions_source': cap_source if srt_written else 'none',
        'formats': formats,
        'width': out_info['width'],
        'height': out_info['height'],
        'duration': round(out_info['duration'], 3),
        'bytes': out_info['bytes'],
        'unheard': True,
        'warnings': warnings,
        'basis': {'captions': cap_mode, 'formats': formats, 'lufs': target_lufs},
    }
    write_atomic(out / 'finish.json', json.dumps(doc, indent=2, ensure_ascii=False) + '\n')
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description='Mix voice, SFX and music (-14 LUFS), build captions and assemble final.mp4.')
    ap.add_argument('video')
    ap.add_argument('--film', default='film.json')
    ap.add_argument('--picture', help='rendered silent picture mp4')
    ap.add_argument('--voice', help='voice WAV override')
    ap.add_argument('--sfx', help='SFX WAV override')
    ap.add_argument('--music', help='assembled music WAV override')
    ap.add_argument('--captions', choices=('burned', 'srt', 'off'), help='caption mode (default from film.json or burned)')
    ap.add_argument('--lufs', type=float, help='target loudness in LUFS (default from film.json or -14)')
    ap.add_argument('--duck-db', type=float, default=DEFAULT_DUCK_DB, help='music ducking depth under voice (default 13.5 dB)')
    a = ap.parse_args(argv)
    try:
        doc = finish_film(a.video, a.film, a.picture, a.voice, a.sfx, a.music, a.captions, a.lufs, a.duck_db)
    except StudioError as e:
        print(f'❌ {e}', file=sys.stderr)
        return 1
    print(json.dumps(doc, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
