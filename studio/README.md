# Kit to Clip Studio

A local page for one film. The person clicks; you do the work in chat. The Studio shows the film as rooms
(Start, Story, Styles, Voice, Storyboard, Music, Finish; their ids are `start`, `story`, `styles`, `voice`, `board`,
`music`, `finish`), writes their clicks into `film.json` and a log, and redraws when you change `film.json`.

## The rooms

| Room | The person | You |
|---|---|---|
| ⓪ Start | Pastes a link or text, drops files, picks the film's brand | Read what they brought and fill in `film.json` |
| ① Story | Picks one of your ideas, edits the beats, edits the script for the voice and the story parts | Write 2 or 3 ideas, then beats, then the script (rules in `references/story-and-voice.md`), then parts with times. Ask for the ✋ script yes when you wrote the script |
| ② Styles | Shortlists styles, paints the style map, sets brand per part, picks the joins | Say if a choice fights the story. Copy build prompt holds every chosen style's code |
| ③ Voice | Copies each segment into Google AI Studio (or another route), drops the takes back | Each take is timed against the script's clean copy; flagged words need a look. Fit the parts to the take times |
| ④ Storyboard | Looks at the panels, comments on any panel, clicks ✋ Yes | Draw the panels with `board.py`, redraw only commented or out-of-date panels, ask for the yes on the board version. After every redraw, ask again with the new version |
| ⑤ Music | Edits hyper-local keyword chips and words to avoid, plays 3 takes per cue on the picture, picks by ear, clicks ✋ Yes | Write 5-layer keywords and words to avoid (`references/music-keywords.md`), run `music.py audition` (3 takes per cue on the picture at −18 LUFS), then `music.py assemble` after the person picks |
| ⑥ Finish | Chooses formats and captions, watches and hears the finished film once, clicks ✋ Yes | Render with `render.py`, mix/duck/master (−14 LUFS) and generate captions with `mix.py`, ask for ✋ Final film; export per-platform folders with `finish.py` after the yes |

## The clickable ✋ yes

The four ✋ stops in `SKILL.md` stay binding. The Studio adds a button; it never approves anything by itself.

1. You ask with the question tool as usual, and run `studio.py ask <video-folder> <stop> "<label>"`, for example
   `storyboard "storyboard v2"`. The stop's room (for music, the ✋ Approval stops panel) then shows
   **✋ Yes, storyboard v2** and **Not yet**. With no ask there is no button. For the storyboard, the label must name
   the board version on screen. If the panels are drawn again after the ask, the stop shows **outdated** and the old
   button no longer counts: ask again.
2. The person clicks. The server writes one `approve` line to the log, stamped with a keyed check (the key is in
   `.studio/approve.key`). A line typed by hand, copied or replayed counts for nothing. A click on an older version
   does not count. **Not yet** logs a `not-yet` line with the person's note.
3. You run `studio.py approvals <video-folder> --record`. It writes each counting click into `film.json` `approvals`
   and prints a `say` line. Repeat it in chat.

A yes the person says in chat is recorded with `studio.py yes <video-folder> <stop> --words "<their words>"`.

Never write `approvals` by hand: `ask`, `approvals --record` and `yes` write it and keep what each yes covered, in
`.studio/approved/<stop>.json`. The script yes covers the script and the parts' words. The storyboard, music and final
yeses cover the script, the parts, the style map, the joins, the brand and the voice files, plus the board version
(storyboard), the music config and audition takes (music, final) and the finish choices and build (final). When any of them changes, wherever the change
came from (including a fresh `music.py audition` round), the stop shows **reopened** (or **outdated** if asked and not yet approved). After you change the film, redraw panels, or make new music takes, run `approvals --record`: it
removes the old yes and says what changed. Say that in chat and ask again.

## Commands

