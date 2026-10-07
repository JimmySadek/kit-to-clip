# Brand video packs: what a brand needs for great videos

The Kit to Clip engine holds no brand. A brand becomes usable for video through a **video pack**: a `kit-to-clip/` folder
next to the brand's kit, in the brand's own repository (for example `.agents/skills/<brand>-brand/kit-to-clip/`). Section 5
is a complete minimal pack for a made-up brand, Acme, to copy from.

## 1. What the brand must provide

| Need | Why a video needs it | If it is missing |
|---|---|---|
| **Colours with roles**: background, text, one accent, muted text, a surface, text on the accent | Formats colour by role, never by hex; one accent keeps the eye on one thing | Ask, or use the quick brand builder (marked provisional) |
| **Fonts as files, with licences**: display, body, label | Video renders offline; a font name without a file renders as a fallback face | Ask for the files, or approve a clearly marked free substitute |
| **Logos as files per background** (on dark, on light) | Never type, redraw or recolour a logo | Use the brand name as plain text and say so |
| **A signature motif**: the brand's most reduced shape or line (a facet, a stroke, a dot) | Neutral formats transform it through the video and land it on the end card | Choose one with the brand owner; never invent a mark that looks like a logo |
| **Motion feel**: energy (calm, steady, punchy), enter/exit/move easing and durations, and a few **written motion rules** ("headlines enter left to right in 0.6 s on a low arc, a touch of motion blur, land sharply") in `guide.md` | Two brands in the same format must move differently; written rules carry the feel the numbers miss | Propose values and two or three rules, sample stills, get approval |
| **Rules and claims**: what the brand never does, what may be claimed | Keeps generated copy truthful and on-voice | Ask; default to showing only facts the user supplied |
| **Approved stills** (`kit-to-clip/approved/`) | The reference for "this is what the brand looks like in motion" | Make sample stills and get approval before rendering |

## 2. The pack files

| File | What it holds |
|---|---|
| `pack.json` | `schema: 1`, `brand` (id), `name`, `version`, `status` (`approved` or `provisional`), `contract: 1`, `hash_indexes`, `copy` (project path: kit path), `templates`, optional `builder` and `guide` |
| `templates/` | Files the engine fills with `{{placeholders}}`: at least `brand.css` and `brand-snippets.js`, usually `frame.md` (the design file HyperFrames enforces) |
| `pack.py` | Optional `build(ctx)` for what data can't express (computed text fit, policy-driven asset lists). Returns `values`, `provenance`, `summary` |
| `guide.md` | How to build with this brand once a project is bridged; the engine prints its path |

Kit files are copied and checked against the kit's recorded hashes (`hash_indexes`). A changed file stops the bridge
(exit 3). A `status` other than `approved` is printed as a warning, and every handoff must say "provisional brand".

## 3. The token contract (v1)

Neutral formats use only these names, so any pack re-skins them. A pack with `"contract": 1` must define every
required variable on `:root` in its `brand.css`; the bridge stops (exit 2) if one is missing.

| Variable | Meaning | Acme (example) |
|---|---|---|
| `--reel-bg`, `--reel-fg` | Main background and text | `#0F3D2E`, `#FFFFFF` |
| `--reel-accent`, `--reel-on-accent` | The one highlight colour, and text on it | `#FFB000`, `#0F3D2E` |
| `--reel-muted`, `--reel-surface` | Secondary text; cards and panels | white at 70%, `#0A2A20` |
| `--reel-font-display`, `--reel-weight-display` | Titles | Inter, 800 |
| `--reel-font-body`, `--reel-weight-body` | Captions and body | Inter, 500 |
| `--reel-font-label`, `--reel-weight-label` | Numbers, tags, labels | Inter, 700 |
| `--reel-ease-enter`, `--reel-ease-exit`, `--reel-ease-move` | `cubic-bezier(...)` curves | see section 5 |
| `--reel-dur-enter`, `--reel-dur-exit`, `--reel-dur-move` | Seconds, as plain numbers | `0.5`, `0.35`, `0.7` |
| `--reel-energy` | `calm`, `steady` or `punchy`: formats scale accents and cut density by it | `steady` |
| `--reel-radius`, `--reel-line` | Corner radius; stroke width for lines and underlines | `8px`, `8px` |

Optional: `--reel-bg-image` (a gradient over `--reel-bg`), `--reel-display-case` (`uppercase` or `none`),
`--reel-display-leading` (line height for the display face).

