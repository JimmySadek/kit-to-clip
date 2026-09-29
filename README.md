# Kit to Clip

Brand kit in, finished clip out. Kit to Clip is an agent skill for Claude Code (and other agents that read
Agent Skills) that makes on-brand videos with [HyperFrames](https://github.com/heygen-com/hyperframes). It reads
your brand's **video pack**, build from a **formats library**, and finish every cut for where it will be posted:
safe zones, loudness, share-size copies, a cover and a contact sheet.

```bash
npx skills add JimmySadek/kit-to-clip
```

Then open any repo in Claude Code and say **"make a video"**. The first time, the front door sets up the video engine
(about 1.6 GB of disk space, 5 to 10 minutes) in one hidden folder, `~/.kit-to-clip`. No API keys, no accounts, telemetry off.

> Status: early. Tested on macOS (Apple silicon). The neutral brand reel format is a draft, Lottie export is not
> supported, and the quick brand builder (a small provisional brand for repos that have none) is not built yet.

## What's inside

One skill, `kit-to-clip`, with modules it reads only when a step needs them:

| Part | What it does |
|---|---|
| `SKILL.md` (front door) | Sets up the engine, finds the repo's brand, asks what you are making, routes to a module |
| `brand/` | Puts a brand's video pack on a HyperFrames project (fonts with licences, logos, `frame.md`, brand tokens); finds the brand's own pictures, even inside slide templates; turns a website into a brand sheet |
| `formats/` | The formats library: neutral formats for any brand (brand reel, teaser loop), formats a brand's pack brings, and cards (headline, stat, list, quote, lower third, lockup) placed on beats or words |
| `finish/` | Platform profiles and checks: safe zones, script errors lint misses, the first three seconds, a motion gate, a sync check for sound, -14 LUFS mastering that lands on target, delivery |
| `loops/` | Seamless loops and loaders: the loop method, loop formats, and exports (GIF, transparent WebM and MOV, APNG, animated WebP, an HTML snippet) |
| `sound/` | Videos with music and effects, sound first: tempo and beats, picture on the beats, effects made from the motion, a sync check on the finished file, a listening checkpoint, and an optional built-in music maker (four styles, any key) |
| `references/` | Brand onboarding and the style workshop |

## How it works

```
"make a video"
   └─ kit-to-clip ─▶ engine ready? (~/.kit-to-clip)
                  ─▶ which brand? (the repo's video pack, a pointer, a kit to onboard, or a neutral look)
                  ─▶ what are we making? (formats for that brand · a loop or loader · saved styles · a new style)
                        └─ build with the brand's pack ─▶ checks ─▶ ✋ stills ─▶ ✋ render ─▶ delivery per platform
```

Nothing renders without a yes: stills and plans come first, because renders take minutes. Videos go into a `reels/`
folder in the repo you are working in (`clips/`, `videos/`, `deliveries/`), kept out of git.

## Your brand

Kit to Clip holds no brand. Each brand keeps a **video pack**, a `kit-to-clip/` folder inside its brand kit skill,
in the brand's own repository, so improving the engine never touches a brand and adding a brand never touches the
engine. The front door looks for a brand in this order:

1. a video pack in the repo (`.agents/skills/*/kit-to-clip/` or `.claude/skills/*/kit-to-clip/`),
2. a pointer, `reels/brand.json`, naming a brand kit installed elsewhere,
3. a brand kit without a pack: **brand onboarding** reads it, proposes motion directions, shows stills and saves a pack,
4. installed brands, brand work with no chosen identity, or no brand at all: it asks, or offers a neutral look.

What a brand must provide, the token contract that lets neutral formats style any brand, and a complete example
pack: [`brand/brand-pack.md`](brand/brand-pack.md).

## Formats

A format is a repeatable recipe with **slots** (the content each video supplies). Neutral formats live in
`formats/neutral/` and style themselves from any pack's tokens. A brand can add its own formats (for example a
highlight edit made for its footage) in its pack's `formats/` folder; they appear only for that brand.

## Setup details

- The engine folder is `$REEL_STUDIO_HOME` if set, else `~/.kit-to-clip`. Setup installs Node 22, ffmpeg (with
  libx264), Python 3.12 with NumPy, SciPy, OpenCV and fontTools, HyperFrames, GSAP and a headless Chrome into it,
  without admin rights. Run it yourself with `bash setup/install.sh` from a clone.
- Every script expects `source scripts/env.sh` first: telemetry off, no global skill installs, the engine's own
  tools on the PATH.
- Updating: run the `npx skills add` command again (or `git pull` in a clone), then re-run setup; it only redoes
  what changed.

## Tests

Negative-control tests: every check must fail on a fixture built to break it and pass on its control.

```bash
source scripts/env.sh && python3 tests/run.py
```

## License

Apache License 2.0, see [LICENSE](LICENSE). HyperFrames, GSAP and the other tools the setup downloads keep their own
licences; see [NOTICE](NOTICE).
