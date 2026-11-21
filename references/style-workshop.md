# Create a new direction, or design a legacy template

For an ordinary video, selected library reference or supplied prompt/code, use `video-journey.md`. Selecting a
reference does not start another concept contest. This guide is for a new direction, or an explicitly
requested reusable slot template. Saving an approved video's treatment uses `personal-references.md`.

## A new direction for this video

Start from what the person already supplied: goal, audience, story, footage, destination, duration, visual likes
and sound choices. Ask only for consequential missing decisions. Do not require a style name, author, brand pack
or early registry entry. Discovering a brand kit does not choose it; original look, a palette and full identity
remain separate options.

Use the catalogue and personal references as inspiration when helpful. Read only selected examples' code. Keep
permitted use and provenance clear, and use `reference-resources.md` for fonts/assets and `open-source-effects.md`
for deterministic integration. For a video link, first use `reference-video.md`; reuse what its analysis answers.
Imagery preparation is conditional, through `imagery.md`.

If the direction is still open, offer a few concise textual concepts with a distinct material, motion language and
signature moment. Three is a useful option, not a compulsory number. When the person has a clear direction,
develop it directly. Use the engine-pinned frontend-design and impeccable guidance for composition and critique.
No automatic batch of sketches, helper model downgrade or competing Full/Quick mode is needed.

Choose timing from the brief: narration, music, visual reading or footage. Music-led transitions can follow chosen
beats; narrated ideas follow the actual recording and pauses. Preserve selected textures, semantic colours and
recognisable subjects when branding. Do not flatten every material into a single accent colour.

Keep the proposal and meaningful decisions in this video's `film.json`. Then follow the four approval stops in `SKILL.md`:

1. Show the storyboard with the ASCII layout: actual canvas, element sizes/positions and platform safe zones. Get the
   ✋ storyboard yes. A silent mini comparison can have its own storyboard yes and scope.
2. Build the approved direction with the existing engine. Canvas2D uses `canvas-reference.md`; no second clock.
   Name the actual code files in `film.json`.
3. Inspect/check representative stills yourself. With music, play the takes on the built picture (✋ music pick).
4. Render without a separate render yes. Build effects/mix before encoding, check the encoded picture and sound, and
   get the ✋ final film yes. Measurements do not establish taste.
5. After the finished video is approved, offer to save its treatment with `styles.py capture`. A title is needed
   only if saving; author is optional. Record reusable instructions/tags separately from this story and brand.

An adaptable code reference is useful because a fresh builder can rebuild it for another story. It does not need
promised content slots. Existing saved templates remain available without conversion or deletion.

## Legacy slot-template workshop, only when requested

Use this route when the person specifically wants a template that can be refilled without redesign. Existing
`styles.py init`, `save`, `new` and `refs` commands remain supported. They are not the default create-new intake.

Find existing material with `formats.py list --all` or `styles.py list --json`. Agree the intended purpose,
platform/canvas, content slots, visual structure, timing driver and sound. Reuse settled answers. For a full brand
identity read its actual kit; an unbranded template needs no invented identity.

When registering the template, use an explicit title and chosen attribution for the legacy command:

```bash
python3 <kit-to-clip>/scripts/styles.py init --title "<title>" --author "<chosen attribution>" [--brand <id>]
python3 <kit-to-clip>/scripts/styles.py refs --style <slug> <reference-files>
```

Do not automatically store the person's name or general preferences. Keep the template recipe in `style.md` and
`style.json`, using the existing fields:

| Field | Purpose |
|---|---|
| `made_for`, `platforms`, `canvas`, `length_s` | Intended use and output shape |
| `mood`, `signature`, `structure` | Feeling, memorable moment and scene/beat sequence |
| `slots` | Required/optional content inputs, their kind and limits |
| `type`, `sound`, `motion_rules` | Typography, audio choices and reusable movement |
| `references`, `dos`, `donts` | Kept reference files and practical constraints |

Show the recipe and the ✋ storyboard, build representative content, run checks, then follow the ✋ music pick (with
music) and the ✋ final film in `SKILL.md`. A slot template should keep content/timing data-driven so a refill changes the intended inputs.
This slot requirement applies to templates, not adaptable code references.

After actual approval and the person's save choice, save a fresh registered template:

```bash
python3 <kit-to-clip>/scripts/styles.py save --style <slug> --project <approved-project> --approve
```

Avoid replacing an existing approved template without the applicable explicit replacement authority. Keep a new
variant under a new slug when appropriate. Template brand reapplication through `styles.py new` is used only when
the person explicitly wants that stored identity. Otherwise rebuild from the saved source in a fresh brief.
