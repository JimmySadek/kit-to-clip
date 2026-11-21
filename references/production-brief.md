# One current production brief

Read when starting, resuming, changing inputs or handing a video to a fresh builder. One coordinator maintains
`<work>/<job>/brief.md`; other workers return outputs and proposed changes. Do not keep competing editable plans.
The helper is Python standard library only and needs no engine, account or network.

## Start and fill progressively

```bash
python3 <kit-to-clip>/scripts/brief.py init --out <work>/<job>/brief.md --request "The user's request"
python3 <kit-to-clip>/scripts/brief.py show --file <work>/<job>/brief.md --json
python3 <kit-to-clip>/scripts/brief.py update --file <work>/<job>/brief.md --expected 1 --patch <patch.json>
```

Use the returned current revision for every later mutation. Unknown fields and invalid patches are rejected.
Objects merge; lists replace; null clears a field (or removes a named asset). `--patch -` accepts JSON from stdin.
Use the initial `show --json` record and this guide for the field structure; command `--help` describes options.
Keep meaningful insights in `decisions`, facts and proposed copy distinguishable, and unanswered items in
`open_questions`. An unchosen field remains unchosen; do not fill it with an invented brand, style or approval.

Example patch for a partially decided, unbranded narrated job:

```json
{
  "route": "idea",
  "destination": {"platform": "youtube", "width": 1920, "height": 1080, "duration_seconds": 28},
  "brand": {"mode": "original"},
  "audio": {
    "timing_driver": "narration",
    "voice": {"choice": "supplied", "path": "voice.wav", "duration_seconds": 27.4},
    "music": {"choice": "none"},
    "effects": {"choice": "none"}
  },
  "open_questions": {"style": "Choose the visual reference"}
}
```

Paths can refer to supplied assets outside the work folder, but the helper reads only explicitly named files and
never scans those folders or copies them into the public skill. Relative paths resolve from the brief's folder.
Keep original prompt/code, image provenance and actual audio versions linked as named project inputs. Atlas source
belongs in a user-chosen private collection. Put structured provenance in `style.reference`: `catalogue_id`,
`origin`, `prompt_file`, `code_file`, `source_root`, `source_sha256` and `permitted_use`. The selected prompt/code
files are fingerprinted; `source_root` is a pointer, never a folder scan. `source_sha256` records the publisher
prompt identity and is verified by `catalogue.py load`, not by the brief helper. Do not confuse it with a
file-by-file input fingerprint. Record the image's creative role in `role` and its source/resolution evidence in `notes`.
Use `assets.<id>.notes` for documentary provenance/licences and `destination.notes` for administrative notes.
Creative changes go in the asset's `role`, actual destination fields, `style.notes` or `brand.notes`, so the helper
can reopen the right approvals. Updating provenance, `style.reference.origin` or `permitted_use` keeps creative
approvals; permission to use the source must still be resolved before handing it off.

For named-brand work, complete the required directive in `brand/README.md` before layout. Record its path in
`decisions.brand_directive`; use `brand.mode: full` and the real `brand.kit`. Register the directive and each
governing skill/guide file as separate named assets with `role: "brand directive"`. This fingerprints actual
inputs and reopens visual approvals when they change. A kit pointer or a handoff listing brand colours alone
does not establish a complete directive. The helper tracks named file versions; it cannot prove the agent
read the guides, extracted their rules correctly or produced recognisable branding. The coordinator and
independent reviewer must check those outcomes.

The Markdown includes readable sections and one authoritative JSON payload. Use the helper to record decisions.
When a person has manually edited the human summary, the helper refuses mutation (exit 6), leaves the file intact
and flags the handoff. Carry the insight into a real patch, then use `update --summary-reconciled` with that patch;
the replaced human text stays in history. Never discard an insight merely because it was outside the JSON payload.
Changing the authoritative JSON by hand breaks its integrity checksum and is refused. This detects accidental
edits, not hostile access by the file's owner. New/updated brief files are private to the local user.

## Record actual approvals

```bash
python3 <kit-to-clip>/scripts/brief.py approve --file <work>/<job>/brief.md --expected N --gate layout --state yes --note "The user's actual approval words" --evidence <reviewed-layout-file>
```

The note is evidence of a real decision, not permission to invent one. Gates are layout, stills, voice-choice,
music-choice, render and listening. Record no/n/a honestly; a sound gate is n/a only when that sound is absent.
Effects-only video still has sound and needs listening. Voice, music and effects start unchosen. Explicitly
declare each absent track as `none`; silence is never inferred from an empty field. Stills require current layout approval; final render
requires stills and the needed approved voice/music versions. A short preview is a separate scope and never closes
the final film's approvals. Keep separate per-job briefs for a concept sample and the production film if needed.
Changing a track to `choice: none` clears its active file/duration (and music tempo) while preserving the original
file and history. Supplying a file together with `none` is refused. Documentary provenance alone does not select
a visual style; use a name, saved reference, catalogue identifier or selected prompt/code file.

Input changes invalidate dependent approvals with reasons. Narration/script changes affect voice and timing;
background music changes do not automatically erase the visual layout. Notes/open questions alone do not erase
creative approvals. Old records and outputs remain available as superseded evidence.
Name implementation files in `assets` with exact `role: "source"` after layout and before stills. Their changes
affect stills/render/listening, while normal creative assets still affect layout. If an edit actually changes the
planned layout, reopen that layout as well. Only `brand.kit` may be a directory pointer; actual source, footage,
script, prompt and audio inputs need individual files. The helper checks named files, not their media contents.

## Resume or hand off

```bash
python3 <kit-to-clip>/scripts/brief.py handoff --file <work>/<job>/brief.md --expected N
```

The read-only snapshot reports the exact revision/digest, input file fingerprints, open questions and gates,
missing/changed inputs and the next work boundary. It can describe an early layout-stage job without final
approvals. A final build also needs its route, screen dimensions/duration, timing driver, brand mode, story/style
or source-footage intent, all sound decisions and required files resolved. A historical gate note alone does not
make an incomplete or stale job ready to render. It never starts a session or renders anything. A fresh builder gets this snapshot, the brief and only
the selected prompt/code and required assets. Compare returned work with the current revision and file hashes.

Never force a stale revision: reread and reconcile. A concurrent writer holds a local lock only during mutation;
readers continue to work. Do not break a lock merely because it looks old. If a crashed writer left a lock, verify
that it stopped and preserve the brief before any authorized cleanup. No background service is introduced.
