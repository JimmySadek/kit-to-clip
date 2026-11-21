# Sound module: videos with music and sound effects

Part of the kit-to-clip skill; `SKILL.md` covers setup and when to come here. Use it for any video that has sound
made for its picture: a Reel with a score, effects on the moves, a teaser with a soundtrack. A clip that only keeps
its own original audio does not need this (finish it with `--no-sync "footage's own sound"`).

```
✋ what and where ─▶ timing driver ─▶ ✋ voice choice ─▶ timing plan ─▶ ✋ storyboard ─▶ picture ─▶ ✋ music pick
      on the picture ─▶ effects from events ─▶ mix + audio preflight ─▶ render ─▶ encoded sync ─▶ ✋ final film ─▶ deliver
```

Plan sound before the detailed picture that depends on it. First select the timing driver in
`references/video-journey.md`: narration, music, visual reading/events or footage. The music-first beat/bar method
below is for **music-led** films. It is not a universal requirement. A narrated explainer follows the approved
recording and actual word timings; background music supports it without moving speech to musical beats or forcing
the finished duration into whole bars. The storyboard and silent style tests come before final audio. The chosen
voice is heard and agreed before the full dependent build; the music is picked by ear on the built picture.

For narration, use supplied audio, installed local voice tooling, or an explicitly chosen guided Google AI Studio
handoff as described in the journey. Keep script separate from performance instructions. Keep narration, music
and effects as separate sources until the final mix, reduce music under speech where appropriate and judge the
combined mix by listening. Replacing a voice take invalidates the storyboard timing, the music pick and the final film yes, not
automatically the selection of unchanged background music.

## 1. The music source (✋ when music is wanted)

Use the brief's already supplied choices. For a music-led job, choose the source before detailed animation.
For background music under narration, agree a suitable source or bed after the spoken script/delivery is stable; the ✋ pick comes on the built picture.
Offer the generator when an original produced track fits, the built-in bed, a supplied track or no music.
These music powers are free/local and need no new account or key; do not require a paid library. Optional
user-directed external voice generation is a separate choice, not a mandatory music dependency.
The selected reference's sound character is the starting point when it fits the story. Keep its meaningful paper,
brush, typing or game sounds rather than replacing them with generic hits. Atlas narration variants can disable
their native music/ambience; an independently approved bed needs an explicit, single mix path. Use
`references/reference-resources.md` for live sound versus baked file custody.

| Option | What it needs |
|---|---|
| **An original track from a description** | the `music-generate` power, ACE-Step (`toolbox.py which music-generate`): free, runs on this computer, ✋ before adding it. Check actual installed tools/models first. A missing model's first download is about 9.4 GB. `ace_takes.py` makes several auditions (step 2) |
| Music made offline (the fallback) | the built-in music maker, `score.py`: no model, ready in seconds, every cue exact to the sample. Four styles, any key, no licence (section "Music made offline"). Use it when the generator is not installed, the person does not want the download or the wait, or no take works |
| They supply a track | the file. Get its beats: add it to the project as the root `<audio>`, then `npx hyperframes beats <project>` writes `beats/<audio>.json` (the HyperFrames `music-to-video` workflow builds on it). For a track outside a project, `python3 <kit-to-clip>/scripts/reference.py beats <file>` reports its tempo and strongest hits (it uses a throwaway project and saves nothing) |
| No music, effects only | place effects from actual visual events. A musical tempo is optional, not a prerequisite |

Say two things before the person picks the generator. **Generated music can sound like an existing song by accident**,
so the description names the genre, mood, instruments and tempo, never an artist or a song. And **you cannot hear the
takes**: the person chooses by listening, on the built picture (✋ music pick, after the picture).

Some destinations limit music. `finish.py plan --profile <p>` prints the destination's sound facts: for Instagram, its
licensed music is for personal, non-commercial use and some business accounts cannot use it, so a brand Reel uses its
own music and effects (made or licensed for commercial use, baked into the file) or the Meta Sound Collection.

## 2. Tempo, bars and sections

