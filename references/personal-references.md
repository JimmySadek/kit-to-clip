# Save and reuse a personal treatment

Saving is optional after the person reviews the finished video and wants this treatment as a future starting
point. Do not require a title or author before making an ordinary video. Use the existing styles registry; never
create another preference store or silently migrate earlier styles.

## Prepare the reviewed source while building

Name the actual editable files in `film.json` `inputs`, one entry each, before the ✋ final film: the entry page and
the JS/CSS it needs (`"kind": "source"`), and the chosen images, fonts and sounds with their provenance in `note`.
A folder pointer does not name its children. Paths are relative to the video folder.

```json
{
  "inputs": [
    {"kind": "source", "path": "project/index.html", "note": "the entry page"},
    {"kind": "source", "path": "project/scene.js", "note": "the scene timeline"},
    {"kind": "image", "path": "project/assets/paper.png", "note": "drawn for this film; CC0"}
  ]
}
```

An entry may also carry `sha256`; capture then checks the file still has those bytes.

## Capture after the optional save decision

Ask only for a missing title; author is optional. The coordinator records useful tags and reusable medium,
motion/pacing instructions, separately from this story's content and brand. The current helper captures finished
video files; existing legacy template commands remain available for other saved motion formats.

```bash
python3 <kit-to-clip>/scripts/styles.py --root <collection-parent> capture \
  --film <video>/film.json --project <video>/project --title "Layered paper" \
  --source index.html --source scene.js --tag paper --tag gentle \
  --medium "Layered paper and soft shadows" --motion "Gentle drift and cut-paper reveals" \
  --finished-output <video>/project/renders/final.mp4 \
  --approval-note "The person's actual words approving the finished output for saving" \
  --preview <video>/project/snapshots/reviewed.png
```

`--root <collection-parent>` uses its `styles/` folder. Omitting it follows the existing studio/repository
discovery; a new neutral reference defaults to the repository's `reels/styles`. `--brand` can choose a brand pack's
storage location, never the next video's brand. Do not save inside the distributed skill.

Capture needs the person's ✋ final film yes in `film.json` `approvals.final` (they watched and heard the finished
film). Rendering is not a yes, and a passing loudness check is a measurement, not consent. A file named in `inputs`
that changed after the finished video was made (or no longer matches its `sha256`) refuses the whole save: render
and show the film again. The explicit finished-file hash and save-approval words record the later decision to keep
the treatment; never invent those words. Sources/assets must be named in `film.json` `inputs`, so an unrelated
project cannot become approved just by pointing at another film.

An older video with a `brief.md` from `scripts/brief.py` still saves with `--brief <job>/brief.md --expected N`
instead of `--film`. That route needs the brief's current render yes, listening for any sound, and build files named
in the brief's `assets` with `role: "source"`.

Only explicitly selected source/assets and covered static dependencies are copied. Use `--asset <relative-file>`
for chosen resources. Missing/uncovered dependencies are reported, not silently treated as portable. Private
original prompt/code/source-root contents, secrets, hidden work folders, node_modules, vendor trees and large
renders are excluded. The finished video is fingerprinted at its original location, not copied into the reference.
Reviewed stills can be retained; other stills remain labelled preview-only. Nothing replaces an existing slug.

The new `style.json` has `kind: reference`, tags/instructions, a source/resource manifest, previews, provenance and
`original_context`. That context includes the previous story/brand; it is not an instruction to use them again.
Static dependency checks cannot discover every path assembled by code. Read the portability report honestly.

## Select and rebuild later

```bash
python3 <kit-to-clip>/scripts/catalogue.py search paper --styles-root <collection-parent>/styles --json
python3 <kit-to-clip>/scripts/styles.py --root <collection-parent> handoff --style layered-paper
```

Catalogue search reads metadata only. An approved record is eligible for recommendation; actual source files are
checked on selection. The read-only handoff lists source paths, hashes, reusable instructions, original context,
resource limits and missing/changed editable files. Resolve those before building. A missing or changed original
finished video is a **provenance warning**, not a dependency of an intact saved source snapshot, so archiving an
old video does not erase the reusable treatment.

Start a fresh `film.json` for the new story and choose original look, palette adaptation or full branding afresh.
Rebuild the reference; it has no promised content slots. `styles.py new` intentionally refuses reference-kind
records and directs you to the fresh builder. Legacy records without `kind` remain templates, with their existing
`init`, `save`, `new` and `refs` commands. Reapply a legacy template's stored brand only when explicitly wanted.
