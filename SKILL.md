---
name: kit-to-clip
description: Kit to Clip turns a brand kit into finished, on-brand videos with HyperFrames. Use it for any video request in any repo or studio folder, including a plain "hi" in a studio, "make a video", a reel, TikTok, Instagram or LinkedIn post, highlight edit, announcement, teaser, title card, animated GIF, website loop or loader, a video with music or sound effects, and for "make it on-brand", "make it ready for Instagram", "set me up", "check for updates" or "I want a new style". It sets up the video engine on first use, finds the repo's brand (or onboards its brand kit), guides the person with questions to a format, a saved style, a loop or a new style, then builds, checks and delivers each cut for its platform. Written for non-technical people.
---

# Kit to Clip

The person may never have used a terminal. You do all the technical work. They make the creative calls.

This is one skill with modules inside. `<kit-to-clip>` below means this skill's folder. Read a module's guide only
when the step you are on needs it.

| Module | Read | What it does |
|---|---|---|
| Front door | this file | setup, the brand, "what are we making?", saved styles |
| Brand | `brand/README.md`, `brand/brand-pack.md` | puts a brand's video pack on a project; what a pack must provide |
| Formats | `formats/README.md` | the recipes: neutral formats, a brand's own formats, cards; delivery per platform |
| Finish | `finish/README.md` | platform profiles, checks before and after the render, mastering, delivery files |
| Loops | `loops/README.md` | seamless loops and loaders: method, loop formats, exports (GIF, WebM, APNG, WebP, snippet) |
| Sound | `sound/README.md` | videos with music and sound effects: sound first, effects from the motion, sync check, listening checkpoint |
| Guides | `references/brand-onboarding.md`, `references/style-workshop.md` | a new brand's first setup; designing a new style |

Brands are not in here. Each brand kit is its own skill (e.g. `acme-brand`) and connects through its video pack, a
`kit-to-clip/` folder inside the kit.

```
brand kit skill ── kit-to-clip/ pack ──▶ brand module ─┐
                                                        ├─▶ a HyperFrames project ─▶ finish module ─▶ deliveries
formats module (recipe + content) ─────────────────────┘      (loops module for loops and loaders)
```

## How to talk here

- Plain, short sentences. No jargon: say "the video engine", not "HyperFrames CLI"; say "the stills", not "snapshots".
- Every decision goes through the AskUserQuestion tool: one decision per question, 2-4 options named for this
  video, a one-line consequence each, and a recommended option first when you have a reason.
- **Show before you spend, cheapest first: an ASCII layout, then stills, then the render.** Before you build, and before
  any change that moves, adds or removes something on screen, draw the layout in ASCII and ask ✋ for a yes. Show the
  canvas size, the destination's safe-zone lines with their pixel values (`finish.py plan --profile <p>` prints them;
  they come from `finish/profiles.json`), each element's position and size, and for a change a before and after pair.
  Flag anything that would land in an unsafe area. Keep it brief: one sketch for each state that matters (the first
  frame, the end card), real pixel numbers, one line for each open decision. Change no file and render nothing until
  they say yes. It costs a few lines instead of a render, and it settles what they expect before any work is spent.
  Never render without a ✋ yes.

  ```
  Instagram Reels 1080 x 1920, live area x 65-1015, y 269-1248.   <!> = inside the covered area
  BEFORE                                          AFTER
  ┌──────────────────────────────┐ y 0     ┌──────────────────────────────┐ y 0
  │ covered by the app           │         │ covered by the app           │
  ├──────────────────────────────┤ y 269   ├──────────────────────────────┤ y 269
  │ headline  65,300  950x180    │         │ headline  65,300  950x180    │
  │ device    240,560 600x520    │         │ device    240,480 600x520    │
  │ url       65,1240 950x60 <!> │         │ url       65,1030 950x60     │
  ├──────────────────────────────┤ y 1248  ├──────────────────────────────┤ y 1248
  │ covered by the app           │         │ covered by the app           │
  └──────────────────────────────┘ y 1920  └──────────────────────────────┘ y 1920
  ```
- Say what is happening during long steps ("Installing the video engine, about 5 minutes").
- Never post, upload or send anything anywhere. Real people need consent before anything is posted: say so.

## Our craft standard

We make art for brands people care about. Resourceful and creative beats quick and plausible, every time.

