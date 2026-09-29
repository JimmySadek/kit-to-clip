# Sound module: videos with music and sound effects

Part of the kit-to-clip skill; `SKILL.md` covers setup and when to come here. Use it for any video that has sound
made for its picture: a Reel with a score, effects on the moves, a teaser with a soundtrack. A clip that only keeps
its own original audio does not need this (finish it with `--no-sync "footage's own sound"`).

```
✋ what and where ─▶ ✋ music source ─▶ tempo and bars ─▶ picture on the beats ─▶ motion trace ─▶ effects from motion
      ─▶ ✋ stills ─▶ render ─▶ audio preflight ─▶ sync check ─▶ ✋ you listen ─▶ polish ─▶ finish ─▶ deliver
```

**Never build the picture first and add sound afterwards.** A 15 s Instagram Reel was built that way (29 Sep 2026): it
passed every check, and the person rejected it, "the audio and the visuals are not flowing together at all". Measured
on the file, picture changes and sound hits matched at 0.06, which is chance. The same agent had just made an approved
GIF by following the loops module step by step. Rebuilt sound-first, 13 of 13 picture moments had their sound within a
frame, and the person said "flows now". The order below is the fix. It is a hard gate: no picture is built before
steps 1 to 3 are done.

## 1. The music source (✋, first question)

Ask before anything else, with options named for this video (offer every row that can work; the music maker needs nothing installed beyond the engine):

| Option | What it needs |
|---|---|
| They supply a track | the file. Get its beats: `npx hyperframes beats <file>` (the HyperFrames `music-to-video` workflow builds on it) |
| Music from the library | the HyperFrames `media-use` music search, which **needs the HeyGen login**. Say so now, before any build, and ask for the login (`media-use resolve --doctor` shows whether it is there) |
| No music, effects only | the effects still need a tempo to sit on: pick one in step 2 and say the video has no music |
| Music made offline | the built-in music maker: four styles, any key, no login and no licence (section "Music made offline"). An option, never a requirement |

Some destinations limit music. `finish.py plan --profile <p>` prints the destination's sound facts: for Instagram, its
licensed music is for personal, non-commercial use and some business accounts cannot use it, so a brand Reel uses its
own music and effects (made or licensed for commercial use, baked into the file) or the Meta Sound Collection.

## 2. Tempo, bars and sections

Choose the tempo so the video is **whole bars**: length = bars x 4 x 60 / bpm. 15 s is 8 bars at 128 bpm; 12 s is
6 bars at 120. Write the sections as beat numbers before any picture exists: the hook, the build, the drop (the biggest
moment), the lift, the end. Ask ✋ to confirm the music and the sections (one line each), then keep them: they are the
score the picture is timed to.

## Music made offline (optional)

The kit can make original music itself: no track to find, no login, no licence, and the music is timed to whole bars
and beats before any picture exists. It is synthesised, so think of it as a good bed, not a produced record, and
**you cannot hear it**: the person's ear decides.

| Style | Tempo, key | What it is |
|---|---|---|
| `pulse` | 128 bpm, A minor | energetic electronic: a heartbeat, a rising build, a four-on-the-floor drop with an arpeggio |
| `calm` | 90 bpm, D major | calm ambient: a slow pad that opens, a soft bell arpeggio, a low drone, a gentle pulse at the drop |
| `uplift` | 118 bpm, G major | bright and positive: piano-like chord stabs, a light kick and claps, an airy arpeggio |
| `cinematic` | 76 bpm, D minor | slow and big: a low drone and strings, drum hits, one long crescendo, a huge final hit |

```bash
python3 <kit-to-clip>/sound/scripts/score.py preview --out sound/previews        # 4 short previews to listen to
python3 <kit-to-clip>/sound/scripts/score.py make --style calm --bpm 100 --key "F major" --bars 8 --out sound/
python3 <kit-to-clip>/sound/scripts/score.py mix sound/music.wav sound/sfx.wav --out sound/mix.wav
```

Ask ✋ which style, after the person has listened to the previews (send them the files; do not describe them as good).
Any key (`--key "C# minor"`), any tempo from 60 to 200, and the chords (`--progression 1,6,7,3`, scale degrees) can be
set; `--seed` gives a different take. The structure is always four sections, hook, build, drop and end (the last is one
bar: a final hit and its tail); `--sections hook:2,build:2,drop:3,end:1` changes their lengths. **Choose the length as
whole bars:** the video is exactly `bars x 4 beats`.

`make` writes `music.wav` and **`score.json`**, the one source of timing: tempo, key, chords, the section beats, and the
`cues` (`hook`, `build`, `drop`, `end`) in beats. Beat `n` is at `n x 60 / bpm` seconds. Put the picture's big moments on
those beats (step 3): the drop is the biggest one. Every tonal note is built from the key's scale and checked; a note
outside the key stops the build. The music is at -18 LUFS with true peak under -3 dBTP, which leaves room for the effects.
`mix` sums music and effects, sets the level and limits true peak at -3 dBTP, so the render does not turn it down.
`score.py analyze <file>` reports length, loudness, peak, how busy, how bright and how much bass a file has.

