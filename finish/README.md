# Finish module: checks and delivery

Part of the kit-to-clip skill; `SKILL.md` covers setup (env.sh, the HyperFrames skills) and when to come here.

A render that plays is not a finished video. An early branded test rendered cleanly and still shipped a mix at
-19.6 LUFS, files too large for a phone upload, a first frame showing an empty card, and a script bug that
silently froze every animation while lint reported zero errors. This module closes those gaps with measured checks
on the real output file. It adds to the HyperFrames workflow and never replaces a HyperFrames step.

## 1. Ask where it goes, before building

If the user hasn't named the destination, ask. One video can have several destinations; different aspect ratios
are different cuts, not one render stretched or auto-cropped.

```bash
python3 <kit-to-clip>/finish/scripts/finish.py plan --profile tiktok,instagram-feed --project <project-dir>
```

This writes `platform.json` and `platform.css` (canvas size and safe-area CSS variables per destination). Keep
titles, captions, logos and key action inside the safe area. Profiles live in `profiles.json`; their safe areas
are heuristics, not published platform specs, so tell the user to check the real upload preview. If a destination
has no profile, ask for its canvas and interface areas rather than guessing, and add a profile once confirmed.

## 2. Check the composition before rendering

```bash
python3 <kit-to-clip>/finish/scripts/finish.py check --project <project-dir>
```

It loads the composition in headless Chrome the way HyperFrames renders it, sub-compositions included, and seeks
through the whole timeline. It fails on script errors in `index.html` or any sub-composition, console errors, files
missing from the project, requests that leave this machine, a sub-composition that does not load, a root timeline
that never registers, zero duration, and errors while seeking, including errors the HyperFrames runtime catches and
hides. Its pass line gives the real duration and the number of sub-compositions loaded. Run it after
`hyperframes lint`, because lint reads the source text and cannot see a script that dies at load (for example a
top-level `const top` in `index.html`). `npx hyperframes check` covers layout and contrast; this check adds remote
requests and hidden seek errors, which `hyperframes check` passes.

Then check the safe area for each destination:

```bash
python3 <kit-to-clip>/finish/scripts/finish.py safe --project <project-dir> --platform tiktok   # or instagram, or x0,y0,x1,y1
```

It steps through the whole timeline and fails when visible text or a logo leaves the destination's safe box. Mark an
element `data-safe-ignore` only when leaving the box is intended, for example a number that slides out of frame
during a camera move, and say so in the report.

**Pitfall: a safe check that measured nothing is not a pass.** HyperFrames loads sub-compositions
(`data-composition-src`) with its runtime, over http. A page opened straight from disk without the runtime never
loads them. An earlier version of this check did exactly that on a film built from sub-compositions (28 Sep 2026):
it measured 0 elements over 0.0 s and still printed a pass. `check` had the same gap: it reported that 64 s film as
a clean 0.00 s. Both checks now serve the project on localhost with the HyperFrames runtime and seek with the
player, the way the renderer does. The safe check fails when the player never gets
ready, the root timeline is missing, a sub-composition does not load, the page throws a script error, the duration
is zero, or no text or logo is visible at any sampled time. Before you report a pass, read its numbers (elements,
seconds, sub-compositions) and compare them with the video you built. If a video has no text or logo at all, report
the safe check as not applicable, not as passed.

**Pitfall: text sized before its font has loaded.** A fit-to-width script that runs at load measures the fallback font,
finds the headline fits, and never shrinks it; when the brand font arrives the line is wider and leaves the safe box
(a headline ran 7 to 11 px outside the Instagram box this way, 29 Sep 2026, and only `safe` caught it). Size text
after `await document.fonts.ready`, or set the font size explicitly instead of fitting it.

## 2b. The first three seconds, and scenes tied to music or voice

```bash
python3 <kit-to-clip>/finish/scripts/finish.py hook --project <project-dir> [--by 3]
python3 <kit-to-clip>/finish/scripts/finish.py anchors --project <project-dir> [--bpm 120 | --beats beats/<audio>.json] [--words transcript.json]
```