1. **Exhaust the sources before saying "we don't have it".** Search the brand kit with
   `python3 <kit-to-clip>/brand/scripts/assets.py search <kit> <words>`: every folder and original, the manifests, SVG
   and Markdown text, and the official press-kit ZIPs the kit links (their file lists). Try several words (the thing,
   its purpose, its screen: "laptop", "device", "mockup", "pipeline"). Only then say it is missing, with the tool's
   "searched" list as evidence and the likely home named (a design library, the brand team). Never swap in a
   lookalike without saying what changed and why.
2. **Match the reference when adapting existing work.** When the job starts from a live post, a deck or a still,
   capture it first, then put your stills side by side with it and list every difference (layout, type, colour,
   crop, assets) before calling it faithful.
3. **Real assets, untouched.** Product screens, photos and logos come from the brand's own files; motion may move,
   crop, reveal or mask them, never repaint what they show.
4. **Look before you show, prove before you claim.** Check every still and the finished contact sheet yourself; every
   "done" names its evidence (check output, file sizes, frame counts, the comparison).
5. **Offer the better idea.** When the brief can be served better (a stronger loop, a cleaner crop, an asset the
   brand already owns), say so in one line with a still, then do what was asked unless they choose it.

## Setup for every shell

- Source `<kit-to-clip>/scripts/env.sh` before any script or video engine command. It finds the engine by itself,
  puts its Node, ffmpeg, Python and Chrome on the PATH, sets `REEL_STUDIO` to it and, inside a workspace,
  `REEL_WORKSPACE`. It also turns telemetry off and stops `hyperframes init` from installing skills globally.
- Load `hyperframes` (router) and the workflow it picks before building. If it is not available as a skill, read
  `$REEL_STUDIO/.claude/skills/hyperframes/SKILL.md` after env.sh, and the workflow skill it names from there.
- Never run `npx hyperframes skills update` or `npx skills add -g` from a workflow. If a HyperFrames workflow says
  to, skip that step when the skill is already present, and tell the user.

## Where things are

| Mode | When | Engine | Videos go to |
|---|---|---|---|
| **Studio folder** | a folder at or above the current one holds `.reel-kit/` (a packaged studio) | that folder | its `clips/`, `work/`, `videos/`, `deliveries/`, `styles/` |
| **Any repo** | everywhere else | `$REEL_STUDIO_HOME`, else the studio this skill came from, else `~/.kit-to-clip` | the repo's `reels/` workspace |

## Step 0: setup (every session, before anything else)

1. **A packaged studio** may carry its own setup and update steps: if the studio folder has `setup/studio.md`, read
   it and follow its steps first, then continue at Step 2.
2. **The engine:** if `<engine>/.reel-kit/ready` is missing, setup has not finished. Tell them in two lines what it
   does: it installs the video engine (HyperFrames, Chrome, ffmpeg, Python), about 1.6 GB of disk, 5-10 minutes, into one
   folder (`~/.kit-to-clip`, or the studio folder), no password needed. Ask ✋ **Set up now** (recommended) /
   **Not now**. Then run `bash <kit-to-clip>/setup/install.sh` (inside a studio folder: `bash setup/install.sh`) in
   the background and wait for it. Relay its ✅ lines in plain words.
3. On ❌: read the named step and the end of `<engine>/.reel-kit/install.log`, find the cause, fix what is fixable
   (it is safe to run again; finished steps are skipped), and only then explain what they need to do. Common causes:
   no internet, less than 3 GB free, a space in the folder path.

**Updates** ("check for updates"): a packaged studio's `setup/studio.md` says how. Otherwise the skill updates where
it was installed from (a git checkout: `git pull`; `npx skills add`: run the same command again), and re-running
`setup/install.sh` refreshes only what changed.

## Step 1: workspace (any-repo mode only)

Outputs live in a `reels/` folder in the repo being worked in (`git rev-parse --show-toplevel`, else the current
folder). If `reels/` does not exist yet, ask once ✋ **Make a reels/ folder here** (recommended; footage and renders
stay out of git) / **Not now**. Then run `bash <kit-to-clip>/scripts/workspace.sh <repo>/reels` (safe to repeat)
and use `reels/clips`, `reels/work`, `reels/videos` and `reels/deliveries` wherever a guide says `clips/`, `work/`,
`videos/` and `deliveries/`. Run video engine commands inside the project under `reels/videos/`: `npx hyperframes`
finds the engine through `reels/node_modules`.

## Step 2: the brand

Run `python3 <kit-to-clip>/scripts/brand.py detect` (add `--json` to read it as data). It reports one state:

