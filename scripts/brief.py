#!/usr/bin/env python3
"""Kit to Clip's production brief: one durable brief.md per video, so a job survives a crash, a new session or a builder.

  brief.py init    --out <work>/<job>/brief.md --request "<what the person asked for>"
  brief.py update  --file <brief.md> --expected N --patch <patch.json | ->  [--note "<why>"] [--summary-reconciled]
  brief.py approve --file <brief.md> --expected N --gate <gate> --state yes|no|n/a --note "<the person's words>"
                   [--evidence <file the person reviewed>]
  brief.py show    --file <brief.md> [--json]
  brief.py handoff --file <brief.md> --expected N        JSON for a builder; reads only, never renders

ONE FILE. brief.md is a readable Markdown summary followed by a fenced JSON block between two marker lines. The JSON
block is the only source of truth; the summary above it is generated from the data on every change.
  Seal: the data carries "seal": "sha256:<hex>" over its canonical JSON (sorted keys, no spaces, without the seal).
  Every read checks it, so a hand edit to the data is refused instead of silently skipping the revision and approval
  rules. This catches accidents; it is not access control (the owner can always rewrite their own file).
  Summary: if the readable text differs from the generated one (blank lines aside), reads still work and the handoff
  flags it, but changes are refused (exit 6) until the person's words are carried into the data, e.g. into
  decisions, with update --summary-reconciled. That update keeps the hand-written lines in the history.

REVISIONS. Every change needs --expected <current revision> and adds one. A stale revision changes nothing (exit 3).
Writers take <brief.md>.lock (created exclusively, removed after the write) and replace the file atomically, so two
writers holding the same revision cannot both succeed. A lock left by a crashed writer is never broken automatically:
when no other writer is running, delete it by hand. KIT_TO_CLIP_BRIEF_LOCK_WAIT sets the seconds to wait (default 10).
init publishes a complete file in one step and never replaces an existing one. The brief is private (mode 600).

PATCHES are JSON objects with any of: request, route, destination, story, style, brand, assets, audio, decisions,
open_questions. Objects merge recursively, lists are replaced whole and null clears a field (an enum goes back to
"unchosen"; a named entry such as an asset is removed from the brief, its file is never touched). Anything unknown
or of the wrong type is refused and the file is left as it was. Fields, all optional:

  request         text (never empty)
  route           idea | footage | mixed | unchosen
  destination     platform, format, aspect, notes: text; width, height: whole number > 0; fps, duration_seconds: > 0
  story           summary, script, notes: text; onscreen: text or list of text; beats: list of text;
                  script_file: path
  style           name, saved_style, notes: text
                  reference: {catalogue_id, origin, permitted_use: text; prompt_file, code_file: path (fingerprinted);
                              source_root: path (a folder pointer, never read or scanned);
                              source_sha256: 64 hex characters, as recorded by the source}
  brand           mode: unchosen | original | palette | full; id, name, notes: text; palette: list of text; kit: path
  assets          {<id>: {path: path, role: text, notes: text}}   ids are letters, digits, dot, dash, underscore
                  (write image provenance, prompts and licences in the asset's notes)
                  role exactly "source" marks editable build code (index.html, scene.js, CSS) for the approved
                  layout: fingerprinted for stills and render, but it does not reopen the layout
  audio           timing_driver: narration | music | visual | footage | unchosen
                  voice:   {choice, path, details, duration_seconds}
                  music:   {choice, path, details, bpm, duration_seconds}
                  effects: {choice, path, details, duration_seconds}
                  choice is none | supplied | guided | generated | unchosen (a new brief: unchosen, never "silent")
  decisions       {<id>: text}       what was decided and why (notes: changing these keeps approvals)
  open_questions  {<id>: text}       null removes a question once it is answered

Paths are local files (a relative path is read from the brief's folder). They are fingerprinted (SHA256) when an
approval is recorded and again on every handoff; nothing is copied, a named folder is never scanned and a special
file (pipe, device) is reported, not read. Only brand.kit may name a folder; any other input that is a folder is
reported as "directory" and blocks the render.

GATES record the person's decision; this script never grants one. --state n/a is only for a sound that is absent.
  layout                         -
  stills                         needs layout yes
  voice-choice / music-choice    yes needs a chosen source (not unchosen/none) whose named file exists;
                                 n/a needs that choice to be none
  render                         needs layout and stills yes, voice-choice and music-choice yes unless that sound is
                                 none, a declared effects choice (none is fine) and every named file present
  listening                      needs render yes; n/a only when voice, music and effects are all none
                                 (effects have no choice gate of their own: listening is where they are heard)
A record counts only while its own inputs are unchanged AND it still passes these same checks against the records
before it, so a stale layout makes stills, render and listening stale too. Any new decision on a gate reopens the
gates after it (a new render yes reopens listening). A preview never closes render or listening.

WHAT A CHANGE REOPENS (older records are kept as "invalidated" with the reason, never deleted). A first choice
reopens approvals that already exist just like a replacement does.
  visual:  request, route, destination, story (not the script), style, brand, assets -> layout, stills, render, listening
           (an asset switching to or from role source counts here too)
  source:  an asset with role source added, changed or removed -> stills, render, listening
  voice:   story.script, story.script_file, audio.voice      -> voice-choice, layout, stills, render, listening
           (only declaring "no voice" where none was set)    -> voice-choice, render, listening
  music:   audio.music                                      -> music-choice, render, listening
                                                               (+ layout, stills when the music drives the timing)
  effects: audio.effects                                    -> render, listening
  timing:  audio.timing_driver                              -> layout, stills, render, listening
  notes:   decisions, open_questions, assets.*.notes        -> nothing
A named file whose bytes changed (or went missing) since an approval makes that approval stale in the handoff by the
same map, and an approval's own --evidence file going stale makes that approval stale.

HANDOFF is allowed at any stage (a layout-stage builder gets one). "unresolved" lists everything a final render still
needs: route, canvas (aspect, or width and height), duration, timing driver, brand mode, a story and a style (idea and
mixed routes) or named footage (footage and mixed routes), declared voice/music/effects choices, the actual file for
every sound that is not none, a file for every source asset, present input files, no stale approval and a
reconciled summary. "may_render" is true
only with a current render yes and nothing unresolved.

Exit codes: 0 done, 1 invalid input or brief, 3 stale revision, 4 another writer holds the lock, 5 gate refused,
6 the readable summary was edited by hand and must be reconciled first.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import errno
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = "kit-to-clip-brief/2"
NAME = "brief.md"
BEGIN = "<!-- kit-to-clip-brief data: the JSON below is the brief; change it with brief.py -->"
END = "<!-- /kit-to-clip-brief data -->"

ROUTES = ("idea", "footage", "mixed", "unchosen")
BRAND_MODES = ("unchosen", "original", "palette", "full")
TIMING = ("narration", "music", "visual", "footage", "unchosen")
SOUND_CHOICES = ("none", "supplied", "guided", "generated", "unchosen")
SOUNDS = ("voice", "music", "effects")
GATES = ("layout", "stills", "voice-choice", "music-choice", "render", "listening")  # also the dependency order
STATES = ("yes", "no", "n/a")
PATCHABLE = ("request", "route", "destination", "story", "style", "brand", "assets", "audio", "decisions",
             "open_questions")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SEAL_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_TEXT = 20000

VISUAL_GATES = ("layout", "stills", "render", "listening")
SOURCE_ROLE = "source"  # an asset with exactly this role is editable build code (index.html, scene.js, CSS)
AREA_GATES = {
    "visual": VISUAL_GATES,
    "source": ("stills", "render", "listening"),
    "voice": ("voice-choice",) + VISUAL_GATES,
    "voice-absent": ("voice-choice", "render", "listening"),
    "music": ("music-choice", "render", "listening"),
    "effects": ("render", "listening"),
    "timing": VISUAL_GATES,
    "notes": (),
}
FILE_AREAS = ("visual", "source", "voice", "music", "effects")
DOWNSTREAM = {
    "layout": ("stills", "render", "listening"),
    "stills": ("render", "listening"),
    "voice-choice": ("render", "listening"),
    "music-choice": ("render", "listening"),
    "render": ("listening",),
    "listening": (),
}

OK, INVALID, STALE, BUSY, REFUSED, RECONCILE = 0, 1, 3, 4, 5, 6


class BriefError(Exception):
    code = INVALID


class StaleRevision(BriefError):
    code = STALE


class Busy(BriefError):
    code = BUSY


class GateRefused(BriefError):
    code = REFUSED


class NeedsReconcile(BriefError):
    code = RECONCILE


# --- schema --------------------------------------------------------------------------------------------------------

def _text(value, where, allow_empty=True):
    if not isinstance(value, str):
        raise BriefError(f"{where} must be text")
    if "\x00" in value or len(value) > MAX_TEXT:
        raise BriefError(f"{where} has a NUL character or is longer than {MAX_TEXT} characters")
    if not allow_empty and not value.strip():
        raise BriefError(f"{where} must not be empty")


def _path(value, where):
    _text(value, where, allow_empty=False)


def _number(value, where, whole=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BriefError(f"{where} must be a number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value <= 0:
        raise BriefError(f"{where} must be finite and greater than 0")
    if whole and not (isinstance(value, int) or float(value).is_integer()):
        raise BriefError(f"{where} must be a whole number")


def _text_list(value, where):
    if not isinstance(value, list):
        raise BriefError(f"{where} must be a list of text")
    for i, item in enumerate(value):
        _text(item, f"{where}[{i}]")


def _text_or_list(value, where):
    if isinstance(value, list):
        _text_list(value, where)
    else:
        _text(value, where)


def _sha(value, where):
    if not isinstance(value, str) or not SHA_RE.match(value):
        raise BriefError(f"{where} must be a SHA256 written as 64 hex characters")


def _enum(options):
    def check(value, where):
        if value not in options:
            raise BriefError(f"{where} must be one of: {', '.join(options)}")
    check.default = "unchosen"
    return check


TEXT, PATH = _text, _path
POS = _number


def WHOLE(value, where):
    _number(value, where, whole=True)


SOUND = {"choice": _enum(SOUND_CHOICES), "path": PATH, "details": TEXT, "duration_seconds": POS}
REFERENCE = {"catalogue_id": TEXT, "origin": TEXT, "prompt_file": PATH, "code_file": PATH, "source_root": PATH,
             "source_sha256": _sha, "permitted_use": TEXT}
SPEC = {
    "request": lambda v, w: _text(v, w, allow_empty=False),
    "route": _enum(ROUTES),
    "destination": {"platform": TEXT, "format": TEXT, "aspect": TEXT, "width": WHOLE, "height": WHOLE, "fps": POS,
                    "duration_seconds": POS, "notes": TEXT},
    "story": {"summary": TEXT, "onscreen": _text_or_list, "beats": _text_list, "script": TEXT, "script_file": PATH,
              "notes": TEXT},
    "style": {"name": TEXT, "saved_style": TEXT, "notes": TEXT, "reference": REFERENCE},
    "brand": {"mode": _enum(BRAND_MODES), "id": TEXT, "name": TEXT, "palette": _text_list, "kit": PATH,
              "notes": TEXT},
    "assets": ("map", {"path": PATH, "role": TEXT, "notes": TEXT}),
    "audio": {"timing_driver": _enum(TIMING),
              "voice": dict(SOUND),
              "music": dict(SOUND, bpm=POS),
              "effects": dict(SOUND)},
    "decisions": ("map", TEXT),
    "open_questions": ("map", TEXT),
}


def _validate(value, spec, where):
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            raise BriefError(f"{where} must be an object")
        for key, item in value.items():
            if key not in spec:
                raise BriefError(f"{where}.{key} is not a brief field (known: {', '.join(spec)})")
            _validate(item, spec[key], f"{where}.{key}")
    elif isinstance(spec, tuple):
        if not isinstance(value, dict):
            raise BriefError(f"{where} must be an object of named entries")
        for key, item in value.items():
            if not ID_RE.match(key):
                raise BriefError(f"{where}: {key!r} is not a plain id (letters, digits, '.', '-', '_')")
            _validate(item, spec[1], f"{where}.{key}")
    else:
        spec(value, where)


def _merge(base, patch, spec, where):
    """RFC 7396-style merge: objects merge, null clears (enums go back to unchosen, named entries and emptied
    objects are removed), anything else replaces."""
    out = dict(base)
    for key, value in patch.items():
        if isinstance(spec, dict):
            if key not in spec:
                raise BriefError(f"{where}.{key} is not a brief field (known: {', '.join(spec)})")
            sub = spec[key]
        else:
            if not ID_RE.match(key):
                raise BriefError(f"{where}: {key!r} is not a plain id (letters, digits, '.', '-', '_')")
            sub = spec[1]
        if value is None:
            if isinstance(spec, tuple):
                out.pop(key, None)                    # a named entry goes; its file is never touched
            elif hasattr(sub, "default"):
                out[key] = sub.default
            elif isinstance(sub, dict) and isinstance(out.get(key), dict):
                cleared = _merge(out[key], {k: None for k in out[key]}, sub, f"{where}.{key}")
                if cleared:
                    out[key] = cleared                # e.g. a sound keeps choice: unchosen
                else:
                    out.pop(key, None)
            else:
                out.pop(key, None)
        elif isinstance(sub, (dict, tuple)) and isinstance(value, dict) and isinstance(out.get(key, {}), dict):
            out[key] = _merge(out.get(key, {}), value, sub, f"{where}.{key}")
        else:
            out[key] = copy.deepcopy(value)
    return out


def empty_sections():
    return {"route": "unchosen", "destination": {}, "story": {}, "style": {}, "brand": {"mode": "unchosen"},
            "assets": {}, "audio": {"timing_driver": "unchosen", **{k: {"choice": "unchosen"} for k in SOUNDS}},
            "decisions": {}, "open_questions": {}}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _check_fingerprint(info, where, needs_area):
    if not isinstance(info, dict) or not isinstance(info.get("path"), str) \
            or not isinstance(info.get("status"), str) \
            or not isinstance(info.get("resolved", ""), str) \
            or not isinstance(info.get("sha256", ""), str) \
            or ("size" in info and not _is_int(info["size"])) \
            or (needs_area and info.get("area") not in FILE_AREAS):
        raise BriefError(f"{where} is not a valid file fingerprint")


def _check_approval(rec, where):
    if not isinstance(rec, dict) or rec.get("gate") not in GATES or rec.get("state") not in STATES \
            or rec.get("status") not in ("current", "superseded", "invalidated") \
            or not isinstance(rec.get("note"), str) or not isinstance(rec.get("at"), str) \
            or not _is_int(rec.get("input_revision")) \
            or not _is_int(rec.get("recorded_revision", 0)) \
            or not isinstance(rec.get("inputs", {}), dict):
        raise BriefError(f"{where} is not a valid approval record")
    for field, info in rec.get("inputs", {}).items():
        _check_fingerprint(info, f"{where}.inputs.{field}", True)
    if "evidence" in rec:
        _check_fingerprint(rec["evidence"], f"{where}.evidence", False)
    for key in ("invalidated", "superseded"):
        if key in rec and (not isinstance(rec[key], dict) or not _is_int(rec[key].get("revision"))
                           or not isinstance(rec[key].get("reason"), str)):
            raise BriefError(f"{where}.{key} must hold a revision and a reason")


def _check_history(h, where):
    if not isinstance(h, dict) or not _is_int(h.get("revision")) or not isinstance(h.get("at"), str) \
            or not isinstance(h.get("action"), str) or not isinstance(h.get("summary", ""), str):
        raise BriefError(f"{where} is not a valid history entry")
    for key in ("changed", "invalidated", "replaced_summary_lines"):
        if key in h and (not isinstance(h[key], list) or not all(isinstance(x, str) for x in h[key])):
            raise BriefError(f"{where}.{key} must be a list of text")


def validate_brief(data):
    if not isinstance(data, dict):
        raise BriefError("the brief data must be a JSON object")
    if data.get("schema") != SCHEMA:
        raise BriefError(f"unknown brief schema {data.get('schema')!r} (expected {SCHEMA})")
    if not _is_int(data.get("revision")) or data["revision"] < 1:
        raise BriefError("revision must be a whole number of at least 1")
    known = set(PATCHABLE) | {"schema", "revision", "created", "updated", "approvals", "history", "seal"}
    extra = set(data) - known
    if extra:
        raise BriefError(f"unknown brief fields: {', '.join(sorted(extra))}")
    if not isinstance(data.get("created"), str) or not isinstance(data.get("updated"), str):
        raise BriefError("created and updated must be timestamps")
    for key in PATCHABLE:
        if key not in data:
            raise BriefError(f"the brief is missing {key}")
        _validate(data[key], SPEC[key], key)
    if "mode" not in data["brand"] or "timing_driver" not in data["audio"] \
            or any(not isinstance(data["audio"].get(k), dict) or "choice" not in data["audio"][k] for k in SOUNDS):
        raise BriefError("the brief must keep brand.mode, audio.timing_driver and a choice for voice, music and "
                         "effects (unchosen until decided)")
    if not isinstance(data.get("approvals"), list) or not isinstance(data.get("history"), list):
        raise BriefError("approvals and history must be lists")
    current = set()
    for i, rec in enumerate(data["approvals"]):
        _check_approval(rec, f"approvals[{i}]")
        if rec["status"] == "current":
            if rec["gate"] in current:
                raise BriefError(f"approvals[{i}]: two current records for {rec['gate']}")
            current.add(rec["gate"])
    for i, h in enumerate(data["history"]):
        _check_history(h, f"history[{i}]")
    return data


# --- reading and writing -------------------------------------------------------------------------------------------

def _strict_json(text, where):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise BriefError(f"{where}: duplicate key {key!r}")
            out[key] = value
        return out

    def constant(name):
        raise BriefError(f"{where}: {name} is not allowed (numbers must be finite)")

    def number(text_value):
        value = float(text_value)
        if not math.isfinite(value):
            raise BriefError(f"{where}: {text_value} is not a finite number")
        return value

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except RecursionError:
        raise BriefError(f"{where} is nested too deeply") from None
    except ValueError as exc:
        raise BriefError(f"{where} is not valid JSON: {exc}") from None


def brief_path(path, must_exist=True):
    p = Path(os.path.abspath(os.path.expanduser(str(path))))
    if p.name != NAME:
        raise BriefError(f"the brief file must be called {NAME}, not {p.name}")
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        if must_exist:
            raise BriefError(f"no brief at {p}")
        return p
    if stat.S_ISLNK(st.st_mode):
        raise BriefError(f"{p} is a symlink; refusing to read or write through it")
    if not stat.S_ISREG(st.st_mode):
        raise BriefError(f"{p} is not a regular file")
    if not must_exist:
        raise BriefError(f"{p} already exists; a new brief never overwrites one")
    return p


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def seal_of(data):
    """SHA256 over the canonical data without its seal."""
    return hashlib.sha256(canonical({k: v for k, v in data.items() if k != "seal"}).encode("utf-8")).hexdigest()


def digest(data):
    return seal_of(data)


def _norm(text):
    return " ".join(text.split())


def split(text):
    """(readable summary, data) from brief.md's text; checks the markers, the seal and the schema."""
    lines = text.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    starts = [i for i, line in enumerate(lines) if line == BEGIN]
    if not starts or not lines or lines[-1] != END:
        raise BriefError("brief.md has no data block (it must end with the kit-to-clip-brief data markers)")
    body = lines[starts[-1] + 1:-1]
    if len(body) < 2 or body[0] != "```json" or body[-1] != "```":
        raise BriefError("the brief's data block must be one fenced ```json block")
    data = _strict_json("\n".join(body[1:-1]), "the brief's data block")
    if not isinstance(data, dict):
        raise BriefError("the brief data must be a JSON object")
    if data.get("schema") != SCHEMA:
        raise BriefError(f"unknown brief schema {data.get('schema')!r} (expected {SCHEMA})")
    seal = data.get("seal")
    if not isinstance(seal, str) or not SEAL_RE.match(seal) or seal != "sha256:" + seal_of(data):
        raise BriefError("the brief's data was changed outside brief.py (its seal does not match). Undo that edit, "
                         "then make the change with brief.py update so revisions and approvals stay true")
    validate_brief(data)
    return "\n".join(lines[:starts[-1]]), data


