#!/usr/bin/env bash
# Global mode: make (or repair) a reel workspace inside the repo you are working in.
#   bash <kit-to-clip>/scripts/workspace.sh [dir]        dir defaults to ./reels
# Creates clips/ work/ videos/ deliveries/, a .reel-workspace marker (env.sh exports REEL_WORKSPACE from it),
# node_modules -> the engine's node_modules (HyperFrames, GSAP, puppeteer-core), and a .gitignore that keeps
# footage, renders and machine-local files out of git. Safe to run again. Prints the workspace path.
# Engine: $REEL_STUDIO_HOME, else the studio these skills were installed from, else ~/.kit-to-clip.
set -euo pipefail

WS="${1:-reels}"
case "$WS" in /*) ;; *) WS="$PWD/$WS" ;; esac
WS="${WS%/}"

d="$PWD"
while [ "$d" != "/" ] && [ ! -d "$d/.reel-kit" ]; do d=$(dirname "$d"); done
if [ -d "$d/.reel-kit" ]; then
  echo "workspace: $d is a studio folder; use its own clips/, work/, videos/ and deliveries/ instead." >&2
  exit 2
fi
own=$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd "$(pwd -P)/../../../.." && pwd -P)   # <studio>/.claude/skills/kit-to-clip/scripts
if [ -n "${REEL_STUDIO_HOME:-}" ]; then engine="$REEL_STUDIO_HOME"
elif [ -d "$own/.reel-kit" ]; then engine="$own"
else engine="${HOME:-}/.kit-to-clip"; fi
engine="${engine%/}"
case "$engine" in /*) ;; *) engine="$PWD/$engine" ;; esac
if [ ! -d "$engine/.reel-kit" ]; then
  echo "workspace: no video engine at $engine (no .reel-kit/ there)." >&2
  echo "  Install the engine there first (setup/install.sh), or set REEL_STUDIO_HOME to your engine folder." >&2
  exit 3
fi
if [ ! -x "$engine/node_modules/.bin/hyperframes" ]; then
  echo "workspace: the engine at $engine is not set up yet (no node_modules/.bin/hyperframes)." >&2
  echo "  Run: bash \"$engine/setup/install.sh\"" >&2
  exit 3
fi

mkdir -p "$WS/clips" "$WS/work" "$WS/videos" "$WS/deliveries"
[ -f "$WS/.reel-workspace" ] || printf 'Kit to Clip workspace (kit-to-clip/scripts/workspace.sh). Videos for this repo; the engine is found by env.sh.\n' > "$WS/.reel-workspace"

if [ -e "$WS/node_modules" ] && [ ! -L "$WS/node_modules" ]; then
  echo "workspace: $WS/node_modules is a real folder, not a link; move it away and run this again." >&2
  exit 4
fi
ln -sfn "$engine/node_modules" "$WS/node_modules"

GI="$WS/.gitignore"
[ -f "$GI" ] || printf '# Kit to Clip reel workspace: footage, renders and machine-local files stay out of git.\n' > "$GI"
for line in node_modules clips/ work/ deliveries/ 'videos/*/assets/' 'videos/*/vendor/' 'videos/*/snapshots/' \
  renders/ '*.mp4' '*.mov' '*.webm' '*.wav'; do
  grep -qxF -- "$line" "$GI" || printf '%s\n' "$line" >> "$GI"
done

echo "$WS"
