# Story and voice

Read when a person brings an inspiration, an idea or a script, and when you write ideas, beats or the script for the
voice in the Studio's ① Story room. The room saves what the person edits into `film.json` (`story`, `script`, then
`parts`); you write your drafts into the same fields and the room shows them.

## Where to start: what the person brings

| They bring | Start at | Write first |
|---|---|---|
| **An inspiration** (a link, a reference film, "something like this") | ① Story, with the reference shown | 2-3 story ideas in its spirit, and styles that match its look |
| **An idea or a topic** | ① Story | 2-3 story ideas, then beats once one is picked, then the script |
| **A full script** | ① Story, then ② Styles | Check it against the voice rules below, then split it into story parts |

Never ask again for what they already gave. A full script skips ideas and beats.

## Ideas, beats, script

1. **Ideas** go into `story.ideas`: 2-3 of them, each `{id, title, line, why}`. `line` is the story in one sentence;
   `why` says why it fits this person's goal. If one idea is clearly stronger, say so and say why. Then stop: the
   person picks one in the room (`story.picked`).
2. **Beats** go into `story.beats`: 5-8 short lines `{id, text}`, in order. Stop again so the person can edit them.
3. **The script** goes into `script`: `{model, voice, segments: [{id, style, text}]}`, ids `seg-01`, `seg-02` … in the
   form below. Then ask for the ✋ script yes (`studio.py ask <video> script "script v<n>"`).
4. **Story parts** come from the script: each part gets the words it speaks and times that fit them. The room's
   estimate (about 2.6 words a second, plus pauses) is a guide; the voice takes give the real times later.

## Writing for the voice (Gemini TTS)

The script is written in the form Gemini TTS in Google AI Studio reads best.

| Rule | Example |
|---|---|
| The text holds **only spoken words**, pause tags and one CAPITAL word. It is read word for word | `Then you WAITED. <long pause> Not anymore.` |
| **One segment per tone.** When the feeling changes, start a new segment with its own Style line | nostalgic → clinical → hopeful is three segments |
| **Keep the Style line short.** Long direction blocks make the voice drift | `calm documentary narrator, reflective` |
| No age, gender, names or accent in the Style line. Choose the voice instead | not `a 40-year-old British man` |
| Small breaths: commas, `--` and `...`. Real breaks: `<short pause>` and `<long pause>` | `Exporting. <short pause> Transferring.` |
| **Never square brackets** like `[Tone: calm]`. They can be read aloud | the room turns `[sigh]` into `<sigh>` and drops `[Tone: …]` |
| **One CAPITAL word** for stress. No asterisks or markdown | `WHERE the team needs them` |
| A `<long pause>` after each turn point | `Then you WAITED! <long pause> Not anymore!` |
| A `<short pause>` between list items | `Upload. <short pause> Share. <short pause> Done.` |
| Human sounds only as tags, in English even for other languages | `<sigh>`, `<chuckle>`, `<breath>`, `<laugh>`, `<whisper>` |
| Try an empty Style first. Reuse the same Style string for segments of the same tone | two hopeful segments share one Style |

The room has a tag palette, an estimate per segment, these checks as warnings, and a **clean copy** (the words without
tags) for captions. The Studio refuses to save a square bracket.

## Voice in 3 steps (③ Voice room)

1. **Copy** a segment: the model, the voice name, the Style line and the text each have a copy button, plus an
   "Open AI Studio" link to the speech page.
2. **Run, listen and download** each segment as `seg-01.wav`, `seg-02.wav` … Not happy? Change the Style line and run
   it again. The person picks the take by ear.
3. **Drop the files** into the room. Parakeet (a free local speech model) times each word against the clean copy and
   flags any word it could not find. Product names are the usual risk.

⚠️ AI Studio's field names come from one Gemini answer; nobody has checked them on the live page yet. Say so if the
person cannot find a field.

Other routes in the same room: their own recording, the free local Kokoro voice, or no voice. AI Studio needs the
person's own Google account; say that before they choose it, and never upload their files yourself.