The pack's `brand-snippets.js` must also set `window.REEL_BRAND`:

```js
window.REEL_BRAND = {
  name: "Acme",
  logo: { onDark: "assets/brand/logo/acme-logo-on-dark.svg", onLight: "assets/brand/logo/acme-logo.svg" },
  motif: { kind: "shape", svg: "<svg ...>...</svg>" },   // kind: "shape" or "line"
  never: ["gradients on the logo", "more than one accent colour per scene"],
};
```

The bridge also writes `reel-tokens.js` into the project: `REEL.ease("enter")` turns the pack's curve into a GSAP
ease (with CustomEase when loaded), `REEL.dur("move")` gives seconds, `REEL.energy` the energy word.

## 4. Making a pack

- **The brand has a kit** (a skill with colours, fonts, logos): write `kit-to-clip/` next to it, starting from section 5.
  Propose the motif and motion values, render sample stills, get approval, then set `status: approved`. The
  front door's brand onboarding (`references/brand-onboarding.md`) walks through it with the person.
- **The repo has no brand yet**: the quick brand builder (planned) makes a small provisional kit and pack from a
  reference or a brainstorm. Take a reference's principles, never its marks.
- Check it: `python3 <kit-to-clip>/brand/scripts/bridge.py --list --project <dir>` must list the brand, and a neutral format
  must build and pass `finish.py check` and `finish.py safe` with it.
- **The brand has its own formats** (a signature edit only it uses): add `"formats": "formats"` to `pack.json` and a
  folder per format under `kit-to-clip/formats/` (see `formats/README.md`). They appear in the front door for that brand only.

## 5. A minimal pack (Acme)

```
acme-brand/                       the brand kit (a skill in the brand's repository)
  assets/fonts/Inter-*.ttf, OFL.txt
  assets/logo/acme-logo.svg, acme-logo-on-dark.svg
  kit-to-clip/
    pack.json
    templates/brand.css
    templates/brand-snippets.js
    guide.md
```

`kit-to-clip/pack.json` (`copy` maps project paths to kit paths):

```json
{
 "schema": 1, "brand": "acme", "name": "Acme", "version": "1", "status": "provisional", "contract": 1,
 "copy": {
  "assets/fonts/Inter-Variable.ttf": "assets/fonts/Inter-Variable.ttf",
  "assets/fonts/Inter-OFL.txt": "assets/fonts/OFL.txt",
  "assets/brand/logo/acme-logo.svg": "assets/logo/acme-logo.svg",
  "assets/brand/logo/acme-logo-on-dark.svg": "assets/logo/acme-logo-on-dark.svg"
 },
 "templates": {"brand.css": "templates/brand.css", "brand-snippets.js": "templates/brand-snippets.js"},
 "guide": "guide.md"
}
```

`kit-to-clip/templates/brand.css` (the bridge copies the kit files first, so `url()` can point at their project paths):

```css
@font-face { font-family: "Inter"; src: url("assets/fonts/Inter-Variable.ttf"); font-weight: 100 900; }
:root {
  --reel-bg: #0F3D2E; --reel-fg: #FFFFFF; --reel-accent: #FFB000; --reel-on-accent: #0F3D2E;
  --reel-muted: rgba(255, 255, 255, .7); --reel-surface: #0A2A20;
  --reel-font-display: "Inter", sans-serif; --reel-weight-display: 800;
  --reel-font-body: "Inter", sans-serif; --reel-weight-body: 500;
  --reel-font-label: "Inter", sans-serif; --reel-weight-label: 700;
  --reel-ease-enter: cubic-bezier(0.22, 1, 0.36, 1); --reel-ease-exit: cubic-bezier(0.64, 0, 0.78, 0);
  --reel-ease-move: cubic-bezier(0.65, 0, 0.35, 1); --reel-dur-enter: 0.5; --reel-dur-exit: 0.35; --reel-dur-move: 0.7;
  --reel-energy: steady; --reel-radius: 8px; --reel-line: 8px;
}
```

`kit-to-clip/templates/brand-snippets.js` sets `window.REEL_BRAND` as in section 3. `kit-to-clip/guide.md` says which kit
references to read and what the brand never allows. Add `templates/frame.md` (HyperFrames' design file) and a
`pack.py` builder when the brand needs them; `{{placeholders}}` in templates are filled from `values` in
`pack.json` or from `build(ctx)`.
