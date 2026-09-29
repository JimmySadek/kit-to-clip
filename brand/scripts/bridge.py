#!/usr/bin/env python3
"""Kit to Clip brand bridge: copy a brand's video pack into a HyperFrames project as files HyperFrames already obeys.

This engine holds no brand. A brand is a video pack kept next to its brand kit, in the brand's own repository:
  <brand kit>/kit-to-clip/pack.json     brand id, status, kit files to copy (dst: src), templates to fill, builder, guide
  <brand kit>/kit-to-clip/templates/    e.g. frame.md, brand.css, brand-snippets.js with {{placeholders}}
  <brand kit>/kit-to-clip/pack.py       optional builder: build(ctx) returns template values for what data can't express
  <brand kit>/kit-to-clip/guide.md      how to build with this brand; read it after bridging
Packs are found in this order, and a brand's first hit wins:
  --brand-skill <kit dir>; walking up from the project (.agents/skills/*/kit-to-clip/, .claude/skills/*/kit-to-clip/), so a
  brand repo's own pack wins; the skills folder next to this one (a studio folder); ~/.claude/skills; ~/.agents/skills.

Writes into <project>: the pack's kit files (hash-checked against the kit's hash indexes), the filled templates,
anything the builder writes, and .reel-brand.json (provenance: kit, file hashes, builder notes, pack).

Usage:
  python3 bridge.py --brand <name> --project <dir> [--canvas 1080x1920] [--brand-skill <kit dir>] [--force]
  python3 bridge.py --list [--project <dir>]
Exit codes: 0 ok, 2 no pack for the brand or a broken pack, 3 kit integrity failure.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK_DIR = "kit-to-clip"          # the video pack folder inside a brand kit
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
# token contract v1 (references/brand-pack.md): the --reel-* names neutral formats use, so any pack re-skins them
CONTRACT_TOKENS = ("bg", "fg", "accent", "on-accent", "muted", "surface", "font-display", "weight-display", "font-body",
                   "weight-body", "font-label", "weight-label", "ease-enter", "ease-exit", "ease-move", "dur-enter",
                   "dur-exit", "dur-move", "energy", "radius", "line")


def die(code, msg):
    print(f"brand: {msg}", file=sys.stderr)
    sys.exit(code)


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def skill_roots(project):
    """Skills folders to search, nearest first."""
    roots = []
    for d in [project, *project.parents]:
        roots += [d / ".agents" / "skills", d / ".claude" / "skills"]
    roots += [HERE.parents[2], Path.home() / ".claude" / "skills", Path.home() / ".agents" / "skills"]
    seen, out = set(), []
    for r in roots:
        if r.is_dir() and r.resolve() not in seen:
            seen.add(r.resolve())
            out.append(r)
    return out


def read_pack(kit):
    """pack.json of a kit, or an error string."""
    try:
        data = json.loads((kit / PACK_DIR / "pack.json").read_text())
    except (OSError, ValueError) as e:
        return None, f"unreadable pack.json ({e})"
    if data.get("schema") != 1 or not data.get("brand"):
        return None, "pack.json needs \"schema\": 1 and a \"brand\""
    return data, None


def find_packs(project):
    """{brand: (kit dir, pack data)} nearest first, plus [(kit dir, problem)] for broken packs."""
    packs, broken = {}, []
    for root in skill_roots(project):
        for pj in sorted(root.glob(f"*/{PACK_DIR}/pack.json")):
            kit = pj.parent.parent
            data, err = read_pack(kit)
            if err:
                broken.append((kit, err))
            elif data["brand"].lower() not in packs:
                packs[data["brand"].lower()] = (kit, data)
    return packs, broken


class Ctx:
    """What a pack builder gets: the kit, pack and project folders, the canvas, and checked copy/write helpers."""

    def __init__(self, kit, data, project, W, H, args):
        self.kit, self.pack, self.project, self.W, self.H, self.args = kit, kit / PACK_DIR, project, W, H, args
        self.files = {}  # project path -> sha256 of every file copied from the kit
        self.indexes = []
        for rel in data.get("hash_indexes", []):
            try:
                self.indexes.append(((kit / rel).parent, json.loads((kit / rel).read_text())["files"]))
            except (OSError, ValueError, KeyError) as e:
                die(3, f"kit hash index {rel} is unreadable ({e})")

    die = staticmethod(die)
    sha256 = staticmethod(sha256)

    def expected(self, src):
        """The kit's recorded sha256 for a kit-relative file, if any index lists it."""
        p = self.kit / src
        for base, files in self.indexes:
            try:
                row = files.get(p.relative_to(base).as_posix())
            except ValueError:
                continue
            if row and row.get("sha256"):
                return row["sha256"]
        return None

    def copy(self, src, dst):
        s, d = self.kit / src, self.project / dst
        if not s.is_file():
            die(3, f"kit is missing {src}")
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        got, exp = sha256(d), self.expected(src)
        if exp and got != exp:
            die(3, f"hash mismatch for {s.name}: kit says {exp[:12]}, file is {got[:12]}")
        self.files[dst] = got
        return got

    def write(self, dst, text):
        d = self.project / dst
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(text)

    @staticmethod
    def font_metrics(font_path, chars="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ", wide="MWmw"):
        """Average advance of `chars` and widest of `wide` in em, measured from the real font (for text fit)."""
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            return None
        f = TTFont(str(font_path))
        cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
        adv = [hmtx[cmap[ord(c)]][0] / upm for c in chars if ord(c) in cmap]
        widest = max(hmtx[cmap[ord(c)]][0] / upm for c in wide if ord(c) in cmap)
        return {"avg_em": round(sum(adv) / len(adv), 4), "widest_em": round(widest, 4)}