For a **music-led** film whose structure follows generated music, whole bars can provide a useful plan:
length = bars x 4 x 60 / bpm. 15 s is 8 bars at 128 bpm; 12 s is 6 bars at 120. Write the sections as beat numbers before the dependent full picture: the hook, the build, the drop (the biggest
moment), the lift, the end. Confirm the tempo and the sections with the person (one line each; this is not a ✋ stop), then keep them: they are the
score the picture is timed to. Under narration, generation may make extra whole bars which are edited to the
spoken duration. Whole-bar generation is not a requirement to move the speech or change the requested video length.

**When the music generator is chosen**, make the takes once the picture is built on the confirmed grid:

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
  says so: re-cut that part of the picture so its big move lands where the music drops, not where the plan guessed. A flat build is only a note
  when the drop lands on the planned beat.
- **Ready for the pipeline:** the best take is levelled like `score.py` (-18 LUFS, true peak under -3 dBTP) and
  written as `music.wav` and `score.json` in the same format. Steps 3 to 6 work unchanged.

Every take stays in `sound/takes/`: `take-s<seed>-x<extra>.wav` is the raw take, `take-s<seed>-x<extra>-ready.wav`
is cut, on the grid and levelled. A take is reused only when it was made with the same settings, extra bars included. `sound/takes.json` holds every number and why the winner won. A `warning` there means every take missed a
check: say so, and offer more takes (`--takes 5`), other seeds (`--seed 40`) or `score.py`. Music comes after the
picture, also in a music-led film: the picture is cut to the planned grid and the takes are made to the same grid.
✋ Play the takes on the built picture and let the person pick by ear; the winner in `takes.json` is only a suggestion.
The same command with `--pick <seed>` makes their pick the music in seconds (the takes are reused). No ACE-Step installed stops with exit 3 and the `score.py` command to use.

Trust `score.json` for the beats. `npx hyperframes beats` reads ACE-Step's beats about 25 ms later than `ace_takes.py`
and `finish.py sync` do: it lands on the low body of the kick, not its attack.

## Music made offline (the fallback)

The kit can make an original synthetic bed without an account or model. Its generator produces whole bars and
beats, which can drive a music-led film or be edited under another timing driver. It is synthesised, so think of it as a bed rather than a produced record, and
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

Agree the style after the person has listened to the previews (send them the files; do not describe them as good).
The ✋ music pick still happens on the built picture.
Any key (`--key "C# minor"`), any tempo from 60 to 200, and the chords (`--progression 1,6,7,3`, scale degrees) can be
set; `--seed` gives a different take. The structure is always four sections, hook, build, drop and end (the last is one
bar: a final hit and its tail); `--sections hook:2,build:2,drop:3,end:1` changes their lengths. **Generate music in
whole bars.** The generated audio spans `bars x 4 beats`; a narrated, visual-led or footage-led video retains its
approved timing and can trim/crossfade that bed. Do not stretch speech or change the requested runtime to fit it.

`make` writes `music.wav` and **`score.json`**, the source of this music's timing: tempo, key, chords, the section beats, and the
`cues` (`hook`, `build`, `drop`, `end`) in beats. Beat `n` is at `n x 60 / bpm` seconds. Put the picture's big moments on
those beats when music leads (step 3). Narration uses its own word/idea timestamps. Every tonal note is built from the key's scale and checked; a note
outside the key stops the build. The music is at -18 LUFS with true peak under -3 dBTP, which leaves room for the effects.
`mix` sums music and effects, sets the level and limits true peak at -3 dBTP, so the render does not turn it down.
`score.py analyze <file>` reports length, loudness, peak, how busy, how bright and how much bass a file has.

Checking the effects on their own: over drum-driven music (`pulse`, `uplift`) the music's own kick lands on the beat, and
`sync` takes the strongest sound near each cue, so it may hear the kick instead of the effect. To check the effects
alone, run `sync` on a copy of the render whose sound is `sfx.wav` only. `calm` and `cinematic` leave the effects
clearer. A picture that visibly stops well before its beat (a long ease-out) also shows up here: the effect follows the
picture, the music follows the beat, and the gap is real. End the move on the beat or shorten the ease.

## 3. Picture on the chosen timing source

