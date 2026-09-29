# Motion vocabulary

Words for directing a video and what each means in a HyperFrames composition. Use them in storyboards and briefs so
"push in on the stat" means the same thing to everyone. Brand packs decide the feel (easing, durations, energy);
these words decide the move.

## Camera

| Term | What the viewer sees | How in HyperFrames/GSAP |
|---|---|---|
| Push in / pull out | The frame moves closer to or away from the subject | Scale a wrapper around the scene up or down, origin on the subject |
| Pan / tilt | The view turns sideways / up or down | Move the wrapper on x / y |
| Dolly, truck | The view travels forward, or sideways past things | Scale plus x on layers, foreground faster than background |
| Parallax | Near things move faster than far things | Separate layers, each moved by a different amount |
| Orbit | The view circles the subject | `rotationY` on a wrapper with `perspective` on the parent |
| Whip pan | A very fast pan that blurs into the next scene | A fast x move with a blur filter, the cut hidden inside it |
| Rack focus | Sharpness shifts from one layer to another | Blur one layer while the other clears |

## Cuts and transitions

| Term | Meaning |
|---|---|
| Hard cut | Straight to the next shot, on a beat |
| Match cut | The next scene starts with a shape, position or motion that matches the last one |
| Smash cut | An abrupt cut from quiet to loud (or back) for contrast |
| J-cut / L-cut | The sound of the next scene starts early / the sound of the last scene runs on |
| Cutaway | A short insert of detail, then back |
| Recolor | The scene changes colour without a cut, often by tweening a CSS variable |
| Carry | An object leaves one scene and arrives in the next, carrying the eye across the cut |

## Animation principles (the ones that matter most in motion graphics)

- **Anticipation:** a small move the opposite way before the main move.
- **Squash and stretch:** an object flattens on impact and stretches when fast; keep its volume.
- **Easing (slow in, slow out):** nothing starts or stops at full speed; the brand's curves live in `--reel-ease-*`.
- **Follow-through and overlap:** parts settle a little after the main move stops.
- **Staging:** one thing to look at at a time.
- **Secondary action:** a small supporting move, never the same idle bob on everything.

## Rhythm

- **Beat grid:** cuts and hits land on beats (at 120 BPM a beat is 0.5 s); motion fills the space between them.
- **Burst, anticipation, reveal, rest:** vary density; give the eye a still moment after a busy run.
- **Hold:** keep the end card still long enough to read (about 2 beats for a logo, longer for a call to action).

## Formats and parts

| Term | Meaning |
|---|---|
| Kinetic typography | Words that move to carry meaning or rhythm |
| Lower third | A name or caption strip in the lower part of the frame (keep it inside the platform's safe area) |
| Logo sting / lockup / end card | A short logo moment / the final logo arrangement / the closing frame with the call to action |
| Motif | The brand's reduced shape or line that returns through the video (the pack's `REEL_BRAND.motif`) |
| Animatic | A rough moving storyboard, to judge timing before polish |
| Seamless loop | The last frame flows into the first; the finish module checks the seam for looping destinations |
