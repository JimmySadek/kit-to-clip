# The video engine (HyperFrames): which part does what

The engine is already installed by setup. This recipe maps each capability to the engine command or skill that
serves it, so nothing it can do is left unused. Read the named skill from `$REEL_STUDIO/.claude/skills/<name>/` (after
env.sh) at use time; it is the source of truth for how, and this page only says where and what we learned.

| Capability | Use | Read before use |
|---|---|---|
| `video-render` | `npx hyperframes render -o <file>.mp4` inside the project | `hyperframes-core`, `hyperframes-cli` |
| `timeline-motion` | GSAP timelines registered on `window.__timelines` | `hyperframes-animation` (its adapter table), `gsap-core`, `gsap-timeline` |
| `text-effects` | GSAP SplitText (free since GSAP 3.13): split into chars, words or lines and stagger them; typewriter with `steps()` eases | `gsap-plugins`, `gsap-core` (eases) |
| `lottie-play` | `adapters/lottie.md`: lottie-web or dotLottie, `autoplay: false`, register on `window.__hfLottie` | `hyperframes-animation/adapters/lottie.md` |
| `3d` | Three.js through `adapters/three.md` (seek with the engine's clock) | `hyperframes-animation/adapters/three.md` |
| `footage-edit` | cut, trim, splice: `general-video`; zoom and Ken Burns: `hyperframes-keyframes`; constant speed: `data-playback-rate` (0.1 to 10); speed ramps: a `rate` lane in `data-automation` | `hyperframes-core/references/creator-editing-recipes.md` (freeze/hold and speed sections) |
| `beat-sync` | `npx hyperframes beats <project>` writes `beats/<audio>.json` | `sound/README.md` (our sound-first rule) |
| `brand-from-website` | `npx hyperframes capture <url>` then our brand sheet | `brand/README.md`, "Brand sheet from a website" |

Also useful, no card needed:
- `npx hyperframes media-treatment --capabilities`: deterministic colour grading of one `<img>` or `<video>`. Use `--analyze` for a suggested correction.
- `npx hyperframes grade-compare`: several grades side by side on one frame, for a ✋ choice.
- `npx hyperframes normalize-audio`: match one clip's loudness to another.
- `npx hyperframes keyframes` and `inspect`: onion-skin and layout diagnostics when motion looks wrong.

## Not used by Kit to Clip

These upload or need an account. Kit to Clip is free and local and never uploads, so leave them out even when a HyperFrames skill suggests them:
- `publish` (hosted link)
- `cloud` (HeyGen cloud render)
- `lambda` and `cloudrun` (paid cloud renders)
- `auth` (HeyGen sign-in)
- the HeyGen media library in `media-use`

The local alternatives are the music maker, sound effects, the voice power and local renders.

## Lessons
- **Pixel Point's `animate-text` skill (24 named text effects) is not offered** (checked 2026-10-08): its repo declares
  no licence, so all rights are reserved. HyperFrames' own adapter note says the same. Build text effects with GSAP
  SplitText instead. The licence watch will offer it once the repo publishes an open licence.
- **Footage edit, mid-clip freeze:** "an arbitrary mid-source freeze needs preprocessing". Extract the frame with
  `ffmpeg -ss <t> -i <clip> -frames:v 1 still.png` and place it as an `<img>` for the hold. For holds and ramps
  measured to the frame, the `frame-exact-edit` capability (FilmCraft) is another route.
- **`hyperframes skills update`:** never run from a workflow (`SKILL.md`, "Setup for every shell").