def parse(text):
    return split(text)[1]


def _read(p):
    try:
        with open(p, "r", encoding="utf-8") as fh:
            text = fh.read()
    except UnicodeDecodeError:
        raise BriefError(f"{p} is not UTF-8 text") from None
    summary, data = split(text)
    return data, _norm(summary) == _norm(human(data)), summary


def load(path):
    return _read(brief_path(path))[0]


def summary_is_current(path):
    return _read(brief_path(path))[1]


def _quote(value):
    if isinstance(value, list):
        return "\n".join(f"> - {line}" for item in value for line in str(item).split("\n"))
    return "\n".join(f"> {line}" for line in str(value).split("\n"))


def _pairs(obj, prefix=""):
    rows = []
    for key, value in obj.items():
        if isinstance(value, dict):
            rows += _pairs(value, f"{prefix}{key}.")
        else:
            shown = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            rows.append(f"- {prefix}{key}: {' '.join(shown.split())}")
    return rows


def human(data):
    out = [f"# Production brief (revision {data['revision']})", "",
           "Kept by Kit to Clip's brief.py and generated from the data block at the end, which is the brief. Put "
           "your own words into decisions or notes with brief.py: a hand edit here blocks changes until reconciled.",
           "", "## Request", "", _quote(data["request"]), "", f"Route: {data['route']}", ""]
    for key in ("destination", "story", "style", "brand", "assets", "audio"):
        rows = _pairs(data[key])
        out += [f"## {key.capitalize()}", ""] + (rows or ["- (not set yet)"]) + [""]
    out += ["## Decisions", ""] + ([f"- {k}: {' '.join(v.split())}" for k, v in data["decisions"].items()]
                                   or ["- (none yet)"]) + [""]
    out += ["## Open questions", ""] + ([f"- {k}: {' '.join(v.split())}" for k, v in data["open_questions"].items()]
                                       or ["- (none)"]) + [""]
    out += ["## Approvals (the person's words, by gate)", ""]
    current = {r["gate"]: r for r in data["approvals"] if r["status"] == "current"}
    for gate in GATES:
        r = current.get(gate)
        out.append(f"- {gate}: {r['state']} at revision {r['input_revision']}: {' '.join(r['note'].split())}"
                   if r else f"- {gate}: open")
    old = [r for r in data["approvals"] if r["status"] != "current"]
    if old:
        out += ["", "Earlier records:", ""]
        for r in old:
            why = r.get("invalidated", {}).get("reason") or r.get("superseded", {}).get("reason", "")
            out.append(f"- {r['gate']} {r['state']} (revision {r['input_revision']}): {r['status']}, {why}")
    out += ["", "## History", ""]
    for h in data["history"]:
        out.append(f"- r{h['revision']} {h['at']} {h['action']}: {' '.join(str(h.get('summary', '')).split())}")
    return "\n".join(out) + "\n"


