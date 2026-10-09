# Recorded effects (Kenney Impact, Interface and Digital packs)

**The default effects** since October 2026: real recorded sounds, CC0, placed on the motion by `effects.py` like any
other hit. The built-in synthesised effects (slam, chime, riser, whoosh) are the fallback and fill what the packs lack.
Why: the person judged the synthesised base "cheap"; recorded hits over generated music (ACE-Step) was the sound they
chose (9 Oct 2026).

| Power | Holds | Size |
|---|---|---|
| `kenney-impact` | about 105 impacts: punch, plate, metal, glass, wood, soft, plank, tin (light, medium, heavy) | about 1 MB |
| `kenney-interface` | 100 short UI sounds: click, tick, switch, toggle, select, confirmation, glass, glitch, scroll, open, close | about 1 MB |
| `kenney-digital` | 60 digital sounds: phaser sweeps up and down, power-ups, laser and tone blips | about 1 MB |

Licence: CC0 (`License.txt` in each zip). Free in commercial projects; credit is not required (you may thank Kenney in
`CREDITS.md`). Each zip is pinned by SHA-256 in its card, so a changed download is refused.

## Use

In `plan.json`, a hit of kind `file` names its power and file; `effects.py` finds it in the installed power:

```json
{ "id": "card", "at": 7.5, "kind": "file", "file": "kenney-impact:impactPlate_heavy_000.ogg", "gain": 0.9, "cue": "the drop" }
```

List a pack's files: `ls "$(python3 <kit-to-clip>/scripts/toolbox.py path kenney-impact audio)"`. Most files have
variants `_000` to `_004`: use different variants for repeated moments, so the same sound never repeats exactly.

## Which sound for which picture moment (starting points)

| Picture moment | Try |
|---|---|
| A big landing, the drop, a slam | `kenney-impact:impactPlate_heavy_*`, `impactPunch_heavy_*` |
| A card or panel locks into place | `kenney-impact:impactMetal_medium_*`, `impactWood_medium_*` |
| A frame or glass panel lands | `kenney-impact:impactGlass_medium_*` |
| A small chip, tag or word appears | `kenney-interface:tick_*`, `click_*` |
| A toggle, a choice, a "yes" | `kenney-interface:switch_*`, `toggle_*`, `confirmation_*` |
| A brand swap, a digital change | `kenney-interface:glitch_*`, `kenney-digital:phaserUp*` |
| Something powers up or builds | `kenney-digital:powerUp*` (or the built-in `riser`) |
| A sweep across the frame | the built-in `whoosh` (the packs hold no real whooshes) |

## Traps

- **Some sounds are tuned.** With a `"key"` in the plan, `effects.py` refuses a file whose notes fall outside it (for
  example `impactBell_heavy_000` sounds F#, outside A minor). Pick another file; never pitch-shift a library effect.
- **Some are very short** (`click_002` is 10 ms): raise the gain a little, or pick a longer variant.
- **Mono files** are panned by `effects.py` from the element's position, like the synthesised hits.
- The room reverb (`"room"` in the plan) applies to them too; recorded sounds already carry some space, so a lighter
  room (`{"wet": 0.12}`) usually fits better.
