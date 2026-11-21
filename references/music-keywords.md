# Music keywords and cues (⑤ Music room)

Read when a film needs music in the Studio's ⑤ Music room. Music is chosen **after the picture is built**, by ear, on
the actual picture at matched loudness (−18 LUFS). Claude never picks a take for the person.

## 1. One cue per story world

Look at the style map and story flips. Each distinct world or mood flip gets its own cue in `film.json` under
`music.cues` (keyed by style id when cues follow style worlds, or by custom cue id with explicit `spans: [[from, to]]`
for a single-style film with a before/after turn):

- A "before vs. after" film often has two cues: e.g., a tense 60 BPM street-traffic cue for the problem, then an upbeat
  120 BPM local festival cue entering on the reveal.
- When a style returns later in the film, its cue returns too (the ribbon and cue map mark it as returning).
- Record exact cue-sheet hits in `hits` (stops, stamps, reveals, logo chord) measured from the built player.

## 2. Hyper-local keywords in 5 layers

Generic mood prompts ("upbeat", "world music", "inspirational") drift toward stock clichés or the wrong region. Write
each cue's keywords in **5 layers**, and show every keyword to the person in Room ⑤ Music with a short reason why
("These are the keywords we suggest, and why"):

| Layer | What it anchors | Example (Cairo street film) | Example (1940s archive film) |
|---|---|---|---|
| **Place and people** | Region, city, era, setting | `Egyptian`, `Cairo` | `1940s newsreel`, `late-night city office` |
| **Local genre** | The exact native genre | `shaabi` | `film noir jazz underscore` |
| **Local instruments** | Instruments by their local names | `accordion`, `oud`, `qanun`, `darbuka`, `riq` | `muted trumpet`, `upright bass`, `brushed snare`, `vibraphone` |
| **Rhythm and scale** | Groove, meter, BPM, modal scale | `maqsum rhythm`, `maqam Hijaz` | `slow swing at 77 BPM`, `minor key` |
| **Scene energy** | What is happening on screen | `street festival energy`, `traffic jam tension` | `waiting-room tension`, `ticking clock` |

Never name an artist, composer, or real song (ACE-Step's notice: generated music can echo real songs).

## 3. Words to avoid (cultural-drift check)

Before generating takes, check every instrument and genre word with one question: **"Which culture or cliché does this
word pull the model toward first?"**

Put misleading words in `music.avoid` as `[word, reason]` so the person sees them and `studio/music.py` strips them if
they slip back into a chip:

- `tabla` → pulls toward Indian percussion instead of Arabic `darbuka` / `riq`.
- `smooth jazz` → pulls toward hotel lounge instead of tense noir underscore.
- `lo-fi` → pulls toward study-beats hip hop and vinyl crackle loops.
- `epic` → pulls toward trailer drums and choirs.
- `corporate` → pulls toward stock ukulele and hand claps.

Treat this check as a creative judgement to test by ear, not a proven automatic filter.

## 4. Audition on the picture, pick by ear, extend

1. Write the 5-layer keywords, `bpm`, `key`, `hits` and `avoid` list into `film.json` `music`. Let the person edit,
   delete or add any chip in Room ⑤ Music.
2. Once the picture is rendered (`studio/render.py` -> `.studio/results/render/picture.mp4`), generate 3 clearly
   different takes per cue at matched loudness (−18 LUFS) placed directly on the cue's slice of the picture:
   ```bash
   source <kit-to-clip>/scripts/env.sh
   python3 <kit-to-clip>/studio/music.py audition <video-folder>
   ```
   (`music.py audition` uses ACE-Step and never falls back to the built-in synth silently; if ACE-Step is not installed,
   stop and offer to install it. Pass `--engine score` only if the person explicitly asks for a temporary synth guide
   track. Every take in Room ⑤ Music shows which engine made it. `--cue <id>` redoes one cue only.)
3. Tell the person the takes are ready in Room ⑤ Music and are **unheard by you**. Ask for the ✋ music pick:
   `studio.py ask <video-folder> music "music pick v1"`.
4. If none fits, read their note in `music.cues.<id>.wrong` (e.g., "too slow", "too much percussion"), update the
   keywords and `avoid` list, explain what changed, and run a new audition round. A new round automatically clears that
   cue's previous pick and reopens any prior ✋ music yes so the person must hear the new takes before picking or approving.
5. Once the person picks a take per cue (`pick`), extend and stitch those exact takes across the full film (never
   generating a brand-new song):
   ```bash
   python3 <kit-to-clip>/studio/music.py assemble <video-folder>
   ```
   This writes `.studio/results/music/score-full.wav`, which `studio/mix.py` ducks 12–15 LU under the voice and masters
   at −14 LUFS for the final watch in Room ⑥ Finish.