| Command | What it does |
|---|---|
| `python3 <kit-to-clip>/studio/studio.py open <video-folder> [--room <id>]` | Starts the Studio for that folder (or reuses the running one) and prints its URL. Give the person that URL |
| `studio.py events <video-folder> --since <n>` | Prints the clicks logged after line `n`. Run it first whenever the person pastes a Studio request |
| `studio.py wait <video-folder> --since <n> [--timeout <s>]` | Optional. Waits for a click you must answer (Ask Claude to do this, ✋ Yes, Not yet, a panel comment), prints it and exits (exit 3 when the timeout passes first). Run it in the background; while it runs, the Ask button is live. It ends after one click, so start it again for the next |
| `studio.py ask <video-folder> <stop> "<label>"` | Asks for a ✋ yes on one version of a stop (`script`, `storyboard`, `music`, `final`). An older yes for that stop goes |
| `studio.py approvals <video-folder> [--record]` | Each stop's state and every ✋ Yes click with whether it counts. `--record` writes the counting clicks as yeses and removes yeses whose inputs changed |
| `studio.py yes <video-folder> <stop> --words "<…>"` | Records a yes the person said in chat, in their words |
| `studio.py voice <video-folder> --seg <seg-01> --file <audio>` | Copies a take to `voice/<seg>` and times its words, as a drop in the Voice room does |
| `studio.py stop <video-folder>` | Stops the Studio. It also stops by itself after 4 hours with no request (an open page keeps it running) |
| `python3 <kit-to-clip>/studio/compose.py <video-folder> [--outline]` | Writes the build prompt to `.studio/prompt.txt` (the page's Copy build prompt does the same). `--outline` also prints its headings and sizes |
| `python3 <kit-to-clip>/studio/board.py <video-folder> [--panel <id>]` | Draws the storyboard (source `scripts/env.sh` first). `--panel p3` or `--panel join-p5` draws one panel again |
| `python3 <kit-to-clip>/studio/music.py audition <video-folder> [--cue <id>]` | Generates 3 ACE-Step takes per cue (never falls back to the synth silently; `--engine score` is only for an explicit temporary guide track), clears any earlier pick and removes any stale assembled `score-full.wav`, levels to −18 LUFS via `finish.py`, and muxes onto the built picture when available |
| `python3 <kit-to-clip>/studio/music.py assemble <video-folder>` | Extends and stitches the person's picked takes across the full film into `.studio/results/music/score-full.wav` (refuses if any cue lacks a current-round pick; labels `is_guide` when any picked take is a temporary synth guide) |
| `python3 <kit-to-clip>/studio/render.py <video-folder> [--html player.html]` | Renders a player HTML (`window.seek(i/fps)`) via bundled Chromium → ffmpeg (`picture.mp4`) and captures the offline SFX stem (`sfx.wav`) |
| `python3 <kit-to-clip>/studio/mix.py <video-folder> [--captions burned\|srt\|off] [--music <wav>]` | Mixes voice + SFX + current assembled music, builds `.srt`/burned-in captions from Parakeet words, and writes `final.mp4`. Ducks music 12–15 LU under the voice and masters to −14 LUFS (true peak ≤ −1 dBTP). Refuses until the ✋ Music yes is recorded and still current; refuses music takes without a matching assembled track, and a `score-full.wav` that no takes or picks explain. `--music` with any other file is labelled outside music in `finish.json`; temporary guide music is labelled too |

The URL holds a secret key. The page swaps it for a cookie and drops it from the address bar. The server listens
on 127.0.0.1 only.

## `film.json`

One file in the video folder. Create it before `open`, from what the person brought. Plain JSON; keep fields you do
not know.

```json
{
  "kit_to_clip_film": 1,
  "title": "How a parcel finds its way",
  "about": "A product explainer",
  "frame": { "width": 1280, "height": 720, "fps": 30 },
  "length": 92.0,
  "brand": null,
  "inputs": [ { "kind": "voice", "path": "inputs/voice.wav", "note": "The voice take" } ],
  "parts": [
    { "id": "p1", "name": "Hook", "from": 0.0, "to": 12.4, "words": "…", "picture": "…", "sound": "…" }
  ],
  "styles": { "shortlist": ["film-noir"], "map": {}, "joins": {} },
  "rooms": { "start": "done", "story": "empty", "styles": "empty", "voice": "empty",
             "board": "empty", "music": "empty", "finish": "empty" }
}
```

| Field | Meaning | Written by |
|---|---|---|
| `kit_to_clip_film` | The file format version, `1` | You |
| `title`, `about`, `frame`, `length` | The film | You |
| `brand` | The film's one brand: `{"name", "skill"}` for a brand skill installed on this computer, `{"name", "skill": null, "other": true}` for another brand (ask the person for its guide), or `null` (the default unless the person named a brand). With `null` every part is as is: the page, the server and `compose.py` ignore any brand or palette mode in the map or a preset | The page (the Start room's Brand picker lists the installed brand skills) and you |
| `inputs` | What the person brought, by path. Files dropped in the Studio land in `<video-folder>/inputs/` | You and the page |
| `parts` | Story parts with times in seconds. A part is the smallest piece a style can cover | You |
| `start` | What the Start room detected and which room it suggests | The page |
| `styles.shortlist` | Catalogue style ids the person is considering | The page (you may seed it) |
| `styles.map` | Per part id: `{"style": <catalogue id>, "brand": "brand" \| "palette" \| "as-is"}` | The page |
| `styles.joins` | Per style change, keyed by the part where the new style starts: `{"type": <id from joins.json>, "note": ""}` | The page. A change with no entry uses the first suggestion in `joins.json` |
| `presets` | Optional named maps the Styles room offers as "Start from": `{"<key>": {"label": …, "map": …, "joins": …}}` | You |
| `rooms` | `empty`, `draft` or `done` per room, for the top bar | The page and you |
| `story` | `{"ideas": [{"id", "title", "line", "why"}], "picked": <idea id or null>, "beats": [{"id", "text"}]}` | You write ideas and beats; the page picks an idea and edits beats |
| `script` | The script for the voice, in the form Gemini TTS reads: `{"model", "voice", "segments": [{"id": "seg-01", "style": "<short Style line>", "text": "<spoken words and tags>"}]}`. Never square brackets | You and the page |
| `voice` | `{"route": "ai-studio" \| "own" \| "kokoro" \| "none", "takes": {"<seg>": {"file", "state": "timing" \| "timed" \| "failed", "words_file", "words", "flagged", "error"}}}`. The word times are in `voice/<seg>.words.json` | The server (from a drop or `studio.py voice`) and the page (the route) |
| `music` | `{"cues": {"<world>": {"name", "style", "bpm", "key", "hits", "spans?", "layers": [{"layer", "chips": [[word, reason]]}], "pick", "pick_round?", "wrong"}}, "avoid": [[word, reason]]}` | You suggest keywords; the page edits chips, picks takes, and logs feedback |
| `finish` | `{"formats": {"wide": true, "tall": false, "square": false}, "captions": "burned" \| "srt" \| "off", "lufs": -14}` | The page and you |
| `approvals` | Per stop (`script`, `storyboard`, `music`, `final`): `{"asked": "<label>", "since": <log line>}` after an ask; `{"asked", "yes": "<the person's words>", "at", "via": "studio" \| "chat", "event"}` after a yes. A changed input that reopens a stop removes its entry on the next `approvals --record` | `studio.py ask`, `approvals --record` and `yes`. The page never writes it |

