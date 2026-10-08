#!/usr/bin/env python3
"""An original music track from a description with ACE-Step 1.5, on this computer. Runs with the ace-step power's Python
(toolbox.py path ace-step python). Models download once into that power's own folder (several GB).

  <ace python> ace_music.py "<description>" <out.wav> --bpm 120 --key "A minor" --bars 8 [--seed 7] [--lyrics file.txt]

Length is given in whole bars of 4/4 (Kit to Clip's sound rule), so the music can loop and cuts can land on bars.
Instrumental unless --lyrics is given. Prints the file, its real length and the seed (keep the seed: it makes the same
track again). Exit 0 ok, 1 generation failed, 2 bad input.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("description")
    ap.add_argument("out")
    ap.add_argument("--bpm", type=int, required=True)
    ap.add_argument("--key", default="", help='e.g. "A minor", "C major" (empty: the model chooses)')
    ap.add_argument("--bars", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--lyrics", help="a text file with lyrics (vocals); without it the track is instrumental")
    ap.add_argument("--with-lm", action="store_true", help="use the 0.6B planning model too (better structure, bigger download)")
    a = ap.parse_args()
    if not 30 <= a.bpm <= 300:
        print("ace_music: --bpm must be 30-300", file=sys.stderr)
        return 2
    seconds = a.bars * 4 * 60.0 / a.bpm
    if not 10 <= seconds <= 600:
        print(f"ace_music: {a.bars} bars at {a.bpm} bpm is {seconds:.1f} s; the model makes 10-600 s", file=sys.stderr)
        return 2

    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    root = Path(sys.prefix).parent                   # <engine>/tools/ace-step (sys.prefix is the power's venv)
    dit = AceStepHandler()
    status, ok = dit.initialize_service(project_root=str(root), config_path="acestep-v15-turbo", device="auto")
    if not ok:
        print(f"ace_music: the music model did not load: {status}", file=sys.stderr)
        return 1
    llm = LLMHandler()
    if a.with_lm:
        llm.initialize(checkpoint_dir=str(root / "checkpoints"), lm_model_path="acestep-5Hz-lm-0.6B", backend="pt", device="auto")
    lyrics = Path(a.lyrics).read_text(encoding="utf-8") if a.lyrics else "[Instrumental]"
    params = GenerationParams(caption=a.description, lyrics=lyrics, instrumental=not a.lyrics, bpm=a.bpm,
                              keyscale=a.key, duration=seconds, seed=a.seed, thinking=a.with_lm, use_cot_metas=a.with_lm)
    config = GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=False, seeds=[a.seed])
    work = Path(a.out).resolve().parent / f".ace-{Path(a.out).stem}"
    result = generate_music(dit, llm, params, config, save_dir=str(work))
    if not result.success or not result.audios:
        print(f"ace_music: generation failed: {result.error}", file=sys.stderr)
        return 1
    produced = Path(result.audios[0]["path"])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(produced), a.out)
    shutil.rmtree(work, ignore_errors=True)
    length = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.out],
                                  capture_output=True, text=True).stdout.strip() or 0)
    info = {"out": a.out, "seconds": round(length, 3), "target_seconds": round(seconds, 3), "bpm": a.bpm, "key": a.key,
            "bars": a.bars, "seed": a.seed, "instrumental": not a.lyrics, "model": "acestep-v15-turbo"}
    Path(a.out).with_suffix(".json").write_text(json.dumps(info, indent=2))
    print(f"ace_music: {a.out} ({length:.2f} s for {a.bars} bars at {a.bpm} bpm, key {a.key or 'auto'}, seed {a.seed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
