# Cutouts and people masks (HyperFrames remove-background)

Runs on this computer. First use downloads the model (`u2net_human_seg`, about 170 MB, Apache-2.0) and a runtime
(`onnxruntime-node`, MIT) into `~/.cache/hyperframes`, once. On Apple silicon it picks CoreML automatically.

```bash
npx hyperframes remove-background <photo.png|clip.mp4> -o cut.png            # a photo: transparent PNG
npx hyperframes remove-background clip.mp4 -o player.webm --quality best      # a clip: transparent WebM (VP9 alpha)
npx hyperframes remove-background clip.mp4 -o player.mov                      # ProRes 4444 for editors
npx hyperframes remove-background clip.mp4 -o player.webm -b plate.webm      # plus the background with a hole
```

## Uses
- **Text behind the player:** stack three layers in the composition:
  1. the original clip
  2. the title
  3. the transparent `player.webm` cut from the same clip, with the same `data-start` and `data-media-start`

  The title then passes behind the person. Keep all three on the same timing, or the cutout drifts.
- **Spotlight:** dim or blur the original, and put the cutout on top at full brightness.
- **Sticker look:** a cutout photo with a white stroke (CSS `filter: drop-shadow(...)` stacked) on a brand-colour card.

## Lessons (tested 2026-10-08 on a padel still, 810x1080)
- **It finds people, not products.** The model is trained on human segmentation. It took the main player and his
  paddle cleanly in 0.6 s, and left out the far players. For a product, a logo or a pet, use the `rembg` card (general
  objects model `isnet-general-use`, below) or say the cutout may be rough.
- **Check the edges at full size before using it.** Fast motion blurs edges, so look at one frame from the fastest
  moment at 100%.
- **The background plate (`-b`) is hole-cut, not filled.** Always put something under it.

## Products, logos, objects, pets: the `rembg` card

```bash
PY=$(python3 <kit-to-clip>/scripts/toolbox.py path rembg python)
"$PY" <kit-to-clip>/toolbox/helpers/rembg_cutout.py product.jpg cut.png                    # isnet-general-use (objects)
"$PY" <kit-to-clip>/toolbox/helpers/rembg_cutout.py pet.jpg cut.png --alpha-matting        # fur and hair: softer edges
```

- **The helper prints how much of the picture it kept.** It exits 3 when almost nothing or almost everything was kept,
  which means the model did not find a subject. Then say so and use the fallback.
- **Clips:** for a person in a clip, use HyperFrames above (video in, transparent video out). For an object in a clip,
  cut out one still per hold, or use the `video-mask` power when it is added.
- **Tested 2026-10-08:** a 200x200 box on a 640x480 card came out as exactly the box (13% kept). The model
  (170 MB, Apache-2.0) downloads once into `<engine>/tools/rembg/models`.
