# Local style gallery

Use discovery inside `video-journey.md`, not as a mandatory format/brand menu. Consider personal references
alongside library references and explain recommendations. Ask only for decisions missing from the request.
Create-new stays directly available. Browsing needs no engine, account, brand or video workspace.

## Recommend, then let the person explore

Read the compact catalogue only at style discovery. `catalogue/index.json` describes all 86 Atlas references in
14 families, with our tags, original-preview links and source hashes. Fit is inferred from publisher descriptions;
it is not audience research or proof that every reference has been rebuilt successfully here. The source is not
bundled. Matching names in old Kit to Clip looks do not mean the implementations are identical.

```bash
python3 <kit-to-clip>/scripts/catalogue.py search paper diagrams --limit 15 --json
python3 <kit-to-clip>/scripts/catalogue.py search paper --styles-root <styles-folder> --json
python3 <kit-to-clip>/scripts/catalogue.py list --json
python3 <kit-to-clip>/scripts/catalogue.py families --json
python3 <kit-to-clip>/scripts/catalogue.py show library:<id> --json
```

Search gives transparent keyword/tag matches. The director considers the brief, constraints and previews, then
explains the strongest candidates in ordinary language. Do not present a keyword rank as creative judgment or
force an unrelated match. Fifteen is a flexible first group. Offer more, the whole catalogue and a new direction.
Approved personal references can join recommendations; drafts remain visible and need development/approval.

## Load one chosen source

After selection, use the explicitly supplied private collection. Do not read all prompts during discovery.

```bash
python3 <kit-to-clip>/scripts/catalogue.py load <id> --source-root <private-source-folder> --json
```

This checks the chosen package's identity and original prompt hash before returning its rebuilding instructions,
style code, shared drawing helpers and sound kit. Keep the original export untouched. A missing file, changed hash
or unsafe path is an unresolved input, not permission to pick another style. Private access does not establish
public redistribution rights. Record source identity/hash, permitted use and selected project inputs in `film.json`.
Do not copy Atlas prompts, drawing code, media or assets into the distributed skill.
Then read `reference-resources.md` for local fonts, sound and other selected-source dependencies. A successful
load is source availability, not proof of production compatibility.

## Browse the local page

The page has **Styles**, **My Styles** and a secondary **Legacy recipes** tab. It initially shows 15 cards, with
topic/family filters and more/all controls. `--query` can start from the brief's topic or visual direction. The
full catalogue remains reachable. Existing local samples and clearly labelled drafts keep their own status.
The original publisher's style-demo and explainer links open only when chosen. No remote media is fetched during
browsing; a link does not claim an approved local render. My Styles shows earlier brand context without applying
it to the next video. No existing collection is migrated.
Recorded reviewed personal stills can be reused locally when their preview hash still matches. A changed or missing
still is flagged, and the page never opens editable code to produce a replacement during browsing. Associate video
samples explicitly with the manifest below. Source integrity/readiness is checked after selection with the saved
reference's handoff, rather than reading every source in the collection.

The generator uses only Python's standard library (Python 3.9 or newer). Browsing existing samples needs no engine
setup or video workspace. When an engine is already available, source `scripts/env.sh` as usual. List the available ids without writing:

```bash
python3 <kit-to-clip>/scripts/gallery.py --project <repo> --list
```

Build into a **new folder**, normally `<work>/<job>/gallery`. It refuses to overwrite an existing page.
Pass only a brand already chosen through the front door. Omitting `--brand` displays that branding is optional.

```bash
python3 <kit-to-clip>/scripts/gallery.py --project <repo> --query "paper diagrams" \
  --samples <work>/<job>/samples.json --out <work>/<job>/gallery
```

`--styles-root <folder>` reads saved styles directly from that folder when the job uses an explicit collection.
Otherwise discovery is the same as `styles.py list`. `--samples` is optional: entries without media show
"No sample yet" and remain discoverable. Serve the generated folder with the host's local preview server and
open it in the host's browser. Do not publish it.

## Associate samples explicitly

Keep `samples.json` next to its local media. Run `--list` first for ids. A minimal example:

```json
{
  "schema": 1,
  "samples": [
    {"id": "look:glass", "kind": "neutral-demo", "poster": "glass.png"},
    {"id": "look:pixel", "kind": "brand", "brand": "acme", "poster": "pixel.png", "video": "pixel.mp4"}
  ]
}
```

- A **neutral-demo** is visibly labelled "Neutral demo", whatever request brand is selected. Never describe it as
  rendered in that brand. The sample's palette is illustrative, not authority for the next video.
- A **brand** sample needs its brand id and is shown only when that id matches the chosen request brand.
- Images can be PNG, JPEG or WebP. Videos can be MP4 or WebM. Use relative paths inside the manifest's folder.
  Remote paths, paths escaping that folder, duplicate associations and unknown ids are refused. Missing local
  media leaves the entry without that preview. Media is copied into the new gallery; source files stay untouched.
- A poster without a video says **Still preview**. A video plays only on click, with native controls. Tall samples
  retain their aspect ratio inside the preview area. A branded clip must be suitable for local viewing under the
  project's own rules before it is associated.
- Format and style status stays visible. A preview never promotes a trial or draft to approved. A draft saved
  style's request continues its workshop; retired or broken entries cannot start a request.

**Copy request** copies a plain-language request to paste into the chat. Branding is optional, and an explicit
original/unbranded choice already answers that decision. If clipboard access is unavailable, the page presents
selectable text. Nothing is sent, built or saved. Pass `--brand <id>` only for an already chosen request brand.

## Making new samples

Reuse existing approved samples when they fit. If new samples are needed, plan their layout and sample copy,
then follow the approval stops in `SKILL.md` (✋ storyboard, then ✋ final film). A gallery request does not authorize a batch render.
Silent samples must have no audio track; sound samples also get the ✋ music pick on the built picture.
Check the actual stills and inspect the gallery on desktop and phone before presenting it. Keep sample sources,
stills and future rendered files in the owning project's work area, outside the public skill package.

The gallery idea and four general look categories were inspired by
[Futurepedia's tutorial](https://www.youtube.com/watch?v=Ge1B-Ok1Pfk). This implementation includes none of its
prompt collection, drawing code, samples or assets. The metadata and external preview links identify the original
references; integration/runtime validation is recorded separately from catalogue availability.