def render(data):
    """brief.md's text; seals the data in place first."""
    data["seal"] = "sha256:" + seal_of(data)
    payload = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
    return f"{human(data)}\n{BEGIN}\n```json\n{payload}\n```\n{END}\n"


def _fsync_dir(folder):
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _temp_with(folder, text):
    """A complete, synced, private (600) temporary file next to the brief."""
    fd, tmp = tempfile.mkstemp(prefix=f".{NAME}.", suffix=".tmp", dir=str(folder))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        _unlink_quietly(tmp)
        raise
    return tmp


def _unlink_quietly(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _write_atomic(p, text):
    tmp = _temp_with(p.parent, text)
    try:
        brief_path(p)  # still a regular file, not a link swapped in meanwhile
        os.replace(tmp, p)
        _fsync_dir(str(p.parent))
    except BaseException:
        _unlink_quietly(tmp)
        raise


class _Lock:
    def __init__(self, p):
        self.path = p.with_name(p.name + ".lock")
        self.fd = None

    def __enter__(self):
        try:
            wait = float(os.environ.get("KIT_TO_CLIP_BRIEF_LOCK_WAIT", "10"))
        except ValueError:
            wait = 10.0
        if not math.isfinite(wait):
            wait = 10.0
        deadline = time.monotonic() + max(0.0, min(wait, 600.0))
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        while True:
            try:
                self.fd = os.open(self.path, flags, 0o600)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise Busy(f"another writer holds {self.path}; if none is running, delete that file and retry")
                time.sleep(0.02)
                continue
            try:
                os.write(self.fd, f"pid {os.getpid()} {now()}\n".encode())
            except OSError:
                self.__exit__()
                raise
            return self

    def __exit__(self, *exc):
        os.close(self.fd)
        _unlink_quietly(self.path)


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mutate(path, expected, change, reconciled=False):
    """Lock, re-read, check revision and summary, apply change(data) -> history entry, validate, write one up."""
    p = brief_path(path)
    if not _is_int(expected):
        raise BriefError("--expected must be a whole number")
    with _Lock(p):
        data, summary_ok, summary = _read(p)
        if data["revision"] != expected:
            raise StaleRevision(f"the brief is at revision {data['revision']}, not {expected}; read it again "
                                "(nothing was changed)")
        kept = []
        if not summary_ok:
            if not reconciled:
                raise NeedsReconcile(
                    "brief.md's readable summary was edited by hand, and a change would replace that text. Nothing "
                    "was changed. Carry the person's words into the brief (e.g. decisions) with: brief.py update "
                    "--summary-reconciled ... (the replaced lines are kept in the history)")
            generated = {_norm(line) for line in human(data).split("\n")}
            kept = [line.strip()[:MAX_TEXT] for line in summary.split("\n")
                    if line.strip() and _norm(line) not in generated][:200]
        new = copy.deepcopy(data)
        new["revision"] = expected + 1
        new["updated"] = now()
        entry = change(new, expected)
        if kept:
            entry["replaced_summary_lines"] = kept
            entry["summary"] += "; hand-written summary reconciled (its lines are kept here)"
        new["history"].append({"revision": new["revision"], "at": new["updated"], **entry})
        validate_brief(new)
        _write_atomic(p, render(new))
        return new


# --- input files ---------------------------------------------------------------------------------------------------

def _is_source(asset):
    return asset.get("role") == SOURCE_ROLE


def _file_ok(field, info):
    """A file input must be a readable regular file; only brand.kit may point at a folder (never scanned)."""
    return info["status"] == "ok" or (field == "brand.kit" and info["status"] == "directory")


def named_files(data):
    """(field, area, path) for every local file the brief names. Folder pointers (source_root) are not inputs."""
    out = []
    if data["brand"].get("kit"):
        out.append(("brand.kit", "visual", data["brand"]["kit"]))
    ref = data["style"].get("reference", {})
    for key in ("prompt_file", "code_file"):
        if ref.get(key):
            out.append((f"style.reference.{key}", "visual", ref[key]))
    for key, asset in sorted(data["assets"].items()):
        if asset.get("path"):
            out.append((f"assets.{key}.path", "source" if _is_source(asset) else "visual", asset["path"]))
    if data["story"].get("script_file"):
        out.append(("story.script_file", "voice", data["story"]["script_file"]))
    for kind in SOUNDS:
        if data["audio"][kind].get("path"):
            out.append((f"audio.{kind}.path", kind, data["audio"][kind]["path"]))
    return out


def fingerprint(brief, raw):
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        p = brief.parent / p
    p = Path(os.path.abspath(p))
    base = {"path": raw, "resolved": str(p)}
    try:
        st = os.stat(p)
    except OSError as exc:
        if exc.errno in (errno.ENOENT, errno.ENOTDIR):
            return dict(base, status="missing")
        return dict(base, status=f"unreadable: {exc.strerror}")
    if stat.S_ISDIR(st.st_mode):
        return dict(base, status="directory")              # a pointer: never listed or scanned
    if not stat.S_ISREG(st.st_mode):
        return dict(base, status="not a regular file")     # a pipe or device is never opened
    h = hashlib.sha256()
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        return dict(base, status=f"unreadable: {exc.strerror}")
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())                         # the file actually opened, not the one stat saw
        if not stat.S_ISREG(st.st_mode):
            return dict(base, status="not a regular file")
        try:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        except OSError as exc:
            return dict(base, status=f"unreadable: {exc.strerror}")
    return dict(base, status="ok", size=st.st_size, sha256=h.hexdigest())


