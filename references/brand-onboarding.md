# Brand onboarding: a brand kit becomes a video pack

Runs once per brand, when `brand.py detect` says `kit`: the repo (or the kit a `reels/brand.json` pointer names)
has a brand kit but no `kit-to-clip/` video pack. The result is a pack saved **into that kit**, so every later video with
this brand starts at the front door's format question. What a pack holds and the token contract it must meet:
`brand/brand-pack.md`.

```
read the source ─▶ brand check ─▶ ✋ 2-3 motion directions ─▶ ✋ choose ─▶ write the pack ─▶ ✋ sample stills ─▶ save
```

Use AskUserQuestion at every ✋, one decision each. Never guess colours, fonts or logos: a plausible guess is worse
than a question.

## 1. Read the brand source

The kit's `SKILL.md` and the references it names; a guideline link or PDF the person gives; or a live website:
capture it and make a brand sheet (`brand/README.md` section 8), which proposes every token with its source and lists
conflicts with the kit. Find the brand's pictures with `assets.py search` and look at all of them with
`assets.py sheet` (section 7). Note the source of every value.

## 2. Brand check

List what exists and what is missing, in the table from `brand-pack.md` section 1:

| Need | Found | Missing or unclear |
|---|---|---|
| Colours with roles (bg, fg, one accent, muted, surface, on-accent) | | |
| Font files with licences (display, body, label) | | |
| Logo files per background (on dark, on light) | | |
| A signature motif (the most reduced shape or line) | | |
| Rules that limit motion (e.g. "calm, precise", reduced motion) | | |
| What may be claimed, what the brand never does | | |

Font rule: guidelines often name licensed fonts without files. Ask for the files, or for the person's OK to use a
clearly marked close free substitute (OFL, with its licence file).

## 3. ✋ Motion directions, then ✋ choose

Shape the directions with `frontend-design` and critique them with `impeccable`; in Quick mode, builder helpers can
sketch more directions first (`references/director-and-builder.md`, sections 2 and 3). The brand's own rules still win.

Propose 2 or 3 directions, each grounded in the brand's own rules, not in another brand's look. For each: a name,
one line on the feeling, the signature device (how the motif moves), the transition, the type entrance, the end
card, the sound mood, the reduced-motion variant and the motion values (`--reel-energy`, easing curves,
durations). Mark a recommendation when the brand's rules point to one.

## 4. Write the pack

Into `<kit>/kit-to-clip/`, with the files in `brand-pack.md` section 2:

- `pack.json`: `schema: 1`, `brand`, `name`, `version: "1"`, `status: "provisional"` until step 5 is approved,
  `contract: 1`, `copy` (fonts, licences and logos from the kit, never redrawn), `templates`, and `hash_indexes`
  when the kit records file hashes.
- `templates/brand.css` with every `--reel-*` token; `templates/brand-snippets.js` with `window.REEL_BRAND` (name,
  logos, motif, `never`); `templates/frame.md` for HyperFrames' design check.
- `guide.md`: which kit references to read, the class names in `brand.css`, and the brand's own rules on screen.
- `pack.py` only for what data can't express (computed text fit, policy-driven asset lists).

Check it: `python3 <kit-to-clip>/brand/scripts/bridge.py --list --project <repo>` must list the brand without "(broken)".

## 5. ✋ Sample stills

Build the neutral brand reel (`formats/neutral/brand-reel/`) with placeholder slots (say so), run the checks,
take stills of 4-6 moments on a dark and a light surface (`npx hyperframes snapshot --describe false`), look at them yourself, then show them. Adjust and repeat, at
most three rounds. Nothing is rendered in this step.

## 6. Save

On approval: set `status: "approved"` (or keep `provisional` and say why), copy the approved stills into
`<kit>/kit-to-clip/approved/`, and add a line to the kit's own README or changelog. Edits after approval are a new
`version`, not a silent change. If the kit lives in its own repository, say which files changed there; committing
or pushing them is the person's call.
