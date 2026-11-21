# Brand module: put a brand on a video

Part of the kit-to-clip skill; `SKILL.md` covers setup (env.sh, the HyperFrames skills) and when to come here.

Turn a brand into the files a HyperFrames project already knows how to obey. HyperFrames reads `frame.md` as brand
truth and its design-adherence check verifies hex values, fonts, corners and the Do's and Don'ts in it. So the
fastest way to be on-brand is to hand HyperFrames a correct `frame.md` plus the real font and logo files, then
build normally.

Kit to Clip holds no brand. Each brand keeps a **video pack** next to its brand kit, in the brand's own
repository: `<brand kit>/kit-to-clip/` with `pack.json` (what to copy, which templates to fill), `templates/`, an
optional `pack.py` and a `guide.md` on how to build with that brand. A brand without a pack: stop and say so (the
front door's brand onboarding makes one). A guessed palette or font would look plausible and be wrong, which is
worse than asking. What a brand must provide, the pack files and the **token contract** that lets neutral formats
style any brand: `brand-pack.md` in this folder.

## 1. Read the brand's own skill

The bridge copies files and tokens; judgment (tone, composition, intensity) comes from the brand kit (e.g.
`acme-brand`) and the pack's `guide.md`, which names what to read.

### Required brand directive before layout

For a named-brand job, locate the owning repository or supplied comprehensive guide. Read its actual `SKILL.md`,
required entry guide and the references it routes to for this video's context. A discovered installation or
cached palette is not evidence that those instructions were read. Use the kit's source hierarchy; record the
repository revision and the actual source files. Ordinary work can use the kit's verified snapshot when its
rules allow that. Refresh live sources only when needed by those rules or a material conflict.

Write a private `brand-directive.md` in the video's work folder. It is a job-specific application of the source,
not a replacement brand guide. Complete these fields before proposing branded layout:

| Required field | What to record |
|---|---|
| Authority | Actual skill/guide path, repository revision or document version, references read, source hierarchy, conflicts/resolutions and any provisional pack status |
| Context | Applicable marketing, product or other register; distinguish identity rules from an old campaign or motion sample |
| Colour roles | Background, foreground, focal emphasis and supporting/semantic colours, with source references |
| Typography | Display/body/label roles, permitted weights, tracking and the actual licensed font files |
| Logo | Exact appropriate export, source/hash, clear space, minimum size and permitted placement/effects |
| Imagery, icons and copy | Relevant required/forbidden treatments and factual or tone constraints; mark unused categories as unused |
| Motion and material | Applicable brand motion rules, reference medium/texture to preserve, and any compatibility conflict or unresolved choice |

In `film.json`, set `brand` (its name and brand skill) and list the completed directive and the actual governing
guide files individually in `inputs`. Include the actual used fonts/logo separately.
Their changes must reach the current brief and reopen the affected storyboard frames. A kit directory pointer alone does not do this.
The fresh builder receives the directive **and** the governing skill/guide material needed to follow it.

If the comprehensive source is missing, inaccessible or contradictory in a way its source hierarchy does not resolve, report that gap and stop the branded
layout/build while other independent work continues. Do not infer an identity from a logo, guessed hexes,
an old brief, a website screenshot or a provisional video pack. Source inspection is normal preparation, not
an extra user approval gate. Do not reinstall, update or edit the brand repository as part of reading it.
A missing kit/pack or an incomplete website-derived guide uses `../references/brand-onboarding.md`; resolve
the missing directive fields there before treating that input as a comprehensive brand guide.

For an explicitly requested unbranded palette experiment, keep `brand` null in `film.json` and note the
palette-only scope and the limited colour roles. Label its comparison as palette-only. It neither requires full identity onboarding nor proves branding.
When testing named-brand integration, use the required directive and show a meaningful matched comparison;
judge both recognisable identity and preserved reference material. A tiny accent swap is not a substitute.

## 2. Keep the environment safe

Source `<kit-to-clip>/scripts/env.sh` in every shell before a HyperFrames command. Without it, `hyperframes init` installs
skills globally into the user's skill folders and both HyperFrames and the skills CLI send telemetry. Never run
`npx hyperframes skills update` or `npx skills add -g` from this workflow; if a workflow skill says to, skip that
step when the skill is already present in the project, and tell the user.

## 3. Bridge the brand into the project

```bash
source <kit-to-clip>/scripts/env.sh
python3 <kit-to-clip>/brand/scripts/bridge.py --list --project <project-dir>          # the packs this project can use
python3 <kit-to-clip>/brand/scripts/bridge.py --brand <id> --project <project-dir> --canvas 1080x1920
```

Use the canvas of the main cut (`1080x1350` for a 4:5 feed cut, `1920x1080` for 16:9). Packs are found nearest
first: a pack in the project's own repository (`.agents/skills/*/kit-to-clip/` or `.claude/skills/*/kit-to-clip/`) wins over an
installed one, so a brand repo always uses its own brand. The bridge copies the files the pack names, checking
each against the kit's recorded hashes, fills the pack's templates (usually `frame.md`, `brand.css`,
`brand-snippets.js`) and writes `.reel-brand.json` (provenance). A pack with token contract v1 is checked for every
`--reel-*` variable and `REEL_BRAND`, and the bridge adds `reel-tokens.js` (the brand's easing and durations for GSAP). Exit code 2 means no pack for that brand, or a
broken pack: stop and report it. Exit code 3 means the kit's files changed: report, do not patch around it.

If the bridge says the brand is **provisional**, say "provisional brand" in the handoff of every video made with it.

## 4. Build with the brand files

Keep the required directive from section 1 current. Read the pack's `guide.md` next (the bridge prints its path as `read next:`). It says which brand references to
read, how to use `brand.css` and the helpers, and what the brand never allows. General rules for every brand:

- Logos come from the copied logo files only; never type, redraw, crop, skew or recolour a logo.
- HyperFrames' lint wants `@font-face` in the same file as the text that uses it; if lint reports
  `font_family_without_font_face`, copy the `@font-face` block from `brand.css` into the composition's `<style>`.
- Plan long display lines with the text-fit numbers the pack puts in `frame.md`, when it gives them.

## 5. Tell the truth on screen

Use only facts you can show: measure times from frames, count only what you can see, and never invent names,
numbers or results the user did not supply. When an effect could pass for reality, add a light honesty line. Real
people need consent before anything is posted; say so in the handoff. The pack's guide adds the brand's own rules.

## 6. Verify before you call it on-brand

1. `npx hyperframes lint`: zero `font_family_without_font_face` findings.
2. `npx hyperframes snapshot --describe false --at <a title moment>` and look at it: the brand's display font must be visible (the
   guide says what to look for). A plain sans-serif means a font failed to load.
3. Run HyperFrames' design-adherence check against `frame.md` (colours, fonts, corners, Don'ts).
4. Report what was copied (the script prints it), which pack and version was used, and anything done by hand.

