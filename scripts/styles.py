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

Where styles live (<styles>):
  --root <dir>                  <dir>/styles
  inside a studio folder        <studio>/styles   (a parent folder holds .reel-kit/; updates never touch it)
  in a repo, with a brand       <brand kit>/kit-to-clip/styles   (the repo's brand from brand.py, or --brand)
  in a repo, no brand           <repo>/reels/styles
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                 # the kit-to-clip skill
VIDEO = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}
REGENERATED = {"frame.md", "brand.css", "brand-snippets.js", ".reel-brand.json", "platform.json", "platform.css"}
SKIP_DIRS = {"vendor", "snapshots", "renders", "node_modules", ".git", "__pycache__"}
CANVAS = {"tiktok": "1080x1920", "instagram": "1080x1920", "instagram-reels": "1080x1920", "youtube-shorts": "1080x1920",
          "instagram-feed": "1080x1350", "youtube": "1920x1080", "website-loop": "1920x1080"}


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


def cmd_list(a):
    rows = []
    for base, _ in styles_dirs(a, a.brand):
        for f in sorted(base.glob("*/style.json")):
            d = json.loads(f.read_text())
            rows.append({**{k: d.get(k) for k in ("slug", "title", "status", "author", "brand", "made_for", "platforms",
                                                  "length_s", "version")}, "path": str(f.parent)})
    if a.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    if not rows:
        print("no saved styles yet", file=sys.stderr)
    for r in rows:
        details = [r["brand"] or "no brand", r["made_for"], ",".join(r["platforms"] or []), f"{r['length_s']} s" if r["length_s"] else None]
        extra = "".join(f" · {x}" for x in details if x)
        print(f"{r['slug']:<22} {(r['title'] or '')[:24]:<24} {r['status']:<9} by {r['author']}{extra} · v{r['version']}")


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


def main():
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
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