Checking the effects on their own: over drum-driven music (`pulse`, `uplift`) the music's own kick lands on the beat, and
`sync` takes the strongest sound near each cue, so it may hear the kick instead of the effect. To check the effects
alone, run `sync` on a copy of the render whose sound is `sfx.wav` only. `calm` and `cinematic` leave the effects
clearer. A picture that visibly stops well before its beat (a long ease-out) also shows up here: the effect follows the
picture, the music follows the beat, and the gap is real. End the move on the beat or shorten the ease.

## 3. Picture on the beats

Time every tween to a beat (`beat time = beat x 60 / bpm`) and mark the element that hits with `data-anchor="beat:N"`.
Then:

```bash
python3 <kit-to-clip>/finish/scripts/finish.py anchors --project <dir> --bpm 128
```

It reads when each element really starts moving or comes to rest on the running timeline and fails when one is off its
beat (window -0.034 to +0.045 s). Fix the timeline, not the attribute.

## 4. Effects from the motion

Every sound needs a visible cause. Do not place effects by hand against a clock: trace the real motion, then make the
effects from it.

```bash
node <kit-to-clip>/finish/scripts/trace.mjs <project-dir> --out motion.json       # elements with data-anchor or data-track
python3 <kit-to-clip>/sound/scripts/effects.py motion.json plan.json --out sound/
```

`trace.mjs` records each marked element's centre, size, opacity and how much of it a viewer can see, every frame. Add
`data-track="name"` to an element that moves but has no anchor. The visible part matters: a headline parked inside a
text mask jumps between two hidden positions, which would read as thousands of px/s of motion.

`plan.json` says which elements get which sound:

```json
{ "key": "A minor",
  "whoosh": [ { "ids": ["chip1", "chip2"], "gain": 0.2, "vref": 2500 } ],
  "hits":   [ { "id": "chip1", "at": 4.6875, "kind": "note", "note": 69, "gain": 0.55, "cue": "chip 1 locks" } ] }
```

- **whoosh:** loudness and brightness follow the element's visible speed (moving and resizing), pan follows where it
  is, and it leads the picture by 15 ms. `vref` is the speed that counts as full loudness (default: its own fastest move).
- **hits:** a sound on the frame the element comes to rest near the scored beat `at`, 10 ms early. `kind`: `note` (a
  plucked note with a bell an octave up), `boom` (a low tuned drop), `thump` and `tick` (untuned), `file` (a library
  effect). A hit that lands when the element is still moving is reported: fix the picture and trace again.
- **One key.** With `"key"` set, a `note` or `boom` outside it is refused and a library effect is checked. Never
  pitch-shift a library effect to make it fit: make a `note` in key. To see which notes the library effects hold:
  `python3 <kit-to-clip>/sound/scripts/pitch.py check --key "A minor" <effects>`; `sound/sfx-pitch.json` lists the
  measured note of each media-use effect (most are noise-like and fit any key; sparkle holds G, chime A, ping D).
- Fewer, meaningful sounds beat many: a scored hit for each picture moment plus the whooshes. 36 effects in 15 s felt
  busy and cheap.

`effects.py` writes `sfx.wav`, a cue sheet, and warnings. Mix `sfx.wav` with the music into one `mix.wav` (`score.py mix` does it and limits the peaks).

## 5. Stills, render, preflight, sync

1. ✋ Show the stills and the plan (a cue list and the tempo), then ask before rendering, as everywhere in this kit.
2. `python3 <kit-to-clip>/finish/scripts/finish.py audio mix.wav`: HyperFrames turns a mix down when its peaks are hot.
   Limit the mix at -3 dBTP and it arrives at the level you set.
3. Render, then check the file:
   `python3 <kit-to-clip>/finish/scripts/finish.py sync renders/<job>.mp4 --cues sound/cue-sheet.json`. Every cue must
   pass. It is a measure of timing, not of taste (`finish/README.md`, section 3a, says what it cannot tell you).

## 6. The listening checkpoint (✋)

You cannot hear. Measurements support the person's ear, they do not replace it. Before any polish:

> The sound is **unheard by me**. I can measure that each hit lands within a frame of its picture moment, but I cannot
> hear whether it feels right. Please listen on your phone with the sound on and tell me what feels off.

Every handoff about a video with sound says "unheard by the agent" until the person has listened, and never calls the
sound "verified" or "checked" on the strength of the sync numbers alone. Then polish, and finish:

```bash
python3 <kit-to-clip>/finish/scripts/finish.py finish renders/<job>.mp4 --profile instagram-reels --out <deliveries> --cues sound/cue-sheet.json
```

## Tools

| Tool | What it does |
|---|---|
| `finish/scripts/trace.mjs` | how each marked element moves and how much of it is visible, every frame (`motion.json`) |
| `sound/scripts/effects.py` | whooshes and hits from `motion.json` and a plan; writes `sfx.wav` and a cue sheet |
| `sound/scripts/pitch.py` | the note of an effect (`measure`, `index`, `check --key`) |
| `sound/scripts/score.py` | music made offline in four styles: `styles`, `preview`, `make` (music and `score.json`), `mix`, `analyze` |
| `finish/scripts/finish.py anchors` | picture lands on its beat, read from the running timeline |
| `finish/scripts/finish.py audio` | what the render will do to the mix's level |
| `finish/scripts/finish.py sync` | each cue's sound lands within a frame of its picture, on the encoded file |
