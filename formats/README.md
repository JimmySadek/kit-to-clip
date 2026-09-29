# Formats module: the formats library

Part of the kit-to-clip skill; `SKILL.md` covers setup (env.sh, the HyperFrames skills) and when to come here.

A format is a repeatable recipe: a structure, motion and sound, and **slots** (the content each video supplies).
The look comes from the brand's video pack (the brand module), the platform layout and finishing from the finish
module. Before building, also load `hyperframes-core` (or read it from `$REEL_STUDIO/.claude/skills/`).

Folders: `<work>` is the per-clip work folder, `<videos>` holds built projects, `<deliveries>` the finished files.
Inside a studio folder use its `work/`, `videos/` and `deliveries/`. In any other repo use its `reels/` workspace
(`reels/work`, `reels/videos`, `reels/deliveries`, clips in `reels/clips`), made by `<kit-to-clip>/scripts/workspace.sh`. Only as a last resort default to `<kit-to-clip>/work` and ask for the rest.

## Which formats exist

```bash
python3 <kit-to-clip>/formats/scripts/formats.py list --project .              # approved formats this project can use
python3 <kit-to-clip>/formats/scripts/formats.py list --project . --all --json  # also drafts; full rows as data
```

Two sources, one list:

| Source | Where | Brand |
|---|---|---|
| Neutral | `<kit-to-clip>/formats/neutral/<id>/format.json` | any brand whose pack has token contract v1 |
| A brand's own | `<brand kit>/kit-to-clip/<formats>/<id>/format.json`, named by `"formats"` in the pack's `pack.json` | that brand only |

`format.json`: `schema: 1`, `id`, `name`, `version`, `status` (`idea`, `draft`, `trial`, `approved`, `retired`),
`made_for` (`clip`, `brief`, `video`, `loop`), `about`, `platforms`, `canvases`, and `journey`: the file to read
before building (default `README.md` in the format's folder). Only `approved` formats are offered in the front door.
A broken `format.json` is listed as `(broken)` with the reason: report it, don't guess around it.

## Running a format: ask first, build only what was picked

Read the format's journey file and follow it. Every journey keeps the same shape, because renders cost time and
tokens: nothing is built or rendered that the user did not choose. Use AskUserQuestion at each ✋, one decision each.

```
✋ content ─▶ (cheap analysis) ─▶ ✋ platforms ─▶ ✋ approve the plan ─▶ build ─▶ checks ─▶ ✋ render ─▶ deliver
```

**Checks** on every project, all must pass before offering a render: `npx hyperframes lint`,
`npx hyperframes check`, `python3 <kit-to-clip>/finish/scripts/finish.py check --project <dir>` (script errors, missing
files) and `python3 <kit-to-clip>/finish/scripts/finish.py safe --project <dir> --platform <p>` (every text and logo stays
inside the platform's safe box for the whole video). Snapshot the key moments and look.

**Deliver** only the confirmed renders, one per platform layout:

```bash
npx hyperframes render -o <file>.mp4            # inside the project, after env.sh
python3 <kit-to-clip>/formats/scripts/deliver.py <file>.mp4 --slug <slug> --format <id> --platforms tiktok --out <deliveries>
```

A render with sound is refused until its sound has been checked against its picture. If the sound was made for the
picture, add `--cues <cue-sheet.json>` (the sound module, `sound/README.md`). If it is the footage's own sound (a clip
that keeps its original audio, as in most clip formats), add `--no-sync "footage's own sound"`; the reason is printed and
recorded.

Output: `<deliveries>/<slug>/<format>/<platform>/` with master, share copy (<= 30 MB), cover, contact sheet,
safe-area check image and `report.json`. Open the contact sheet before handing over.

## Neutral formats

Neutral formats hold no brand: they style themselves only from the pack's token contract (`--reel-*` variables and
`REEL_BRAND`, see `brand/brand-pack.md`), so one build works for any brand.

| Format | Status | What it is |
|---|---|---|
| `neutral/brand-reel/` | draft | 24 beats: motif, headline, stat, three points, flurry, lockup. Slots with character limits, `--variant auto` for variety. See its `README.md` |
| `neutral/teaser-loop/` | draft | a still teaser as a seamless loop (GIF, web): opens on the finished layout; background wave or breathe, accent ring and line. See its `README.md` |

Drafts are not offered in the front door until approved. Directing words (push in, match cut, carry,
anticipation, beat grid): `references/motion-vocabulary.md`.

## Cards: build a brief video from reusable scenes

```bash
python3 <kit-to-clip>/formats/scripts/cards.py list [--purpose stat]
python3 <kit-to-clip>/formats/scripts/cards.py compose --brand <id> --spec spec.json --out <videos>/<job> --canvas 1080x1350 --platform instagram-feed
```

Six cards (`formats/cards/cards.json`): **headline**, **stat**, **list**, **quote** and **lockup** take over the frame;
**lower-third** sits over footage. Each has slots with limits, a duration range and its entrance, styled only from
the pack's tokens (a line motif marks list points with a dash). A spec lists the cards in order; `"anchor": "beat:6"`
or `"word:launch"` places a card on the music (`"bpm"`) or the voice (`"words"`, from `hyperframes transcribe`), and
`finish.py anchors` checks them later. The first card opens part way into its entrance, so the first frame is never
empty. Only say what can be sourced: a stat card needs a real number and, ideally, its `source`.

## Safe zones (1080x1920)

| Platform | Keep text, logos and key graphics inside | Source |
|---|---|---|
| TikTok | x 120-840, y 252-1280 (top 252, bottom 640, left 120, right 240) | TikTok in-feed safe-zone template (540x960: 126/320/60/120) |
| Instagram Reels | x 65-1015, y 269-1248 (14% top, 35% bottom, 6% sides) | Meta Reels Ads Guide; Reels and Stories unified in 2026 |

Footage may run full-bleed; only overlays must stay inside. TikTok ads with long captions or add-ons shrink the zone
further: check the real upload preview before posting. The Instagram profile grid shows the middle 3:4 of a cover.

## Adding a format to a brand

Put it in the brand's own repository, never in Kit to Clip: a folder per format under `<brand kit>/kit-to-clip/formats/`
with its `format.json`, template and build script, a journey file, and `"formats": "formats"` in `pack.json`. Real
people appear in clip formats: the journey must remind the user about consent and never post without a go-ahead.