Joins come from the map: a join exists wherever two neighbouring parts have different styles. An entry in `joins`
with no style change behind it is ignored.

The page replaces only `start`, `styles`, `rooms`, `brand`, `parts`, `story`, `script`, `music` and `finish`, one section at a time (No brand also sets every part to as is); an upload also adds to `inputs`, and a voice drop to `voice`. You edit the file directly; the last
write wins per section. When you change `film.json`, the open room redraws within a second. If the person is typing,
the page shows a Reload bar instead.

## The event log

`<video-folder>/.studio/events.jsonl` gets one line per meaningful click and is never cleared:

```json
{"n": 14, "at": "2026-10-22T10:03:11Z", "room": "styles", "kind": "map", "detail": {"part": "p5", "style": "product-launch"}}
```

Kinds the page logs: `open`, `paste`, `map`, `brand` (one part's mode), `brand-pick` (the film's brand),
`join`, `preset`, `shortlist`, `copy-prompt`, `copy-build-prompt`, `ask` (the person pressed Ask Claude to do this;
`detail.request` holds the text), `not-yet`, `parts`, `story`, `script`, `music`, `finish` and
`comment` (`{"panel", "text", "board", "panel_version"}`; the server fills in the versions). Kinds only the server
writes: `upload` (a dropped file), `approve` (a ✋ Yes click, stamped), `reopen` (a save from the page reopened a
stop; your own changes show only in `approvals`) and `voice` (a take dropped, timed or failed, or the route changed). Typing logs once, when the person leaves the field.

## The storyboard panels

`board.py` draws one rough panel per story part and one per style join, at their times, with each style's own code
in the bundled browser. A part panel shows its style at the part's moment in that style's animation; a join panel
shows the old style's last moment and the new style's first, split on a diagonal. Panels land in
`<video-folder>/.studio/results/board/` with `board.json`:

```json
{"version": 3, "made": "…", "redrawn": ["p3"], "layout": {"canvas": [1280, 720], "safe": {"youtube": {"left": 64, "right": 1216, "top": 36, "bottom": 648}}},
 "panels": [{"id": "p3", "kind": "part", "at": 31.6, "style": "…", "version": 2, "file": "p3.png", "basis": {…}}]}
```

`redrawn` is `"all"` after a full drawing. The board version goes up with every drawing; a panel's own version only when it is drawn again. The room shows the
panels as soon as they land, flags a panel whose part, style, brand or join changed since (`basis`), and shows open
comments under their panel. A comment stays open until that panel is drawn again. Panels are rough: no brand yet, and
text positions are only checked against the canvas and the safe box.

## Live previews and the private style folder

The style cards draw each style's hero frame with that style's own code, from the private style library. The library
is not part of this package. Point the Studio at it with one line in `~/.config/kit-to-clip/config.json`:

```json
{ "atlas_dir": "/path/to/the/style/library" }
```

`KIT_TO_CLIP_ATLAS=<folder>` overrides that line for one run. Without it, cards show names and tags only. A folder inside this package is refused.

Each preview runs in a sealed frame: it cannot read the film, the cookie or the log, and cannot reach the network
apart from Google Fonts. Only the card under the pointer or the keyboard focus moves; library styles are written for frame-by-frame renders,
so "Play the demo" shows their full motion.

## Privacy

- The build prompt (`.studio/prompt.txt` and the clipboard) and the storyboard panels hold private library code. Never commit it, paste it
  into a public place or copy parts of it into this package.
- `open` writes `<video-folder>/.studio/.gitignore`, so the log, the prompt and the server file stay out of git.
- Dropped files stay on this computer, in `<video-folder>/inputs/` (voice takes in `voice/`). Files over 500 MB are
  copied in by hand.
- Voice takes are timed by Parakeet, a separate local program (toolbox card `parakeet`). Nothing is uploaded.
  Google AI Studio is the person's own choice and needs their Google account; the Studio only copies text for it.
