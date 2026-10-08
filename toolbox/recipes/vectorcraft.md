# VectorCraft: logo files to clean SVG, trace, simplify

**Early tool:** the first release was on 30 Sep 2026. Check every result by looking at it.

```bash
VC=$(python3 <kit-to-clip>/scripts/toolbox.py path vectorcraft)
"$VC" info logo.ai                                     # what came in, warnings, fonts, artboards: read this first
"$VC" convert logo.ai logo.svg --outline-text          # .ai .eps .pdf .emf .dxf -> SVG (text as paths: no font needed)
"$VC" convert brochure.pdf mark.svg --artboard 2       # one artboard (0-based) of a multi-page file
"$VC" run --in ink.svg --cmd select.all --cmd object.path.simplify --params '{"tolerance":1.5}' --export ink-smooth.svg
"$VC" run --in logo.png --cmd imageTrace.make --params '{"preset":"<name from imageTrace.presets>"}' --export logo.svg
```

## Uses in Kit to Clip
- **Brand onboarding**, when a kit holds the logo only as `.ai`, `.eps` or `.pdf`: convert it to SVG with
  `--outline-text`, then compare a still of the SVG with the original side by side before using it. A logo is never
  redrawn: if the conversion changes it, say what changed.
- **Before EffectCraft or an SVG draw-on:** hand-drawn polylines (HyperFrames ink, 70+ points per loop) become a few
  smooth curves. Draw-ons look cleaner and stay editable.
- **A PNG-only logo:** image trace gives vector shapes. Only use them with a person's ✋ after they see the trace next to
  the original, because tracing changes edges.

## Tested (0.6.0, 2026-10-08)
- **Simplify:** a 121-point jagged loop became 11 anchors and kept its shape (stills compared). Tolerance 1.5 suits
  ink, while lower values keep more detail.
- **Round trip:** SVG → PDF → SVG kept all 3 paths, colours and stroke caps.
- **`info`** reports import warnings, such as an EPS read only from its preview. Pass them on in plain words.