| State | What it means | Do this |
|---|---|---|
| `pack` | the repo has a brand video pack | Say which brand you will use ("Using the Acme video pack"). Two or more: ask ✋ which. A `provisional` pack: say "provisional brand" in every handoff |
| `pointer` | `reels/brand.json` names a kit installed elsewhere, and it has a pack | Use it and say where it comes from |
| `kit` | a brand kit with no video pack yet | Offer ✋ **Set up this brand for video** (brand onboarding, `references/brand-onboarding.md`; about 20 minutes, saved into the kit) / **Neutral look for now** |
| `unchosen` | brand work in the repo, no chosen identity | Say "identity not chosen", then ask ✋ a brand from one of the repo's directions (onboarding from that source) / a neutral look |
| `none` | no brand in the repo | Say "no brand here", then ask ✋ which brand this repo is for: one per installed pack and installed kit the report lists (a kit still needs onboarding: say so), or a neutral look. After they pick an installed one, run `brand.py use --kit <name>` so the repo remembers it, and detect again |

Never guess colours, fonts or logos. A brand known only from its website: onboarding starts from a brand sheet
(`brand/README.md`, "Brand sheet from a website"). A quick provisional brand for a repo with none is not built yet:
say so, and offer the neutral look.

## Step 3: what are we making?

List what this brand can use, after env.sh:

```bash
python3 <kit-to-clip>/formats/scripts/formats.py list --brand <id> --project .   # approved formats: neutral + this brand's own
python3 <kit-to-clip>/scripts/styles.py list                                      # saved styles for this brand
```

Ask ✋ **What are we making?** with one option per approved format that fits (name it, and say what it needs, e.g.
"a clip" for `made_for: clip`), one per approved saved style, plus:

| They want | Goes to |
|---|---|
| A format from the list | its `journey` file (the path `formats.py` prints): read it and follow it step by step |
| A loop, a loader, an animated GIF or a moving version of a still (e.g. a LinkedIn teaser) | `loops/README.md` |
| A video with sound: music, sound effects, a soundtrack, effects on the moves | `sound/README.md`: sound first, with a hard gate. Steps 0 to 2 (setup, workspace, brand) run as usual; then the music source is the first creative question, before any picture, and the tempo is chosen so the length is whole bars, put the picture on the beats, make the effects from the motion, check the sync on the file, and stop for a ✋ listening checkpoint before polish. Never build the picture first. If library music needs the HeyGen login, say so at the start and ask; the built-in music maker (four styles) needs no login |
| An announcement, promo, event or launch post from words and numbers | cards: `formats/README.md`, "Cards" (a sequence of headline, stat, list, quote, lower-third, lockup) |
| A video in a saved style | "Using a saved style" below |
| ✨ A new style of video | the style workshop: `references/style-workshop.md` |
| Something else (captions on a video, a title card, a one-off) | the `hyperframes` workflows, then the brand and finish modules |

If they already said what they want ("make a Fold Cut of this clip", "make this post move"), skip the question.
Neutral formats need a pack with token contract 1 (`brand/scripts/bridge.py --list` shows it); drafts are not offered
unless they ask for them by name. If a clip was mentioned, check it is in `clips/` or ask them to drag it there.

**Direct requests** skip the front door's questions but not its rules: "make it ready for Instagram" goes straight
to the finish module; "put our brand on this project" to the brand module; env.sh and the brand check still apply.

## Using a saved style

1. Read the style's `style.md` and `style.json` (`styles.py list --json` prints its path): its slots say what
   content each video needs.
2. Ask for that content (clip, words, stats) and the platforms, one question at a time.
3. `python3 <kit-to-clip>/scripts/styles.py new --style <slug> --out <videos>/<job>` copies the approved template
   and re-applies the brand. Fill the slots, keep everything else as approved.
4. Checks, ✋ stills, ✋ render, then finish and deliver as `finish/README.md` describes
   (`<deliveries>/<job>/<style>/<platform>/`). One platform per cut; never stretch or crop a finished render.

A style marked `draft` is still being designed: offer to continue its workshop instead of using it.

## Ground rules for every video

- Brand comes from the brand's video pack only (the brand module).
- On screen, say only what the footage or the person supplied: no invented names, numbers, scores or results.
- Checks before any render offer: `npx hyperframes lint`, `npx hyperframes check`, and finish `check`, `safe` and
  `hook` (the first three seconds).
- Look at the stills and the finished contact sheet yourself before showing them.
- A video with sound is unheard by you: say "unheard by the agent" in every handoff until the person has listened, and
  never call its sound verified on the strength of the sync numbers. `finish` refuses a render with sound that has no
  passing sync check (or a `--no-sync` reason).
