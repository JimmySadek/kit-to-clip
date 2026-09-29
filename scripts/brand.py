#!/usr/bin/env python3
"""Kit to Clip brand detection: find the brand of the repo (or studio folder) a video is being made in.

Checks in this order and reports the first state that applies:
  pack        a video pack in the repo (.agents/skills/*/kit-to-clip/ or .claude/skills/*/kit-to-clip/); two or more: ask which
  pointer     reels/brand.json names a brand kit installed elsewhere ({"kit": "<skill name or folder>"}) and its pack
  kit         a brand kit in the repo with no video pack yet: brand onboarding saves one into that kit
  unchosen    brand work in the repo but no chosen identity (docs/brand/, brand/, branding/): offer a quick brand
              from one of those directions, a quick brand from a reference, or a neutral look
  none        no brand in the repo: ask which installed brand it is for, or offer a quick brand or a neutral look
Brands installed outside the repo are listed, never used as the repo's brand on their own: "installed" packs, and
"installed kits" (a brand-named skill with logo files and no video pack yet, e.g. a company's brand skill). Once
the person picks one, `use` saves the choice as reels/brand.json, so the next detect says pointer (or kit, which
leads to brand onboarding).

  python3 brand.py detect [--repo <dir>] [--json]
  python3 brand.py use --kit <skill name or folder> [--repo <dir>]

The repo is --repo, else the git top level of the current folder, else the studio folder above it (.reel-kit/),
else the current folder. Exit 0 always; exit 2 when the brand bridge is missing.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                 # the kit-to-clip skill
SKILLS = ROOT.parent               # the skills folder it sits in (a studio's .claude/skills, or a global one)
BRAND_WORDS = re.compile(r"\b(brand|brand kit|identity|design system|style guide)\b", re.I)
PACK_DIR = "kit-to-clip"            # the video pack folder inside a brand kit (bridge.py)
BRAND_DIRS = ("docs/brand", "brand", "branding", "docs/branding", "design/brand")


def load_bridge():
    for p in [ROOT / "brand" / "scripts" / "bridge.py"]:
        if p.is_file():
            spec = importlib.util.spec_from_file_location("reel_bridge", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    print("brand: brand/scripts/bridge.py is missing from this Kit to Clip install", file=sys.stderr)
    sys.exit(2)


def repo_root(explicit):
    if explicit:
        return Path(explicit).expanduser().resolve()
    cwd = Path.cwd().resolve()
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=cwd)
    if r.returncode == 0 and r.stdout.strip():
        return Path(r.stdout.strip()).resolve()
    for d in [cwd, *cwd.parents]:
        if (d / ".reel-kit").is_dir():
            return d
    return cwd


def inside(path, root):
    for p in {path, path.resolve()}:
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def skill_dirs(root):
    for base in (root / ".agents" / "skills", root / ".claude" / "skills"):
        if base.is_dir():
            yield from sorted(d for d in base.iterdir() if (d / "SKILL.md").is_file())


def frontmatter(skill):
    text = (skill / "SKILL.md").read_text(errors="replace")
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


def is_brand_kit(skill):
    if re.search(r"(^|-)(brand|design|identity)($|-)", skill.name):
        return True
    return bool(BRAND_WORDS.search(frontmatter(skill)))


def has_logo(kit):
    return any(f.suffix.lower() in (".svg", ".png") for f in kit.rglob("*") if "logo" in str(f.relative_to(kit)).lower())


def installed_kits(root):
    """Brand kits in the global skill folders with logo files and no video pack yet (not inside the repo)."""
    seen, out = set(), []
    for base in (Path.home() / ".claude" / "skills", Path.home() / ".agents" / "skills", SKILLS):
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not (d / "SKILL.md").is_file() or inside(d, root) or d.resolve() in seen:
                continue
            if re.search(r"(^|-)(brand|design|identity)$", d.name) and not (d / PACK_DIR / "pack.json").exists() and has_logo(d):
                seen.add(d.resolve())
                out.append({"kit": d.name, "path": str(d)})
    return out


def pack_row(brand, kit, data):
    return {"brand": brand, "name": data.get("name", brand), "version": data.get("version"),
            "status": data.get("status", "approved"), "kit": str(kit), "formats": bool(data.get("formats"))}


def resolve_pointer(root, bridge):
    f = root / "reels" / "brand.json"
    if not f.is_file():
        return None
    try:
        ref = json.loads(f.read_text())
    except (OSError, ValueError) as e:
        return {"file": str(f), "problem": f"unreadable ({e})"}
    kit_ref = ref.get("kit")
    if not kit_ref:
        return {"file": str(f), "problem": 'needs "kit": the brand kit skill name or folder'}
    tries = [Path(kit_ref).expanduser()] if "/" in kit_ref else []
    tries += [Path.home() / ".claude/skills" / kit_ref, Path.home() / ".agents/skills" / kit_ref, SKILLS / kit_ref]
    kit = next((t for t in tries if (t / "SKILL.md").is_file()), None)
    if not kit:
        return {"file": str(f), "kit": kit_ref, "problem": "that brand kit is not installed"}
    data, err = bridge.read_pack(kit) if (kit / PACK_DIR / "pack.json").is_file() else (None, None)
    out = {"file": str(f), "kit": str(kit)}
    if err:
        out["problem"] = f"its pack is broken: {err}"
    elif data:
        out["pack"] = pack_row(data["brand"].lower(), kit, data)
    return out


def detect(root):
    bridge = load_bridge()
    packs, broken = bridge.find_packs(root)
    here = [pack_row(b, kit, d) for b, (kit, d) in packs.items() if inside(kit, root)]
    installed = [pack_row(b, kit, d) for b, (kit, d) in packs.items() if not inside(kit, root)]
    result = {"repo": str(root), "installed": installed, "installed_kits": installed_kits(root),
              "broken": [{"kit": str(k), "problem": e} for k, e in broken if inside(k, root)]}
    if here:
        return {**result, "state": "pack", "packs": here,
                "next": "ask which brand" if len(here) > 1 else f"use {here[0]['name']} ({here[0]['status']})"}
    pointer = resolve_pointer(root, bridge)
    if pointer and pointer.get("pack"):
        return {**result, "state": "pointer", "pointer": pointer, "packs": [pointer["pack"]],
                "next": f"use {pointer['pack']['name']} from {pointer['kit']}"}
    kits = [str(d) for d in skill_dirs(root) if is_brand_kit(d) and not (d / PACK_DIR / "pack.json").exists()]
    if pointer and pointer.get("kit") and not pointer.get("problem"):
        kits.append(pointer["kit"])
    if kits:
        return {**result, "state": "kit", "kits": kits, "pointer": pointer,
                "next": "brand onboarding (references/brand-onboarding.md): save a pack into the kit"}
    work = [str(root / d) for d in BRAND_DIRS if (root / d).is_dir()]
    if work:
        return {**result, "state": "unchosen", "brand_work": work, "pointer": pointer,
                "next": "flag 'identity not chosen'; offer a quick brand from one of these directions, from a reference, or a neutral look"}
    return {**result, "state": "none", "pointer": pointer,
            "next": "flag 'no brand here'; ask which installed brand this repo is for (then `brand.py use --kit <name>`), "
                    "or offer a quick brand or a neutral look"}


def use(root, kit_ref):
    """Save the brand choice for this repo as reels/brand.json (a pointer to an installed kit)."""
    tries = [Path(kit_ref).expanduser()] if "/" in kit_ref else []
    tries += [Path.home() / ".claude/skills" / kit_ref, Path.home() / ".agents/skills" / kit_ref, SKILLS / kit_ref]
    if not any((t / "SKILL.md").is_file() for t in tries):
        print(f"brand: no installed brand kit '{kit_ref}'", file=sys.stderr)
        sys.exit(2)
    f = root / "reels" / "brand.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"kit": kit_ref}, indent=1) + "\n")
    print(f"brand: {f} -> {kit_ref}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["detect", "use"])
    ap.add_argument("--repo")
    ap.add_argument("--kit", help="for use: the brand kit's skill name (e.g. acme-brand) or folder")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.command == "use":
        if not a.kit:
            ap.error("use needs --kit")
        use(repo_root(a.repo), a.kit)
        return
    r = detect(repo_root(a.repo))
    if a.json:
        print(json.dumps(r, indent=1))
        return
    print(f"brand: {r['state']} in {r['repo']}")
    for p in r.get("packs", []):
        print(f"  pack\t{p['brand']}\t{p['name']}\tv{p['version']}\t{p['status']}\t{p['kit']}")
    for k in r.get("kits", []):
        print(f"  kit without a video pack\t{k}")
    for w in r.get("brand_work", []):
        print(f"  brand work, no chosen identity\t{w}")
    if r.get("pointer") and r["pointer"].get("problem"):
        print(f"  pointer {r['pointer']['file']}: {r['pointer']['problem']}")
    for b in r["broken"]:
        print(f"  (broken pack)\t{b['kit']}\t{b['problem']}")
    for p in r["installed"]:
        print(f"  installed elsewhere\t{p['brand']}\t{p['name']}\t{p['status']}\t{p['kit']}")
    for k in r["installed_kits"]:
        print(f"  installed kit without a video pack\t{k['kit']}\t{k['path']}")
    print(f"  next: {r['next']}")


if __name__ == "__main__":
    main()