`hook` fails when the first frame shows only background, when no readable text or logo is on screen by `--by`
seconds (people scroll with the sound off), or when nothing moves in the first second.

`anchors` checks that scenes really land on the music or the voice. Mark an element with `data-anchor` ("beat:8",
"word:launch", "word:launch#2", "t:3.5"): beats from `hyperframes beats` (or `--bpm`), words from `hyperframes
transcribe`. It loads the composition the way the renderer does, steps through every frame and reads **when the element
really starts moving, or comes to rest** (a move that ends on the beat counts, as a hit does). What `data-start` or
`data-at` claim is only shown next to it: a tween placed 0.2 s after its declared time fails. The window is
**-0.034 to +0.045 s** (one frame early to a little late), for hits. An element marked `data-anchor-scope="scene"` gets
-0.2 to +1.8 s (a scene may follow its beat by a moment); `--window` and `--scene-window` change them. It fails on
drift, on an element that never moves or fades in, on an anchor it cannot resolve, or when nothing is anchored.
Motion while an element is hidden (a headline parked inside a text mask) does not count. Put the anchor on the element
that moves: a still container around moving children has nothing to measure.

## 3. Render, then finish the real file

Render with HyperFrames as usual (`npx hyperframes render -o <file>`). Then:

```bash
python3 <kit-to-clip>/finish/scripts/finish.py finish <render.mp4> --profile tiktok --out <deliver-dir> --name <slug> [--cover-at 12.5]
```

Per destination it writes:

| Output | What and why |
|---|---|
| `-master.mp4` | Video stream copied when possible (no quality loss); audio mastered to -14 LUFS with true peak at or below -1 dBTP: gain, a 4x-oversampled limiter, then correction on the encoded file until both are in. The report states the loudness range and warns above 11 LU |
| `-share.mp4` | Re-encoded until it fits the 30 MB cap for phone/chat uploads |
| `-cover.png` | Frame at `--cover-at` (default 40% in). Choose a moment with the subject and title readable |
| `-contact.png` | One frame per second from the finished master |
| `-safe-check.png` | Cover with the destination's unsafe areas tinted red |
| `.report.json` | Every measured number and pass/fail |
| `-share.gif` | `gif` profile only: 15 fps, loops forever, stepped down in width until it fits the size cap |

It also checks what only the encoded file shows. A first frame of one flat colour fails (the video opens on
nothing; pass `--allow-flat-open` only when that is intended, such as a fade from black). A black flash under
0.5 s fails. For looping destinations (`website-loop`, `gif`) the jump from the last frame back to the first may be
at most twice the usual change between neighbouring frames, or the loop visibly jumps. Long black holds and
freezes of 2.5 s or more mid-video are listed as warnings: holds are often intended, so decide and say why.

**Flash guard (WCAG 2.3.1).** Every `finish` and `loop` run also fails when any part of the picture about a quarter of
the central field of view flashes more than 3 times in one second (general or saturated-red flashes): fast full-frame
cuts between dark and bright, strobing hits. `finish.py flash <render>` runs it alone. Fix it by slowing the cuts,
softening the brightness change or shrinking the flashing area. It's a screening aid: paid UK or EU broadcast still
needs a certified test (Harding). Calibrated 2026-10-08 on real beat-cut sports highlights: they peaked at 1 to 2 flashes a second.

A render **with sound** is refused unless the sound was checked against the picture (section 3a), or you say why it
was not: `--no-sync "footage's own sound"` for a clip that keeps its original audio. The reason is printed and recorded
in the report.

Exit code 1 means a check failed; the printed line names it. A canvas mismatch is reported as needing a
recomposed cut. Do not "fix" it by stretching or cropping the finished render.

## 3a. Sound: does it follow the picture?

A video whose sound was made for its picture (music, effects, a score) must prove the sound lands on the picture.
Every other check passed a Reel whose sound and picture matched at 0.06, which is chance. Build sound-first (the sound
module, `sound/README.md`), then check the finished file:

```bash
python3 <kit-to-clip>/finish/scripts/finish.py sync <render.mp4> --cues <cue-sheet.json>
```

