#!/usr/bin/env bash
# Kit to Clip engine setup. Claude runs this for you (the kit-to-clip skill); you can also run it yourself:
#   bash <kit-to-clip skill>/setup/install.sh [<engine folder>]   the engine for every repo: $REEL_STUDIO_HOME, else ~/.kit-to-clip
#   bash setup/install.sh                                          inside a studio folder (a copy of this setup/ folder): that folder
# It detects the machine and installs everything the videos need INSIDE the engine folder:
#   micromamba -> Node 22, ffmpeg, Python 3.12 + numpy/scipy/opencv/fonttools   (.reel-kit/env)
#   HyperFrames 0.8.77 + GSAP 3.15.0                                             (node_modules)
#   headless Chrome for rendering                                                 (HyperFrames' own download)
#   HyperFrames + GSAP agent skills, pinned                                       (.claude/skills)
# No admin password, no Homebrew, nothing outside that folder except Chrome's download cache.
# Safe to run again: finished steps are skipped. Deleting the folder removes everything else.
# A studio can list skills that must be present after setup in setup/studio-skills.txt (one name per line).
set -euo pipefail

SETUP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"      # the pinned files next to this script
if [ -n "${1:-}" ]; then STUDIO="$1"
elif [ -f "$SETUP/../SKILL.md" ]; then STUDIO="${REEL_STUDIO_HOME:-$HOME/.kit-to-clip}"   # run from the skill itself
else STUDIO="$(dirname "$SETUP")"; fi                                                   # <studio>/setup/install.sh
mkdir -p "$STUDIO"
STUDIO="$(cd "$STUDIO" && pwd)"
KIT="$STUDIO/.reel-kit"
ENV_DIR="$KIT/env"
MAMBA="$KIT/bin/micromamba"
mkdir -p "$KIT/bin"
LOG="$KIT/install.log"
: > "$LOG"

step() { printf '\n▶ %s\n' "$*"; }
ok()   { printf '  ✅ %s\n' "$*"; }
fail() { printf '  ❌ %s\n     Details: %s\n' "$1" "$LOG"; exit 1; }
quiet() { "$@" >>"$LOG" 2>&1; }
# A step re-runs when its input file changed since the last successful run (after an update).
fresh() { [ -f "$KIT/stamp-$1" ] && [ "$(cat "$KIT/stamp-$1")" = "$(shasum -a 256 "$2" | cut -d' ' -f1)" ]; }
stamp() { shasum -a 256 "$2" | cut -d' ' -f1 > "$KIT/stamp-$1"; }

export DO_NOT_TRACK=1 HYPERFRAMES_NO_TELEMETRY=1 DISABLE_TELEMETRY=1 HYPERFRAMES_SKIP_SKILLS=1
export MAMBA_ROOT_PREFIX="$KIT/mamba" MAMBA_NO_BANNER=1 CONDA_PKGS_DIRS="$KIT/mamba/pkgs"

# 1. Machine ----------------------------------------------------------------------------------
step "Checking this computer"
OS="$(uname -s)"; ARCH="$(uname -m)"
case "$OS/$ARCH" in
  Darwin/arm64)  PLAT=osx-arm64;   NAME="Mac with Apple silicon, macOS $(sw_vers -productVersion)" ;;
  Darwin/x86_64) PLAT=osx-64;      NAME="Mac with Intel chip, macOS $(sw_vers -productVersion)" ;;
  Linux/x86_64)  PLAT=linux-64;    NAME="Linux x86_64 (untested)" ;;
  Linux/aarch64) PLAT=linux-aarch64; NAME="Linux ARM (untested)" ;;
  *) fail "This computer ($OS $ARCH) is not supported. Use a Mac, or Linux/WSL on Windows." "uname: $OS $ARCH" ;;
