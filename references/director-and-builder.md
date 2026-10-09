# Director and builder: who makes the video

Part of the kit-to-clip skill. `SKILL.md` says when to come here: once per job, right after "what are we making?".
It sets who plans, who builds and who checks, and how the design skills and quick sketches fit in.

Learned from a test on 9 Oct 2026: the same 45 s film made by two teams. A small, fast model (Haiku 5.5) built
flawlessly: every engine check passed and every beat landed. On its own it also designed timidly (the film shrank
into "slides" after the first scene) and invented fake causes for sounds. With a strong director (Opus 5.5) planning
and checking during the build, the person judged the result clearly better. So: **a director always leads. A builder
never works alone.** A director's polish *after* delivery made only subtle differences the person barely noticed, so
it is offered, never automatic (section 7). A third run, the strongest model alone on the same brief, was **faster
(43 min against 70-80) and judged better** than either team: so **Full is the default**, and builder helpers earn their
place where they are fast and cheap: sketching many directions, and simple, mechanical jobs.

## 1. Two modes (✋ once per job)

| Mode | Who plans | Who builds | Who checks and polishes | Use it for |
|---|---|---|---|---|
| **Full** (default) | the director | the director | the director | every film by default: in the test it was faster and better |
| **Quick** | the director | builder helpers on a smaller, faster model | the director, at the gates during the build | simple, mechanical jobs (a per-platform re-cut of an approved film, a card from a saved style, batch variants) |

Whatever the mode, **quick sketches** of many directions (section 3) use builder helpers when the host has them: that is
where they were clearly worth it (minutes per round).

- **The director** is you, the agent the person talks to, on the strongest model the host offers.
- **Never a builder alone.** A builder never talks to the person, never makes a creative call the plan did not make,
  never installs anything, never posts. It builds, checks its own work and reports.
- Use **Full** unless the job is simple and mechanical, then offer ✋ **Quick** (faster on cheap, repetitive work) /
  **Full**, with one line each, and remember the answer (`memory.py prefer --topic general`).