The cue sheet lists each picture moment the sound is meant to hit: `[{"cue": "chip 1 locks", "picture_t": 4.6875,
"sound_t": 4.6567}]` (`sound_t` is optional). `sync` measures the **encoded file**: for each cue it takes the strongest
sound onset within -100 to +150 ms of the picture time and passes it between **-33 ms (one frame late) and +45 ms
(early)**. People notice sound ahead of the picture from about 45 ms and behind it from about 125 ms (ITU-R BT.1359,
the widely quoted values; the standard itself was not opened). It prints every cue's offset, fails on a cue with no
sound near it, and writes `<render>.sync.json` next to the render, which `finish` then reads. `finish --cues` runs it
inline; a report for an older version of the render is refused.

What it does not tell you: it takes the strongest onset near the cue, so a loud music hit on the beat can carry a cue
whose effect is missing, and a loud sound near a soft hit can win. It catches sound that is absent or off the picture;
it cannot say which sound it heard, or whether the sound is good. The whole-file figure (picture changes against sound
onsets, near 0 for sound that ignores the picture) is reported, with no pass mark. Only the person can approve the
sound: never call it verified before they have listened.

Before the render, check what HyperFrames will do to the mix:

```bash
python3 <kit-to-clip>/finish/scripts/finish.py audio <mix.wav>
```

HyperFrames encodes the mix to AAC more than once, measures the true peak, and turns the whole track down when it is
over -1 dBFS (to -1.5). Two Reels lost 2.9 dB and 1.2 dB that way. `audio` predicts it (within about 0.3 dB on those
two); limit the mix at -3 dBTP and the render leaves the level alone (measured: -0.1 and -0.2 dB). `finish` masters
every delivery again, so this only decides the level `finish` starts from.

## 3b. Loops, loaders and GIFs

```bash
python3 <kit-to-clip>/finish/scripts/finish.py loop <render> --out <dir> --export gif,mp4,webm[,mov,apng,webp] --gif-profile linkedin-gif
python3 <kit-to-clip>/finish/scripts/finish.py snippet --project <project-dir> --out <dir>
```

`loop` checks the seam, then exports from one render; a transparent MOV or WebM keeps its alpha in every export. The
GIF uses one palette, position-fixed dithering and changed-rectangle frames, lowers the frame rate to meet a frame cap
and steps the width down to meet the size cap. Profile `linkedin-gif`: 5 MB and 250 frames (LinkedIn Help a426534).
`snippet` makes a live HTML version for websites, checked in Chrome (plays, loops, holds still for reduced motion).
The loops module (`loops/README.md`) has the method.

## 4. Look before you deliver

Open the contact sheet and the safe-check image and actually look: first and last frames (an empty first
frame is a common miss), text overflow, overlays covering earlier frames, captions inside the red zones, logo
placement. Snapshots taken during authoring do not replace this; the finished file is what the viewer sees.

## 5. Report plainly

State per destination: canvas, duration, loudness and true peak, master and share sizes, and anything that failed
or was not checked (for example "safe areas are heuristics; check the upload preview"). Mention consent when real
people appear, and never post or upload anything without the user's explicit go-ahead.

## Notes

- Muted autoplay loops (`website-loop`) are finished without audio.
- Source footage with sparse keyframes makes HyperFrames freeze or skip frames. If the render log warns about
  it, re-encode the source with `ffmpeg -i in.mp4 -c:v libx264 -crf 12 -g 30 -keyint_min 30 -c:a copy out.mp4` and render again.
- Needs ffmpeg/ffprobe. `sync` and `audio` also need numpy (the engine's Python has it: source `scripts/env.sh`). `check`, `safe`, `anchors`, `hook` and `trace` also need node, puppeteer-core and the hyperframes package, which a
  HyperFrames install already has. They look in node_modules in or above the project, then in the engine studio
  (`$REEL_STUDIO`, `$REEL_STUDIO_HOME`, the studio the skills came from, or `~/.kit-to-clip`), so a project outside
  the studio folder is still checked.
