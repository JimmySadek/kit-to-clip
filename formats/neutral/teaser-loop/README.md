# Teaser loop (neutral format, draft)

A still teaser brought to life as a seamless loop, for animated GIFs (LinkedIn, email, web) and muted autoplay.
It **opens on the finished layout**, so the first frame and the thumbnail read at once, then only a few things move:
a band of light travels outward along the background art from its focus (or the art breathes, for video), an accent
ring pulses, the accent line draws under the focal word with skip-ink and sweeps away, and the last frame flows
back into the first. Everything is periodic, so the loop has no seam.

First made for a brand's LinkedIn ad teaser (28 Sep 2026): a still with a headline, a product device and background art.

## The journey

1. **✋ The reference.** When the job adapts an existing piece (a live post, a still), capture it and measure it:
   where the headline, focal word, logo and media sit, the background colour, how dense the background art is.
2. **Find the brand's own pictures** with `brand/scripts/assets.py search <kit> <words>`, then **look at every picture**
   with `assets.py sheet <kit> --out <dir>` (names mislead; office templates hide pictures). Copy what you use into
   the job's clips folder with a `SOURCES.md` (template, inner path, sha256).
3. **Slots** (`slots.json`, limits in `format.json`): `headline` with `*focal*` and `|` line breaks; `background` and
   its `background_crop` (fractions; values past 0-1 let the canvas colour show), `background_feather` (raise the side
   where the picture ends inside the canvas), `background_opacity`, `focus`; `media`, `media_box`, `media_edge`;
   `logo_box`, `headline_box`, `headline_size`, `headline_leading`; `background_motion` (`wave` for GIFs, `breathe`
   for video); `duration` (6 to 12 s).
4. **Build:** `python3 build.py --brand <id> --slots slots.json --out <videos>/<job> --canvas 1080x1080`.
5. **Checks:** `npx hyperframes lint`, `finish.py check`, `finish.py hook`. Snapshot the loop at 0, 1, 2, 3, 5 and
   the last frame, and **measure the first frame against the reference** (positions within a few pixels, the
   background colour, the density of the art). Look for seams, darkened areas and clipped lines yourself.
6. **✋ Stills**, then render: `npx hyperframes render -o renders/<job>.mp4 --quality delivery`.
7. **Deliver:** `finish.py loop <render> --out <deliveries>/<job>/<platform> --export gif,mp4,webm --gif-profile linkedin-gif`
   (or `gif` for chat and docs). It fails on a visible seam, a GIF over the size or frame cap, or a missing encoder.

## Why the defaults are what they are

- **GIFs store only changed pixels.** Moving the whole background (`breathe`) changed every pixel and made a 7.6 MB
  GIF even at 360 px; the `wave` keeps the art still and lights only a moving band of dots: 3.8 MB at 720 px.
- **The canvas takes the picture's own edge colour** (sampled from its border), so feathered or faded art never
  shows a line.
- **The wave layer adds light only**: a filter subtracts the art's background colour and turns brightness into
  opacity, so no pixel can get darker (measured: 0 darker pixels in every frame of the first teaser made with it).
- **The underline is a real underline** on a transparent copy of the focal word, so it skips descenders.
