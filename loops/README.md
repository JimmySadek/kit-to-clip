# Loops module: seamless loops and loaders

Part of the kit-to-clip skill; `SKILL.md` covers setup and when to come here. Use it for animated GIFs (a LinkedIn
teaser, an email header), website and app loops, loaders, and "make this still move".

```
✋ what and where ─▶ ✋ the brief ─▶ ✋ 3 motion ideas as stills ─▶ build ─▶ checks ─▶ ✋ stills ─▶ render ─▶ exports ─▶ deliver
```

**Never skip the brief and the motion ideas.** The first real loop (a LinkedIn teaser, 28 Sep 2026) was built straight
from the still, with the motion chosen by the agent and the reference matched pixel by pixel: it was faithful and
rejected as too subtle, the wrong kind of motion, and not the real brief. Fidelity to the still is the floor, not the
goal.

## 1. Ask what and where (✋, one question each)

| Destination | Canvas | Export | Limits |
|---|---|---|---|
| LinkedIn feed post or single-image ad | 1:1 (1080 or 1200) or 4:5 | GIF, profile `linkedin-gif` | 5 MB, 250 frames (LinkedIn Help a426534) |
| Chat, docs, email | any | GIF, profile `gif` | about 8 MB |
| Website or app hero | the slot's size | MP4 + WebM in a `<video autoplay muted loop playsinline>`, or the live snippet | keep it light; `embed_html` in the report |
| Loader or overlay on any background | small, transparent | WebM (alpha), APNG, animated WebP, MOV (ProRes 4444) | render with `--format mov` so the alpha survives |

Lottie is not supported: HyperFrames draws with HTML and GSAP, and nothing converts that to Lottie reliably. Say so
and offer WebM, APNG or the snippet.

## 1b. The brief, then three motion ideas (✋ each)

Ask, one question each, with options named for this piece: **what the loop must do** (stop the scroll, explain the
product, announce), **what should move** (the words, the product or screen, the brand art, the story from A to B),
and **how much** (calm, lively, bold). Then propose **three genuinely different motion ideas** (one close to the still,
one bolder, one unexpected), each as 2 or 3 stills from a quick build plus one line on what moves and when, and let the
person pick or mix. Motion must be visible at phone size in the feed: if a change is only clear when you compare
frames, it is too subtle.

## 2. Pick a loop format

`python3 <kit-to-clip>/formats/scripts/formats.py list --made-for loop --project . --all` lists them. Today:

| Format | Status | What it is |
|---|---|---|
| `formats/neutral/teaser-loop/` | draft | a still teaser brought to life: opens on the finished layout, background wave or breathe, accent ring, accent line; see its README |

A brand's pack can add its own loop formats (`made_for: loop`).

## 3. The loop method (for any loop you build)

- **Everything periodic.** Drive every moving part from one loop clock `p` in [0, 1): positions with `sin(2πp)`,
  pulses with whole cycles per loop, draws that finish and clear before the end. Frame L must equal frame 0.
- **Open on the finished picture** for posts and ads: the first frame is the thumbnail and the still people see before
  autoplay. For a loader, open on its rest state.
- **Design for the medium.** A GIF stores only changed pixels: keep large areas still and move small ones (a band, a
  line, a ring); full-frame motion belongs in MP4 or WebM.
- **Reduced motion:** the live snippet holds still on `data-rest-at` of the root (seconds), else the last frame.
- **Real assets:** backgrounds, devices and screens come from the brand's own files (`brand/scripts/assets.py`).

## 4. Checks and exports

```bash
python3 <kit-to-clip>/finish/scripts/finish.py hook --project <dir>          # first frame, readable muted, moves at once
npx hyperframes render -o renders/<job>.mp4 --quality delivery              # or --format mov for transparency
python3 <kit-to-clip>/finish/scripts/finish.py loop renders/<job>.mp4 --out <deliveries>/<job>/<platform> \
        --export gif,mp4,webm --gif-profile linkedin-gif
python3 <kit-to-clip>/finish/scripts/finish.py snippet --project <dir> --out <deliveries>/<job>/web   # live HTML
```

`loop` fails when the seam jumps (last frame vs first, against neighbouring frames), when a GIF breaks its profile's
size or frame cap (it lowers the frame rate to fit a frame cap, then steps the width down to fit the size), or when an
encoder is missing (animated WebP needs `img2webp`, installed by setup). It writes a poster PNG and `report.json`
with an `embed_html` line for the web. `snippet` works for single-file compositions and is checked in Chrome: it must
play, loop and hold still for reduced motion.
