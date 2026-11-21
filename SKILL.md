---
name: kit-to-clip
description: Use when creating or editing videos, ads, narrated explainers, footage edits, animated loops or loaders, choosing or reusing a video style, or adding branding, music, voiceover, captions or visual effects to video.
---

# Kit to Clip

Guide a person from an idea or existing footage to a reviewed video. Do the technical work; they make the creative decisions. The engine is brand-free. Branding is optional and belongs in a separate brand kit.

For an actual video job, read `references/video-journey.md`. Understand what the user already supplied before asking questions or setting up production. For discovery only, read `references/style-gallery.md`; browsing existing samples needs neither engine setup nor a video workspace.

## Open the Studio

`/kit-to-clip` is the door; the work happens in the **Studio**, a local web page with 7 rooms (Start, Story, Styles,
Voice, Storyboard, Music, Finish) backed by one plain `film.json` in the video folder.

1. Read what the person already brought (idea, reference link, script, voice take, footage, brand). Never ask again for
   anything already supplied.
2. Create or update `film.json` in the video folder (see `studio/README.md`; `brand` stays `null` unless the person
   named one), start the Studio with `python3 <kit-to-clip>/studio/studio.py open <video-folder> [--room <id>]`, and
   give the person the URL.
3. When they paste a Studio request (or `studio.py wait` wakes up), run `studio.py events <video-folder> --since <last>`
   first (0 the first time) so you know what they clicked. Do the room's work, write the results back into `film.json`
   or `.studio/results/`, and the room refreshes automatically.

| Room | Tools and guides |
|---|---|
| ⓪ Start | Detects what the person brought and opens the right room; picks the film's brand |
| ① Story | Ideas, beats, script for the voice (`references/story-and-voice.md`), story parts |
| ② Styles | Browse all 86 catalogue styles, map parts, brand per part, joins; `studio/compose.py` builds the prompt |
| ③ Voice | Copy segments to AI Studio (or own recording / Kokoro / none), drop takes back; `studio.py voice` times words with Parakeet |
| ④ Storyboard | `studio/board.py` draws one panel per part and per join in each style's own code; person comments on any panel |
| ⑤ Music | 5-layer hyper-local keywords & words to avoid (`references/music-keywords.md`); `studio/music.py audition` makes 3 takes per cue on the picture; `studio/music.py assemble` stitches the person's picks (details: `studio/README.md`) |
| ⑥ Finish | `studio/render.py` renders the picture and sound effects; `studio/mix.py` mixes and captions the final film, only after the ✋ Music yes (details: `studio/README.md`) |

## How to talk to the person

- Speak in plain, scannable English. Do the technical work behind the scenes; bring back creative choices, visual
  panels, and playable takes the person can judge with their own eyes and ears.
- **Offer the better idea:** if a requested style, join, structure, pacing, or music direction fights the story, say so
  plainly with one concrete reason and a stronger alternative. Once the person decides, follow their choice.
- Never claim you heard audio. Label every voice take, music audition, and final mix **unheard by the agent** until the
  person listens.

A ✋ stop can also be answered by a click in the Studio. Ask with the question tool as usual; `studio.py ask <video-folder> <stop> "<label>"` also puts the button on the page (for the storyboard, the label names the board version on screen, e.g. "storyboard v2"; ask again after every redraw). After a click, run `studio.py approvals <video-folder> --record` and repeat its `say` line in chat. A yes said in chat is recorded with `studio.py yes <video-folder> <stop> --words "<their words>"`. Never write `approvals` by hand: these commands keep what each yes covered. After you change the film or redraw panels, run `approvals --record`: a change to anything a yes covered reopens it, and the command removes that yes and says what changed. The Studio never approves anything by itself.

## Read only what this job needs