def snapshot(brief, data):
    return {field: dict(fingerprint(brief, raw), area=area) for field, area, raw in named_files(data)}


def _same(a, b):
    return (a.get("path"), a.get("status"), a.get("sha256")) == (b.get("path"), b.get("status"), b.get("sha256"))


def _area_gates(area, timing_driver):
    return AREA_GATES[area] + (("layout", "stills") if area == "music" and timing_driver == "music" else ())


def stale_reasons(rec, now_files, brief, timing_driver):
    """Why a recorded approval's own inputs no longer match the files on disk (empty list when they still do)."""
    reasons = []
    for field, then in rec.get("inputs", {}).items():
        if rec["gate"] not in _area_gates(then["area"], timing_driver):
            continue
        cur = now_files.get(field)
        if cur is None or cur.get("path") != then.get("path"):
            continue  # renamed through the brief: handled when the patch invalidated it
        if not _same(then, cur):
            reasons.append(f"{field} ({cur['path']}) is {'missing' if cur['status'] == 'missing' else 'changed'} "
                           "since this approval")
    ev = rec.get("evidence")
    if ev:
        cur = fingerprint(brief, ev["path"])
        if not _same(ev, cur):
            reasons.append(f"the evidence file {ev['path']} is {cur['status'] if cur['status'] != 'ok' else 'changed'}")
    return reasons