## 7. Find the brand's own assets (never say "we don't have it" first)

```bash
python3 <kit-to-clip>/brand/scripts/assets.py search <brand kit> <word> [<word> ...]   # names, manifests, text, press-kit ZIP lists
python3 <kit-to-clip>/brand/scripts/assets.py sheet  <brand kit> --out <dir>             # numbered contact sheets of EVERY picture
```

`search` reads every folder (originals included), the manifests' use and avoid notes, SVG and Markdown text, and the
file lists of the official press-kit ZIPs the kit links, and always prints where it looked. Names mislead and office
templates hide pictures, so also run `sheet` and **look at every sheet**: it thumbnails every raster file and every
picture inside the kit's .pptx, .docx, .xlsx and .key files, and `index.json` maps each number to its file. A real
teaser's device and background were found this way, inside a slide template, under names like `image3.png`.
Record what you use in the job's `SOURCES.md` (file, inner path, sha256).

## 8. Brand sheet from a website

When a brand is known only from its website (onboarding step 1), capture it and turn it into a sheet:

```bash
npx hyperframes capture <url> --skip-vision -o <capture-dir>          # after env.sh; --skip-vision keeps it local
python3 <kit-to-clip>/brand/scripts/brandsheet.py <capture-dir> --out brand-sheet.md --json proposal.json [--kit <brand kit>]
```

It proposes each `--reel-*` token with where it came from (the page's section backgrounds, text colours, the accent its
buttons use, the text on those buttons, faces per role, the brand's own button radius; cookie and consent banners are
ignored), lists logo candidates, and says what a website cannot tell. With `--kit` it lists conflicts with the kit's
pack (for example a site set in its product UI face where the brand's marketing kit names a different display face). Nothing in it is final until the
brand owner confirms it; web font files are not a licence.

## Pitfalls learned the hard way

- An `<svg>` used directly as a timed clip (`class="clip" data-start=…`) is not hidden outside its window. Wrap it in a `<div>`.
- Don't name a script variable `top`, `name`, `status` or other `window` globals at top level: the whole script dies and lint does not notice.
- A timed wrapper around `<video data-start>` gives wrong frames; only time one of them.
- Full-screen overlays (tints, flashes) must start at `opacity: 0` in CSS or they cover earlier frames.
- With a Gemini, OpenRouter or Vertex key in the shell, the video engine's stills and website capture send frames to
  that service by default (and download a Google package first). env.sh removes those keys; also pass
  `--describe false` to `snapshot` and `--skip-vision` to `capture`, every time.
