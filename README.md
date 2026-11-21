# Kit to Clip

<p align="center">
  <img src="assets/banner.png" alt="Kit to Clip: a brand kit turned into finished 9:16, 1:1 and 16:9 videos" width="100%">
</p>

**From an idea or existing footage to a reviewed video.** Kit to Clip is an agent skill for Claude Code (and other
agents that read Agent Skills), using [HyperFrames](https://github.com/heygen-com/hyperframes). It helps develop the
story, choose a reference, prepare voice/music/effects, build the video and finish it for its destination. Keep the
reference's original look, adapt a palette or use a full brand identity. Branding is optional.

<table>
  <tr>
    <td width="34%" align="center">
      <img src="assets/showcase.gif" alt="A 15 second Instagram Reel made by Kit to Clip: tilted paper kit pieces straighten into a framed clip, then 9:16, 1:1 and 16:9 cuts, ending on the install command" width="100%">
    </td>
    <td>
      <p><b>Made by Kit to Clip, from a short brief.</b></p>
      <p>This 15 second Reel was planned, designed, scored, checked and finished by the skill itself: no footage,
      no stock, no video model. Every frame is HTML and GSAP, rendered on the computer it was made on.</p>
      <ul>
        <li>readable with the sound off from the first frame</li>
        <li>21 sound hits, each within a frame of its picture moment (checked on the file)</li>
        <li>mastered to -14 LUFS, inside Instagram's safe zones</li>
      </ul>
    </td>
  </tr>
</table>

```bash
npx skills add JimmySadek/kit-to-clip
```

Then open any repo in Claude Code and say **"make a video"**. The first time, it sets up the video engine (about 1.6 GB,
5 to 10 minutes) in one hidden folder, `~/.kit-to-clip`. **The required rendering tools are free and local:** no
provider account or API key is required by the engine, and telemetry/online frame descriptions are off. Your host
agent has its own access requirements. Optional external voice or image generation is your choice; the skill
explains outgoing prompts/assets and any account or credit requirement before using that route.

## What you can make

| Say | You get |
|---|---|
| "Make a reel from this clip" | A 9:16 cut for Instagram Reels, TikTok and YouTube Shorts, inside each app's safe zone |
| "Make a launch film for our feature" | A designed motion film, 16:9 and 9:16, with music and effects on the beat |
| "Announce our launch" | Cards (headline, stat, list, quote, lower third, logo) timed to the music |
| "Make our logo loop" / "an animated GIF for LinkedIn" | A seamless loop or loader: GIF, transparent WebM or MOV, APNG, WebP, an HTML snippet, or Lottie for vector work |
| "A narrated explainer" | A voice-over, word-timed captions and scenes that start on their words |
| "Add music and sound effects" | Music-led edits follow approved musical cues; narrated edits follow the voice. Effects follow visual events, and the final mix needs listening |
| "Make it like this video" + a link | The reference read (speech, frames, cuts, beats), then a style of your own built on its principles |
| "Help me choose a style" | A shortlist drawn from 86 tagged Atlas references and your personal references, with reasons and original-preview links |
| "I want a new style" | Develop a new direction, with an optional reusable reference after the video is approved |

## How it works

```
"make a video"
  ├─ brief     goal, audience, destination, duration and supplied inputs
  ├─ route     a new story, an edit of existing footage, or both
  ├─ style     recommendations, My Styles, browse more, or create a new direction
  ├─ brand     keep the look, adapt palette/logo, or use a full identity
  ├─ story     exact words, sequence, imagery only where needed; ✋ script when Kit to Clip wrote it
  ├─ sound     choose the voice; choose what governs timing
  ├─ build     ✋ storyboard first, then a fresh builder + current brief; ✋ music pick on the built picture
  ├─ check     lint · runtime · safe zones · first 3 seconds · beats · sync · flash guard
  └─ deliver   ✋ final film (watched and heard), then per-platform files; optionally save the treatment
```

Four stops need your yes: the script (when Kit to Clip wrote it), the storyboard before building, the music pick
on the built picture, and the final film with its sound. Videos go into a `reels/` folder in the repo you are working
in (`clips/`, `videos/`, `deliveries/`), kept out of git.

The local gallery has **Styles**, **My Styles** and retained **Legacy recipes**. It starts with 15 cards and lets
you search, browse families or show more. Publisher previews open only on request. The bundled catalogue contains
metadata and links, **not Atlas prompts, drawing code or media**. Rebuilding a chosen reference requires your own
private source package, checked by identity and hash. Private use does not grant redistribution rights. All 86
are catalogued; that does not mean all 86 have been rendered or approved inside Kit to Clip.

One `film.json` in the video folder keeps the story, selected reference, brand choice, assets, sound versions, open
decisions and approvals. A new session can resume from it. Changed inputs reopen affected approvals rather than silently using
an old build. A short style/brand comparison has its own approvals and never approves the full film.

## Taste built in

Kit to Clip plans each video with design skills, so it designs instead of filling slides:

- **[frontend-design](https://github.com/anthropics/skills)** (Anthropic) shapes the look: type, colour, composition,
  a bold direction. Kit to Clip keeps its craft and replaces its web-motion advice with seekable GSAP timelines.
- **[impeccable](https://github.com/pbakaus/impeccable)** critiques the plan, the sketches and the stills: hierarchy,
  spacing, empty space, too timid or too loud.
- **A specialist for the video type**, recommended when the job matches: social shorts, product ads, launch films,
  SaaS demos, explainers, highlight and hype edits, beat-synced edits, kinetic type, data stories, sound design
  (from [calesthio/generative-media-skills](https://github.com/calesthio/generative-media-skills)).

The agent you talk to is the **director**: it gathers decisions, maintains the brief and checks the builder's work.
The recommended fresh builder is Claude Opus 5.5 at high effort when available. An unavailable model or session
launch is disclosed, with a complete handoff when needed. Independent preparation can run in parallel on capable
hosts; one coordinator owns shared decisions, and creative approvals still belong to you.

## Powers

When an idea needs more than HTML and GSAP, the director can reach for a free, local power. Each one is pinned, checked
against a licence policy (no non-commercial, AGPL or revenue-capped licences, ever) and installed only after a yes,
with a fallback when you say no.

| Family | Powers |
|---|---|
| Looks and texture | living shader backgrounds (paper-shaders), generative canvas and painterly brushes (p5, p5.brush), hand-drawn lines (Rough.js) |
| Physics and particles | thousands of particles and confetti (PixiJS), real 2D physics (Rapier), spring motion (Motion) |
| 3D and layers | 3D logos and products (Blender), After Effects-style layers and Lottie export (effectcraft), vector files from .ai and .eps (vectorcraft) |
| Footage | cut people or objects out of clips (HyperFrames cutout, rembg, SAM 2), smooth slow motion (RIFE), sharper frames (Real-ESRGAN), frame-exact edits (filmcraft) |
| Voice and words | a natural voice in several languages (Kokoro), word-level captions (whisper.cpp, Parakeet) |
| Sound | original music from a description (ACE-Step), recorded CC0 effects (Kenney), effects tuned to the music's key |
| References | read a video link: transcript, frames, cuts and beats |

## Sound that lands

- **Choose the timing driver.** Narration-led edits follow the approved recording and word timings. Music-led
  edits follow the approved track. Silent explainers follow readability; footage edits follow the material.
  Music can come from the reference's sound direction, generated auditions, a supplied track, a simple bed or none.
  Existing generation/beat tools remain available, but speech is never forced into whole musical bars.
- **Effects from the motion.** Whooshes follow what moves; hits sit on the frame something comes to rest, in the
  music's key. Recorded CC0 impacts, clicks and sweeps are the default; synthesised ones fill the gaps.
- **Checked on the file.** `finish.py sync` measures every hit against its picture moment on the rendered video, and
  `finish` refuses a cut that is off. Then you listen: the agent never calls a sound good it has not heard.

## Your brand

Kit to Clip holds no brand. Each brand keeps a **video pack**, a `kit-to-clip/` folder inside its brand kit skill, in
the brand's own repository, so improving the engine never touches a brand and adding a brand never touches the engine.
After choosing whether/how to brand the video, the skill can locate a kit in this order:

1. a video pack in the repo (`.agents/skills/*/kit-to-clip/` or `.claude/skills/*/kit-to-clip/`),
2. a pointer, `reels/brand.json`, naming a brand kit installed elsewhere,
3. a brand kit without a pack: **brand onboarding** reads it, proposes motion directions, shows stills and saves a pack,
4. installed brands when the chosen identity is elsewhere. No identity is invented for an unbranded video.

Palette adaptation assigns colour roles while preserving the style's textures, medium and meaningful colours.
A previous personal style's brand is context, not an automatic choice for the next video.

What a brand must provide, the token contract that lets neutral formats style any brand, and a complete example pack:
[`brand/brand-pack.md`](brand/brand-pack.md).

## What's inside

One skill, `kit-to-clip`, with modules it reads only when a step needs them:

| Part | What it does |
|---|---|
| `SKILL.md` (front door) | Understands the request, routes idea/footage work and loads only the guides needed now |
| `catalogue/`, `scripts/catalogue.py`, gallery | Metadata discovery, transparent keyword shortlists, original previews and selected-only private source loading |
| `studio/`, `film.json` | The Studio page and the film's brief: current decisions, inputs, the brand, and each stop's yes (`scripts/brief.py` stays for older briefs) |
| `references/director-and-builder.md` | How a video gets made: the plan, design skills, specialists, the power palette, sketches, helpers, checks |
| `brand/` | Puts a brand's video pack on a project (fonts with licences, logos, tokens); finds the brand's own pictures; turns a website into a brand sheet |
| `formats/` | The formats library: neutral formats for any brand (brand reel, explainer, teaser loop), a brand's own formats, and cards placed on beats or words |
| `finish/` | Platform profiles and checks: safe zones, script errors lint misses, the first three seconds, beats, sync, a flash guard, -14 LUFS mastering, delivery |
| `loops/` | Seamless loops and loaders and their exports |
| `sound/` | Voice/music choices, timing priority, generation, effects, mixing, sync checks and listening |
| `toolbox/` | The powers: what each does, how it installs (pinned, checksummed), its licence, its fallback, and the licence and update watches |
| `references/` | Brand onboarding, the style workshop, learning from a video you like, borrowing an effect from an open-source project |

## A video you like

Say **"make it like this video"** with a link (Instagram, TikTok, YouTube, X and more). Kit to Clip reads it, measures
its cuts and whether they land on the music, and turns the borrowed principles (never the footage, music or words)
into a starting point for the requested video, with optional branding.

Reading links uses a companion skill, [Video Fetcher to Markdown](https://github.com/JimmySadek/video-fetcher-to-markdown):
transcript with local Whisper, a contact sheet of frames, and the file. Kit to Clip checks for it and asks before
installing it (`npx skills add JimmySadek/video-fetcher-to-markdown`); its download and speech tools go into the engine
folder, not your system.

## Setup details

- The engine folder is `$REEL_STUDIO_HOME` if set, else `~/.kit-to-clip`. Setup installs Node 22, ffmpeg (with
  libx264), Python 3.12 with NumPy, SciPy, OpenCV and fontTools, HyperFrames, GSAP, the pinned agent skills and a
  headless Chrome into it, without admin rights. Run it yourself with `bash setup/install.sh` from a clone.
- Powers install into the same folder, each after a yes. The largest is the music generator (its models are about
  9.4 GB, downloaded on first use).
- Every script expects `source scripts/env.sh` first: telemetry off, no global skill installs, online vision keys
  removed so stills stay local, the engine's own tools on the PATH.
- Updating: run the `npx skills add` command again (or `git pull` in a clone), then re-run setup; it only redoes what
  changed.

> Status: young and moving fast. Tested on macOS (Apple silicon). The neutral brand reel format is a draft, Lottie
> export covers vector animation only, and the quick brand builder (a small provisional brand for repos that have
> none) is not built yet.

## Tests

Negative-control tests: every check must fail on a fixture built to break it and pass on its control.

```bash
source scripts/env.sh && python3 tests/run.py
```

## License

Apache License 2.0, see [LICENSE](LICENSE). HyperFrames, GSAP, the pinned agent skills, the powers and the other tools
the setup downloads keep their own licences; see [NOTICE](NOTICE).