# --- gates ---------------------------------------------------------------------------------------------------------

def _needs(data, kind):
    """True unless that sound is declared absent (unchosen counts as maybe present)."""
    return data["audio"][kind]["choice"] != "none"


def _has_sound(data):
    return any(_needs(data, kind) for kind in SOUNDS)


def gate_problems(data, files, valid, gate, state):
    """Why a gate cannot hold `state` now, given the records that still count (`valid`: gate -> record).
    The same checks guard a new approval and decide whether a recorded one still counts."""
    def yes(g):
        return g in valid and valid[g]["state"] == "yes"

    if state == "no":
        return []
    if state == "n/a":
        if gate in ("voice-choice", "music-choice"):
            kind = gate.split("-")[0]
            if _needs(data, kind):
                return [f"{gate} can be n/a only when audio.{kind}.choice is none "
                        f"(it is {data['audio'][kind]['choice']})"]
            return []
        if gate == "listening":
            return [] if not _has_sound(data) else \
                ["listening can be n/a only when voice, music and effects are all none"]
        return [f"{gate} cannot be n/a: it is always the person's yes or no"]
    problems = []
    if gate == "stills" and not yes("layout"):
        problems.append("stills need a current, unchanged layout yes first")
    if gate in ("voice-choice", "music-choice"):
        kind = gate.split("-")[0]
        choice = data["audio"][kind]["choice"]
        if choice in ("unchosen", "none"):
            problems.append(f"audio.{kind}.choice is {choice}; record what was chosen before approving it")
        named = data["audio"][kind].get("path")
        if named and files.get(f"audio.{kind}.path", {}).get("status") != "ok":
            problems.append(f"the named {kind} file {named} is missing or not a readable file")
    if gate == "render":
        missing = [g for g in ("layout", "stills") if not yes(g)]
        for kind in ("voice", "music"):
            if data["audio"][kind]["choice"] == "unchosen":
                missing.append(f"a {kind} choice (set audio.{kind}.choice; none if there is no {kind})")
            elif _needs(data, kind) and not yes(f"{kind}-choice"):
                missing.append(f"{kind}-choice")
        if data["audio"]["effects"]["choice"] == "unchosen":
            missing.append("an effects choice (set audio.effects.choice; none if there are no sound effects)")
        absent = [f for f, info in files.items() if not _file_ok(f, info)]
        if absent:
            missing.append("present input files (" + ", ".join(absent) + ")")
        if missing:
            problems.append("render needs, current and unchanged: " + "; ".join(missing))
    if gate == "listening":
        if not _has_sound(data):
            problems.append("there is no sound to listen to; record listening as n/a")
        if not yes("render"):
            problems.append("listening needs a current, unchanged render yes first (a preview does not count)")
    return problems