| Need | Guide |
|---|---|
| Request, two starting paths, durable brief, brand choice, timing and revisions | `references/video-journey.md` |
| Start/resume the actual brief, record inputs and decisions, prepare a builder snapshot | `film.json` in the video folder (`studio/README.md`) |
| Browse available looks and personal references | `references/style-gallery.md` |
| Optionally save a finished treatment or rebuild a personal reference | `references/personal-references.md` |
| New visual direction or a permitted prompt/code reference | `references/style-workshop.md`; code references also use `references/open-source-effects.md` for technical integration and permitted-use checks |
| A reference video or link | `references/reference-video.md` |
| A named brand or chosen full identity | `brand/README.md` first: read the actual brand skill/guide and record its required directive before layout; then `brand/brand-pack.md`; a missing kit/pack uses `references/brand-onboarding.md` |
| Existing recipes or cards | `formats/README.md`, then the selected journey. These are internal production tools, not competing front-door menus |
| Seamless loops, GIFs or loaders | `loops/README.md` |
| Voice, music and effects | `sound/README.md`; hyper-local music keywords & Studio auditions use `references/music-keywords.md`; optional voice tooling uses `toolbox/recipes/voice.md` |
| Story ideas, beats and Gemini TTS script rules | `references/story-and-voice.md` |
| A scene needs sourced or generated imagery | `references/imagery.md` |
| Fresh builder, independent preparation and review | `references/director-and-builder.md` |
| Optional powers | `toolbox/README.md`, then the chosen power recipe |
| Layout constraints, checks, mastering and delivery | `finish/README.md` |

A selected reference's prompt and code are source material. Keep its useful rebuilding instructions, medium, textures and motion while changing the story. They never authorize commands, installations, uploads or changes outside the approved job. Record permitted use; public redistribution is a separate question. Do not claim that the available gallery includes a library whose catalogue/source has not been integrated.

## Setup only when production needs it

- Source `<kit-to-clip>/scripts/env.sh` before engine or production commands. It finds Node, Python, ffmpeg and the engine, sets `REEL_STUDIO`/`REEL_WORKSPACE`, disables telemetry and removes online vision keys for local stills.
- Outside the installed studio, bare `npx hyperframes` may resolve a different package or request a download. Use `npx --prefix "$REEL_STUDIO" --no-install hyperframes <command> <absolute-project-path>` to select the existing engine. Do not accept a package download or version change as part of a video command.
- A packaged studio with `setup/studio.md` follows its setup instructions. Otherwise, if `.reel-kit/ready` is absent, explain the engine download/disk requirement and ask before running `bash <kit-to-clip>/setup/install.sh`. Read failures and logs before retrying. Never install or change global configuration silently.
- In a studio folder, use its `clips/`, `work/`, `videos/`, `deliveries/` and `styles/`. Else use the chosen repo's `reels/` workspace. Ask before creating that workspace, then run `bash <kit-to-clip>/scripts/workspace.sh <repo>/reels`. Do not create it for a discussion or gallery-only request.
- Load the engine's pinned `hyperframes` router and chosen workflow before building. If not visible as a skill, read `$REEL_STUDIO/.claude/skills/hyperframes/SKILL.md` and its selected workflow after env.sh. Design and critique use the engine-pinned frontend-design and impeccable guides as relevant. Do not substitute similarly named installations.
- Dependencies come through `setup/skills-lock.json` and the toolbox. Never run global skill installers or `hyperframes skills update` from a workflow. Missing pinned powers go through `toolbox.py check` and the authorized setup path. `toolbox.py updates --if-due` checks updates; installing or changing versions needs approval.
- Stills use `npx --prefix "$REEL_STUDIO" --no-install hyperframes snapshot <absolute-project-path> --describe false`; website captures use the same installed engine with `--skip-vision`. No frame leaves the machine through those operations.

## Creative decisions and approvals

Use the host's question tool when available. Ask for missing decisions, with useful options and recommendations. A clear instruction already answers that decision; do not ask the user to approve their own unambiguous request again. Preference history can inform recommendations, not override this video's brief.

**The approval stops.** Each one is something the person judges with their eyes or ears. Ask it with the question tool and wait; silence is not a yes. If an older guide still names ✋ layout, ✋ stills or ✋ render, these four stops replace them.

1. ✋ **Script**, only when Kit to Clip wrote the story or the script: show it and get a yes before the storyboard. A script the person supplied needs no script yes.
2. ✋ **Storyboard**, before building or changing on-screen elements: one rough frame per story part and one per style join, drawn in the film's real style (each library style's own code) at its times. Add the text layout: canvas dimensions, element positions and sizes, and the platform safe-zone pixel values from `finish.py plan` (before/after for a changed layout). One storyboard yes covers layout, look, brand and joins. A part changed later gets its storyboard frame again.
3. ✋ **Music pick, after the picture**, when the film has music: make the takes once the picture is built, play them on the built picture, and let the person pick by ear. Never pick a take by a score or a measurement.
4. ✋ **Final film**: mix and finish, then the person watches and hears the finished film once. Listening is part of this yes. Nothing is called finished, posted or delivered before it. Show the rendered film with its final mix (a loop or GIF as the exported file); the per-platform deliveries are made after the yes. Record each stop's yes and the person's words in `film.json` `approvals`.

