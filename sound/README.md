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

Ask before anything else, with options named for this video. **Offer the music generator first: it is the default.**
Offer every row that can work. Kit to Clip is free and local: never offer a source that needs an account, a key or a
payment (the HyperFrames `media-use` library needs a HeyGen login, so it is not used):

| Option | What it needs |
|---|---|
| **An original track from a description (the default, offer it first)** | the `music-generate` power, ACE-Step (`toolbox.py which music-generate`): free, runs on this computer, ✋ before adding it. The first run downloads about 9.4 GB, and each take takes minutes. `ace_takes.py` makes a few takes and readies the best one (step 2) |
| Music made offline (the fallback) | the built-in music maker, `score.py`: no model, ready in seconds, every cue exact to the sample. Four styles, any key, no licence (section "Music made offline"). Use it when the generator is not installed, the person does not want the download or the wait, or no take works |
| They supply a track | the file. Get its beats: add it to the project as the root `<audio>`, then `npx hyperframes beats <project>` writes `beats/<audio>.json` (the HyperFrames `music-to-video` workflow builds on it). For a track outside a project, `python3 <kit-to-clip>/scripts/reference.py beats <file>` reports its tempo and strongest hits (it uses a throwaway project and saves nothing) |
| No music, effects only | the effects still need a tempo to sit on: pick one in step 2 and say the video has no music |

Say two things before the person picks the generator. **Generated music can sound like an existing song by accident**,
so the description names the genre, mood, instruments and tempo, never an artist or a song. And **you cannot hear the
takes**: the person listens to them before any picture is built.

Some destinations limit music. `finish.py plan --profile <p>` prints the destination's sound facts: for Instagram, its
licensed music is for personal, non-commercial use and some business accounts cannot use it, so a brand Reel uses its
own music and effects (made or licensed for commercial use, baked into the file) or the Meta Sound Collection.

## 2. Tempo, bars and sections

Choose the tempo so the video is **whole bars**: length = bars x 4 x 60 / bpm. 15 s is 8 bars at 128 bpm; 12 s is
6 bars at 120. Write the sections as beat numbers before any picture exists: the hook, the build, the drop (the biggest
moment), the lift, the end. Ask ✋ to confirm the music and the sections (one line each), then keep them: they are the
score the picture is timed to.

**With the music generator (the default)**, make the takes once the tempo and sections are confirmed:

```bash
python3 <kit-to-clip>/sound/scripts/ace_takes.py "energetic electronic, punchy drums, synth bass, bright stabs" \
    --bpm 128 --key "A minor" --bars 8 --sections hook:2,build:2,drop:3,end:1 --takes 3 --seed 11 --out sound/
```

A raw take does not keep our timing. Measured on 9 Oct 2026: the beats sat 45 to 160 ms after the grid, the drop
landed where the model chose, endings faded to near silence, the mixes were 80 to 94% bass, and the peaks were hot.
`ace_takes.py` fixes what it can and chooses among the takes for the rest:

- **On the grid:** it finds where each take's beats really are, shifts the take so beat 0 is at 0.000 s, and makes it
  exactly `bars x 4 x 60 / bpm` long.
- **Extra bars, then a cut:** ACE-Step fades out over its last bars, so each take is made `--extra-bars` longer
  (default: 4, or half the bars when that is more) and cut after the target bars. The model's fade falls after the cut,
  and the last half beat fades out so the cut does not click. `--extra-bars 0` keeps the model's own ending.
- **Scored against the sections:** it measures the loudness of every bar. The build should rise, the drop should be
  clearly above the build, the end should not be silent. Tight beats, a hit on the end cue, less bass and peaks that
  need little limiting add points. No hit in the music on the end cue is a note, not a failure: land a recorded hit
  there in the effects plan (step 4). It cannot move the model's drop: it picks the take that follows the plan.
- **The music's own drop:** it also measures where each take really drops (its biggest lift from one bar to the
  next) and writes it to `score.json` (`source.measured_drop_beat`). When a take drops on another beat, `takes.json`
  says so: put the picture's big move where the music drops, not where the plan guessed. A flat build is only a note
  when the drop lands on the planned beat.
- **Ready for the pipeline:** the best take is levelled like `score.py` (-18 LUFS, true peak under -3 dBTP) and
  written as `music.wav` and `score.json` in the same format. Steps 3 to 6 work unchanged.

