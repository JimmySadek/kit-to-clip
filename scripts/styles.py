#!/usr/bin/env python3
"""Saved video styles, stored with the brand they were made for.

A style is a reusable recipe: <styles>/<slug>/style.json (the answers from the style workshop), style.md (the
human-readable recipe), template/ (the approved HyperFrames project, without footage or generated brand files)
and approved/ (the stills that were signed off). Formats (neutral ones and a brand's own) are listed by
formats/scripts/formats.py, not here.

  styles.py list [--brand <id>]                       saved styles, one per line (JSON with --json)
  styles.py init --title "Court Cam" --author "<name>" [--brand <id>] [--from <format or style>]
  styles.py save --style court-cam --project videos/court-cam-draft [--approve]
  styles.py new  --style court-cam --out videos/<job>  copy the template, re-apply the brand, add GSAP
  styles.py refs --style court-cam <file> [<file> ...]  keep reference pictures, videos' notes and sheets in refs/

Saved references (kind "reference"): a finished video's treatment, kept as adaptable code, not a template.
  styles.py capture --film <video>/film.json --project <job project> --title "Ink Wash"
                    --finished-output <the finished video> --approval-note "<the person's own words>"
                    (an older brief: --brief <job>/brief.md --expected N instead of --film)
                    [--slug S] [--author A] [--tag T ...] [--medium M] [--motion M] [--pacing P] [--notes N]
                    [--source <file> ...] [--asset <file> ...] [--preview <file> ...] [--brand <id>]
  styles.py handoff --style ink-wash                    read-only JSON for a fresh build; never builds or copies
capture needs the person's ✋ final film yes in film.json `approvals.final` (listening included). An older brief.md
still works: it needs the brief's current, unchanged render yes and listening yes (or every sound declared none), read
through brief.py's own handoff. A measurement is never an approval. Render yes is permission to render, not a review
of the finished file, so capture also needs the finished video (fingerprinted where it is, never copied) and the
person's own words approving it for saving, recorded verbatim; they are never inferred from a file name or levels.
Only files the film names (in film.json `inputs`, none changed after the finished video was made) or an older brief
names (build files as assets with role "source", before the stills and render decisions) are covered by that approval: every --source (default index.html) and --asset must be one of them, unchanged, and a
referenced file the brief does not name is left out with the reason. It always makes a NEW folder and never replaces
one. It keeps the selected editable sources and the local text sources they reference, the pictures, fonts or sounds
named with --asset (provenance from the brief's asset notes), still previews (in previews/, marked as evidence only
when the brief recorded a decision on that exact file; a video preview is fingerprinted, not copied) and a manifest
of external or uncopied dependencies. The dependency scan reads literal src/href/url()/@import/import/fetch paths,
so paths built at run time are not found. Hidden files, credentials, vendor/node_modules/renders, videos, brand files
made per job, prompt packages and the brief's private library (prompt_file, code_file and everything under
source_root) are never copied or read. The original story and brand are kept apart as context only; a reference has
no slots and no brand, so new on a reference stops with fresh-build guidance.
Without --root or a studio, capture saves to <repo>/reels/styles (or the --brand pack's folder), never inside the
skill package. A record without "kind" is a legacy template and works as before.

Where styles live (<styles>):
  --root <dir>                  <dir>/styles
  inside a studio folder        <studio>/styles   (a parent folder holds .reel-kit/; updates never touch it)
  in a repo, with a brand       <brand kit>/kit-to-clip/styles   (the repo's brand from brand.py, or --brand)
  in a repo, no brand           <repo>/reels/styles
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                 # the kit-to-clip skill
VIDEO = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}
REGENERATED = {"frame.md", "brand.css", "brand-snippets.js", ".reel-brand.json", "platform.json", "platform.css"}
SKIP_DIRS = {"vendor", "snapshots", "renders", "node_modules", ".git", "__pycache__"}
CANVAS = {"tiktok": "1080x1920", "instagram": "1080x1920", "instagram-reels": "1080x1920", "youtube-shorts": "1080x1920",
          "instagram-feed": "1080x1350", "youtube": "1920x1080", "website-loop": "1920x1080"}
KINDS = ("template", "reference")          # a record without "kind" is a legacy template
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SOURCE_EXT = {".html", ".htm", ".css", ".js", ".mjs", ".json", ".svg", ".md", ".txt"}
SCANNED = {".html", ".htm", ".css", ".js", ".mjs", ".svg"}
STILLS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
FINISHED = VIDEO | {".gif"}
SECRET = re.compile(r"(credential|secret|password|api[-_]?key|^id_[rd]sa|\.pem$|\.key$|\.p12$|\.pfx$)", re.I)
MAX_SOURCE, MAX_ASSET, MAX_TEXT = 2_000_000, 20_000_000, 4000
REF_PATTERNS = [re.compile(r"""\b(?:src|href|poster|data-src)\s*=\s*["']([^"']+)["']""", re.I),
                re.compile(r"""url\(\s*["']?([^"')\s]+)["']?\s*\)""", re.I),
                re.compile(r"""@import\s+["']([^"']+)["']""", re.I),
                re.compile(r"""\bimport\s*(?:[\w*{}\s,]+?\s*from\s*)?\(?\s*["']([^"']+)["']"""),
                re.compile(r"""\bfetch\(\s*["']([^"']+)["']""")]
SCAN_NOTE = ("Static scan: literal paths in src, href, poster, data-src, url(), @import, import and fetch are followed; "
             "paths built at run time (variables, templates, string joins) are not found.")
NOT_A_FILE = ("#", "data:", "blob:", "mailto:", "tel:", "javascript:", "about:")
EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")
CONTEXT_NOTE = ("The story and brand this was first made for, kept as context only: never applied to a new video "
                "automatically; choose the new job's story and brand fresh.")
UNCOVERED = ("not named in the brief, so the person's current render approval does not cover its bytes; name it in "
             "the brief's assets (role source) before the stills and render decisions")
UNCOVERED_FILM = ("not named in film.json inputs, so the person's ✋ final film yes does not cover it; name the build "
                  "files there before the final film")
BRAND_RULE = ("Choose this job's brand fresh (the reference's own look, a palette, or a full identity). The original "
              "brand in original_context is context only and is never applied automatically.")


def load_module(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def styles_dirs(a, brand=None):
    """[(styles folder, brand id or None)] this command reads; the first one is where new styles go."""
    if a.root:
        return [(Path(a.root).expanduser().resolve() / "styles", brand)]
    d = Path.cwd().resolve()
    for p in [d, *d.parents]:
        if (p / ".reel-kit").is_dir():
            return [(p / "styles", brand)]
    found = load_module("reel_brand_detect", HERE / "brand.py")
    r = found.detect(found.repo_root(None))
    packs = r.get("packs", [])
    if brand:
        packs = [p for p in packs + r.get("installed", []) if p["brand"] == brand.lower()][:1]
        if not packs:
            sys.exit(f"styles: no video pack for brand '{brand}' in this repo or installed")
    return [(Path(p["kit"]) / "kit-to-clip" / "styles", p["brand"]) for p in packs] + [(Path(r["repo"]) / "reels" / "styles", None)]


def format_ids():
    try:
        mod = load_module("reel_formats_list", ROOT / "formats" / "scripts" / "formats.py")
        return {r["id"] for r in mod.collect(Path.cwd().resolve())}
    except SystemExit:
        return set()


def find_style(a, slug):
    for base, _ in styles_dirs(a):
        if (base / slug / "style.json").exists():
            return base / slug
    return None


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "style"


def load(style_dir):
    return json.loads((style_dir / "style.json").read_text())


def dump(style_dir, data):
    (style_dir / "style.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def kind_of(data):
    return data.get("kind") or "template"


def cmd_list(a):
    rows, problems = [], []
    for base, _ in styles_dirs(a, a.brand):
        for f in sorted(base.glob("*/style.json")):
            if f.parent.name.startswith("."):    # a capture's work folder (or one a crash left) is not a style
                continue
            try:
                d = json.loads(f.read_text())
            except (OSError, ValueError) as e:
                problems.append(f"{f}: not readable JSON ({e})")
                continue
            if not isinstance(d, dict):
                problems.append(f"{f}: not a JSON object")
                continue
            tags = d.get("tags") if isinstance(d.get("tags"), list) else []
            rows.append({**{k: d.get(k) for k in ("slug", "title", "status", "author", "brand", "made_for", "platforms",
                                                  "length_s", "version")}, "path": str(f.parent),
                         "kind": kind_of(d), "tags": [t for t in tags if isinstance(t, str)]})
    for p in problems:
        print(f"styles: skipped {p}", file=sys.stderr)
    if a.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    if not rows:
        print("no saved styles yet", file=sys.stderr)
    for r in rows:
        details = [r["brand"] or "no brand", r["made_for"], ",".join(r["platforms"] or []), f"{r['length_s']} s" if r["length_s"] else None,
                   "reference (adapt in a fresh build)" if r["kind"] == "reference" else None]
        extra = "".join(f" · {x}" for x in details if x)
        by = f" by {r['author']}" if r["author"] else ""
        print(f"{r['slug']:<22} {(r['title'] or '')[:24]:<24} {r['status'] or '?':<9}{by}{extra} · v{r['version']}")


def cmd_init(a):
    slug = a.slug or slugify(a.title)
    if slug in format_ids():
        sys.exit(f"styles: '{slug}' is already a format's name; pick another title")
    dirs = styles_dirs(a, a.brand)
    if not a.brand and len([b for _, b in dirs if b]) > 1:
        sys.exit("styles: this repo has more than one brand; pass --brand <id>")
    base, brand = dirs[0]
    d = base / slug
    if (d / "style.json").exists():
        sys.exit(f"styles: {slug} already exists ({d}); use another title or --slug")
    d.mkdir(parents=True)
    today = datetime.date.today().isoformat()
    data = {
        "slug": slug, "title": a.title, "author": a.author, "created": today, "updated": today, "version": 1,
        "status": "draft", "brand": brand, "remix_of": a.from_style,
        "made_for": None, "platforms": [], "canvas": None, "length_s": None, "mood": None,
        "structure": [], "slots": [], "type": None, "sound": None, "signature": None,
        "dos": [], "donts": [], "references": [], "motion_rules": [],
    }
    dump(d, data)
    (d / "style.md").write_text(f"# {a.title}\n\nBy {a.author}, {today}. Status: draft.\n\n"
                                "Written by the style workshop (kit-to-clip). Sections: purpose, beat sheet, slots, "
                                "look, type, sound, signature moment, do and don't.\n")
    print(d)


def copy_template(project, dst):
    for src in project.rglob("*"):
        rel = src.relative_to(project)
        if any(part in SKIP_DIRS for part in rel.parts) or src.is_dir():
            continue
        if rel.name in REGENERATED or rel.suffix.lower() in VIDEO or rel.name == ".DS_Store":
            continue
        if rel.parts[:2] in {("assets", "fonts"), ("assets", "brand"), ("assets", "stills")}:
            continue
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)


def cmd_save(a):
    d = find_style(a, a.style)
    if not d:
        sys.exit(f"styles: no style '{a.style}'; run init first")
    project = Path(a.project).resolve()
    if not (project / "index.html").exists():
        sys.exit(f"styles: {project} has no index.html")
    data = load(d)
    if kind_of(data) == "reference":
        sys.exit(f"styles: '{a.style}' is a saved reference; references are never replaced. Save the new treatment "
                 "as a new reference with styles.py capture")
    if (d / "template").exists():
        data["version"] = data.get("version", 1) + (1 if data.get("status") == "approved" else 0)
        shutil.rmtree(d / "template")
    copy_template(project, d / "template")
    shots = sorted((project / "snapshots").glob("*.png")) if (project / "snapshots").exists() else []
    if shots:
        (d / "approved").mkdir(exist_ok=True)
        for s in shots:
            shutil.copy2(s, d / "approved" / s.name)
    data["updated"] = datetime.date.today().isoformat()
    data["status"] = "approved" if a.approve else data.get("status", "draft")
    dump(d, data)
    size = sum(f.stat().st_size for f in (d / "template").rglob("*") if f.is_file())
    print(f"saved {a.style} v{data['version']} ({data['status']}): template {size / 1e6:.1f} MB, {len(shots)} approved stills")


def cmd_refs(a):
    d = find_style(a, a.style)
    if not d:
        sys.exit(f"styles: no style '{a.style}'; run init first")
    data = load(d)
    refs = d / "refs"
    refs.mkdir(exist_ok=True)
    kept = data.get("references") or []
    for name in a.files:
        src = Path(name).expanduser()
        if not src.is_file():
            sys.exit(f"styles: not a file: {src}")
        if src.suffix.lower() in VIDEO:
            sys.exit(f"styles: {src.name} is a video; keep its reference.md and contact sheet instead")
        shutil.copy2(src, refs / src.name)
        if src.name not in kept:
            kept.append(src.name)
    data["references"] = kept
    data["updated"] = datetime.date.today().isoformat()
    dump(d, data)
    print(f"{a.style}: {len(kept)} reference(s) in {refs}")


def cmd_new(a):
    d = find_style(a, a.style)
    try:
        is_reference = bool(d) and kind_of(load(d)) == "reference"
    except (OSError, ValueError, AttributeError):
        is_reference = False
    if is_reference:
        sys.exit(f"styles: '{a.style}' is a saved code reference, not a template: it has no slots and carries no "
                 "brand, so nothing was created. Start a fresh build for the new story: read it with "
                 f"styles.py handoff --style {a.style} (read-only), adapt its medium, motion and pacing to the new "
                 "story, and choose this job's brand fresh (its original brand is context only).")
    if not d or not (d / "template" / "index.html").exists():
        sys.exit(f"styles: style '{a.style}' has no saved template yet")
    data = load(d)
    out = Path(a.out).resolve()
    if out.exists() and any(out.iterdir()):
        sys.exit(f"styles: {out} is not empty")
    shutil.copytree(d / "template", out, dirs_exist_ok=True)
    canvas = a.canvas or data.get("canvas") or CANVAS.get((data.get("platforms") or ["tiktok"])[0], "1080x1920")
    if data.get("brand"):
        bridge = ROOT / "brand" / "scripts" / "bridge.py"
        subprocess.run([sys.executable, str(bridge), "--brand", data["brand"], "--project", str(out),
                        "--canvas", canvas, "--force"], check=True)
    gsap = next((p / "node_modules/gsap/dist/gsap.min.js" for p in [out, *out.parents]
                 if (p / "node_modules/gsap/dist/gsap.min.js").exists()), None)
    if gsap:
        (out / "vendor").mkdir(exist_ok=True)
        shutil.copy2(gsap, out / "vendor" / "gsap.min.js")
    print(f"new project from {a.style} v{data.get('version')}: {out} (canvas {canvas}); fill the slots in style.json")


# --- saved references ----------------------------------------------------------------------------------------------
def inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([path, root]) == root


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def text_arg(value, what):
    if value is not None and ("\x00" in value or len(value) > MAX_TEXT):
        sys.exit(f"styles: {what} has a NUL character or is longer than {MAX_TEXT} characters")
    return value.strip() if value and value.strip() else None


def final_approval(brief_mod, path, expected):
    """brief.py's own handoff, refused unless the person's render yes and listening (or declared silence) still count."""
    try:
        h = brief_mod.handoff(path, expected)
    except brief_mod.BriefError as e:
        sys.exit(f"styles: capture refused: the brief cannot be used ({e})")
    approvals, problems = h["approvals"], []

    def counts(gate, states):
        rec = approvals.get(gate)
        return bool(rec) and rec["state"] in states and not rec["stale"]

    def why(gate):
        rec = approvals.get(gate)
        if not rec:
            return "none recorded"
        return f"recorded {rec['state']}" + (f", no longer counts: {'; '.join(rec['stale_reasons'])}" if rec["stale"] else "")

    if not counts("render", ("yes",)):
        problems.append(f"no current render yes from the person ({why('render')})")
    sounds = [k for k in brief_mod.SOUNDS if h["inputs"]["audio"][k]["choice"] != "none"]
    if sounds:
        if not counts("listening", ("yes",)):
            problems.append(f"no current listening yes for the {', '.join(sounds)} ({why('listening')}); a loudness "
                            "or level check is a measurement, not the person's listening")
    elif "listening" in approvals and not counts("listening", ("yes", "n/a")):
        problems.append(f"listening was decided but does not count ({why('listening')})")
    problems += [f"gate still open: {g}" for g in h["open_gates"]]
    problems += h["unresolved"]
    if problems:
        sys.exit("styles: capture refused: the video is not finally approved in its brief, so nothing was saved:\n  - "
                 + "\n  - ".join(dict.fromkeys(problems)))
    return h


def looks_like_prompt(real):
    try:
        with open(real, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and ("prompt" in data or isinstance(data.get("info"), dict) and "prompt" in data["info"])


def name_refusal(rel):
    parts = rel.parts
    if not parts or parts[0] == ".." or rel.is_absolute():
        return "outside the project folder"
    if any(p.startswith(".") for p in parts):
        return "a hidden file (settings, credentials or version control); never copied"
    lib = next((p for p in parts if p in SKIP_DIRS), None)
    if lib:
        return f"in {lib}/ (a library, build or render folder); install or copy it again for a new build"
    if rel.name in REGENERATED:
        return "made per job by the brand bridge; choose the new job's brand instead of reusing this one"
    if rel.suffix.lower() in VIDEO:
        return "a video; footage and renders are not kept in a reference"
    if SECRET.search(rel.name):
        return "looks like a credential or secret; never copied"
    return None


def refusal(project, rel, role, private):
    """Why a project file may not go into a reference (None when it may). rel is relative to the project."""
    why = name_refusal(rel)
    if why:
        return why
    real = os.path.realpath(project / rel)
    if not inside(real, project):
        return "links outside the project folder"
    why = name_refusal(Path(os.path.relpath(real, project)))   # a link inside the project is judged by its target
    if why:
        return f"links to a file that is {why}"
    if any(inside(real, root) for root in private):
        return "the private library source named in the brief; it stays in your own collection"
    if not os.path.exists(real):
        return "missing"
    if not os.path.isfile(real):
        return "not a regular file"
    if rel.name in ("brief.md", "film.json"):
        return "the production brief; its story and brand are kept as context instead"
    size = os.path.getsize(real)
    if real.lower().endswith(".json") and size <= MAX_SOURCE and looks_like_prompt(real):
        return "looks like a private prompt package; not copied"
    if role == "source":
        if rel.suffix.lower() not in SOURCE_EXT:
            return "not an editable text source (keep pictures, fonts and sounds with --asset)"
        if size > MAX_SOURCE:
            return "too large for an editable source file"
    elif size > MAX_ASSET:
        return "too large to keep in a reference"
    return None


def selected(project, raw, role, private, covered, uncovered=lambda real: UNCOVERED):
    if not raw or os.path.isabs(os.path.expanduser(raw)):
        sys.exit(f"styles: --{role} {raw!r} must be a path relative to --project")
    rel = Path(os.path.normpath(raw))
    why = refusal(project, rel, role, private)
    if not why and os.path.realpath(project / rel) not in covered:
        why = uncovered(os.path.realpath(project / rel))
    if why:
        sys.exit(f"styles: --{role} {raw}: {why}; nothing was saved")
    return rel


def scan(project, rel):
    """(external refs, local project-relative paths) referenced by one selected text source."""
    text = (project / rel).read_text(encoding="utf-8", errors="replace")
    external, local = [], []
    for pat in REF_PATTERNS:
        for m in pat.finditer(text):
            ref = m.group(1).strip()
            if not ref or ref.startswith(NOT_A_FILE) or "${" in ref or "{{" in ref:
                continue
            if EXTERNAL.match(ref):
                external.append(ref)
                continue
            path = unquote(ref.split("#")[0].split("?")[0])
            if not path:
                continue
            target = project / path.lstrip("/") if path.startswith("/") else project / rel.parent / path
            local.append((ref, Path(os.path.relpath(os.path.normpath(target), project))))
    return external, local


def collect(project, sources, assets, private, covered, uncovered=lambda real: UNCOVERED):
    """Walk the selected sources' references: what is kept, what is external and what is left behind (and why)."""
    keep = {rel: ("source", "selected") for rel in sources}
    keep.update({rel: ("asset", "selected") for rel in assets if rel not in keep})
    external, not_copied, queue, seen = {}, {}, list(sources), set(sources)
    while queue:
        rel = queue.pop(0)
        if rel.suffix.lower() not in SCANNED:
            continue
        ext, local = scan(project, rel)
        for ref in ext:
            external.setdefault(ref, {"ref": ref, "found_in": rel.as_posix(),
                                      "note": "outside this machine's files; a new build must reach or replace it"})
        for ref, dep in local:
            if dep in keep or dep in seen:
                continue
            seen.add(dep)
            role = "source" if dep.suffix.lower() in SOURCE_EXT else "asset"
            why = refusal(project, dep, role, private)
            if not why and role == "asset":
                why = "an asset not chosen for the reference; pass --asset <path> to keep it with its provenance"
            if not why and os.path.realpath(project / dep) not in covered:
                why = uncovered(os.path.realpath(project / dep))
            name = ref if why == "outside the project folder" else dep.as_posix()
            if why:
                not_copied.setdefault(name, {"ref": name, "found_in": rel.as_posix(), "reason": why})
            else:
                keep[dep] = ("source", "dependency")
                queue.append(dep)
    return keep, list(external.values()), list(not_copied.values())


def capture_base(a):
    dirs = styles_dirs(a, a.brand)
    base = dirs[0][0] if a.brand or len(dirs) == 1 else dirs[-1][0]   # a reference is brand-neutral by default
    if inside(base, ROOT):
        sys.exit(f"styles: refusing to save inside the Kit to Clip skill package, which is distributed publicly "
                 f"({base}); pass --root <a private folder>")
    return base


def asset_notes(brief_file, inputs):
    """{real path: (role, notes)} for the brief's named assets, for provenance."""
    out = {}
    for asset in inputs["assets"].values():
        if asset.get("path"):
            p = Path(os.path.expanduser(asset["path"]))
            p = p if p.is_absolute() else brief_file.parent / p
            out[os.path.realpath(p)] = (asset.get("role"), asset.get("notes"))
    return out


def original_context(inputs):
    pick = lambda d, keys: {k: d[k] for k in keys if k in d}
    audio = inputs["audio"]
    return {"note": CONTEXT_NOTE, "request": inputs["request"], "route": inputs["route"],
            "destination": dict(inputs["destination"]),
            "story": pick(inputs["story"], ("summary", "beats", "onscreen", "script", "notes")),
            "brand": pick(inputs["brand"], ("mode", "id", "name", "palette", "notes")),
            "audio": {"timing_driver": audio["timing_driver"],
                      **{k: pick(audio[k], ("choice", "details")) for k in ("voice", "music", "effects")}}}


def approval_record(rec):
    out = {k: rec[k] for k in ("state", "note", "at", "input_revision") if k in rec}
    if rec.get("evidence"):
        out["evidence"] = {k: rec["evidence"].get(k) for k in ("path", "sha256", "size")}
    return out


def finished_output(raw):
    """The finished video, fingerprinted where it is (never copied)."""
    p = Path(os.path.realpath(os.path.expanduser(raw)))
    if not p.is_file() or SECRET.search(p.name):
        sys.exit(f"styles: --finished-output {raw} is not a readable file; nothing was saved")
    if p.suffix.lower() not in FINISHED:
        sys.exit(f"styles: --finished-output {raw} must be the finished video ({', '.join(sorted(FINISHED))}); "
                 "nothing was saved")
    return {"path": str(p), "sha256": sha256(p), "size": p.stat().st_size, "copied": False}


def final_basis(approvals, sounds, matches):
    """The decisions the save actually rests on, in order, without claiming any that did not happen."""
    parts = ["layout yes", "stills yes"]
    parts += [f"{g} yes" for g in ("voice-choice", "music-choice") if approvals.get(g, {}).get("state") == "yes"]
    parts.append("render yes (permission to render, not a review of the finished file)")
    if sounds:
        parts.append("listening yes on the mix " + {True: "(its evidence file is this finished output)",
                                                     False: "(given on a different file than this finished output)",
                                                     None: "(not tied to a specific file)"}[matches])
    else:
        parts.append("no sound, so no listening review took place")
    parts.append("then the person's own words approving this finished output for saving (approval_note, as "
                 "supplied by the caller)")
    return "; ".join(parts)


def reference_md(data):
    ins, ref, ctx = data["instructions"], data["reference"], data["original_context"]
    lines = [f"# {data['title']}", "",
             f"A personal code reference saved on {data['created']} from a finished video the person approved for "
             "saving. It is not a template: it "
             "has no slots and applies no brand. Reuse it in a fresh build: read the sources, keep what makes the "
             "treatment work, and fit the subjects, text and timing to the new story.", "",
             "## Reusable instructions", ""]
    lines += [f"- {k.replace('_', ' ')}: {v}" for k, v in ins.items()] or ["- (none written)"]
    lines += ["", f"Tags: {', '.join(data['tags']) or '(none)'}", "", "## Files", "", f"Entry: {ref['entry']}", ""]
    lines += [f"- {f['path']} ({f['role']}, {f['selected']})" + (f": {f['provenance']}" if f.get("provenance") else "")
              for f in ref["files"]]
    lines += ["", "## Portability", "", ref["portability"], ""]
    lines += [f"- external: {e['ref']} (in {e['found_in']})" for e in ref["external"]]
    lines += [f"- not copied: {n['ref']} (in {n['found_in']}): {n['reason']}" for n in ref["not_copied"]]
    lines += ["", "## Previews", ""]
    lines += [f"- {p.get('path') or p.get('external_path')}" + (" (the finished output)" if p.get("finished_output") else "")
              + (f" (the file the {', '.join(p['evidence_for'])} decision was recorded on)" if p.get("evidence_for")
                 else " (preview only: not recorded as the file of any decision)") for p in ref["previews"]] \
        or ["- (none supplied)"]
    brand = ctx["brand"]
    lines += ["", "## Original context (context only)", "", ctx["note"], "",
              f"- request: {' '.join(ctx['request'].split())}",
              f"- story: {' '.join(str(ctx['story'].get('summary', '(not recorded)')).split())}",
              f"- brand: {brand.get('name') or brand.get('id') or 'none'} (mode {brand.get('mode')})", "",
              "## Provenance", "",
              (f"Film {data['provenance']['film']}" if "film" in data["provenance"] else
               f"Brief {data['provenance']['brief']} at revision {data['provenance']['brief_revision']}") +
              f"; project {data['provenance']['project']}.", "",
              f"Basis: {data['provenance']['final_save']['basis']}.", "",
              f"Finished output (fingerprinted, not copied): {data['provenance']['final_save']['finished_output']['path']}",
              f"Words recorded for the save: {' '.join(data['provenance']['final_save']['approval_note'].split())}"]
    return "\n".join(lines) + "\n"


FILM_STOPS = ("script", "storyboard", "music", "final")


def film_basis(approvals, sounds):
    """The four-stop decisions a film.json save rests on, in order, without claiming any that did not happen."""
    parts = [label for stop, label in (("script", "script yes"), ("storyboard", "storyboard yes"),
                                       ("music", "music pick yes (heard on the built picture)")) if stop in approvals]
    parts.append("✋ final film yes on the finished film, " + ("listening included" if sounds else
                                                             "a film with no sound, so no listening took place"))
    parts.append("then the person's own words approving this finished output for saving (approval_note, as "
                 "supplied by the caller)")
    return "; ".join(parts)


def film_source(a, final):
    """What film.json approves: the person's ✋ final film yes, and the files it names that did not change after the
    finished video was made."""
    film_file = Path(os.path.abspath(os.path.expanduser(a.film)))
    if film_file.is_dir():
        film_file = film_file / "film.json"
    try:
        film = json.loads(film_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"styles: capture refused: {film_file} is not a readable film.json ({e})")
    if not isinstance(film, dict) or film.get("kit_to_clip_film") != 1:
        sys.exit(f"styles: capture refused: {film_file} is not a Kit to Clip film.json (kit_to_clip_film 1)")
    raw = film.get("approvals") if isinstance(film.get("approvals"), dict) else {}
    approvals = {s: {"state": "yes", "note": rec["yes"].strip(), **({"at": rec["at"]} if isinstance(rec.get("at"), str)
                                                                    else {})}
                 for s, rec in raw.items() if s in FILM_STOPS and isinstance(rec, dict)
                 and isinstance(rec.get("yes"), str) and rec["yes"].strip()}
    if "final" not in approvals:
        sys.exit("styles: capture refused: film.json has no ✋ final film yes (approvals.final), so nothing was saved. "
                 "Rendering is not a yes, and a loudness or level check is a measurement, not the person's listening")
    made = os.path.getmtime(final["path"])
    covered, stale, notes = {}, {}, {}
    inputs = [i for i in film.get("inputs") or [] if isinstance(i, dict) and isinstance(i.get("path"), str) and i["path"]]
    for n, item in enumerate(inputs):
        p = Path(os.path.expanduser(item["path"]))
        real = os.path.realpath(p if p.is_absolute() else film_file.parent / p)
        notes[real] = (item.get("kind"), item.get("note"))
        if not os.path.isfile(real):
            continue
        if isinstance(item.get("sha256"), str) and item["sha256"] != sha256(real):
            stale[item["path"]] = "changed since film.json recorded its fingerprint"
        elif os.path.getmtime(real) > made:
            stale[item["path"]] = "changed after the finished video was made"
        else:
            covered[real] = f"inputs[{n}].path"
    if stale:                      # the person saw and heard a film made from other bytes
        sys.exit("styles: capture refused: the ✋ final film yes no longer covers the build, so nothing was saved; "
                 "render and show the film again:\n  - " + "\n  - ".join(f"{p}: {why}" for p, why in stale.items()))
    sounds = sorted({i.get("kind") for i in inputs} & {"voice", "music", "effects"} | ({"music"} & set(approvals)))
    brand = film.get("brand") if isinstance(film.get("brand"), dict) else {}
    parts = [p for p in film.get("parts") or [] if isinstance(p, dict)]
    context = {"note": CONTEXT_NOTE, "request": str(film.get("about") or film.get("title") or ""), "route": "film.json",
               "destination": {k: film[k] for k in ("frame", "length") if k in film},
               "story": {"summary": film.get("about") or film.get("title"),
                         "beats": [p.get("name") for p in parts if p.get("name")]},
               "brand": {"mode": "brand" if brand else "original", "id": brand.get("skill"), "name": brand.get("name")},
               "audio": {k: {"choice": "supplied" if k in sounds else "none"} for k in ("voice", "music", "effects")}}
    return {"covered": covered, "uncovered": lambda real: UNCOVERED_FILM, "private": set(),
            "style_notes": None, "notes": notes, "approvals": approvals, "field": "film_field", "context": context,
            "head": {"film": str(film_file), "film_sha256": sha256(film_file)}, "tail": {},
            "record": approvals, "basis": film_basis(approvals, sounds), "matches": None,
            "rule": "every saved file is named in film.json inputs and was not changed after the finished video was "
                    "made (the ✋ final film yes covers that film)"}


def brief_source(a, final):
    """What an older brief.py brief approves: its current render yes and listening, and the files it fingerprinted."""
    brief_mod = load_module("reel_brief_for_capture", HERE / "brief.py")
    brief_file = Path(os.path.abspath(os.path.expanduser(a.brief)))
    h = final_approval(brief_mod, brief_file, a.expected)
    inputs, approvals = h["inputs"], h["approvals"]
    ref_files = inputs["style"].get("reference", {})
    private = {os.path.realpath(p if p.is_absolute() else brief_file.parent / p)
               for p in (Path(os.path.expanduser(ref_files[k])) for k in ("prompt_file", "code_file", "source_root")
                         if ref_files.get(k))}
    sounds = [k for k in brief_mod.SOUNDS if inputs["audio"][k]["choice"] != "none"]
    heard = approvals.get("listening", {}).get("evidence", {}).get("sha256") if sounds else None
    matches = None if not heard else heard == final["sha256"]
    record = {**{g: approval_record(approvals[g]) for g in ("layout", "stills", "voice-choice", "music-choice")
                 if g in approvals},
              "render": approval_record(approvals["render"]),
              "listening": approval_record(approvals["listening"]) if "listening" in approvals
              and approvals["listening"]["state"] == "yes" else
              dict({"silent": True}, **({"state": "n/a", "note": approvals["listening"]["note"]}
                                        if "listening" in approvals else {}))}
    # The current render approval holds; so every named file whose status is ok is the byte-for-byte file it covered.
    return {"covered": {os.path.realpath(r["resolved"]): r["field"] for r in h["files"] if r["status"] == "ok"},
            "uncovered": lambda real: UNCOVERED, "private": private,
            "style_notes": inputs["style"].get("notes") or None, "notes": asset_notes(brief_file, inputs),
            "approvals": approvals, "field": "brief_field", "context": original_context(inputs),
            "head": {"brief": str(brief_file), "brief_revision": h["revision"], "brief_digest": h["digest"]},
            "tail": {"style_name": inputs["style"].get("name"), "saved_style": inputs["style"].get("saved_style"),
                     "style_reference": {k: ref_files[k] for k in ("catalogue_id", "origin", "permitted_use",
                                                                   "source_sha256") if k in ref_files}},
            "record": record, "basis": final_basis(approvals, sounds, matches), "matches": matches,
            "rule": "every saved file is named in the brief and unchanged since the current render approval (input "
                    f"revision {approvals['render']['input_revision']})"}


def cmd_capture(a):
    if bool(a.film) == bool(a.brief):
        sys.exit("styles: capture needs --film <video>/film.json (or, for an older brief, --brief with --expected)")
    if a.brief and a.expected is None:
        sys.exit("styles: --brief needs --expected <the brief revision the person approved>")
    title = text_arg(a.title, "--title")
    if not title:
        sys.exit("styles: --title must not be empty")
    slug = a.slug if a.slug is not None else slugify(title)
    if not SLUG_RE.match(slug):
        sys.exit(f"styles: '{slug}' is not a usable folder name (lower-case letters, digits and dashes)")
    base = capture_base(a)
    dest = base / slug
    if os.path.lexists(dest) or find_style(a, slug):
        sys.exit(f"styles: {slug} already exists ({dest}); a reference is always saved as a new folder, so pick "
                 "another title or --slug")
    if slug in format_ids():
        sys.exit(f"styles: '{slug}' is already a format's name; pick another title or --slug")
    words = text_arg(a.approval_note, "--approval-note")
    if not words:
        sys.exit("styles: --approval-note must be the person's own words approving the finished video for saving; "
                 "nothing was saved (render yes is permission to render, not that approval)")
    final = finished_output(a.finished_output)
    src = film_source(a, final) if a.film else brief_source(a, final)
    covered, private, uncovered = src["covered"], src["private"], src["uncovered"]
    project = Path(os.path.realpath(os.path.expanduser(a.project)))
    if not project.is_dir():
        sys.exit(f"styles: --project {a.project} is not a folder")
    raw_sources = a.source or (["index.html"] if (project / "index.html").is_file() else [])
    if not raw_sources:
        sys.exit("styles: name the editable source with --source <file inside --project>")
    sources = list(dict.fromkeys(selected(project, s, "source", private, covered, uncovered) for s in raw_sources))
    assets = list(dict.fromkeys(selected(project, s, "asset", private, covered, uncovered) for s in a.asset or []))
    previews = []
    for raw in a.preview or []:
        p = Path(os.path.realpath(os.path.expanduser(raw)))
        if not p.is_file() or SECRET.search(p.name):
            sys.exit(f"styles: --preview {raw} is not a readable picture or video file")
        if p.suffix.lower() not in STILLS | VIDEO:
            sys.exit(f"styles: --preview {raw} must be a still picture ({', '.join(sorted(STILLS))}) or a video")
        if p.suffix.lower() in STILLS and p.stat().st_size > MAX_ASSET:
            sys.exit(f"styles: --preview {raw} is too large to keep")
        previews.append(p)
    tags = []
    for t in a.tag or []:
        t = text_arg(t, "--tag")
        if t and t not in tags:
            tags.append(t[:80])
    instructions = {k: v for k, v in (("medium", text_arg(a.medium, "--medium")), ("motion", text_arg(a.motion, "--motion")),
                                      ("pacing", text_arg(a.pacing, "--pacing")), ("notes", text_arg(a.notes, "--notes")),
                                      ("style_notes", src["style_notes"])) if v}
    keep, external, not_copied = collect(project, sources, assets, private, covered, uncovered)

    approvals, notes = src["approvals"], src["notes"]
    today = datetime.date.today().isoformat()
    base.mkdir(parents=True, exist_ok=True)
    if inside(base, ROOT):
        sys.exit(f"styles: refusing to save inside the Kit to Clip skill package ({base})")
    work = Path(tempfile.mkdtemp(prefix=f".capture-{slug}-", dir=base))   # hidden: no reader lists it meanwhile
    claimed = False
    try:
        files = []
        for rel, (role, how) in sorted(keep.items(), key=lambda x: x[0].as_posix()):
            out = work / "source" / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(os.path.realpath(project / rel), out)
            row = {"path": f"source/{rel.as_posix()}", "from": rel.as_posix(), "role": role, "selected": how,
                   "size": out.stat().st_size, "sha256": sha256(out),
                   src["field"]: covered[os.path.realpath(project / rel)]}
            if role == "asset":
                asset_role, note = notes.get(os.path.realpath(project / rel), (None, None))
                row["provenance"] = note or "not recorded in the brief; check its rights before reusing it"
                if asset_role:
                    row["asset_role"] = asset_role
            files.append(row)
        kept_previews = []
        for p in previews:
            digest = sha256(p)
            on = [g for g, apr in approvals.items() if apr.get("evidence", {}).get("sha256") == digest]
            row = {"from": str(p), "sha256": digest, "size": p.stat().st_size, "evidence_for": on,
                   "approval_evidence": bool(on), "finished_output": digest == final["sha256"]}
            if p.suffix.lower() in STILLS:
                (work / "previews").mkdir(exist_ok=True)
                name = p.name if not (work / "previews" / p.name).exists() else f"{len(kept_previews)}-{p.name}"
                shutil.copy2(p, work / "previews" / name)
                row["path"] = f"previews/{name}"
            else:
                row.update(external_path=str(p), note="a video preview is fingerprinted where it is, not copied")
            kept_previews.append(row)
        portable = not external and not not_copied
        portability = ("Self-contained as far as the static scan sees: every local file it found is kept here; "
                       "check paths built at run time yourself." if portable else
                       f"Partly portable: the static scan found {len(external)} external reference(s) and "
                       f"{len(not_copied)} local file(s) that were not copied (listed with reasons). A new build must "
                       "supply or replace them; paths built at run time are not found by the scan.")
        data = {
            "slug": slug, "title": title, "author": text_arg(a.author, "--author"), "created": today, "updated": today,
            "version": 1, "status": "approved", "kind": "reference", "brand": None, "remix_of": None,
            "made_for": None, "platforms": [], "canvas": None, "length_s": None, "mood": None,
            "structure": [], "slots": [], "type": None, "sound": None, "signature": None,
            "dos": [], "donts": [], "references": [], "motion_rules": [],
            "tags": tags, "instructions": instructions,
            "reference": {"entry": f"source/{sources[0].as_posix()}", "files": files, "external": external,
                          "not_copied": not_copied, "portable": portable, "portability": portability,
                          "dependency_scan": SCAN_NOTE, "previews": kept_previews},
            "provenance": {"captured": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           **src["head"], "project": str(project), "approvals": src["record"], **src["tail"],
                           "final_save": {"finished_output": final, "approval_note": words,
                                          "approval_note_source": "supplied with --approval-note as the person's own "
                                          "words about this finished output; recorded verbatim, not verified by "
                                          "this tool", "basis": src["basis"],
                                          "listening_evidence_matches": src["matches"],
                                          "source_coverage": {"files": [f["path"] for f in files],
                                                              "rule": src["rule"]}}},
            "original_context": src["context"],
        }
        dump(work, data)
        (work / "style.md").write_text(reference_md(data))
        try:
            os.mkdir(dest)                 # claims the new name; fails if anything appeared there meanwhile
        except FileExistsError:
            sys.exit(f"styles: {dest} appeared meanwhile; nothing was replaced")
        claimed = True
        os.rename(work, dest)              # replaces only the empty folder just claimed
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        if claimed and dest.is_dir() and not dest.is_symlink() and not any(dest.iterdir()):
            os.rmdir(dest)
        raise
    print(f"saved reference {slug} ({len(files)} file(s), {len(kept_previews)} preview(s)) in {dest}; "
          f"{'self-contained' if portable else 'partly portable: see not_copied and external in style.json'}")


def contained_style(a, name):
    if not name or name.startswith(".") or name != Path(name).name or "\\" in name:
        sys.exit(f"styles: '{name}' is not a saved-style folder name")
    for base, _ in styles_dirs(a):
        rec = base / name / "style.json"
        if os.path.lexists(rec):
            if not inside(rec, base):
                sys.exit(f"styles: {base / name} links outside the styles folder {base}; not read")
            return base / name
    return None


def cmd_handoff(a):
    d = contained_style(a, a.style)
    if not d:
        sys.exit(f"styles: no saved style '{a.style}'")
    try:
        data = load(d)
    except (OSError, ValueError) as e:
        sys.exit(f"styles: {d / 'style.json'} is not readable JSON ({e})")
    if not isinstance(data, dict) or kind_of(data) != "reference" or not isinstance(data.get("reference"), dict):
        sys.exit(f"styles: '{a.style}' is a legacy template, not a reference; start from it with styles.py new")
    ref = data["reference"]
    files, changed, missing = [], [], []
    for f in ref.get("files") or []:
        p = d / f.get("path", "")
        if not f.get("path") or not inside(p, d):
            missing.append(str(f.get("path")))
            continue
        if not p.is_file():
            missing.append(f["path"])
        elif sha256(p) != f.get("sha256"):
            changed.append(f["path"])
        files.append({**f, "path": str(p)})
    previews = [{**p, "path": str(d / p["path"])} if p.get("path") else p for p in ref.get("previews") or []]
    provenance_warnings = []
    prov = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    final = prov.get("final_save").get("finished_output") if isinstance(prov.get("final_save"), dict) else None
    if isinstance(final, dict) and isinstance(final.get("path"), str) and final["path"]:
        # read where it was, never copied: flag any later change
        final = dict(final, status="missing" if not os.path.isfile(final["path"]) else
                     "ok" if sha256(final["path"]) == final.get("sha256") else "changed")
        if final["status"] != "ok":
            provenance_warnings.append(f"Original finished output is {final['status']}: {final['path']}. "
                                       "The saved editable reference is checked separately.")
    else:
        final = None
    entry_rel = ref.get("entry")
    entry = d / entry_rel if isinstance(entry_rel, str) and entry_rel else None
    entry_valid = entry is not None and inside(entry, d) and entry.is_file()
    if not entry_valid:
        missing.append("reference entry file")
    elif not any(os.path.realpath(f["path"]) == os.path.realpath(entry) for f in files):
        missing.append("reference entry has no recorded file fingerprint")
    out = {"slug": d.name, "title": data.get("title"), "kind": "reference", "status": data.get("status"),
           "ready_to_reuse": data.get("status") == "approved" and not changed and not missing, "path": str(d),
           "entry": str(entry) if entry_valid else None, "files": files, "changed_files": changed,
           "missing_files": missing, "external": ref.get("external") or [], "not_copied": ref.get("not_copied") or [],
           "portable": ref.get("portable"), "portability": ref.get("portability"),
           "dependency_scan": ref.get("dependency_scan"), "previews": previews, "finished_output": final,
           "provenance_warnings": provenance_warnings,
           "instructions": data.get("instructions") or {}, "tags": data.get("tags") or [],
           "brand": None, "brand_rule": BRAND_RULE,
           "original_context": data.get("original_context") or {}, "provenance": data.get("provenance") or {},
           "next_steps": ["Start a fresh brief and build for the new story; this reference is not a template and has "
                          "no slots.",
                          "Read the entry and source files; keep the medium, motion and pacing in instructions and "
                          "change subjects, text and timing to fit the new story.",
                          "Supply or replace everything listed in external and not_copied.",
                          BRAND_RULE],
           "note": "Reads only. It never copies, builds, renders or starts a builder."}
    print(json.dumps(out, indent=2, ensure_ascii=False))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--json", action="store_true"); p.add_argument("--brand"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("init"); p.add_argument("--title", required=True); p.add_argument("--author", required=True)
    p.add_argument("--slug"); p.add_argument("--brand"); p.add_argument("--from", dest="from_style"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("save"); p.add_argument("--style", required=True); p.add_argument("--project", required=True)
    p.add_argument("--approve", action="store_true"); p.set_defaults(fn=cmd_save)
    p = sub.add_parser("new"); p.add_argument("--style", required=True); p.add_argument("--out", required=True)
    p.add_argument("--canvas"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("refs"); p.add_argument("--style", required=True); p.add_argument("files", nargs="+")
    p.set_defaults(fn=cmd_refs)
    p = sub.add_parser("capture", help="save an approved video's treatment as a NEW personal code reference")
    p.add_argument("--film", help="the video's film.json, holding the person's ✋ final film yes in approvals.final")
    p.add_argument("--brief", help="an older video's brief.md (written by brief.py), instead of --film")
    p.add_argument("--expected", type=int, help="with --brief: the brief revision the person approved")
    p.add_argument("--project", required=True, help="the approved project folder")
    p.add_argument("--title", required=True); p.add_argument("--slug"); p.add_argument("--author")
    p.add_argument("--brand", help="save in this brand pack's styles folder (location only; never applied)")
    p.add_argument("--source", action="append", help="editable source inside --project (repeatable; default index.html)")
    p.add_argument("--asset", action="append", help="picture, font or sound inside --project to keep (repeatable)")
    p.add_argument("--preview", action="append", help="a preview still or video (repeatable; marked as evidence "
                   "only when the brief recorded a decision on that exact file)")
    p.add_argument("--tag", action="append"); p.add_argument("--medium"); p.add_argument("--motion")
    p.add_argument("--pacing"); p.add_argument("--notes")
    p.add_argument("--finished-output", required=True,
                   help="the finished video the person approved for saving (fingerprinted where it is, never copied)")
    p.add_argument("--approval-note", required=True,
                   help="the person's own words approving that finished video for saving, recorded verbatim")
    p.set_defaults(fn=cmd_capture)
    p = sub.add_parser("handoff", help="read-only JSON for a fresh build from a saved reference")
    p.add_argument("--style", required=True); p.set_defaults(fn=cmd_handoff)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