esac
ok "$NAME"
case "$STUDIO" in *" "*) fail "The folder path has a space in it: $STUDIO. Move the folder somewhere without spaces (for example your home folder) and run setup again." "-" ;; esac
FREE_GB=$(df -Pk "$STUDIO" | awk 'NR==2 {print int($4/1048576)}')
[ "$FREE_GB" -ge 3 ] || fail "Only ${FREE_GB} GB free disk space; setup needs about 3 GB." "df"
ok "${FREE_GB} GB free disk space"
command -v curl >/dev/null || fail "curl is missing (it ships with every Mac)." "-"
curl -fsS --max-time 15 -o /dev/null https://conda.anaconda.org || fail "No internet connection (setup downloads about 1 GB once)." "curl conda.anaconda.org"
ok "Internet connection works"
if [ "$OS" = Darwin ]; then xattr -dr com.apple.quarantine "$STUDIO" 2>/dev/null || true; fi

# 2. micromamba (single file, no admin rights) --------------------------------------------------
step "Getting the package manager (micromamba)"
if [ ! -x "$MAMBA" ]; then
  quiet curl -fsSL --retry 3 "https://micro.mamba.pm/api/micromamba/$PLAT/latest" -o "$KIT/micromamba.tar.bz2" \
    || fail "Could not download micromamba." "curl micro.mamba.pm"
  quiet tar -xjf "$KIT/micromamba.tar.bz2" -C "$KIT" bin/micromamba || fail "Could not unpack micromamba." "tar"
  rm -f "$KIT/micromamba.tar.bz2"
fi
ok "micromamba $("$MAMBA" --version)"

# 3. Node, ffmpeg, Python and Python packages ---------------------------------------------------
step "Installing Node, ffmpeg and Python into $STUDIO (a few minutes the first time)"
if ! fresh env "$SETUP/environment.yml" || [ ! -x "$ENV_DIR/bin/node" ]; then
  quiet "$MAMBA" create -y -p "$ENV_DIR" -f "$SETUP/environment.yml" \
    || fail "Installing Node, ffmpeg and Python failed." "micromamba create"
  stamp env "$SETUP/environment.yml"
fi
export PATH="$ENV_DIR/bin:$PATH"
"$ENV_DIR/bin/python3" -c "import numpy, scipy, cv2, fontTools" 2>>"$LOG" || fail "Python packages did not import." "python3 -c import"
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264 || fail "ffmpeg was installed without the H.264 encoder (libx264)." "ffmpeg -encoders"
ok "Node $(node -v), $(ffmpeg -version | head -1 | cut -d' ' -f1-3), Python $(python3 -c 'import platform;print(platform.python_version())')"

# 4. HyperFrames + GSAP -------------------------------------------------------------------------
step "Installing HyperFrames 0.8.77 and GSAP 3.15.0"
cp "$SETUP/package.json" "$SETUP/package-lock.json" "$STUDIO/"
if ! fresh npm "$SETUP/package-lock.json" || [ ! -x "$STUDIO/node_modules/.bin/hyperframes" ]; then
  (cd "$STUDIO" && quiet npm ci --no-audit --no-fund) || fail "npm could not install HyperFrames." "npm ci"
  stamp npm "$SETUP/package-lock.json"
fi
ok "HyperFrames $(cd "$STUDIO" && npx --no-install hyperframes --version 2>/dev/null | tail -1)"

# 5. Headless Chrome for rendering --------------------------------------------------------------
step "Getting the headless Chrome that renders the videos"
(cd "$STUDIO" && quiet npx --no-install hyperframes browser ensure) || fail "Chrome download failed." "hyperframes browser ensure"
# Record the Chrome that `browser ensure` just downloaded (~/.cache/hyperframes/chrome). `browser path` alone
# prefers ANY Chrome in ~/.cache/puppeteer (left by other tools), which differs from what every other user renders
# with and breaks if that other cache is deleted. The helper below reads HyperFrames' own download cache.
CHROME="$(cd "$STUDIO" && HF_CHROME_CACHE="$HOME/.cache/hyperframes/chrome" node --input-type=module -e '
const { Browser, detectBrowserPlatform, getInstalledBrowsers } = await import("@puppeteer/browsers");
const { existsSync } = await import("node:fs");
const platform = detectBrowserPlatform();
const num = (id) => id.split(".").map((n) => parseInt(n, 10) || 0);
const newer = (a, b) => { const x = num(a), y = num(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0);
  return false; };