- **Quick needs a host that can start a helper on a smaller model.** In Claude Code: the Agent tool with
  `model: "haiku"`. On the Anthropic API `haiku` means Haiku 5.5. On Amazon Bedrock, Google Cloud and Microsoft
  Foundry it still means Haiku 4.5: pass the full model id `claude-haiku-5-5` (or the platform's own id) instead.
  A host without helpers (Codex today) runs **Full**: say so in one line.
- **The director may step in at any time** and fix something itself when that is faster than a fix list. Log it.

## 2. Design skills in the planning phase

Kit to Clip pins two design skills (`setup/skills-lock.json`; setup installs them with the engine):

- **`frontend-design`** (Anthropic): load it **before writing the plan**, to choose a bold, specific direction: type,
  colour, composition, contrast, what makes this piece memorable. ⚠️ Its motion advice is written for web pages
  (CSS-only animation, hover and scroll effects). **Ignore that part.** In Kit to Clip every move is a seekable GSAP
  tween on the HyperFrames timeline (`hyperframes-animation`, `gsap-*` skills): the same time always gives the same frame.
- **`impeccable`**: load it to **critique** the plan, the sketches, the option stills and the film stills: hierarchy,
  spacing, type, empty space, "too timid" or "too loud". Its reference docs work on their own. Its `scripts/impeccable`
  engine is optional: the first run downloads a checksum-verified program from impeccable's GitHub releases into
  `<engine>/tools/impeccable` (`env.sh` sets `IMPECCABLE_HOME`). Ask ✋ before that first run, with one line on what
  it adds. Without a yes, critique from its docs.
- A brand's own pack always wins over both skills: they shape the design, the pack sets the brand.

### Specialist skills by video type (optional, recommended when relevant)

On top of the two design skills (every job), **loading a specialist is recommended when the job's video type clearly
matches** one below: read it before writing the plan. Use one, two at most. It is never required. They are pinned with
the engine (calesthio/generative-media-skills, MIT).

| The job | Load |
|---|---|
| A social short, Reel, TikTok or Short | `social-short-production` |
| A product ad, a 6-15 s bumper | `product-ad-production` |
| A launch or brand film | `brand-launch-film-production` |
| A SaaS or app demo, a walkthrough | `saas-product-demo-production` |
| An explainer | `explainer-video-production` |
| Event or match highlights, a hype piece | `cinematic-trailer-production`, `editing-montage` |
| A beat-synced or music-driven edit | `music-video-production`, `music-supervision-scoring` |
| Kinetic type, a title card, a lower third | `title-kinetic-typography` |
| Any other motion piece, or none fits | `motion-graphics-direction` (plus `storyboard-previsualization` for a long piece) |
| A data story, animated charts | `d3-animated-data-visualization` |
| The sound effects plan | `sound-design-foley` |

When you use them, three rules win over what they say:
- **Kit to Clip is free and local.** Skip every step that needs a provider, a key, an account, generated footage or a
  generated person (they mention some, for example a paid music service).
- **HyperFrames builds it.** Take their craft rules (hooks, pacing, hierarchy, shot grammar, timing); build with the
  HyperFrames and GSAP skills, seekable on the timeline. Ignore other engines' code.
- **Platform facts change.** Their platform numbers are dated: check `finish/profiles.json` and say when they differ.

These specialists are new (October 2026). In a first blind test on a 15 s Reel, the film with them and the film
without them were judged about the same, at about 10% more tokens and fewer redos; real jobs with richer briefs may
benefit more. Note in the plan which ones you loaded, so later jobs can tell.

### The power palette (in the plan, not after it)

Kit to Clip's toolbox powers are creative options, not only fixes for missing features. While you write the directions
and the plan, run `python3 <kit-to-clip>/scripts/toolbox.py list` and ask what each family could add to **this** idea:

| Family | Powers | What it can bring |
|---|---|---|
| Looks and texture | `paper-shaders`, `p5`, `p5-brush`, `roughjs` | living gradients and grain in brand colours, watercolour or pencil, a hand-drawn line |
| Physics and particles | `pixi`, `rapier`, `motion` | confetti, sparks, things that fall and pile up, springy app-like UI |
| 3D and layers | `blender`, `effectcraft`, `vectorcraft` | a 3D logo or product, After Effects-style layered vectors, logos from .ai or .eps |
| Lottie | `dotlottie`, `lottie-web` | a Lottie recoloured to the brand, a Lottie export |
| Footage | `hf-cutout`, `rembg`, `sam2`, `rife`, `realesrgan`, `filmcraft` | cutouts, text behind a person, smooth slow motion, sharper frames, exact edits |
| Voice and words | `kokoro-voice`, `hf-transcribe`, `parakeet` | a voice-over, word-timed captions |
| Sound | `music-maker`, `ace-step`, `sound-effects` | music made for the piece, effects from the motion |
| References | `media-fetcher`, `video-reader-tools` | learning from a video the person likes |

- Name the powers each direction uses in its paragraph, and in the plan's scene table, with the reason. A direction
  can use none: plain HTML and GSAP are often enough.
- Read a power's recipe (`toolbox/recipes/<id>.md`) before planning on it: seekable timing, "bake" steps and limits.
- A power that is not installed costs a ✋ (Step 4 in `SKILL.md`): say what it adds and its size, and keep a fallback
  direction that needs nothing new.

## 3. Quick sketches while brainstorming

This is where builder helpers shine, in either mode. It replaces "two or three motion options as stills".

```
the brief ─▶ the director proposes 5-6 clearly different directions (one paragraph each: look, motion idea, why it fits)
          ─▶ builders sketch each one (at most 3 at a time): 2 stills (the first frame and the key moment)
             or a 3-5 s low-resolution motion test, labelled "sketch"
          ─▶ the director checks the sheet (drops broken ones, says what each is) ─▶ ✋ the person reacts
          ─▶ the director refines 1-2 directions ─▶ the plan
```

- **The director writes the directions so they differ at every shown moment** (layout, depth, texture, how the brand
  arrives), not one design with three filters. A builder left alone makes sketches that are too alike.
- Sketches are for feeling, not finish: no sound, no polish, no render longer than 5 s.
- A host without helpers: the director sketches 2-3 directions itself.

## 4. The director's plan

Write it to `<work>/<job>/plan.md` before any build. A builder follows it literally, so what the plan leaves out the
builder decides timidly. The plan must hold:

1. **Concept:** one paragraph. The idea that makes it memorable.
2. **Music:** the source and every setting (tempo, key, bars, seed), the length in whole bars, the sections as beats.
3. **Scenes:** one row per scene: beats, seconds, the fact it shows, what is on screen, the motion, the transition, the
   sound role (reveal, big move, accent, hold).
4. **A layout for every scene**, not only the first frame and the end card: an ASCII sketch with the canvas, the safe
   lines and each element's box in pixels. In the test, the plan's boxes held exactly where they were drawn and
   nowhere else.
5. **Sizes and fill** (at 1920x1080, scaled for other canvases): body text at least 40 px, labels at least 28 px, shapes
   and icons at least 200 px on their short side, and **no settled frame more than about half empty**.
6. **Where each sound comes from:** for every hit, the element and the beat it comes to rest on.
7. **Risks** and how each will be checked.

## 5. The builder brief and the builder rules

Give each builder one task at a time, a short prompt that **points to files instead of pasting them** (long prompts
cost more, and Haiku 5.5's price rises five times above 100K tokens of prompt), and these rules:

- Read the plan, the brief, `SKILL.md` and the guides the task needs. Source `env.sh` in every shell.
- Work only in your own folders. Never read another builder's folders.
- Never ask the person anything, never install, never post, never delete. Edit files with the edit tools, not with
  scripts that write files. List leftover temp files in your report.
- Take every still with `npx hyperframes snapshot --describe false` (`env.sh` also removes the online vision keys).
- Use `npx hyperframes check`, not `npm run check` (the project template's script can download a package).
- **Big moves come to rest ON their beat.** To land on beat N, start the move during beat N-1 (open the scene one
  beat early if needed) and accelerate into place (`power2.in` or similar). A slow ease-out that starts on the beat
  lands late, and its sound has no cause.
- **Never add an element only to carry a sound.** Every hit follows a real move you can see.
- Stop at a failed gate (`finish` refusing a cue, a check failing three times): report the numbers and your diagnosis,
  never force it (`--no-sync` is the director's decision).
- Report honestly: paths, every check's output with numbers, what failed, what you changed from the plan and why. The
  sound is unheard by you.

## 6. Gates (Quick mode)

The director checks at each gate and logs one line in `<work>/<job>/teamwork-log.md`:
✅ **approved** (nothing changed), 📝 **fix list** (the builder applies it), 🛠️ **intervened** (the director changed it).

| Gate | The director checks |
|---|---|
| Plan (when a builder drafted it) | facts only from the brief, the music maths, the layout for every scene, sizes and fill |
| Sketches and option stills | truly different at every moment, the brand from its real pack, nothing cut off |
| Film stills | **settled** stills (each scene's last beat), not mid-entrance ones; sizes, fill, safe zones; `impeccable` critique |
| Sound | every hit sits on a real move that rests on its beat; `finish.py sync` passes on the render |
| Delivery | the files: size, length, sound, loudness, contact sheet |

- **A fix list is short, numbered and specific** ("S10: the loader ring 300 px or more"). In the test, 6 of 6 fix lists
  landed on the first try.
- After **two fix rounds** on the same problem, the director does it.
- The person's ✋ gates stay the director's job: the layout, the stills, the listening checkpoint, the render.

## 7. Polish after delivery: offered, never automatic

Put the director's time into the plan and the gates **during** the build: that is where it changed the result (in the
test, every fix list landed and turned "slides" into a designed film). A polish **after** delivery mostly moved
numbers the person could not see or hear, and made them wait.

- After delivery, look at the contact sheet once. If something is clearly worth fixing, **offer it**: one line per fix,
  with what the person will notice and the time it takes ("the end card is half empty: fill it, about 3 minutes").
  ✋ **Fix these** / **Keep it as it is**. Never polish without a yes.
- Offer only what a viewer would notice. Timing already inside the sync window, a warning nobody sees, a few pixels
  of margin: leave them.
- If the person disliked something you cannot fix with a polish (for example the built-in effect sounds), say so
  plainly instead of polishing around it.

## 8. Rhythm traps (measured in the test)

- **Half-frame beats.** At 30 fps a beat often falls between two frames (beat 56 at 128 bpm is 26.25 s, frame 787.5).
  End such a move about one frame early, or the check reads the rest one frame late.
- **3D turns look landed early.** The last degrees of a turn barely change the picture. Run the turn about 0.1 s past
  the beat (more on a narrow phone plane) so the eye sees it land on the beat.
- **The same move is faster on a phone.** A plate rising 1920 px in a beat is twice as fast as 1080 px, so its whoosh
  is twice as loud and can mask the hit. Raise the whoosh's `vref` for the 9:16 cut.
- **A scene cut is a fine cause** for a hit when the cut itself is the moment. A thin line drawn only to carry the hit
  is not.

## 9. Costs and limits

- Haiku 5.5 costs about 1/40 of Opus 5.5 per token for prompts up to 100K tokens ($0.10 / $0.50 per million input /
  output tokens against $4 / $20, Anthropic's prices in October 2026). In the test, one full film took a builder about
  70-80 minutes over six tasks.
- About 25-35 minutes per film were rework that a full plan (layouts for every scene, sizes, sound causes) would have
  prevented. Spend the director's time on the plan.
- At most three builders at a time, and at most two renders at once on a laptop.
