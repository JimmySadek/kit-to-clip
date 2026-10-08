#!/usr/bin/env python3
"""Cut out the main subject of a picture (products, logos, objects, pets): transparent PNG. Runs with the rembg power's
Python (toolbox.py path rembg python); the model downloads once into that power's own folder.

  <rembg python> rembg_cutout.py <in.png|jpg|webp> <out.png> [--model isnet-general-use] [--alpha-matting]
"""
import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--model", default="isnet-general-use", help="isnet-general-use (objects), u2net (general), u2net_human_seg (people)")
    ap.add_argument("--alpha-matting", action="store_true", help="softer, more exact edges (hair, fur); slower")
    a = ap.parse_args()
    # sys.prefix is the power's own venv (<engine>/tools/rembg/venv); never resolve() the interpreter, which is a
    # symlink to the engine's Python and would put the model in the engine instead.
    os.environ.setdefault("U2NET_HOME", str(Path(sys.prefix).parent / "models"))
    from PIL import Image
    from rembg import new_session, remove
    image = Image.open(a.src)
    result = remove(image, session=new_session(a.model), alpha_matting=a.alpha_matting)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    result.save(a.out)
    alpha = result.getchannel("A")
    kept = sum(1 for v in alpha.getdata() if v > 128) / (alpha.width * alpha.height)
    print(f"cut out {a.src} -> {a.out} with {a.model}: {kept:.0%} of the picture kept")
    return 0 if 0.005 < kept < 0.995 else 3


if __name__ == "__main__":
    sys.exit(main())