let best;
for (const b of await getInstalledBrowsers({ cacheDir: process.env.HF_CHROME_CACHE })) {
  if (b.browser !== Browser.CHROMEHEADLESSSHELL || b.platform !== platform || !existsSync(b.executablePath)) continue;
  if (!best || newer(b.buildId, best.buildId)) best = b;
}
if (best) console.log(best.executablePath);
' 2>>"$LOG")" || CHROME=""
CHROME_SOURCE="HyperFrames download cache"
if [ -z "$CHROME" ] || [ ! -x "$CHROME" ]; then
  CHROME="$(cd "$STUDIO" && npx --no-install hyperframes browser path 2>>"$LOG" | tail -1)"
  CHROME_SOURCE="hyperframes browser path (fallback)"
fi
[ -x "$CHROME" ] || fail "Chrome was not found after download." "hyperframes browser path -> $CHROME"
CHROME_VERSION="$("$CHROME" --version 2>>"$LOG")" || fail "The downloaded Chrome does not start. Run setup again." "$CHROME --version"
echo "Chrome for rendering: $CHROME_SOURCE -> $CHROME ($CHROME_VERSION)" >>"$LOG"
printf '%s\n' "$CHROME" > "$KIT/browser-path"
ok "Chrome ready ($CHROME_VERSION)"

# 6. HyperFrames + GSAP agent skills (pinned by setup/skills-lock.json) ------------------------
step "Installing the HyperFrames and GSAP skills for Claude"
cp "$SETUP/skills-lock.json" "$STUDIO/skills-lock.json"
if ! fresh skills "$SETUP/skills-lock.json" || [ ! -f "$STUDIO/.claude/skills/hyperframes/SKILL.md" ]; then
  (cd "$STUDIO" && quiet npx -y skills@1.7.0 experimental_install) || fail "Skill install failed." "skills experimental_install"
  # The restore writes to .agents/skills (Codex and others); Claude Code reads .claude/skills, so mirror them.
  for n in $(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["skills"]))' "$SETUP/skills-lock.json"); do
    if [ -f "$STUDIO/.agents/skills/$n/SKILL.md" ]; then
      rsync -a --delete "$STUDIO/.agents/skills/$n/" "$STUDIO/.claude/skills/$n/"
    fi
  done
  stamp skills "$SETUP/skills-lock.json"
fi
MISSING=$(python3 - "$STUDIO" "$SETUP/skills-lock.json" <<'EOF'
import json, sys, pathlib
root = pathlib.Path(sys.argv[1])
names = json.loads(pathlib.Path(sys.argv[2]).read_text())["skills"]
print(" ".join(n for n in names if not (root / ".claude/skills" / n / "SKILL.md").exists()))
EOF
)
[ -z "$MISSING" ] || fail "These skills did not install: $MISSING" "skills experimental_install"
ok "$(ls -d "$STUDIO"/.claude/skills/*/ | wc -l | tr -d ' ') skills in place"

# Kit to Clip used to be four skills (reel-studio, reel-brand, reel-formats, reel-finish). A studio updated to the
# one-skill layout drops those folders, so the agent never sees two copies of the engine.
if [ -f "$STUDIO/.claude/skills/kit-to-clip/SKILL.md" ]; then
  for old in reel-studio reel-brand reel-formats reel-finish; do
    if [ -d "$STUDIO/.claude/skills/$old" ]; then rm -rf "${STUDIO:?}/.claude/skills/$old"; echo "removed old skill folder $old" >>"$LOG"; fi
  done
fi

# 7. Final check --------------------------------------------------------------------------------
step "Final check"
(cd "$STUDIO" && HYPERFRAMES_BROWSER_PATH="$CHROME" quiet npx --no-install hyperframes doctor) || fail "hyperframes doctor reported a problem." "hyperframes doctor"
if [ -f "$SETUP/studio-skills.txt" ]; then
  while IFS= read -r s; do
    case "$s" in ''|'#'*) continue ;; esac
    [ -f "$STUDIO/.claude/skills/$s/SKILL.md" ] || fail "The $s skill is missing from .claude/skills (download the studio again)." "-"
  done < "$SETUP/studio-skills.txt"
fi
date "+%Y-%m-%d %H:%M" > "$KIT/ready"
ok "Everything is installed. Setup is done."