The beat method below applies when music leads. For narration, use actual word/idea times and pauses; for visual
explanations use reading time and visual events; for footage preserve editorial intent. Record these times in the
brief/cue files, rather than inventing musical anchors for every move. Do not shift the voice to a strong beat.

In the music-led method, give the scored beats roles and describe them in plain words: **the reveal** (the
first strong beat: the hero arrives), **the big move** (the next strong beat or the drop: the scale-up, the slam),
**small accents** (the beats between: a tick, a pulse, a word), and **the hold** (the end card rests about two beats).
Big moves only on strong beats; accents never compete with them.

Time scored transitions/arrivals to their chosen beats (`beat time = beat x 60 / bpm`) and mark those elements with
`data-anchor="beat:N"`. Continuous/background motion need not move on every beat.
Then:

```bash
python3 <kit-to-clip>/finish/scripts/finish.py anchors --project <dir> --bpm 128
```

It reads when each element really starts moving or comes to rest on the running timeline and fails when one is off its
beat (window -0.034 to +0.045 s). Fix the timeline, not the attribute.

## 4. Effects from the motion

Every effect needs an intended visual/story cause. Derive its timing from the real visual event: trace DOM motion
where applicable, or record the exact Canvas event and inspect its actual frame. Do not invent a musical grid for
a narration-led or effects-only video.

`trace.mjs` observes DOM elements. A Canvas reference needs explicit timed visual/sound events tied to its drawing
function and actual frame checks; do not claim Canvas timing is proved by an empty DOM trace. Preserve meaningful
surface sounds from the chosen reference, and avoid adding a second background track when an approved track exists.

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

1. The stills and the plan (a cue list and the tempo) belong to the ✋ storyboard. There is no separate yes before
   rendering: render, check, and bring the result to the ✋ final film.
2. `python3 <kit-to-clip>/finish/scripts/finish.py audio mix.wav`: HyperFrames turns a mix down when its peaks are hot.
   Limit the mix at -3 dBTP and it arrives at the level you set.
3. Render, then check the file:
   `python3 <kit-to-clip>/finish/scripts/finish.py sync renders/<job>.mp4 --cues sound/cue-sheet.json`. Every cue must
   pass. It is a measure of timing, not of taste (`finish/README.md`, section 3a, says what it cannot tell you).

## 6. The final film: watch and listen (✋)

You cannot hear. Measurements support the person's ear, they do not replace it. Listening is part of the ✋ final film
yes: the person watches and hears the finished film once, and nothing is called finished or delivered before it. Say:

> The sound is **unheard by me**. I can measure that each hit lands within a frame of its picture moment, but I cannot
> hear whether it feels right. Please listen on your phone with the sound on and tell me what feels off.

Every handoff about a video with sound says "unheard by the agent" until the person has listened, and never calls the
sound "verified" or "checked" on the strength of the sync numbers alone. Fix what they hear, show it again, and make
the deliveries once they say yes:

```bash
python3 <kit-to-clip>/finish/scripts/finish.py finish renders/<job>.mp4 --profile instagram-reels --out <deliveries> --cues sound/cue-sheet.json
```

## Tools

| Tool | What it does |
|---|---|
| `finish/scripts/trace.mjs` | how each marked element moves and how much of it is visible, every frame (`motion.json`) |
| `sound/scripts/effects.py` | whooshes, hits (note, boom, slam, chime, thump, tick, file), risers and the room, from `motion.json` and a plan; writes `sfx.wav` and a cue sheet |
| `sound/scripts/pitch.py` | the note of an effect (`measure`, `index`, `check --key`) |
| `sound/scripts/ace_takes.py` | ACE-Step auditions when chosen, put on the tempo grid and scored against sections; writes `music.wav` and `score.json`, keeps every take, `--pick <seed>` after listening, `--self-test` |
| `sound/scripts/score.py` | the fallback music, made offline in four styles: `styles`, `preview`, `make` (music and `score.json`), `mix`, `analyze` |
| `finish/scripts/finish.py anchors` | picture lands on its beat, read from the running timeline |
| `finish/scripts/finish.py audio` | what the render will do to the mix's level |
| `finish/scripts/finish.py sync` | each cue's sound lands within a frame of its picture, on the encoded file |