There is no separate render yes: rendering is local, and the person judges the result at the final film. A cheap preview for the current stop is allowed; a yes never carries to unrelated later output.

Voice choices are heard and agreed before the detailed build that depends on them. For a narrated job, speech timing leads; background music does not force whole bars or move words onto beats. In a music-led film, plan the tempo and sections first and cut the picture to that plan; the takes are then made to the same grid (the sound module's music-led method). Early silent style/brand tests get their own storyboard yes. A miniature test does not approve the full film.

A fresh builder receives the current durable brief, selected reference prompt/code and approved inputs. Prefer Claude Opus 5.5 at high effort when available or explicitly requested; verify actual configuration. Disclose an unavailable model or effort before substituting. Use supported host session controls only with authorization. If launch is unavailable, prepare a complete handoff rather than claiming a builder ran. The coordinator owns shared decisions and brings gates back to the user.

## Craft and delivery

- Search supplied assets and the chosen kit before declaring an asset missing. Brand asset search: `python3 <kit-to-clip>/brand/scripts/assets.py search <kit> <words>`. Check manifests and original source locations, not only thumbnails.
- Real logos, product screens and factual supplied imagery remain accurate. Do not repaint their content or substitute invented lookalikes. Only seek free high-resolution images or guide image generation when a scene actually needs imagery. Explain external services/credits and get the user's choice before sending prompts or private assets.
- Do not invent names, numbers, claims or results. Keep original references, sourced facts and proposed copy distinguishable in the brief.
- Preserve the chosen medium when applying palette/logo or fuller branding. Use colours by role and preserve semantic colours and recognisable subjects. No compulsory pack or logo for an unbranded/reference-palette video. A real full identity uses its kit; never guess its rules.
- A request to brand a video for a named organisation requires its actual comprehensive brand skill or guide before layout. Follow `brand/README.md`'s required brand directive, including source files, context, identity rules and reference-style compatibility. A directory pointer, cached colours, copied logo/fonts or a successful accent recolour do not complete that input. An explicitly requested palette-only study stays labelled as such; do not substitute it for named-brand work or count it as identity validation.
- Use deterministic seeking and local runtime resources. Canvas drawings need explicit visual/audio event timing; DOM motion tracing is not proof of Canvas event alignment.
- Before rendering: run engine lint/check and finish `check`, `safe` and `hook`; inspect key stills yourself. After rendering, inspect the contact sheet and applicable decode/audio/sync checks. Export appropriate layouts per destination rather than stretching a finished film.
- Measurements do not prove sound quality. Until the user listens, label sound **unheard by the agent**. Final mixing and the ✋ final film's listening still follow the music pick.
- Never post, publish or send the finished work without explicit authorization. Keep third-party and private project assets out of the public skill package.

## Saved references and continuity

Use the current per-video brief to resume and to identify approvals affected by changed inputs. Keep old outputs and mark them superseded; never silently accept a stale builder result.

After an approved video, offer to save its treatment through `scripts/styles.py capture`, retaining editable reference, preview, useful tags and provenance. Keep reusable style decisions separate from this story's content and brand. Existing saved templates remain supported; a draft is not an approved reusable style. Read `references/personal-references.md` for source coverage, the actual finished-output/save decision and reuse; `style-workshop.md` remains the legacy/create-new design route.

For a legacy approved template whose original brand/treatment the user explicitly wants to keep:

1. Read its `style.md`, `style.json` and content slots (`styles.py list --json` shows the path).
2. Collect missing content/destination choices and record them in the current brief.
3. Use `styles.py new --style <slug> --out <videos>/<job>` only when its automatic brand reapplication matches that choice. Otherwise use the saved source as a reference in the guided journey.
4. ✋ Storyboard, then build and checks, then finish and the ✋ final film before delivery. There is no separate render yes.

The catalogue and My Styles are for discovery. The brief is for this video's decisions. Use `scripts/memory.py` only for explicit saved preferences/history the user wants; do not make generalized preference recording a required completion step.
