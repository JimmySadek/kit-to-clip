# EffectCraft: layered motion, SVG to layers, Lottie export

**Early tool:** the first release was on 1 Oct 2026 and versions change daily. Check every result by looking at it.

Read before use: the tool's own `docs/agents.md` and `docs/control-protocol.md` (links on the card). Every action is
an engine command with JSON parameters. `effectcraft-cli commands --filter <word>` finds one, and
`effectcraft-cli describe <id>` shows its parameters.

```bash
EC=$(python3 <kit-to-clip>/scripts/toolbox.py path effectcraft)
```

## SVG to a draw-on Lottie (tested on 0.6.0, 2026-10-08)

```bash
"$EC" --empty --save-as p.ecproj --json run comp.new '{"name":"m","width":512,"height":512,"frameRate":30,"duration":2}' \
      file.import '{"paths":["/abs/path/mark.svg"],"addToComp":true}'
"$EC" --project p.ecproj --save --json exec layer.create --params '{"op":"shapesFromVector","layers":["#1"]}'
"$EC" --project p.ecproj --save --json exec edit.clear --params '{"layers":["#2"]}'          # delete the SVG picture layer
"$EC" --project p.ecproj props m '#1' --flat | grep /path/path                               # one group per SVG element
"$EC" --project p.ecproj --save --json run layer.addShapeItem '{"layer":"#1","kind":"trim","group":"contents/group"}' \
      prop.addKey '{"layer":"#1","path":"contents/group/contents/trim/end","time":0,"value":0}' \
      prop.addKey '{"layer":"#1","path":"contents/group/contents/trim/end","time":1.5,"value":100}'   # repeat per group
"$EC" --project p.ecproj --json exec file.exportLottie --params '{"comp":"m","path":"/abs/path/mark.json"}'
```

## Traps found by testing
- **The SVG stays inside the Lottie as a picture** unless you delete the imported layer (`edit.clear` on `#2`, after
  `shapesFromVector`). Hiding it does not help. Without this, the full static logo sits under the draw-on. The smoke
  test checks for `data:image` in the export.
- **Group order is reversed.** `contents/group` is the *last* element of the SVG, `group#2` the one before, and so on.
  Add Trim Paths to every group you want drawn, and match them by checking the props and stills, never by position.
- **Paths you create yourself need `"space":"comp"`** in `shape.newPath`, or they land shifted by half the canvas.
  The SVG route places paths correctly by itself.
- **JSX scripting cannot create paths yet** (`unknown kind 'path'`). Use the command route (CLI `run` / `exec`, or MCP
  `batch` with `$N.key` references).
- **Easing:** `add_keyframe` with `"interpolation":"easyEase"` (MCP), or `keys.select` then `keys.easyEase`.
- **Hand-drawn input:** HyperFrames-style polylines (70+ points per loop) import as many vertices. Run VectorCraft's
  `object.path.simplify` first (227 points became 27, 20 of them curves).
- **Taper** (`stroke/taper/startLength`, `startWidth` around 10) gives brush-like ink, but Lottie drops it with the
  warning "no Lottie equivalent". Taper is for videos rendered by EffectCraft, not for Lottie files.

## Proof
- **Playback:** an exported 2.3 KB Lottie, played with lottie-web inside a HyperFrames render, matched EffectCraft's
  own frames at 0.5, 1.0 and 1.5 s.
- **Rendering:** `"$EC" --project p.ecproj render --comp m --format prores --prores 4444 --channels rgba --out o.mov`
  gives transparent ProRes in under a second for 2 s at 1080x1350.
