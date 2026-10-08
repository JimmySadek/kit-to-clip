# Brand reel (neutral format, trial)

A 24-beat brand reel (12 s at 120 BPM) for any brand whose video pack has token contract v1: the brand's motif
arrives, steps aside for a headline told word by word, turns beside a stat that counts up over the accent rule, marks
three proof points, spins through a short flurry and lands as punctuation next to the logo. Every colour, font, curve
and duration comes from the pack's `--reel-*` tokens, so the same build looks like each brand on that brand's own
pack.

```bash
python3 build.py --brand <name> --slots slots.json --out <reels>/videos/<job> --platform tiktok [--canvas 1080x1920]
```

| Slot | Limit | What to put |
|---|---|---|
| `headline` | 32 characters | One statement, 3 to 6 words; the last word takes the accent |
| `stat_value` | 7 | A number you can source (`12`, `3x`, `98%`); it counts up from zero |
| `stat_label` | 36 | What the number measures |
| `points` | 3 items, 26 each | Three short proof points |
| `tagline` | 36 | The line under the logo |

Slots over their limits stop the build before anything is written. `--platform` keeps the layout inside that
destination's safe area (`finish/profiles.json`). `--music` takes a track already cut to `--bpm`.

**Variety:** three devices change per video: the motif's entrance (draw, drop, spin), the headline style (rise, mask,
scale) and the flurry (invert, recolor; calm brands get a soft accent wash). `--variant auto` (the default) picks a
set that shares at most one device with each of the last three brand reels for the same brand in the same folder,
and `.reel-format.json` records it. Energy from the pack (`calm`, `steady`, `punchy`) scales every duration.

**Checks** before offering a render: `npx hyperframes lint`, `finish.py check`, `finish.py safe --platform <p>`, then
look at stills. Status is trial (offered as "new"; the maintainer decides when it is approved): tried on a dark, punchy brand with a shape motif and a light test brand (calm, line
motif) on 28 Sep 2026; it is not offered in the front door until approved.
