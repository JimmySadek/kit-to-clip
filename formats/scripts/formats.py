#!/usr/bin/env python3
"""Kit to Clip formats: list the video formats this project can use.

Two sources, one list:
  neutral   <this skill>/neutral/*/format.json: no brand, styled from any pack's token contract (brand "any")
  packs     <brand kit>/kit-to-clip/<formats>/*/format.json for every video pack the bridge can find from the project
            (pack.json "formats": "<folder>"), e.g. a brand's own highlight formats. Brand = that pack's brand.
A format's folder holds its format.json; "journey" names the file to read before building it.

  python3 formats.py list [--project <dir>] [--all] [--brand <name>] [--made-for clip|brief|video|loop] [--json]

By default only approved formats are listed (the front door offers nothing else); --all adds drafts, trials and
retired ones. Broken format files are always listed, marked (broken). Exit 0, or 2 when the brand bridge is missing.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
STATUSES = ("idea", "draft", "trial", "approved", "retired")
MADE_FOR = ("clip", "brief", "video", "loop")


def load_bridge():
    for p in [SKILL.parent / "brand" / "scripts" / "bridge.py"]:     # <kit-to-clip>/brand/scripts/bridge.py
        if p.is_file():
            spec = importlib.util.spec_from_file_location("reel_bridge", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    print("formats: brand/scripts/bridge.py is missing from this Kit to Clip install", file=sys.stderr)
    sys.exit(2)


def read_format(path, brand, source):
    """One format row, or a broken row naming the problem."""
    row = {"brand": brand, "source": source, "folder": str(path.parent)}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        return {**row, "id": path.parent.name, "broken": f"unreadable format.json ({e})"}
    problems = []
    if data.get("schema") != 1:
        problems.append('needs "schema": 1')
    for key in ("id", "name", "status", "made_for"):
        if not data.get(key):
            problems.append(f'needs "{key}"')
    if data.get("status") and data["status"] not in STATUSES:
        problems.append(f"status '{data['status']}' is not one of {', '.join(STATUSES)}")
    if data.get("made_for") and data["made_for"] not in MADE_FOR:
        problems.append(f"made_for '{data['made_for']}' is not one of {', '.join(MADE_FOR)}")
    journey = data.get("journey", "README.md")
    jpath = (path.parent / journey).resolve()
    if not jpath.is_file():
        problems.append(f"journey file {journey} not found")
    row.update({k: data.get(k) for k in ("id", "name", "version", "status", "made_for", "about", "platforms", "canvases")})
    row["id"] = row["id"] or path.parent.name
    row["journey"] = str(jpath)
    if problems:
        row["broken"] = "; ".join(problems)
    return row


def collect(project):
    rows = [read_format(p, "any", "neutral") for p in sorted((SKILL / "neutral").glob("*/format.json"))]
    bridge = load_bridge()
    packs, _ = bridge.find_packs(project)
    for brand, (kit, data) in packs.items():
        folder = data.get("formats")
        if not folder:
            continue
        base = kit / bridge.PACK_DIR / folder
        if not base.is_dir():
            rows.append({"brand": brand, "source": str(kit), "id": folder, "folder": str(base),
                         "broken": f"pack.json names formats folder '{folder}', which does not exist"})
            continue
        rows += [read_format(p, brand, str(kit)) for p in sorted(base.glob("*/format.json"))]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["list"])
    ap.add_argument("--project", help="where the video will be made (default: the current folder)")
    ap.add_argument("--all", action="store_true", help="include drafts, trials and retired formats")
    ap.add_argument("--brand", help="only this brand's formats, plus the neutral ones")
    ap.add_argument("--made-for", choices=MADE_FOR)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    project = Path(a.project).resolve() if a.project else Path.cwd().resolve()
    rows = []
    for r in collect(project):
        if a.brand and r["brand"] not in ("any", a.brand.lower()):
            continue
        if not r.get("broken") and not a.all and r.get("status") != "approved":
            continue
        if a.made_for and not r.get("broken") and r.get("made_for") != a.made_for:
            continue
        rows.append(r)
    if a.json:
        print(json.dumps(rows, indent=1))
        return
    if not rows:
        print("no formats found" + ("" if a.all else " (approved only; --all shows drafts)"), file=sys.stderr)
    for r in rows:
        if r.get("broken"):
            print(f"(broken)\t{r['brand']}\t{r['id']}\t{r['folder']}\t{r['broken']}")
        else:
            plats = ",".join(r.get("platforms") or []) or "-"
            print(f"{r['id']}\t{r['name']}\t{r['status']}\t{r['made_for']}\t{r['brand']}\t{plats}\t{r['journey']}")


if __name__ == "__main__":
    main()
