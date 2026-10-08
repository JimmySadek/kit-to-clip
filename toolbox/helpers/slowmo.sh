#!/usr/bin/env bash
# Smooth slow motion with RIFE: invents the frames between frames, so a 4x slow-down plays smoothly instead of
# repeating each frame four times. Runs on this computer's GPU (Vulkan through Metal).
#   bash slowmo.sh <clip> <out.mp4> [--factor 2|4|8] [--start S] [--length S] [--model rife-v4.6]
# Source the skill's scripts/env.sh first (ffmpeg). The RIFE power must be installed (toolbox.py install rife).
set -euo pipefail
SRC="${1:?usage: slowmo.sh <clip> <out.mp4> [--factor 4] [--start S] [--length S]}"; OUT="${2:?missing out.mp4}"; shift 2
FACTOR=4; START=""; LENGTH=""; MODEL="rife-v4.6"
while [ $# -gt 0 ]; do
  case "$1" in
    --factor) FACTOR="$2"; shift 2 ;;
    --start) START="$2"; shift 2 ;;
    --length) LENGTH="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    *) echo "slowmo: unknown option $1" >&2; exit 2 ;;
  esac
done
case "$FACTOR" in 2|4|8) ;; *) echo "slowmo: --factor must be 2, 4 or 8" >&2; exit 2 ;; esac
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RIFE="$(python3 "$HERE/../../scripts/toolbox.py" path rife cli)" || { echo "slowmo: the rife power is not installed" >&2; exit 3; }
MODELS="$(dirname "$RIFE")/$MODEL"
[ -d "$MODELS" ] || { echo "slowmo: no model folder $MODELS" >&2; exit 2; }
FPS="$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$SRC")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/in" "$WORK/out"
CUT=(); [ -n "$START" ] && CUT+=(-ss "$START"); [ -n "$LENGTH" ] && CUT+=(-t "$LENGTH")
ffmpeg -v error -y ${CUT[@]+"${CUT[@]}"} -i "$SRC" -an -vsync 0 "$WORK/in/%08d.png"   # bash 3.2 (macOS): empty array is "unbound" under set -u
N_IN=$(ls "$WORK/in" | wc -l | tr -d ' ')
N_OUT=$((N_IN * FACTOR))
"$RIFE" -i "$WORK/in" -o "$WORK/out" -m "$MODELS" -n "$N_OUT" >/dev/null 2>"$WORK/rife.log" || { tail -5 "$WORK/rife.log" >&2; exit 1; }
# same frame rate as the source: FACTOR times more frames play FACTOR times slower, every frame different
ffmpeg -v error -y -framerate "$FPS" -i "$WORK/out/%08d.png" -c:v libx264 -crf 17 -pix_fmt yuv420p -movflags +faststart "$OUT"
echo "slowmo: $N_IN frames -> $N_OUT frames (${FACTOR}x slower at $FPS fps, model $MODEL) -> $OUT"