Every take stays in `sound/takes/`: `take-s<seed>-x<extra>.wav` is the raw take, `take-s<seed>-x<extra>-ready.wav`
is cut, on the grid and levelled. A take is reused only when it was made with the same settings, extra bars included. `sound/takes.json` holds every number and why the winner won. A `warning` there means every take missed a
check: say so, and offer more takes (`--takes 5`), other seeds (`--seed 40`) or `score.py`. ✋ Play the takes to the
person before building the picture. If they prefer another one, the same command with `--pick <seed>` makes it the
music in seconds (the takes are reused). No ACE-Step installed stops with exit 3 and the `score.py` command to use.

Trust `score.json` for the beats. `npx hyperframes beats` reads ACE-Step's beats about 25 ms later than `ace_takes.py`
and `finish.py sync` do: it lands on the low body of the kick, not its attack.

## Music made offline (the fallback)

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

Give each beat a role before timing anything, and say them to the person in plain words: **the reveal** (the
first strong beat: the hero arrives), **the big move** (the next strong beat or the drop: the scale-up, the slam),
**small accents** (the beats between: a tick, a pulse, a word), and **the hold** (the end card rests about two beats).
Big moves only on strong beats; accents never compete with them.

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
  "room": { "wet": 0.22, "decay": 1.1 },
  "whoosh": [ { "ids": ["chip1", "chip2"], "gain": 0.2, "vref": 2500 } ],
  "hits":   [ { "id": "chip1", "at": 4.6875, "kind": "note", "note": 69, "gain": 0.55, "cue": "chip 1 locks" },
              { "id": "chip2", "at": 9.0, "kind": "riser", "length": 1.5, "note": 76, "cue": "chip 2 locks" } ] }
```

- **whoosh:** loudness and brightness follow the element's visible speed (moving and resizing), pan follows where it
  is, and it leads the picture by 15 ms. `vref` is the speed that counts as full loudness (default: its own fastest move).
- **hits:** a sound on the frame the element comes to rest near the scored beat `at`, 10 ms early. `kind`:
  - `note`: a plucked note with a bell an octave up (in key).
  - `boom`: a low tuned drop (in key).
  - `slam`: a big landing. A boom, a thump under it and a soft click on the front. The low end leads (in key).
  - `chime`: a note and a quieter note a perfect fifth above it. Both must be in key.
  - `thump` and `tick`: untuned hits.
  - `file`: a library effect.

  A hit that lands when the element is still moving is reported: fix the picture and trace again.
- **risers:** a swell that builds up to the landing. It is filtered noise and a tone that rises two octaves, and it
  **ends on the frame the element comes to rest**. `length` is in seconds (0.25 to 4.0, default 1.0). `note` is an
  optional target for the tone (in key). Its cue is its end, the landing. A soft tick sits on the landing, so
  `finish sync` can hear where the riser ends.
- **room:** a short, dark room reverb (the sound of a small room) on the whole layer, so the sounds sit in a space
  instead of sounding dry. **On by default**: `wet` 0.22 (the share of reverb, 0 to 1) and `decay` 1.1 s (the tail
  falls by 60 dB in 1.1 s, 0.2 to 4 s). Set `"room": false` to turn it off.
- **One key.** With `"key"` set, a `note`, `boom`, `slam` or `chime` outside it is refused, and so is a chime whose
  fifth is outside it. A riser's `note` must be in key too. A library effect is checked. Never
  pitch-shift a library effect to make it fit: make a `note` in key. To see which notes the library effects hold:
  `python3 <kit-to-clip>/sound/scripts/pitch.py check --key "A minor" <effects>`; `sound/sfx-pitch.json` lists the
  measured note of each media-use effect (most are noise-like and fit any key; sparkle holds G, chime A, ping D).
- Fewer, meaningful sounds beat many: a scored hit for each picture moment plus the whooshes. 36 effects in 15 s felt
  busy and cheap.

Never add an element only to carry a sound: every hit and riser follows a real move you can see.

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
| `sound/scripts/effects.py` | whooshes, hits (note, boom, slam, chime, thump, tick, file), risers and the room, from `motion.json` and a plan; writes `sfx.wav` and a cue sheet |
| `sound/scripts/pitch.py` | the note of an effect (`measure`, `index`, `check --key`) |
| `sound/scripts/ace_takes.py` | the default music: ACE-Step takes from a description, put on the tempo grid and scored against the sections; writes the best as `music.wav` and `score.json` (`score.py`'s format), keeps every take, `--pick <seed>` after listening, `--self-test` |
| `sound/scripts/score.py` | the fallback music, made offline in four styles: `styles`, `preview`, `make` (music and `score.json`), `mix`, `analyze` |
| `finish/scripts/finish.py anchors` | picture lands on its beat, read from the running timeline |
| `finish/scripts/finish.py audio` | what the render will do to the mix's level |
| `finish/scripts/finish.py sync` | each cue's sound lands within a frame of its picture, on the encoded file |
