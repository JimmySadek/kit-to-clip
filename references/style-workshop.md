# The style workshop: designing a new video style

Someone wants a kind of video that none of the listed formats or saved styles covers. Act as their creative
director: ask, propose, show, adjust, then save it so the next video in this style takes minutes. They decide; you
do the work. The brand is the one the front door found (or a neutral look); its pack's `guide.md` and the brand
kit's own references set what is allowed.

```
✋ name ─▶ ✋ starting point ─▶ ✋ purpose + platforms ─▶ ✋ mood ─▶ ✋ length + pace ─▶ ✋ words on screen ─▶ ✋ sound
     ─▶ ✋ pick 1 of 3 concepts ─▶ ✋ approve the recipe ─▶ build ─▶ ✋ stills (≤3 rounds) ─▶ ✋ test render ─▶ ✋ save
```

Use AskUserQuestion for every ✋, one decision each. Options below are starting points: adapt the labels to what
they already told you, mark a recommendation when their earlier answers point to one, and remember that "Other"
always lets them describe something new. If they answer several questions in one message, skip those questions.

## 1. The questions

1. **Who and what** (plain chat, not a menu): "What should we call this style, and what's your name?" Save the
   name in `.reel-kit/user.json` inside a studio folder (`{"name": ...}`) and don't ask again. Then:
   `styles.py init --title "<title>" --author "<name>" [--brand <id>] [--from <format or style>]`. The style is
   saved with the brand (`<brand kit>/kit-to-clip/styles/`), in a studio's `styles/`, or in `reels/styles/` without a brand.
2. **Starting point:** a clip (highlight, match, demo) · words and graphics only (announcement, stat, promo) ·
   an existing video that needs graphics on top · a short loop (website, screens at a venue).
3. **Purpose + platforms** (multi-select platforms): TikTok · Instagram Reels · Instagram feed 4:5 · YouTube
   Shorts · YouTube or website 16:9. Ask the purpose in the same question's wording ("to hype a tournament?
   to teach a shot?") only if it's not clear yet.
4. **Mood:** Hype (fast cuts, slams, big type) · Premium (slow moves, lots of space, one accent) · Playful
   (bounces, stickers, surprises) · Coach (freeze, annotate, explain). Tie each to what the brand allows (its
   pack's `guide.md` names the kit references to read) and to its motion energy (`--reel-energy`).
5. **Length + pace:** 6-10 s teaser · 15-20 s · 25-30 s · 45-60 s. Say what fits each platform.
6. **Words on screen:** big titles in the brand's display face · clean captions · numbers and stat chips · almost none.
7. **Sound:** a score the brand's pack already has (its formats may ship one) · the clip's own sound · silent
   (muted autoplay) · a new score made for this style (takes longer; synthesise it in code with fixed seeds: no
   downloads, no licensed music).

If they want to remix an existing format or style, start from its files (the format folder that
`formats.py list --all` shows, or the saved style's folder that `styles.py list --json` shows) and ask only what
should change.

## 2. Three concepts, then the recipe

Propose **three concepts** as one question with previews. Each has a name, one line on the feeling, the
**signature moment** (the one thing people will remember, e.g. "the ball leaves a red fold trail") and a
tiny beat sheet:

```
0-2 s  hook: freeze on the serve, title slams in
2-9 s  rally at 1.5x, shot counter ticks
9-12 s key shot: 0.3x + red fold burst
12-15 s end card: logo + one stat
```

Make the three genuinely different (for example one safe, one bold, one unexpected), each grounded in their
answers and the brand's rules. After they pick, write the **recipe** into the style's `style.md` and `style.json`:

| Field (style.json) | Meaning |
|---|---|
| `made_for` | clip, brief, video or loop |
| `platforms`, `canvas`, `length_s` | where it goes and its main canvas |
| `mood`, `signature` | the feeling and the memorable moment |
| `structure` | the beat sheet: `[{"from": 0, "to": 2, "beat": "hook", "does": "..."}]` |
| `slots` | what each new video must supply: `[{"name": "clip", "kind": "video", "required": true, "note": "..."}]` |
| `type`, `sound` | words-on-screen treatment, sound choice and file |
| `dos`, `donts` | rules learned while designing (add to them during the stills rounds) |

Show a short summary (the beat sheet and the slots) and ask ✋ **Approve the recipe** / **Change something**.

## 3. Build and show stills

1. Pick sample content: their clip in `clips/`, or placeholder words for a brief style (say it's placeholder).
   For a clip, find real moments from the frames (a brand's clip formats may bring tools for this).
2. Make the project in `videos/<slug>-draft/`: follow the `hyperframes` workflow, run the brand bridge for
   the canvas, and `finish.py plan` for the platform's safe areas. Keep all timing data-driven from the slots so
   the template can be refilled later.
3. Run the checks (lint, check, finish `check` and `safe`), then `npx hyperframes snapshot` at 4-6 key
   moments. Look at them yourself first; fix anything broken before showing.
4. Show the stills and ask ✋ **Looks right** / **Change something** (they say what). After three rounds of
   changes, suggest either saving what works or trying a different concept, so it doesn't loop forever.

## 4. Test render and save

1. ✋ **Render a test video** (say how long it takes). Render, then `finish.py finish` for one platform and show
   the contact sheet and the video path.
2. ✋ **Save this style** / **Keep adjusting** / **Throw it away**. On save:
   `styles.py save --style <slug> --project videos/<slug>-draft --approve`. It keeps the template, the recipe and
   the approved stills; footage and brand files are left out and re-created per video.
3. Tell them: the style now appears in the front door for every future video with this brand, where it lives
   (the path `styles.py save` printed), and that sharing it means sending that folder (it goes into the other
   person's styles folder for the same brand).

## Watch out for

- A style is only reusable if its content comes from slots. Hard-coded times or words make every video the same.
- Plan every title with the text-fit numbers in the project's `frame.md` when the pack gives them; wide display
  faces overflow first.
- New effects that could pass for reality (removed players, fire) need a small honesty line on screen.
- Keep it to one signature moment. Three competing effects read as noise on a phone.