def effective(data, brief, files=None):
    """gate -> (current record, reasons it no longer counts), walking the gates in dependency order so a stale or
    missing prerequisite makes everything after it stale too."""
    files = snapshot(brief, data) if files is None else files
    current = {r["gate"]: r for r in data["approvals"] if r["status"] == "current"}
    valid, out = {}, {}
    for gate in GATES:
        rec = current.get(gate)
        if rec is None:
            continue
        reasons = stale_reasons(rec, files, brief, data["audio"]["timing_driver"])
        reasons += gate_problems(data, files, valid, gate, rec["state"])
        out[gate] = (rec, reasons)
        if not reasons:
            valid[gate] = rec
    return out


def _passes(eff, gate, states=("yes",)):
    rec = eff.get(gate)
    return bool(rec) and rec[0]["state"] in states and not rec[1]


# --- commands ------------------------------------------------------------------------------------------------------

def init_brief(out, request):
    _text(request, "request", allow_empty=False)
    p = brief_path(out, must_exist=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = now()
    data = {"schema": SCHEMA, "revision": 1, "created": stamp, "updated": stamp, "request": request,
            **empty_sections(), "approvals": [],
            "history": [{"revision": 1, "at": stamp, "action": "init", "summary": "brief created"}]}
    validate_brief(data)
    text = render(data)
    tmp = _temp_with(p.parent, text)
    try:
        try:
            os.link(tmp, p)        # publishes the complete file in one step; fails if anything is already there
        except FileExistsError:
            raise BriefError(f"{p} already exists; a new brief never overwrites one") from None
        except OSError as exc:
            if exc.errno not in (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV, errno.EMLINK):
                raise
            _create_exclusive(p, text)  # a folder without hard links: still never overwrites
    finally:
        _unlink_quietly(tmp)
    _fsync_dir(str(p.parent))
    return data


def _create_exclusive(p, text):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(p, flags, 0o600)
    except FileExistsError:
        raise BriefError(f"{p} already exists; a new brief never overwrites one") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        _unlink_quietly(p)
        raise


def _voice_content(d):
    v = d["audio"]["voice"]
    return v["choice"] not in ("unchosen", "none") or bool(v.get("path")) or bool(d["story"].get("script")) \
        or bool(d["story"].get("script_file"))


def _changed_areas(old, new):
    areas = {}

    def add(area, what):
        areas.setdefault(area, []).append(what)

    def visual_value(key, value):
        # Documentary notes do not change the picture. Creative constraints belong
        # in the actual destination fields, asset role, style notes or brand notes.
        if key == "destination":
            return {k: v for k, v in value.items() if k != "notes"}
        if key == "style":
            kept = dict(value)
            reference = {k: v for k, v in (kept.get("reference") or {}).items()
                         if k not in ("origin", "permitted_use") and v is not None}
            kept["reference"] = reference or None
            return kept
        return value

    def asset_views(assets):
        # (creative, source) without documentary notes. Source code builds the approved layout, so it reopens
        # what it draws but not the layout; an asset switching role leaves the creative view, reopening layout.
        creative, source = {}, {}
        for name, asset in assets.items():
            fields = {k: v for k, v in asset.items() if k != "notes" and v is not None}
            if fields:
                (source if _is_source(asset) else creative)[name] = fields
        return creative, source

    for key in ("request", "route", "destination", "style", "brand"):
        if old[key] != new[key]:
            add("visual" if visual_value(key, old[key]) != visual_value(key, new[key]) else "notes", key)
    if old["assets"] != new["assets"]:
        (old_creative, old_source), (new_creative, new_source) = asset_views(old["assets"]), asset_views(new["assets"])
        if old_creative != new_creative:
            add("visual", "assets")
        if old_source != new_source:
            add("source", "source assets")
        if (old_creative, old_source) == (new_creative, new_source):
            add("notes", "assets")
    voice_keys = ("script", "script_file")
    if {k: v for k, v in old["story"].items() if k not in voice_keys} != \
            {k: v for k, v in new["story"].items() if k not in voice_keys}:
        add("visual", "story")
    # A first voice or script reopens existing approvals like a replacement; only declaring "no voice" does not
    # touch the visuals, because nothing could have been timed to it.
    voice_area = "voice" if _voice_content(old) or _voice_content(new) else "voice-absent"
    for k in voice_keys:
        if old["story"].get(k) != new["story"].get(k):
            add(voice_area, f"story.{k}")
    if old["audio"]["voice"] != new["audio"]["voice"]:
        add(voice_area, "audio.voice")
    for kind in ("music", "effects"):
        if old["audio"][kind] != new["audio"][kind]:
            add(kind, f"audio.{kind}")
    if old["audio"]["timing_driver"] != new["audio"]["timing_driver"]:
        add("timing", "audio.timing_driver")
    for key in ("decisions", "open_questions"):
        if old[key] != new[key]:
            add("notes", key)
    return areas


def _invalidate(data, gates, reason, revision):
    hit = []
    for rec in data["approvals"]:
        if rec["status"] == "current" and rec["gate"] in gates:
            rec["status"] = "invalidated"
            rec["invalidated"] = {"revision": revision, "reason": reason}
            hit.append(rec["gate"])
    return hit


def read_patch(source):
    if source == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(source, "r", encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise BriefError(f"cannot read the patch {source}: {exc}") from None
    patch = _strict_json(text, "the patch")
    if not isinstance(patch, dict):
        raise BriefError("the patch must be a JSON object")
    return patch


def update(path, expected, patch, note=None, summary_reconciled=False):
    if not isinstance(patch, dict) or not patch:
        raise BriefError("the patch must be a non-empty JSON object")
    bad = [k for k in patch if k not in PATCHABLE]
    if bad:
        raise BriefError(f"not patchable: {', '.join(bad)} (allowed: {', '.join(PATCHABLE)})")
    if note is not None:
        _text(note, "--note")

    def change(data, rev):
        old = copy.deepcopy(data)
        for key, value in patch.items():
            if key == "request" or not isinstance(SPEC[key], (dict, tuple)):
                if value is None and key == "request":
                    raise BriefError("request cannot be cleared")
                data[key] = SPEC[key].default if value is None else copy.deepcopy(value)
            elif value is None:
                data[key] = empty_sections()[key]
            elif not isinstance(value, dict):
                raise BriefError(f"{key} must be an object")
            else:
                data[key] = _merge(data[key], value, SPEC[key], key)
        for key in PATCHABLE:
            _validate(data[key], SPEC[key], key)
        audio_patch = patch.get("audio") or {}
        for kind in SOUNDS:
            track_patch = audio_patch.get(kind) if isinstance(audio_patch, dict) else None
            if isinstance(track_patch, dict) and track_patch.get("choice") == "none":
                if track_patch.get("path") is not None:
                    raise BriefError(f"audio.{kind}: choice none cannot name a sound file")
                # Drop the active input, not the original file or its history.
                data["audio"][kind].pop("path", None)
                data["audio"][kind].pop("duration_seconds", None)
                if kind == "music":
                    data["audio"][kind].pop("bpm", None)
        areas = _changed_areas(old, data)
        invalidated = []
        for area, what in areas.items():
            gates = set(AREA_GATES[area])
            if area == "music" and "music" in (old["audio"]["timing_driver"], data["audio"]["timing_driver"]):
                gates |= {"layout", "stills"}
            invalidated += _invalidate(data, gates, f"{', '.join(what)} changed at revision {rev + 1}", rev + 1)
        changed = sorted(w for what in areas.values() for w in what)
        summary = "changed " + (", ".join(changed) if changed else "nothing")
        if invalidated:
            summary += "; reopened " + ", ".join(sorted(set(invalidated)))
        if note:
            summary += f" ({note})"
        return {"action": "update", "summary": summary, "changed": changed, "invalidated": sorted(set(invalidated))}

    return _mutate(path, expected, change, reconciled=summary_reconciled)


def approve(path, expected, gate, state, note, evidence=None):
    if gate not in GATES:
        raise BriefError(f"unknown gate {gate!r} (gates: {', '.join(GATES)})")
    if state not in STATES:
        raise BriefError(f"unknown state {state!r} (states: {', '.join(STATES)})")
    if not isinstance(note, str) or not note.strip():
        raise BriefError("--note must hold the person's decision in their words; an approval needs evidence")
    _text(note, "--note")
    brief = brief_path(path)
    ev = None
    if evidence is not None:
        _path(evidence, "--evidence")
        ev = fingerprint(brief, evidence)
        if ev["status"] != "ok":
            raise BriefError(f"the evidence file {evidence} is {ev['status']}")

    def change(data, rev):
        files = snapshot(brief, data)
        eff = effective(data, brief, files)
        valid = {g: r for g, (r, reasons) in eff.items() if not reasons}
        problems = gate_problems(data, files, valid, gate, state)
        if problems:
            raise GateRefused("; ".join(problems))
        for rec in data["approvals"]:
            if rec["status"] == "current" and rec["gate"] == gate:
                rec["status"] = "superseded"
                rec["superseded"] = {"revision": rev + 1, "reason": f"new {gate} decision at revision {rev + 1}"}
        # Whatever came after this gate was decided on the older decision, so it is reopened.
        reopened = _invalidate(data, set(DOWNSTREAM[gate]), f"{gate} decided again ({state}) at revision {rev + 1}",
                               rev + 1)
        rec = {"gate": gate, "state": state, "input_revision": rev, "recorded_revision": rev + 1,
               "at": data["updated"], "note": note, "status": "current", "inputs": files}
        if ev:
            rec["evidence"] = ev
        data["approvals"].append(rec)
        summary = f"{gate} {state}: {note}"
        if reopened:
            summary += "; reopened " + ", ".join(sorted(set(reopened)))
        return {"action": "approve", "summary": summary, "gate": gate, "state": state,
                "invalidated": sorted(set(reopened))}

    return _mutate(brief, expected, change)


def _story_set(data):
    return any(data["story"].get(k) for k in ("summary", "onscreen", "beats", "script", "script_file"))


def _style_set(data):
    style = data["style"]
    reference = style.get("reference") or {}
    return bool(style.get("name") or style.get("saved_style") or
                any(reference.get(k) for k in ("catalogue_id", "prompt_file", "code_file")))


def unresolved(data, files):
    """Everything a final render still needs. A partial brief may still be handed to a layout-stage builder."""
    out = []
    d = data["destination"]
    if data["route"] == "unchosen":
        out.append("route is unchosen (idea, footage or mixed)")
    if not (d.get("aspect") or (d.get("width") and d.get("height"))):
        out.append("destination has no canvas (aspect, or width and height)")
    if not d.get("duration_seconds"):
        out.append("destination.duration_seconds is not set")
    if data["brand"]["mode"] == "unchosen":
        out.append("brand.mode is unchosen (original, palette or full)")
    if data["audio"]["timing_driver"] == "unchosen":
        out.append("audio.timing_driver is unchosen (narration, music, visual or footage)")
    for driver, kind in (("narration", "voice"), ("music", "music")):
        if data["audio"]["timing_driver"] == driver and data["audio"][kind]["choice"] == "none":
            out.append(f"audio.timing_driver is {driver} but audio.{kind}.choice is none")
    if data["route"] in ("idea", "mixed", "unchosen"):
        if not _style_set(data):
            out.append("style is not chosen (name, saved_style or reference)")
        if not _story_set(data):
            out.append("story is empty (summary, onscreen, beats or script)")
    if data["route"] in ("footage", "mixed") and not any(a.get("path") for a in data["assets"].values()):
        out.append("the footage route names no footage files in assets")
    for kind in SOUNDS:
        sound = data["audio"][kind]
        if sound["choice"] == "none" and sound.get("path"):
            out.append(f"audio.{kind}.choice is none but still names a sound file; clear the active path")
        if sound["choice"] == "unchosen":
            out.append(f"audio.{kind}.choice is unchosen (none, supplied, guided or generated)")
        elif sound["choice"] != "none" and not sound.get("path"):
            out.append(f"audio.{kind}.path must name the actual {kind} file ({sound['choice']}) before the final "
                       "render")
    for key, asset in sorted(data["assets"].items()):
        if _is_source(asset) and not asset.get("path"):
            out.append(f"assets.{key} has role source but names no file")
    for field, info in files.items():
        if not _file_ok(field, info):
            status = "a folder, not a file" if info["status"] == "directory" else info["status"]
            out.append(f"input {field} ({info['path']}) is {status}")
    return out


def handoff(path, expected):
    brief = brief_path(path)
    if not _is_int(expected):
        raise BriefError("--expected must be a whole number")
    data, summary_ok, _ = _read(brief)
    if data["revision"] != expected:
        raise StaleRevision(f"the brief is at revision {data['revision']}, not {expected}; read it again")
    files = snapshot(brief, data)
    eff = effective(data, brief, files)
    approved_inputs = {}
    for rec, _ in eff.values():
        for field, info in rec.get("inputs", {}).items():
            if rec["gate"] in _area_gates(info["area"], data["audio"]["timing_driver"]):
                approved_inputs.setdefault(field, []).append(info)
    file_rows = []
    for field, info in files.items():
        row = {"field": field, **{k: v for k, v in info.items() if k != "area"}, "area": info["area"]}
        if info["status"] == "ok" and any(then.get("path") == info["path"] and then.get("sha256")
                                          and then.get("sha256") != info["sha256"]
                                          for then in approved_inputs.get(field, [])):
            row["status"] = "changed"
        file_rows.append(row)
    approvals = {}
    for gate in GATES:
        if gate in eff:
            rec, reasons = eff[gate]
            approvals[gate] = {"state": rec["state"], "input_revision": rec["input_revision"], "note": rec["note"],
                               "at": rec["at"], "stale": bool(reasons), "stale_reasons": reasons}
            if rec.get("evidence"):
                approvals[gate]["evidence"] = rec["evidence"]
    needed = ["layout", "stills"] + [f"{k}-choice" for k in ("voice", "music") if _needs(data, k)] + ["render"]
    if _has_sound(data):
        needed.append("listening")
    open_gates = [g for g in needed if not _passes(eff, g, ("yes", "n/a"))]
    todo = unresolved(data, files)
    todo += [f"{g} approval no longer counts: {'; '.join(eff[g][1])}" for g in GATES if g in eff and eff[g][1]]
    if not summary_ok:
        todo.append("the readable summary in brief.md was edited by hand: carry that text into the brief with "
                    "update --summary-reconciled before any change")
    return {
        "brief": str(brief),
        "revision": data["revision"],
        "digest": digest(data),
        "inputs": {k: data[k] for k in PATCHABLE if k not in ("decisions", "open_questions")},
        "decisions": data["decisions"],
        "files": file_rows,
        "approvals": approvals,
        "open_gates": open_gates,
        "next_gate": open_gates[0] if open_gates else None,
        "open_questions": data["open_questions"],
        "unresolved": todo,
        "summary_needs_reconciliation": not summary_ok,
        "may_render": _passes(eff, "render") and not todo,
        "note": "This handoff only reads the brief. It never starts a build or a render; the person's gates decide.",
    }


# --- command line --------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="brief.py", description="Kit to Clip's durable production brief (brief.md).",
                                 epilog="Exit codes: 0 done, 1 invalid, 3 stale revision, 4 locked, 5 gate refused, "
                                        "6 hand-edited summary must be reconciled.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="create a new brief.md (never overwrites)")
    p.add_argument("--out", required=True, help="path to the new <work>/<job>/brief.md")
    p.add_argument("--request", required=True, help="what the person asked for, in their words")
    p = sub.add_parser("update", help="merge a JSON patch into the brief")
    p.add_argument("--file", required=True)
    p.add_argument("--expected", required=True, type=int, help="the revision you read")
    p.add_argument("--patch", required=True, help="a JSON object file, or - for stdin")
    p.add_argument("--note", help="why, for the history")
    p.add_argument("--summary-reconciled", action="store_true",
                   help="the hand-written summary text has been carried into this patch; regenerate the summary "
                        "(its replaced lines are kept in the history)")
    p = sub.add_parser("approve", help="record the person's decision at a gate (never grants one)")
    p.add_argument("--file", required=True)
    p.add_argument("--expected", required=True, type=int, help="the revision the person decided on")
    p.add_argument("--gate", required=True, choices=GATES)
    p.add_argument("--state", required=True, choices=STATES)
    p.add_argument("--note", required=True, help="the person's decision, in their words")
    p.add_argument("--evidence", help="optional local file the person reviewed (fingerprinted)")
    p = sub.add_parser("show", help="print the brief (readable, or the exact data with --json)")
    p.add_argument("--file", required=True)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("handoff", help="JSON for a builder at the current revision; reads only")
    p.add_argument("--file", required=True)
    p.add_argument("--expected", required=True, type=int)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "init":
            data = init_brief(args.out, args.request)
            print(f"created {brief_path(args.out)} at revision {data['revision']}")
        elif args.cmd == "update":
            data = update(args.file, args.expected, read_patch(args.patch), args.note, args.summary_reconciled)
            print(f"revision {data['revision']}: {data['history'][-1]['summary']}")
        elif args.cmd == "approve":
            data = approve(args.file, args.expected, args.gate, args.state, args.note, args.evidence)
            print(f"revision {data['revision']}: {data['history'][-1]['summary']}")
        elif args.cmd == "show":
            data, summary_ok, _ = _read(brief_path(args.file))
            if not summary_ok:
                print("brief.py: note: the readable summary was edited by hand; this shows the data, which is the "
                      "brief. Reconcile with update --summary-reconciled.", file=sys.stderr)
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print(human(data), end="")
        elif args.cmd == "handoff":
            print(json.dumps(handoff(args.file, args.expected), indent=2, ensure_ascii=False))
    except BriefError as exc:
        print(f"brief.py: {exc}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"brief.py: {exc}", file=sys.stderr)
        return INVALID
    return OK


if __name__ == "__main__":
    sys.exit(main())