def bridge(kit, data, project, W, H, args):
    brand, pack = data["brand"].lower(), kit / PACK_DIR
    project.mkdir(parents=True, exist_ok=True)
    ctx = Ctx(kit, data, project, W, H, args)
    for dst, src in data.get("copy", {}).items():
        ctx.copy(src, dst)
    result = {}
    if data.get("builder"):
        spec = importlib.util.spec_from_file_location(f"reel_pack_{brand}", pack / data["builder"])
        if not spec or not (pack / data["builder"]).is_file():
            die(2, f"pack builder {pack / data['builder']} not found")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.build(ctx) or {}
    values = {**data.get("values", {}), **result.get("values", {})}
    for out, tpl in data.get("templates", {}).items():
        text = (pack / tpl).read_text()
        missing = sorted(set(PLACEHOLDER.findall(text)) - set(values))
        if missing:
            die(2, f"template {tpl} needs values the pack does not give: {', '.join(missing)}")
        ctx.write(out, PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), text))
    contract = data.get("contract")
    if contract:
        if contract != 1:
            die(2, f"the pack uses token contract {contract}; this engine knows contract 1")
        css, js = project / data.get("contract_css", "brand.css"), project / data.get("contract_js", "brand-snippets.js")
        text = css.read_text() if css.is_file() else ""
        missing = [f"--reel-{t}" for t in CONTRACT_TOKENS if not re.search(rf"--reel-{t}\s*:", text)]
        if missing:
            die(2, f"the pack declares token contract 1 but {css.name} does not define: {', '.join(missing)}")
        if not (js.is_file() and re.search(r"window\.REEL_BRAND\s*=", js.read_text())):
            die(2, f"the pack declares token contract 1 but {js.name} does not set window.REEL_BRAND")
        shutil.copy2(HERE.parent / "runtime" / "reel-tokens.js", project / "reel-tokens.js")
    status = data.get("status", "approved")
    manifest = {"brand": brand, "source_skill": str(kit), **result.get("provenance", {}), "files": ctx.files,
                "pack": {"path": str(pack), "version": data.get("version"), "status": status, "contract": contract}}
    ctx.write(".reel-brand.json", json.dumps(manifest, indent=1))

    print(f"brand: {brand} -> {project}")
    print(f"  pack: {pack} (v{data.get('version', '?')}, {status})")
    for line in result.get("summary", []):
        print("  " + line)
    print("  wrote " + ", ".join([*data.get("templates", {}), *(["reel-tokens.js"] if contract else []), ".reel-brand.json"]))
    print(f"  token contract: v{contract}, neutral formats can use this brand" if contract
          else "  token contract: none, so neutral formats cannot use this brand yet (references/brand-pack.md)")
    if data.get("guide") and (pack / data["guide"]).is_file():
        print(f"  read next: {pack / data['guide']}")
    if status != "approved":
        print(f"  ⚠ {status} brand: say so in the handoff for every video made with it")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand")
    ap.add_argument("--project")
    ap.add_argument("--canvas", default="1080x1920", help="WxH of the main cut, used for text-fit numbers")
    ap.add_argument("--brand-skill", help="brand kit folder holding kit-to-clip/pack.json (skips the search)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing frame.md")
    ap.add_argument("--list", action="store_true", help="list the video packs this project can use")
    a = ap.parse_args()
    project = Path(a.project).resolve() if a.project else Path.cwd().resolve()

    if a.list:
        packs, broken = find_packs(project)
        for b, (kit, data) in packs.items():
            print(f"{b}\t{data.get('name', b)}\tv{data.get('version', '?')}\t{data.get('status', 'approved')}\t{kit}")
        for kit, err in broken:
            print(f"(broken)\t{kit}\t{err}")
        if not packs:
            print("no video packs found", file=sys.stderr)
        return
    if not a.brand or not a.project:
        ap.error("--brand and --project are required (or use --list)")

    brand = a.brand.lower().strip()
    if a.brand_skill:
        kit = Path(a.brand_skill).expanduser()
        data, err = read_pack(kit)
        if err:
            die(2, f"{kit / PACK_DIR / 'pack.json'}: {err}")
        if data["brand"].lower() != brand:
            die(2, f"the pack in {kit} is for '{data['brand']}', not '{a.brand}'")
    else:
        packs, broken = find_packs(project)
        if brand not in packs:
            note = "".join(f"\n  broken pack in {k}: {e}" for k, e in broken)
            die(2, f"no video pack for brand '{a.brand}'. Found: {', '.join(sorted(packs)) or 'none'}. "
                   "Do not invent tokens: set the brand up first (brand onboarding) or ask for the brand source." + note)
        kit, data = packs[brand]
    if (project / "frame.md").exists() and not a.force:
        die(2, f"{project / 'frame.md'} exists; rerun with --force to replace it")
    W, H = (int(v) for v in a.canvas.lower().split("x"))
    bridge(kit, data, project, W, H, a)


if __name__ == "__main__":
    main()
