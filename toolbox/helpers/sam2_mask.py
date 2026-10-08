#!/usr/bin/env python3
"""Follow one object through a clip with SAM 2 and cut it out: a transparent WebM of the object, a black-and-white mask
video, and the mask frames. Any object: a ball, a racket, a product, a person. Runs with the sam2 power's Python
(toolbox.py path sam2 python) on this computer (Apple GPU through MPS when available, else CPU).

  <sam2 python> sam2_mask.py <clip> <out_dir> (--point X,Y | --box X0,Y0,X1,Y1) [--at S] [--start S] [--length S]

  --point / --box   where the object is, in the clip's own pixels, on the frame at --at seconds (default: the first frame)
  --start/--length  the part of the clip to work on (keep it to one shot; long clips are slow)
Outputs in <out_dir>: object.webm (VP9 with alpha), mask.mp4, masks/00000.png ... and report.json.
Exit 0 ok, 2 bad input, 3 the object was lost in more than a quarter of the frames (say so; try a box or another frame).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("out")
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--point")
    where.add_argument("--box")
    ap.add_argument("--at", type=float, default=0.0)
    ap.add_argument("--start", type=float)
    ap.add_argument("--length", type=float)
    ap.add_argument("--model", default="small", choices=("small",))
    a = ap.parse_args()

    import numpy as np
    import torch
    from PIL import Image
    from sam2.build_sam import build_sam2_video_predictor

    tool = Path(sys.prefix).parent                     # <engine>/tools/sam2 (sys.prefix is the power's venv)
    ckpt = tool / "checkpoints" / "sam2.1_hiera_small.pt"
    if not ckpt.is_file():
        print(f"sam2_mask: checkpoint missing at {ckpt} (reinstall the sam2 power)", file=sys.stderr)
        return 2
    out = Path(a.out)
    (out / "masks").mkdir(parents=True, exist_ok=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width,height,r_frame_rate", "-of", "json", a.clip], capture_output=True, text=True).stdout)
    st = probe["streams"][0]
    num, den = (st["r_frame_rate"].split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)

    with tempfile.TemporaryDirectory(prefix="sam2-frames-") as tmp:
        cut = (["-ss", str(a.start)] if a.start is not None else []) + (["-t", str(a.length)] if a.length is not None else [])
        subprocess.run(["ffmpeg", "-v", "error", "-y", *cut, "-i", a.clip, "-q:v", "2", "-start_number", "0", f"{tmp}/%05d.jpg"], check=True)
        frames = sorted(Path(tmp).glob("*.jpg"))
        if not frames:
            print("sam2_mask: no frames in that range", file=sys.stderr)
            return 2
        prompt_frame = min(len(frames) - 1, max(0, round((a.at - (a.start or 0.0)) * fps)))
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        predictor = build_sam2_video_predictor("configs/sam2.1/sam2.1_hiera_s.yaml", str(ckpt), device=device)
        with torch.inference_mode():
            state = predictor.init_state(video_path=tmp)
            if a.point:
                x, y = (float(v) for v in a.point.split(","))
                predictor.add_new_points_or_box(state, frame_idx=prompt_frame, obj_id=1,
                                                points=np.array([[x, y]], dtype=np.float32), labels=np.array([1], np.int32))
            else:
                box = np.array([float(v) for v in a.box.split(",")], dtype=np.float32)
                predictor.add_new_points_or_box(state, frame_idx=prompt_frame, obj_id=1, box=box)
            masks = {}
            for reverse in (False, True):
                if reverse and prompt_frame == 0:
                    continue
                for idx, _ids, logits in predictor.propagate_in_video(state, start_frame_idx=prompt_frame, reverse=reverse):
                    masks[idx] = (logits[0, 0] > 0).cpu().numpy()
        cover = []
        for i, frame in enumerate(frames):
            m = masks.get(i)
            if m is None:
                m = np.zeros(Image.open(frame).size[::-1], bool)
            Image.fromarray((m * 255).astype(np.uint8)).save(out / "masks" / f"{i:05d}.png")
            cover.append(float(m.mean()))
        rate = f"{num}/{den}"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", rate, "-i", f"{tmp}/%05d.jpg", "-framerate", rate, "-i", str(out / "masks" / "%05d.png"),
                        "-filter_complex", "[1]format=gray[m];[0][m]alphamerge,format=yuva420p", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30",
                        "-auto-alt-ref", "0", str(out / "object.webm")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", rate, "-i", str(out / "masks" / "%05d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(out / "mask.mp4")], check=True)
    lost = sum(1 for c in cover if c < 0.0005)
    report = {"clip": a.clip, "frames": len(cover), "fps": fps, "prompt_frame": prompt_frame, "device": device,
              "frames_lost": lost, "mean_cover": round(sum(cover) / len(cover), 4), "outputs": ["object.webm", "mask.mp4", "masks/"]}
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(f"sam2_mask: followed the object through {len(cover) - lost} of {len(cover)} frames on {device}; "
          f"average cover {report['mean_cover']:.1%} of the picture -> {out}/object.webm")
    return 3 if lost > len(cover) / 4 else 0


if __name__ == "__main__":
    sys.exit(main())
