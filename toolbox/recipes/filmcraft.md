# FilmCraft: frame-exact edits and editable timelines

**Early tool:** the first release was on 30 Sep 2026. Check every export by looking at it and measuring it.

Read before use: the tool's own `docs/agents.md` (MCP tools: `command_run`, `command_batch`, `sequence_inspect`,
`media_import`, `render_frame`). Every action is an engine command; `filmcraft-cli commands` lists 650+.

## The quick way: an edit list

```bash
FC=$(python3 <kit-to-clip>/scripts/toolbox.py path filmcraft)
node <kit-to-clip>/toolbox/helpers/filmcraft_edit.mjs "$FC" spec.json
```

```json
{"clip": "/abs/source.mp4", "out": "/abs/edit.mp4", "fcpxml": "/abs/edit.fcpxml",
 "edits": [{"from": 0, "to": 1.6667}, {"hold": 2.4}, {"from": 1.6667, "to": 3.5, "speed": 1.3093},
           {"hold": 2.2}, {"from": 3.5, "to": 12.3333, "speed": 2.2083}],
 "bitrateKbps": 8000, "loudnessLufs": -14}
```

- **Segments** are source seconds, in the order they play. The first one must start at 0 (trim the clip first).
- **A hold** freezes the first frame of the segment after it.
- **Speed** is a multiple (2 = twice as fast).
- **It prints** the exact length, frame count and plan. The `.fcpxml` opens in Final Cut Pro and Premiere for a hand
  re-cut (capability `timeline-export`). `file.exportEdl`, `exportAaf` and `exportOtio` also exist.

## When to use it rather than HyperFrames
- **Use FilmCraft when** a hold falls in the middle of a clip (HyperFrames needs the frame extracted first), or when
  speed must change exactly at a frame, or when an editor wants a timeline file.
- **Use HyperFrames when** the edit lives inside a designed composition with text and motion. Then the FilmCraft
  output becomes one `<video>` in it.

## Rules learned by testing (2026-10-08)
- **Holds before speed ramps.** After a speed change, clip starts land between frames, and a hold placed "at the
  start" misses the clip ("place the playhead over a video clip").
- **Hold at the exact start tick of the clip.** Don't add 1 tick: that leaves a 1-frame sliver, and the speed change
  then lands on the sliver.
- **Select a clip before `clip.speedDuration`,** or it says "no clips selected".
- **Always set the export range** (`range: "custom"`, `endSeconds`). FilmCraft keeps the old sequence length after
  ripple edits and otherwise exports a still tail.
- **Exports run as jobs:** pass `wait: true`.
- **`loudnessLufs: -14` measured -14.8 LUFS.** Still run `finish.py`, the real mastering gate, on the result.

## Proof
- The smoke test edits a 4 s clip into 1 s, then a 1 s hold, then 2 s at 2x. That gives exactly 3.0 s and 90 frames,
  with a freeze detected from 1 s and a valid FCPXML 1.10.
- On a real 22 s padel clip, a freeze-and-ramp plan (holds of 2.4 s and 2.2 s, speeds 1.3093 and 2.2083) matched to
  the frame.
