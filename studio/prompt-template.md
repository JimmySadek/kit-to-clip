# Build prompt: {{title}}

You are building one animated explainer film as a single HTML file. Everything you need is in this prompt: the film
plan, the story parts with their times, the style map, and the reference code for every style the film uses.
Read it all before you write anything.

# 1. WHAT TO BUILD

- One self-contained HTML file: a {{width}}×{{height}} canvas that scales to fit the window (letterboxed, never
  stretched) and a small control bar with play/pause, a scrubber and the current time.
- The film is a pure function of time. Every frame is drawn from `t` (seconds) alone: no state carried from the last
  frame, no `Math.random()` at draw time. Seed all randomness from the shared helper library so the same `t` always
  gives the same pixels.
- The player contract. The file must offer exactly these, because the film is later rendered frame by frame:
  - `window.DURATION`: the film length in seconds.
  - `window.seek(t)`: draws the frame at time `t`, at once, with no waiting.
  - `window.scoreSound(k, from = 0)`: schedules every sound on the sound kit `k`, with times in film seconds.
  - Playback goes through the sound kit's `SOUND.live`, starting from the playhead:
    `SOUND.live((k) => window.scoreSound(k, t), t, { voiceover: false })`. The voice is a separate track
    (section 3); the player's own sound is effects, beds and any music.
- Known trap in the sound kit: a long sound (a bed, a hum, a held tone of about 1.5 s or more) that began before the
  play point gets a negative start time and throws, which silences everything after it. In `scoreSound`, start such
  sounds at `Math.max(start, from)` and shorten them to match. Test play from several points in the film.
- Load every font the styles use before the first frame is drawn (await each one), so the first frame is final.
- It is watched on phones. Keep every word large enough to read on a phone held upright at {{width}}×{{height}}:
  headlines big, labels never tiny, and nothing important in the outer edge of the frame.

# 2. MY FILM

- Title: {{title}}
- About: {{about}}
- Length: {{length}} s. Frame: {{width}}×{{height}} at {{fps}} fps.

The story parts. Each row is one part of the film, with its time span, the words heard, what the picture shows,
what you hear, its style and how the brand applies.

{{parts_table}}

# 3. VOICE TIMING

{{voice_timing}}

# 4. STYLE MAP

{{style_map}}

# 5. HOW TO MIX STYLES

- Each run of parts lives entirely in its own style's medium: its rendering technique, palette, textures, lettering
  and finishing passes. Take those from the style's reference source below, not from memory.
- Keep the medium, change the subject. The reference sources explain other topics; draw my subjects, accurately,
  in each style's way. Do not carry a style's props or demo content into my film.
- No style borrows from another. A part in style A shows nothing of style B, except inside a join.
- Each join is its own designed moment of a few seconds at the part boundary, built from both media (the outgoing
  style breaking down, the incoming one appearing). Use the join type and description given for it in section 4.
- When a style returns later in the film, it returns as itself: same look, same finishing, so the viewer recognises
  the world.
- The finishing passes of each style (grain, paper, vignette, glow, scan lines and so on) run on every frame of its
  runs. They are what make the medium read as real.

# 6. BRAND

{{brand}}

# 7. STOPS FIRST

These are the approval stops for this film. Do not skip one, and do not treat silence as a yes.

1. **Storyboard first.** Before building the film, make the storyboard: one rough frame per story part and one per
   join, laid out at their times, drawn with each style's own code (still frames from the reference sources,
   adapted to my subjects). Show it, then **stop and wait for one storyboard yes**. That one yes covers layout,
   look, brand and joins.
2. **Build.** After the storyboard yes, build the full player. There is no separate yes for rendering: rendering is
   local, and I judge the result.
3. **Music, after the picture.** If the film has music, make the takes only once the picture is built, play them on
   the built picture, and **stop for my music pick by ear**. Never pick a take by a score or a measurement.
4. **Final film.** Mix and finish, then show me the finished film to watch and hear once.
   **Stop for my final film yes.** Listening is part of that yes. Nothing is called finished before it.

The script yes comes earlier, in chat, whenever Kit to Clip wrote the script. It is not repeated
here.

# 8. OUTPUTS

- The player HTML file, following the contract in section 1.
- Sound stems: when `window.SCORE_STEM` is set to `'sfx'` or `'music'` before scoring, `scoreSound` plays only that
  layer. With no value it plays the full mix.
- A cue sheet: one line per event that matters for music (cuts, hits, stamps, joins, silences), with the time
  measured in the built player, not the storyboard.
- A timed script: one line per spoken line, `start–end | words`, in film seconds.

# 9. SHARED CODE

Two code kits used by every style below. Include each one once, unchanged.

{{shared_code}}

# 10. STYLES

The reference source of each style the film uses, once each, even when the map returns to a style. Each comes with
its style card (look, motion, how it explains) and its font link.

{{style_sources}}
