# Explainer (neutral format, trial)

A narrated explainer: **the voice comes first** and the picture follows it. Every scene starts on the first word of its
sentence, and `finish.py anchors` proves it. Captions are burned in, with the spoken word highlighted, because most
feed video plays muted. The look comes from one of nine illustration styles drawn in the brand's tokens. It needs a
brand pack with token contract v1.

```
✋ script ─▶ voice ─▶ word timings ─▶ ✋ storyboard (style + scenes) ─▶ build ─▶ checks ─▶ (✋ music pick) ─▶ render ─▶ ✋ final film ─▶ deliver
```

## 1. The script (✋)
- **Write it with the person:** 3 to 6 short sentences, one idea each, about 2 to 3 words a second. That is roughly
  20 to 30 s for a social post.
- **Use only words and facts the person gave or approved.** No invented numbers.
- **Save it as `script.txt`.** It becomes the spelling of record for the captions.

## 2. The voice
- **Their own recording:** a file they supply. Best for founders' voices.
- **Or the free voice:** the `voice-over` power (`toolbox.py which voice-over`, then `toolbox/recipes/voice.md`):
  ```bash
  HYPERFRAMES_PYTHON="$(python3 <kit-to-clip>/scripts/toolbox.py path kokoro-voice python)" npx hyperframes tts script.txt -v am_michael -o voice.wav
  ```
  Offer two or three voices as a ✋ choice by name and sound ("calm US male", "bright UK female").

## 3. Word timings
```bash
HYPERFRAMES_PARAKEET="$(python3 <kit-to-clip>/scripts/toolbox.py path parakeet cli)" npx hyperframes transcribe voice.wav -d tr
```
The `transcribe` power gives `tr/transcript.json` with each word's start and end. Misheard names ("Padle") are fixed by
`--script` at build time when the words line up one to one. When they don't, the build warns.

## 4. Scenes and style (✋ storyboard)
`scenes.json` holds one scene per sentence, in order:

```json
[{"say": "Padel moves fast", "headline": "Padel moves fast.", "sub": "Every rally is a story."},
 {"say": "Read the rally", "headline": "Read the rally", "sub": "before it happens", "visual": "assets/court.svg"}]
```

- **`say`:** the sentence's first words, exactly as spoken.
- **`headline`:** up to 34 characters.
- **`sub`:** optional, up to 60.
- **`visual`:** optional; the brand's own picture or icon (never a lookalike).

**The nine styles:**

| Style | Look |
|---|---|
| `clean` | only the brand's tokens: an accent ring that draws on |
| `cut-paper` | layered paper shapes, soft shadows, grain, the headline on a paper strip |
| `risograph` | two inks, halftone dots, slight misregistration, print grain |
| `sketchbook` | ruled paper, pencil loops and arrows drawn on, a marker underline |
| `isometric` | blocks on an isometric grid that drop in |
| `glass` | overlapping translucent panes with connected dots, revealed in depth order |
| `pixel` | 16-bit block shapes and stepped paths; brand fonts and supplied images stay untouched |
| `chalkboard` | hand-drawn nodes and arrows in the brand's colours, revealed as strokes |
| `flat-vector` | a simple input, process and output diagram with large solid shapes |

Show the person a still of two or three styles with their own headline, then the storyboard for the pick, and get
the ✋ storyboard yes before building. Remember the pick:
`memory.py prefer --like "sketchbook explainers" --topic format`.

To browse by sight, use the [local style gallery](../../../references/style-gallery.md). It lists all nine looks,
formats and saved styles. A neutral demo is labelled as such; it does not prove an adaptation to the chosen brand.
The new looks are original implementations inspired by the categories in
[Futurepedia's explainer tutorial](https://www.youtube.com/watch?v=Ge1B-Ok1Pfk). No tutorial code or media is bundled.

## 5. Build and check
```bash
python3 <kit-to-clip>/formats/neutral/explainer/build.py --brand <id> --voice voice.wav --transcript tr/transcript.json \
        --script script.txt --scenes scenes.json --style sketchbook --platform tiktok --out <videos>/<job>
npx hyperframes lint                                            # inside the project
python3 <kit-to-clip>/finish/scripts/finish.py check   --project <videos>/<job>
python3 <kit-to-clip>/finish/scripts/finish.py safe    --project <videos>/<job> --platform tiktok
python3 <kit-to-clip>/finish/scripts/finish.py hook    --project <videos>/<job>
python3 <kit-to-clip>/finish/scripts/finish.py anchors --project <videos>/<job>    # every scene on its word
```

All must pass before stills. The first scene's art is on screen from frame 0, and a small logo sits in the corner,
so the video never opens on empty background.

## 6. Stills, music pick, render, final film
- **Stills:** `npx hyperframes snapshot --describe false --at <each scene's start + 1 s>`. Look at every one yourself;
  they are checks, not a separate yes.
- **✋ Music pick**, when the film has music: play the takes on the built picture, let the person pick by ear, then
  run the same build again with `--music <picked take>`.
- **Render, then the ✋ final film:** the voice and any music are unheard by the agent until the person watches and
  hears the finished film. Then finish and deliver (`formats/README.md`, "Deliver"). The voice is made for the picture, so
  pass `--no-sync "narration, scenes anchored to words (finish.py anchors)"`, or a cue sheet when there are effects.

## Tested 2026-10-08
- **Setup:** a 26-word script for a sports brand voiced by Kokoro (`am_michael`, 9.7 s), timed by Parakeet. The captions corrected
  "Padle" to "Padel" from the script.
- **Checks:** all five styles built. On `clean`: lint 0, console ✓, TikTok safe ✓ (36 elements), hook ✓, and anchors
  ✓ (5 scenes within one frame of their words).
- **Render:** the full sketchbook render (11.1 s, 1080x1920) took 14 s, and the flash guard passed

**Status: trial.** It is offered as a new format; the maintainer decides when it becomes approved.
