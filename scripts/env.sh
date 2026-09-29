# Kit to Clip: source before any HyperFrames command or reel script (works in bash and zsh).
# Telemetry off (HyperFrames PostHog + skills CLI), no global skill installs by `hyperframes init`.
# Inside a studio folder (a parent folder holds .reel-kit/), use its own Node, ffmpeg, Python and Chrome
# (installed by setup/install.sh).
# Global mode: outside a studio, use the engine studio the same way: $REEL_STUDIO_HOME, else the studio these skills
# were installed from (this file is <studio>/.claude/skills/kit-to-clip/scripts/env.sh), else ~/.kit-to-clip.
# A parent folder holding a .reel-workspace file (made by kit-to-clip/scripts/workspace.sh) is exported as
# REEL_WORKSPACE: that repo's reels/ folder for clips, work, videos and deliveries.
# Otherwise reuse a locally cached headless Chrome when one exists (avoids a Chrome download on first render).
export DO_NOT_TRACK=1 HYPERFRAMES_NO_TELEMETRY=1 DISABLE_TELEMETRY=1 HYPERFRAMES_SKIP_SKILLS=1
_reel_dir="$PWD"
while [ "$_reel_dir" != "/" ] && [ ! -d "$_reel_dir/.reel-kit" ]; do _reel_dir=$(dirname "$_reel_dir"); done
if [ ! -d "$_reel_dir/.reel-kit" ]; then
  if [ -n "${BASH_SOURCE:-}" ]; then _reel_self="${BASH_SOURCE[0]}"; elif [ -n "${ZSH_VERSION:-}" ]; then eval '_reel_self="${(%):-%x}"'; else _reel_self=""; fi
  _reel_own=""
  if [ -n "$_reel_self" ]; then _reel_own=$(cd "$(dirname "$_reel_self")" 2>/dev/null && cd "$(pwd -P)/../../../.." && pwd -P) || _reel_own=""; fi
  if [ -n "${REEL_STUDIO_HOME:-}" ]; then _reel_dir="$REEL_STUDIO_HOME"
  elif [ -n "$_reel_own" ] && [ -d "$_reel_own/.reel-kit" ]; then _reel_dir="$_reel_own"
  else _reel_dir="${HOME:-}/.kit-to-clip"; fi
  case "$_reel_dir" in /) ;; */) _reel_dir="${_reel_dir%/}" ;; esac
  case "$_reel_dir" in /*) ;; *) _reel_dir="$PWD/$_reel_dir" ;; esac
fi
if [ -d "$_reel_dir/.reel-kit" ]; then
  export REEL_STUDIO="$_reel_dir"
  if [ -x "$_reel_dir/.reel-kit/env/bin/node" ]; then
    case ":$PATH:" in *":$_reel_dir/.reel-kit/env/bin:"*) ;; *) export PATH="$_reel_dir/.reel-kit/env/bin:$PATH" ;; esac
  fi
  if [ -z "${HYPERFRAMES_BROWSER_PATH:-}" ] && [ -f "$_reel_dir/.reel-kit/browser-path" ]; then
    _reel_chrome=$(head -1 "$_reel_dir/.reel-kit/browser-path")
    if [ -n "$_reel_chrome" ] && [ -x "$_reel_chrome" ]; then export HYPERFRAMES_BROWSER_PATH="$_reel_chrome"; fi
  fi
fi
_reel_dir="$PWD"
while [ "$_reel_dir" != "/" ] && [ ! -f "$_reel_dir/.reel-workspace" ]; do _reel_dir=$(dirname "$_reel_dir"); done
if [ -f "$_reel_dir/.reel-workspace" ]; then export REEL_WORKSPACE="$_reel_dir"; else unset REEL_WORKSPACE; fi
if [ -z "${HYPERFRAMES_BROWSER_PATH:-}" ]; then
  _reel_chrome=$(find "$HOME/Library/Caches/ms-playwright" "$HOME/.cache/ms-playwright" -maxdepth 3 -type f \
    -name chrome-headless-shell -path "*chromium_headless_shell-*" 2>/dev/null | sort | tail -1)
  if [ -n "$_reel_chrome" ] && [ -x "$_reel_chrome" ]; then export HYPERFRAMES_BROWSER_PATH="$_reel_chrome"; fi
fi
unset _reel_dir _reel_chrome _reel_self _reel_own
