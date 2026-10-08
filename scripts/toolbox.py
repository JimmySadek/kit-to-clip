#!/usr/bin/env python3
"""Kit to Clip's toolbox: the powers it can use, whether they are ready, and how to get them.

  toolbox.py list [--json]                    every power: what it does and its state
  toolbox.py doctor [--json]                  the state of every power on this computer
  toolbox.py which <capability> [--json]      who provides a capability (exit 0 ready, 3 not ready)
  toolbox.py check <id>                       exit 0 ready, 3 not installed or outdated, 4 blocked or awaiting review
  toolbox.py install <id> [--dry-run]         install the pinned version into the engine (ask the person first)
  toolbox.py smoke <id>                       prove it works on this computer
  toolbox.py path <id> [<entry>]              the command or file to run it with
  toolbox.py vendor <id> <project>            copy its browser files into a video project's vendor/ and credit them
  toolbox.py licence [<id>] [--online] [--deps] [--json]   licence watch (exit 4 when anything is blocked)
  toolbox.py updates [--if-due] [--try <id>] [--json]      update watch: versions, new docs, skills, MCP, licence
  toolbox.py pin <id> <version>               use another version on this computer (after the person's yes)
  toolbox.py lint                             check every card (tests run this)

A power is described by a card, toolbox/cards/<id>.json; capabilities are listed in toolbox/capabilities.json and the
licence rules in toolbox/policy.json. Installed powers live in <engine>/tools/<id>/, never in a repo. Source
scripts/env.sh first so the engine's Python, Node and ffmpeg are on the PATH. Nothing here posts or uploads anything;
it only downloads the pinned files a card names, checks their checksums and puts them in the engine folder.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
TOOLBOX = SKILL_DIR / "toolbox"
CARDS = Path(os.environ.get("KIT_TO_CLIP_CARDS") or TOOLBOX / "cards")
POLICY = TOOLBOX / "policy.json"
CAPABILITIES = TOOLBOX / "capabilities.json"
FIXTURES = TOOLBOX / "fixtures"
KINDS = ("builtin", "skill", "release", "app", "pip", "npm")
RANK = {"allow": 0, "review": 1, "block": 2}
UPDATE_EVERY_DAYS = 7
WATCH_DEFAULT = ["AGENTS.md", "CLAUDE.md", "llms.txt", ".mcp.json", "skills", "docs/agents.md", "docs/mcp.md"]


# ── places ────────────────────────────────────────────────────────────────
def engine_dir() -> Path:
    for key in ("REEL_STUDIO", "REEL_STUDIO_HOME"):
        if os.environ.get(key):
            return Path(os.environ[key]).expanduser()
    return Path.home() / ".kit-to-clip"


def tools_root() -> Path:
    return Path(os.environ.get("KIT_TO_CLIP_TOOLS") or engine_dir() / "tools").expanduser()


def state_root() -> Path:
    return Path(os.environ.get("KIT_TO_CLIP_STATE") or engine_dir() / "state").expanduser()


def engine_python() -> str:
    python = engine_dir() / ".reel-kit" / "env" / "bin" / "python"
    return str(python) if python.is_file() else sys.executable


def plat_key() -> str:
    return f"{sys.platform}-{platform.machine()}"


# ── data ──────────────────────────────────────────────────────────────────
def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_cards() -> dict[str, dict]:
    cards = {}
    for path in sorted(CARDS.glob("*.json")):
        card = read_json(path)
        if isinstance(card, dict):
            card["_path"] = str(path)
            cards[card.get("id") or path.stem] = card
    return cards


def capabilities() -> dict:
    return (read_json(CAPABILITIES, {}) or {}).get("capabilities", {})


def pinned(card: dict) -> str:
    pins = read_json(state_root() / "pins.json", {}) or {}
    return str(pins.get(card["id"]) or card.get("pinned") or "")


def fill(template, card: dict, version: str):
    """Put the version (and a few names) into a string or list from a card."""
    if isinstance(template, list):
        return [fill(t, card, version) for t in template]
    if isinstance(template, dict):
        return {k: fill(v, card, version) for k, v in template.items()}
    if isinstance(template, str):
        return template.replace("{version}", version).replace("{id}", card["id"])
    return template


# ── licences ──────────────────────────────────────────────────────────────
def policy() -> dict:
    return read_json(POLICY, {}) or {}


def classify(expression: str | None, usage: str = "library", rules: dict | None = None) -> dict:
    """allow / review / block for an SPDX-like licence expression used in a given way. Block always wins."""
    rules = rules or policy()
    text = (expression or "").strip()
    if not text:
        return {"verdict": "review", "why": "no licence found", "licence": ""}

    def blocked(words: str) -> dict | None:
        for rule in rules.get("block", []):
            if re.search(rule["match"], words.lower()):
                return {"verdict": "block", "why": rule["why"], "licence": words}
        return None

    # A real SPDX expression ("MIT OR AGPL-3.0") is judged part by part, so a friendly choice can win. Free text
    # ("free for non-commercial or academic use") is judged as a whole, so a restriction anywhere blocks it.
    bare = re.sub(r"[()]", " ", text)
    pieces = [p for p in re.split(r"\s+(?:OR|AND)\s+", bare, flags=re.I) if p.strip()]
    spdx_like = all(re.fullmatch(r"[A-Za-z0-9.+-]+(\s+WITH\s+[A-Za-z0-9.+-]+)?", p.strip()) for p in pieces)
    if not spdx_like:
        hit = blocked(text)
        if hit:
            return hit
    aliases = {k.lower(): v for k, v in rules.get("aliases", {}).items()}
    allow = {a.lower(): a for a in rules.get("allow", [])}
    allow_as = {k.lower(): v for k, v in rules.get("allow_as", {}).items()}

    def atom(token: str) -> dict:
        token = re.sub(r"\s+WITH\s+.*$", "", token.strip().strip("()").strip(), flags=re.I)
        hit = blocked(token)
        if hit:
            return hit
        name = aliases.get(token.lower(), token)
        key = name.lower()
        if key in allow:
            return {"verdict": "allow", "why": f"{allow[key]} is on the allow list", "licence": name}
        if key in allow_as:
            if usage in allow_as[key]:
                return {"verdict": "allow", "why": f"{name} is fine as a {usage}", "licence": name}
            return {"verdict": "review", "why": f"{name} is only fine as: {', '.join(allow_as[key])}", "licence": name}
        for rule in rules.get("patterns", []):           # free-text spellings: "MIT licensed, as found in …", "ISC License (ISCL)"
            if re.search(rule["match"], key):
                known = rule["spdx"]
                if known.lower() in allow:
                    return {"verdict": "allow", "why": f"{known} (read from {name!r}) is on the allow list", "licence": known}
                if known.lower() in allow_as:
                    ok = usage in allow_as[known.lower()]
                    return {"verdict": "allow" if ok else "review", "licence": known,
                            "why": f"{known} (read from {name!r}) is " + (f"fine as a {usage}" if ok else f"only fine as: {', '.join(allow_as[known.lower()])}")}
        for rule in rules.get("review", []):
            if re.search(rule["match"], key):
                return {"verdict": "review", "why": rule["why"], "licence": name}
        return {"verdict": "review", "why": f"{name} is not on the allow list", "licence": name}

    def any_of(part: str) -> dict:  # A OR B: we may pick the friendliest
        splitter = r"\s+OR\s+|\s*/\s*" if spdx_like else r"\s+OR\s+"
        options = [all_of(p) for p in re.split(splitter, part, flags=re.I) if p.strip()]
        return min(options, key=lambda r: RANK[r["verdict"]])

    def all_of(part: str) -> dict:  # A AND B: every one must be fine
        options = [atom(p) for p in re.split(r"\s+AND\s+", part, flags=re.I) if p.strip()]
        return max(options, key=lambda r: RANK[r["verdict"]])

    result = any_of(text.replace("(", " ").replace(")", " "))
    return {**result, "licence": text}


def card_licence(card: dict) -> dict:
    """The card's verdict: its code licence and (when it downloads one) its model licence; a recorded decision may turn
    a review into an allow, never a block."""
    lic = card.get("licence") or {}
    parts = [classify(lic.get("spdx"), lic.get("usage", "library"))]
    if lic.get("model_spdx") is not None or lic.get("model"):
        parts.append(classify(lic.get("model_spdx"), "model-weights"))
    worst = max(parts, key=lambda r: RANK[r["verdict"]])
    decision = lic.get("decision") or {}
    if worst["verdict"] == "review" and decision.get("verdict") == "allow":
        return {**worst, "verdict": "allow", "why": f"reviewed: {decision.get('note', '')} ({decision.get('by', '?')}, {decision.get('date', '?')})"}
    return worst


# ── state of a power ──────────────────────────────────────────────────────
def skill_places(name: str) -> list[Path]:
    places = [SKILL_DIR.parent / name, engine_dir() / ".claude" / "skills" / name]
    cwd = Path.cwd()
    for folder in [cwd, *cwd.parents]:
        places += [folder / ".claude" / "skills" / name, folder / ".agents" / "skills" / name]
    home = Path.home()
    places += [home / ".claude" / "skills" / name, home / ".agents" / "skills" / name, home / ".codex" / "skills" / name]
    return places


def placeholders(card: dict) -> dict:
    return {"engine": str(engine_dir()), "skill": str(SKILL_DIR), "tools": str(tools_root() / card["id"])}


def expand(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def installed(card: dict) -> dict | None:
    """What is on this computer for a card, or None."""
    kind = card.get("kind")
    detect = card.get("detect") or {}
    if kind == "builtin":
        files = [Path(expand(f, placeholders(card))).expanduser() for f in detect.get("files", [])]
        if not all(f.exists() for f in files):
            return None
        found = []
        for command in detect.get("commands", []):  # "a|b": either one will do
            hit = next((shutil.which(c) for c in command.split("|") if shutil.which(c)), None)
            if not hit:
                return None
            found.append(hit)
        paths = [str(f) for f in files] + found
        return {"version": "built in", "paths": paths} if paths else None
    if kind == "skill":
        for place in skill_places(detect.get("skill") or card["id"]):
            if (place / "SKILL.md").is_file() and all((place / r).exists() for r in detect.get("requires", [])):
                return {"version": "installed", "path": str(place.resolve())}
        return None
    record = read_json(tools_root() / card["id"] / "installed.json")
    if not record:
        return None
    entries = record.get("entries", {})
    if entries and not all(Path(p).exists() for p in entries.values()):
        return None
    return record


def state_of(card: dict) -> dict:
    lic = card_licence(card)
    have = installed(card)
    want = pinned(card)
    if lic["verdict"] == "block":
        state = "blocked"
    elif lic["verdict"] == "review":
        state = "review"
    elif not have:
        state = "missing"
    elif card.get("kind") in ("builtin", "skill") or not want or str(have.get("version")) == want:
        state = "ready"
    else:
        state = "update"
    return {"id": card["id"], "name": card.get("name", card["id"]), "state": state, "pinned": want,
            "installed": (have or {}).get("version"), "licence": lic, "maturity": card.get("maturity", "stable"),
            "capabilities": card.get("capabilities", []), "size_mb": card.get("size_mb"), "about": card.get("about", ""),
            "fallback": card.get("fallback", "")}


STATE_WORDS = {
    "ready": "✅ ready",
    "update": "🔄 installed, another version is pinned",
    "missing": "⬜ not installed",
    "review": "⚠️ licence needs a person to read it",
    "blocked": "❌ blocked by the licence policy",
}


# ── commands: overview ────────────────────────────────────────────────────
def cmd_list(args) -> int:
    rows = [state_of(c) for c in load_cards().values()]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for r in rows:
        early = " (early)" if r["maturity"] == "early" else ""
        print(f"{r['id']:<20} {STATE_WORDS[r['state']]:<42} {r['about']}{early}")
    return 0


def cmd_doctor(args) -> int:
    rows = [state_of(c) for c in load_cards().values()]
    engine_ready = (engine_dir() / ".reel-kit" / "ready").is_file()
    if args.json:
        print(json.dumps({"engine": str(engine_dir()), "engine_ready": engine_ready, "tools": str(tools_root()), "powers": rows}, indent=2))
        return 0
    print(f"engine: {engine_dir()} ({'ready' if engine_ready else 'setup not finished'})")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
        extra = f"  pinned {r['pinned']}" if r["pinned"] else ""
        if r["state"] in ("review", "blocked"):
            extra += f"  ({r['licence']['why']})"
        print(f"  {STATE_WORDS[r['state']]:<42} {r['id']}{extra}")
    print("summary: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    return 0


def providers(capability: str) -> list[dict]:
    rows = [state_of(c) for c in load_cards().values() if capability in c.get("capabilities", [])]
    order = {"ready": 0, "update": 1, "missing": 2, "review": 3, "blocked": 4}
    cards = load_cards()
    return sorted(rows, key=lambda r: (order[r["state"]], r["maturity"] != "stable", cards[r["id"]].get("rank", 50)))


def cmd_which(args) -> int:
    caps = capabilities()
    if args.capability not in caps:
        close = [c for c in caps if args.capability.lower() in c or c in args.capability.lower()]
        print(f"❌ unknown capability: {args.capability}" + (f" (did you mean {', '.join(close)}?)" if close else ""), file=sys.stderr)
        print("   capabilities: " + ", ".join(sorted(caps)), file=sys.stderr)
        return 2
    info = caps[args.capability]
    rows = providers(args.capability)
    ready = [r for r in rows if r["state"] == "ready"]
    if args.json:
        print(json.dumps({"capability": args.capability, **info, "providers": rows, "ready": bool(ready)}, indent=2))
        return 0 if ready else 3
    print(f"{args.capability}: {info['about']}")
    for r in rows:
        card = load_cards()[r["id"]]
        if r["state"] == "ready":
            recipe = f"  recipe: toolbox/{card['recipe']}" if card.get("recipe") else (f"  guide: {card['guide']}" if card.get("guide") else "")
            print(f"  ✅ {r['name']} ready{recipe}")
        elif r["state"] in ("missing", "update"):
            size = f"about {r['size_mb']} MB, " if r["size_mb"] else ""
            early = "young tool, checked frame by frame; " if r["maturity"] == "early" else ""
            print(f"  ⬜ {r['name']}: {size}free, runs on this computer; {early}{card.get('about', '')}")
            print(f"     with a ✋ yes: python3 {SKILL_DIR}/scripts/toolbox.py install {r['id']}")
        else:
            print(f"  {STATE_WORDS[r['state']]}: {r['name']} ({r['licence']['why']})")
    print(f"  fallback: {info['fallback']}")
    return 0 if ready else 3


def cmd_check(args) -> int:
    cards = load_cards()
    if args.id not in cards:
        print(f"❌ no card named {args.id}", file=sys.stderr)
        return 2
    r = state_of(cards[args.id])
    print(f"{r['id']}: {STATE_WORDS[r['state']]}" + (f" ({r['licence']['why']})" if r["state"] in ("review", "blocked") else ""))
    return {"ready": 0, "missing": 3, "update": 3, "review": 4, "blocked": 4}[r["state"]]


# ── downloads and install ─────────────────────────────────────────────────
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    run = subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(dest), url], capture_output=True, text=True)
    if run.returncode != 0:
        raise RuntimeError(f"download failed: {url} ({run.stderr.strip()[-200:]})")


def run_quiet(command: list[str], log: Path, cwd: Path | None = None, env: dict | None = None) -> None:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(shlex.quote(c) for c in command) + "\n")
        handle.flush()
        result = subprocess.run(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"step failed ({' '.join(command[:3])} …); details in {log}")


def install_release(card: dict, version: str, dest: Path, log: Path, allow_unchecked: bool) -> dict:
    spec = fill(card["install"], card, version)
    spec = {**spec, **(spec.get("platforms") or {}).get(plat_key(), {})}
    asset = spec["asset"]
    url = spec.get("url") or f"https://github.com/{spec['repo']}/releases/download/{spec['tag']}/{asset}"
    work = dest.parent / ".download"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    file = work / asset
    print(f"  downloading {asset}…", file=sys.stderr)
    download(url, file)
    got = sha256(file)
    expected = (card["install"].get("sha256") or {}).get(f"{version}/{plat_key()}") or (card["install"].get("sha256") or {}).get(version)
    if not expected and spec.get("sums"):
        sums_url = spec.get("sums_url") or f"https://github.com/{spec['repo']}/releases/download/{spec['tag']}/{spec['sums']}"
        download(sums_url, work / "sums.txt")
        for line in (work / "sums.txt").read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.replace("*", " ").split()
            if len(parts) >= 2 and parts[-1].endswith(asset):
                expected = parts[0].lower()
    if expected and got != expected.lower():
        raise RuntimeError(f"checksum mismatch for {asset}: expected {expected}, got {got}. Nothing was installed.")
    if not expected and not allow_unchecked:
        raise RuntimeError(f"{asset} has no published checksum; not installed (sha256 {got}). Pin its hash in the card first.")
    target = dest / version
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    kind = spec.get("extract", "zip")
    if kind == "zip":
        run_quiet(["ditto", "-x", "-k", str(file), str(target)] if sys.platform == "darwin" else ["unzip", "-q", str(file), "-d", str(target)], log)
    elif kind in ("tar.gz", "tgz", "tar.xz", "tar"):
        run_quiet(["tar", "-xf", str(file), "-C", str(target)], log)
    elif kind == "dmg":
        mount = work / "mount"
        mount.mkdir()
        run_quiet(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(file)], log)
        try:
            apps = list(mount.glob("*.app"))
            if not apps:
                raise RuntimeError("the disk image holds no app")
            run_quiet(["ditto", str(apps[0]), str(target / apps[0].name)], log)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True)
    elif kind == "none":
        shutil.copy2(file, target / asset)
    else:
        raise RuntimeError(f"unknown extract kind {kind}")
    if sys.platform == "darwin":
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(target)], capture_output=True)
    entries = {name: str(target / rel) for name, rel in (spec.get("entries") or {}).items()}
    for path in entries.values():
        if Path(path).is_file():
            os.chmod(path, os.stat(path).st_mode | 0o111)
    shutil.rmtree(work, ignore_errors=True)
    return {"entries": entries, "sha256": got, "source": url}


def install_pip(card: dict, version: str, dest: Path, log: Path) -> dict:
    spec = fill(card["install"], card, version)
    venv = dest / "venv"
    if not (venv / "bin" / "python").is_file():
        run_quiet([engine_python(), "-m", "venv", str(venv)], log)
    python = str(venv / "bin" / "python")
    run_quiet([python, "-m", "pip", "install", "--quiet", "--upgrade", "pip"], log)
    extra = []
    if spec.get("index_url"):
        extra += ["--extra-index-url", spec["index_url"]]
    env = {**os.environ, **{k: str(v) for k, v in (spec.get("env") or {}).items()}}
    run_quiet([python, "-m", "pip", "install", "--quiet", *extra, *spec["packages"]], log, env=env)
    values = {"python": python, "venv": str(venv), "tools": str(dest), "scratch": str(dest)}
    for step in spec.get("post", []):
        if isinstance(step, dict) and "sh" in step:
            run_quiet(["bash", "-c", expand(step["sh"], {k: shlex.quote(v) for k, v in values.items()})], log, cwd=dest, env=env)
        else:
            run_quiet([expand(s, values) for s in step], log, cwd=dest, env=env)
    entries = {"python": python}
    for name, rel in (spec.get("entries") or {}).items():
        entries[name] = str(dest / rel)
    return {"entries": entries, "source": "pypi: " + " ".join(spec["packages"])}


def install_npm(card: dict, version: str, dest: Path, log: Path) -> dict:
    spec = fill(card["install"], card, version)
    target = dest / version
    target.mkdir(parents=True, exist_ok=True)
    if not (target / "package.json").is_file():
        write_json(target / "package.json", {"name": f"kit-to-clip-tool-{card['id']}", "private": True})
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm was not found: source scripts/env.sh first")
    run_quiet([npm, "install", "--no-audit", "--no-fund", "--ignore-scripts", "--save-exact", *spec["packages"]], log, cwd=target)
    entries = {name: str(target / rel) for name, rel in (spec.get("entries") or {}).items()}
    for src in (card.get("vendor") or {}).get("files", {}):
        entries.setdefault(Path(src).name, str(target / src))
    return {"entries": entries, "source": "npm: " + " ".join(spec["packages"])}


def do_install(card: dict, version: str, root: Path, allow_unchecked: bool = False) -> dict:
    dest = root / card["id"]
    dest.mkdir(parents=True, exist_ok=True)
    log = dest / "install.log"
    log.write_text(f"install {card['id']} {version} on {dt.datetime.now().isoformat(timespec='seconds')}\n", encoding="utf-8")
    kind = card["kind"]
    if kind in ("release", "app"):
        record = install_release(card, version, dest, log, allow_unchecked)
    elif kind == "pip":
        record = install_pip(card, version, dest, log)
    elif kind == "npm":
        record = install_npm(card, version, dest, log)
    else:
        raise RuntimeError(f"{kind} powers are not installed by the toolbox")
    size = subprocess.run(["du", "-sm", str(dest)], capture_output=True, text=True).stdout.split()
    record.update({"id": card["id"], "version": version, "kind": kind, "date": dt.date.today().isoformat(),
                   "size_mb": int(size[0]) if size else None})
    write_json(dest / "installed.json", record)
    return record


def cmd_install(args) -> int:
    cards = load_cards()
    if args.id not in cards:
        print(f"❌ no card named {args.id}", file=sys.stderr)
        return 2
    card = cards[args.id]
    lic = card_licence(card)
    if lic["verdict"] != "allow":
        print(f"❌ {card['name']} is not installed: licence {lic['verdict']} ({lic['why']}).", file=sys.stderr)
        return 4
    kind = card["kind"]
    brew = (card.get("install") or {}).get("brew")
    if brew and shutil.which("brew"):
        # Homebrew is free; when it is already on this computer it is often the cleanest route. Never install Homebrew
        # itself (that needs an admin password); without it, the card's own route below is used.
        if args.dry_run:
            print(f"brew install {brew}")
            return 0
        print(f"Installing {card['name']} with Homebrew (brew install {brew})…", file=sys.stderr)
        result = subprocess.run(["brew", "install", *brew.split()])
        if result.returncode != 0:
            print("❌ brew install failed; the lines above say why", file=sys.stderr)
            return 1
        print(f"✅ {card['name']} installed with Homebrew. Next: toolbox.py check {card['id']}")
        return 0
    if kind == "builtin" and not (card.get("install") or {}).get("command"):
        print(f"{card['name']} is part of the video engine: run setup (bash {SKILL_DIR}/setup/install.sh).")
        return 0 if installed(card) else 3
    if kind in ("skill", "builtin"):
        command = expand((card.get("install") or {}).get("command", ""), {"skill": shlex.quote(str(SKILL_DIR))})
        if args.dry_run:
            print(command)
            return 0
        result = subprocess.run(command, shell=True)
        if result.returncode != 0:
            print("❌ the skill install failed; the lines above say why", file=sys.stderr)
            return 1
        print(f"✅ {card['name']} installed. A new session is needed before it loads as a skill.")
        return 0
    version = pinned(card)
    if args.dry_run:
        print(json.dumps({"id": card["id"], "version": version, "kind": kind, "into": str(tools_root() / card["id"]),
                          "install": fill(card.get("install"), card, version)}, indent=2))
        return 0
    size = f" (about {card['size_mb']} MB)" if card.get("size_mb") else ""
    print(f"Installing {card['name']} {version}{size} into {tools_root() / card['id']}…", file=sys.stderr)
    try:
        record = do_install(card, version, tools_root(), args.allow_unchecked)
    except (RuntimeError, OSError, KeyError) as error:
        print(f"❌ {error}", file=sys.stderr)
        return 1
    print(f"✅ {card['name']} {version} installed ({record.get('size_mb')} MB). Next: toolbox.py smoke {card['id']}")
    return 0


# ── use: path, vendor, smoke ──────────────────────────────────────────────
def entry_path(card: dict, name: str | None = None) -> str | None:
    have = installed(card)
    if not have:
        return None
    if card["kind"] == "skill":
        return have.get("path")
    if card["kind"] == "builtin":
        paths = have.get("paths") or []
        return paths[0] if paths else None
    entries = have.get("entries") or {}
    if name:
        return entries.get(name)
    preferred = (card.get("install") or {}).get("main")
    return entries.get(preferred) if preferred else next(iter(entries.values()), None)


def cmd_path(args) -> int:
    cards = load_cards()
    card = cards.get(args.id)
    if not card:
        print(f"❌ no card named {args.id}", file=sys.stderr)
        return 2
    path = entry_path(card, args.entry)
    if not path:
        print(f"{args.id} is not installed (toolbox.py install {args.id}, after a ✋ yes)", file=sys.stderr)
        return 3
    print(path)
    return 0


def cmd_vendor(args) -> int:
    cards = load_cards()
    card = cards.get(args.id)
    if not card or not card.get("vendor"):
        print(f"❌ {args.id} has no browser files to copy", file=sys.stderr)
        return 2
    have = installed(card)
    if not have:
        print(f"{args.id} is not installed (toolbox.py install {args.id}, after a ✋ yes)", file=sys.stderr)
        return 3
    project = Path(args.project).expanduser()
    if not project.is_dir():
        print(f"❌ not a folder: {project}", file=sys.stderr)
        return 2
    base = tools_root() / card["id"] / str(have["version"])
    copied = []
    for src, dst in card["vendor"]["files"].items():
        source = base / src
        target = project / "vendor" / dst
        if not source.is_file():
            print(f"❌ missing in the installed tool: {source}", file=sys.stderr)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(f"vendor/{dst}")
    credits = project / "CREDITS.md"
    line = f"- {card['name']} {have['version']} ({card['licence'].get('spdx')}), {card.get('homepage', '')}: {', '.join(copied)}"
    lines = credits.read_text(encoding="utf-8").splitlines() if credits.is_file() else ["# Credits", ""]
    lines = [l for l in lines if not l.startswith(f"- {card['name']} ")]       # one line per library: replace, never add twice
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) == 1:
        lines.append("")
    credits.write_text("\n".join(lines + [line]) + "\n", encoding="utf-8")
    print("\n".join(f"✅ {c}" for c in copied))
    return 0


def smoke_values(card: dict, scratch: Path) -> dict:
    have = installed(card) or {}
    values = {"scratch": str(scratch), "fixtures": str(FIXTURES), "skill": str(SKILL_DIR), "engine": str(engine_dir()),
              "tools": str(tools_root() / card["id"]), "python3": engine_python()}
    for name, path in (have.get("entries") or {}).items():
        values[name] = path
    if have.get("path"):
        values["path"] = have["path"]
    return values


def run_smoke(card: dict) -> tuple[bool, str]:
    smoke = card.get("smoke")
    if not smoke:
        return True, "no smoke test for this card"
    if not installed(card):
        return False, "not installed"
    scratch = Path(tempfile.mkdtemp(prefix=f"smoke-{card['id']}-"))
    values = smoke_values(card, scratch)
    log = scratch / "smoke.log"
    try:
        for step in smoke.get("steps", []):
            if isinstance(step, dict) and "sh" in step:
                command = ["bash", "-c", expand(step["sh"], {k: shlex.quote(v) for k, v in values.items()})]
            else:
                command = [expand(s, values) for s in step]
            with open(log, "a", encoding="utf-8") as handle:
                handle.write("$ " + " ".join(command) + "\n")
                handle.flush()
                result = subprocess.run(command, cwd=scratch, stdout=handle, stderr=subprocess.STDOUT,
                                        timeout=smoke.get("timeout", 900))
            if result.returncode != 0:
                tail = log.read_text(encoding="utf-8", errors="replace")[-600:]
                return False, f"step failed: {' '.join(command)[:160]}\n{tail}"
        for expect in smoke.get("expect", []):
            path = Path(expand(expect["file"], values))
            if not path.is_file():
                return False, f"expected file missing: {path}"
            if path.stat().st_size < expect.get("min_bytes", 1):
                return False, f"{path.name} is only {path.stat().st_size} bytes"
            if expect.get("contains") and expect["contains"] not in path.read_text(encoding="utf-8", errors="replace"):
                return False, f"{path.name} does not contain {expect['contains']!r}"
            if expect.get("absent") and expect["absent"] in path.read_text(encoding="utf-8", errors="replace"):
                return False, f"{path.name} contains {expect['absent']!r}, which it must not"
        return True, f"passed (scratch: {scratch})"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    finally:
        if smoke.get("keep") is not True and os.environ.get("KIT_TO_CLIP_KEEP_SMOKE") != "1":
            shutil.rmtree(scratch, ignore_errors=True)


def cmd_smoke(args) -> int:
    cards = load_cards()
    ids = list(cards) if args.id == "all" else [args.id]
    worst = 0
    for cid in ids:
        card = cards.get(cid)
        if not card:
            print(f"❌ no card named {cid}", file=sys.stderr)
            return 2
        if args.id == "all" and not installed(card):
            continue
        ok, message = run_smoke(card)
        print(f"{'✅' if ok else '❌'} {cid}: {message}")
        worst = worst if ok else 1
    return worst


# ── licence watch ─────────────────────────────────────────────────────────
def http_json(url: str, timeout: int = 20):
    request = urllib.request.Request(url, headers={"User-Agent": "kit-to-clip-toolbox", "Accept": "application/json"})
    token = os.environ.get("GITHUB_TOKEN") if "api.github.com" in url else None
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def github(path: str):
    """GitHub API through the gh tool when it is signed in (higher limits), else plain HTTPS."""
    if shutil.which("gh"):
        result = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout or "null")
        if "Not Found" in result.stderr or "HTTP 404" in result.stderr:
            return None
    try:
        return http_json("https://api.github.com/" + path.lstrip("/"))
    except Exception:  # noqa: BLE001 - network or 404: treated as "not found"
        return None


def online_licence(card: dict, version: str | None = None) -> dict:
    """The licence the upstream states today, from GitHub, npm, PyPI or Hugging Face."""
    up = card.get("upstream") or {}
    found = {}
    try:
        if up.get("npm"):
            data = http_json(f"https://registry.npmjs.org/{up['npm']}/{version or 'latest'}")
            value = data.get("license")
            found["npm"] = value.get("type") if isinstance(value, dict) else value
        if up.get("pypi"):
            data = http_json(f"https://pypi.org/pypi/{up['pypi']}/{version + '/' if version else ''}json")
            info = data.get("info", {})
            value = info.get("license_expression") or info.get("license") or ""
            if not value or len(value) > 80:
                classifiers = [c.split("::")[-1].strip() for c in info.get("classifiers", []) if c.startswith("License ::")]
                value = " OR ".join(classifiers) or value[:80]
            found["pypi"] = value
        if up.get("github"):
            data = github(f"repos/{up['github']}/license")
            if data:
                found["github"] = (data.get("license") or {}).get("spdx_id")
        if up.get("hf"):
            data = http_json(f"https://huggingface.co/api/models/{up['hf']}")
            found["hf"] = (data.get("cardData") or {}).get("license") or next(
                (t.split(":", 1)[1] for t in data.get("tags", []) if t.startswith("license:")), None)
    except Exception as error:  # noqa: BLE001
        found["error"] = str(error)[:160]
    return found


def scan_node_modules(folder: Path) -> list[dict]:
    """Every package under a node_modules folder, nested ones included (npm does not hoist everything), once each."""
    rows, seen = [], set()
    if not folder.is_dir():
        return rows
    stack = [folder]
    while stack:
        modules = stack.pop()
        packages = []
        for child in modules.iterdir():
            if child.name.startswith("@") and child.is_dir():
                packages += [p for p in child.iterdir() if p.is_dir()]
            elif child.is_dir() and not child.name.startswith("."):
                packages.append(child)
        for package in packages:
            if (package / "node_modules").is_dir():
                stack.append(package / "node_modules")
            meta = read_json(package / "package.json")
            if not isinstance(meta, dict) or not meta.get("name"):
                continue
            key = (meta["name"], meta.get("version"))
            if key in seen:
                continue
            seen.add(key)
            value = meta.get("license")
            if isinstance(value, dict):
                value = value.get("type")
            if not value and isinstance(meta.get("licenses"), list):
                value = " OR ".join(str(l.get("type", l)) if isinstance(l, dict) else str(l) for l in meta["licenses"])
            rows.append({"name": meta["name"], "version": meta.get("version"), "licence": value or ""})
    return rows


def scan_venv(python: Path) -> list[dict]:
    code = ("import json, importlib.metadata as m\nout=[]\n"
            "for d in m.distributions():\n"
            "  md=d.metadata; lic=md.get('License-Expression') or ''\n"
            "  if not lic:\n"
            "    cl=[c.split('::')[-1].strip() for c in (md.get_all('Classifier') or []) if c.startswith('License ::')]\n"
            "    lic=' OR '.join(cl) or (md.get('License') or '')[:80]\n"
            "  out.append({'name': md.get('Name'), 'version': md.get('Version'), 'licence': lic})\n"
            "print(json.dumps(out))")
    result = subprocess.run([str(python), "-c", code], capture_output=True, text=True)
    return json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else []


def dependency_report(rules: dict) -> list[dict]:
    """Every package the engine and the installed powers bring along, with a verdict. Python packages that only ship
    files (no licence field) are reviewed, never assumed fine."""
    decisions = (rules.get("decisions") or {})
    rows = []
    for row in scan_node_modules(engine_dir() / "node_modules"):
        rows.append({**row, "where": "engine (npm)", **classify(row["licence"], "library", rules)})
    cards = load_cards()
    for record_file in sorted(tools_root().glob("*/installed.json")):
        record = read_json(record_file) or {}
        tool = record_file.parent
        # a tool's insides are judged the way we use the tool: a program we only run is a separate program, all of it
        usage = ((cards.get(tool.name) or {}).get("licence") or {}).get("usage", "library")
        if record.get("kind") == "npm":
            for row in scan_node_modules(tool / str(record.get("version")) / "node_modules"):
                rows.append({**row, "where": f"{tool.name} (npm)", **classify(row["licence"], "file-in-project", rules)})
        if (tool / "venv" / "bin" / "python").is_file():
            for row in scan_venv(tool / "venv" / "bin" / "python"):
                rows.append({**row, "where": f"{tool.name} (pip)", **classify(row["licence"], usage, rules)})
    for row in rows:
        decision = decisions.get(str(row["name"]).lower())
        if row["verdict"] == "review" and decision and decision.get("verdict") == "allow":
            row.update(verdict="allow", why=f"reviewed: {decision.get('note', '')} ({decision.get('by')}, {decision.get('date')})")
    return rows


def cmd_licence(args) -> int:
    rules = policy()
    local = read_json(state_root() / "licence-decisions.json", {}) or {}
    rules = {**rules, "decisions": {**(rules.get("decisions") or {}), **local}}
    cards = load_cards()
    ids = [args.id] if args.id else list(cards)
    report = {"cards": [], "dependencies": []}
    for cid in ids:
        card = cards.get(cid)
        if not card:
            print(f"❌ no card named {cid}", file=sys.stderr)
            return 2
        row = {"id": cid, "stated": (card.get("licence") or {}).get("spdx"), **card_licence(card)}
        if args.online and card.get("upstream"):
            row["online"] = online_licence(card)
            for source, value in row["online"].items():
                if source == "error" or not value:
                    continue
                verdict = classify(value, (card.get("licence") or {}).get("usage", "library"), rules)
                decided = ((card.get("licence") or {}).get("decision") or {}).get("verdict") == "allow"
                if verdict["verdict"] == "review" and decided:
                    continue      # a person already read the licence file (e.g. GitHub says NOASSERTION for a plain MIT file)
                if RANK[verdict["verdict"]] > RANK[row["verdict"]]:
                    row.update(verdict=verdict["verdict"], why=f"{source} now says {value}: {verdict['why']}")
        report["cards"].append(row)
    if args.deps:
        report["dependencies"] = dependency_report(rules)
    all_rows = report["cards"] + report["dependencies"]
    blocked = [r for r in all_rows if r["verdict"] == "block"]
    review = [r for r in all_rows if r["verdict"] == "review"]
    write_json(state_root() / "licence.json", {"checked": dt.datetime.now().isoformat(timespec="seconds"),
                                               "blocked": len(blocked), "review": len(review), **report})
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for row in report["cards"]:
            mark = {"allow": "✅", "review": "⚠️", "block": "❌"}[row["verdict"]]
            print(f"{mark} {row['id']:<20} {row.get('stated') or '?':<28} {row['why']}")
        if args.deps:
            deps = report["dependencies"]
            print(f"dependencies: {len(deps)} packages, {sum(r['verdict'] == 'allow' for r in deps)} fine, "
                  f"{sum(r['verdict'] == 'review' for r in deps)} to read, {sum(r['verdict'] == 'block' for r in deps)} blocked")
            for row in deps:
                if row["verdict"] != "allow":
                    mark = "❌" if row["verdict"] == "block" else "⚠️"
                    print(f"  {mark} {row['where']}: {row['name']} {row.get('version') or ''}: {row['licence'] or 'no licence field'} ({row['why']})")
        print(f"summary: {len(blocked)} blocked, {len(review)} need a person to read the licence")
    return 4 if blocked else 0


# ── update watch ──────────────────────────────────────────────────────────
def version_key(text: str):
    parts = re.findall(r"\d+|[a-z]+", str(text).lower().lstrip("v"))
    return [(0, int(p)) if p.isdigit() else (-1, p) for p in parts]


def newer(a: str, b: str) -> bool:
    return version_key(a) > version_key(b)


def latest_upstream(card: dict) -> dict:
    up = card.get("upstream") or {}
    try:
        if up.get("index"):             # a download page: the newest version the pattern finds there
            request = urllib.request.Request(up["index"], headers={"User-Agent": "kit-to-clip-toolbox"})
            with urllib.request.urlopen(request, timeout=20) as response:
                page = response.read().decode("utf-8", errors="replace")
            found = sorted(set(re.findall(up["pattern"], page)), key=version_key)
            return {"version": found[-1], "source": "download page"} if found else {"error": "no version found on the download page"}
        if up.get("npm"):
            data = http_json(f"https://registry.npmjs.org/{up['npm']}")
            return {"version": data.get("dist-tags", {}).get("latest"), "source": "npm"}
        if up.get("pypi"):
            data = http_json(f"https://pypi.org/pypi/{up['pypi']}/json")
            return {"version": data.get("info", {}).get("version"), "source": "pypi"}
        if up.get("github"):
            release = github(f"repos/{up['github']}/releases/latest")
            if release and release.get("tag_name"):
                return {"version": release["tag_name"].lstrip("v"), "tag": release["tag_name"], "source": "github",
                        "notes": (release.get("body") or "")[:1500], "date": release.get("published_at")}
            commits = github(f"repos/{up['github']}/commits?per_page=1")
            if commits:
                return {"version": commits[0]["sha"][:12], "source": "github (no releases: latest commit)",
                        "date": commits[0].get("commit", {}).get("committer", {}).get("date")}
        if up.get("hf"):
            data = http_json(f"https://huggingface.co/api/models/{up['hf']}")
            return {"version": (data.get("sha") or "")[:12], "source": "huggingface", "date": data.get("lastModified")}
    except Exception as error:  # noqa: BLE001
        return {"error": str(error)[:160]}
    return {}


def watched_files(repo: str, ref: str, paths: list[str]) -> dict:
    """What the agent-facing files look like at a ref: file sha, or a folder's entry names."""
    out = {}
    for path in paths:
        data = github(f"repos/{repo}/contents/{path}?ref={ref}")
        if isinstance(data, dict):
            out[path] = data.get("sha")
        elif isinstance(data, list):
            out[path] = sorted(item.get("name") for item in data)
    return out


def resolve_tag(repo: str, version: str, tag_format: str) -> str | None:
    """The git tag for a version: the card's tag format, then the usual spellings."""
    for candidate in dict.fromkeys([tag_format.replace("{version}", version), f"v{version}", version]):
        if github(f"repos/{repo}/git/ref/tags/{candidate}"):
            return candidate
    return None


def watch_changes(card: dict, latest: dict) -> list[str]:
    repo = (card.get("upstream") or {}).get("github")
    if not repo or not latest.get("version"):
        return []
    paths = card.get("watch") or WATCH_DEFAULT
    tag_format = (card.get("install") or {}).get("tag") or "v{version}"
    new_ref = latest.get("tag") or resolve_tag(repo, latest["version"], tag_format)
    old_ref = resolve_tag(repo, pinned(card), tag_format)
    if not new_ref or not old_ref:
        return [f"could not find git tags for {pinned(card)} and {latest['version']} to compare the agent docs"]
    before, after = watched_files(repo, old_ref, paths), watched_files(repo, new_ref, paths)
    notes = []
    for path in paths:
        if path in after and path not in before:
            notes.append(f"new: {path}")
        elif path in before and path not in after:
            notes.append(f"removed: {path}")
        elif path in after and before[path] != after[path]:
            if isinstance(after[path], list):
                added = sorted(set(after[path]) - set(before[path]))
                notes.append(f"changed: {path}/" + (f" (new: {', '.join(added)})" if added else ""))
            else:
                notes.append(f"changed: {path}")
    text = latest.get("notes", "").lower()
    for word in ("mcp", "skill", "cli", "agent", "llms.txt", "breaking", "licen"):
        if word in text:
            notes.append(f"release notes mention: {word}")
    return notes


def cmd_updates(args) -> int:
    state_file = state_root() / "updates.json"
    previous = read_json(state_file, {}) or {}
    if args.if_due and previous.get("checked"):
        age = dt.datetime.now() - dt.datetime.fromisoformat(previous["checked"])
        if age.days < UPDATE_EVERY_DAYS:
            print(f"update watch: last checked {age.days} day(s) ago; next check in {UPDATE_EVERY_DAYS - age.days} day(s)")
            return 0
    cards = load_cards()
    rows = []
    for cid, card in cards.items():
        if args.try_id and cid != args.try_id:
            continue
        if not card.get("upstream"):
            continue
        latest = latest_upstream(card)
        row = {"id": cid, "pinned": pinned(card), "latest": latest.get("version"), "date": latest.get("date"),
               "source": latest.get("source"), "status": "current", "notes": []}
        if latest.get("error"):
            row.update(status="unknown", notes=[latest["error"]])
        elif latest.get("version") and row["pinned"] and latest["version"] != row["pinned"] and \
                (latest["source"] not in ("npm", "pypi", "github", "download page") or newer(latest["version"], row["pinned"])):
            row["status"] = "update"
            row["notes"] = watch_changes(card, latest)
            lic = online_licence(card, latest["version"] if latest.get("source") in ("npm", "pypi") else None)
            row["licence_now"] = lic
            for source, value in lic.items():
                if source != "error" and value:
                    verdict = classify(value, (card.get("licence") or {}).get("usage", "library"))
                    if verdict["verdict"] == "block":
                        row["status"] = "blocked"
                        row["notes"].append(f"licence changed to {value}: {verdict['why']}")
        if args.try_id and row["status"] == "update":
            with tempfile.TemporaryDirectory(prefix=f"try-{cid}-") as tmp:
                old_tools = os.environ.get("KIT_TO_CLIP_TOOLS")
                os.environ["KIT_TO_CLIP_TOOLS"] = tmp
                try:
                    do_install(card, latest["version"], Path(tmp), allow_unchecked=False)
                    ok, message = run_smoke(card)
                    row["try"] = {"installed": True, "smoke": ok, "message": message[:300]}
                except (RuntimeError, OSError, KeyError) as error:
                    row["try"] = {"installed": False, "smoke": False, "message": str(error)[:300]}
                finally:
                    if old_tools is None:
                        os.environ.pop("KIT_TO_CLIP_TOOLS", None)
                    else:
                        os.environ["KIT_TO_CLIP_TOOLS"] = old_tools
        rows.append(row)
    if not args.try_id:
        write_json(state_file, {"checked": dt.datetime.now().isoformat(timespec="seconds"), "results": rows})
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for row in rows:
        mark = {"current": "✅", "update": "🔄", "blocked": "❌", "unknown": "❔"}[row["status"]]
        line = f"{mark} {row['id']:<20} pinned {row['pinned'] or '-':<12} latest {row['latest'] or '?'}"
        print(line)
        for note in row["notes"]:
            print(f"     {note}")
        if row.get("try"):
            t = row["try"]
            print(f"     tried the new version: {'installed' if t['installed'] else 'install failed'}, "
                  f"smoke {'passed' if t['smoke'] else 'failed'}: {t['message'][:160]}")
    updates = [r for r in rows if r["status"] == "update"]
    print(f"summary: {len(updates)} update(s) available, {sum(r['status'] == 'blocked' for r in rows)} blocked by a licence change. "
          "Pins move only after a smoke test and the person's yes (toolbox.py updates --try <id>, then pin).")
    return 0


def cmd_pin(args) -> int:
    cards = load_cards()
    if args.id not in cards:
        print(f"❌ no card named {args.id}", file=sys.stderr)
        return 2
    pins_file = state_root() / "pins.json"
    pins = read_json(pins_file, {}) or {}
    if args.version in ("card", "reset"):
        pins.pop(args.id, None)
        print(f"{args.id}: back to the card's version {cards[args.id].get('pinned')}")
    else:
        pins[args.id] = args.version
        print(f"{args.id}: this computer now uses {args.version}; install it with toolbox.py install {args.id}")
    write_json(pins_file, pins)
    return 0


# ── lint ──────────────────────────────────────────────────────────────────
REQUIRED = ("schema", "id", "name", "about", "kind", "capabilities", "licence", "maturity", "fallback")


def lint_card(card: dict, caps: dict) -> list[str]:
    errors = []
    cid = card.get("id", "?")
    for key in REQUIRED:
        if key not in card:
            errors.append(f"{cid}: missing {key}")
    if Path(card.get("_path", "")).stem != cid:
        errors.append(f"{cid}: file name must be {cid}.json")
    if card.get("kind") not in KINDS:
        errors.append(f"{cid}: kind must be one of {', '.join(KINDS)}")
    if card.get("maturity") not in ("stable", "early"):
        errors.append(f"{cid}: maturity must be stable or early")
    for cap in card.get("capabilities", []):
        if cap not in caps:
            errors.append(f"{cid}: unknown capability {cap}")
    lic = card.get("licence") or {}
    if not lic.get("spdx"):
        errors.append(f"{cid}: licence.spdx is required")
    if card_licence(card)["verdict"] == "block":
        errors.append(f"{cid}: licence is blocked by policy ({card_licence(card)['why']})")
    if card.get("recipe") and not (TOOLBOX / card["recipe"]).is_file():
        errors.append(f"{cid}: recipe {card['recipe']} not found")
    if card.get("guide") and not (SKILL_DIR / card["guide"]).is_file():
        errors.append(f"{cid}: guide {card['guide']} not found")
    kind = card.get("kind")
    install = card.get("install") or {}
    if kind in ("release", "app", "pip", "npm") and not card.get("pinned"):
        errors.append(f"{cid}: pinned version required")
    if kind in ("release", "app"):
        for key in ("repo", "tag", "asset") if not install.get("url") else ("asset",):
            if key not in install:
                errors.append(f"{cid}: install.{key} required")
        if not install.get("sha256") and not install.get("sums"):
            errors.append(f"{cid}: install needs sha256 or sums (a checksum)")
    if kind in ("pip", "npm") and not install.get("packages"):
        errors.append(f"{cid}: install.packages required")
    if kind == "skill" and not install.get("command"):
        errors.append(f"{cid}: install.command required")
    if kind == "builtin" and not ((card.get("detect") or {}).get("files") or (card.get("detect") or {}).get("commands")):
        errors.append(f"{cid}: detect.files or detect.commands required")
    if kind not in ("builtin",) and not card.get("upstream"):
        errors.append(f"{cid}: upstream required so the update and licence watches can follow it")
    return errors


def cmd_lint(args) -> int:
    caps = capabilities()
    errors = []
    cards = load_cards()
    for path in sorted(CARDS.glob("*.json")):
        if not isinstance(read_json(path), dict):
            errors.append(f"{path.name}: not valid JSON")
    for card in cards.values():
        errors += lint_card(card, caps)
    for cap, info in caps.items():
        if not info.get("fallback"):
            errors.append(f"capability {cap}: fallback required")
    if errors:
        print("\n".join(f"❌ {e}" for e in errors))
        return 1
    print(f"✅ {len(cards)} cards, {len(caps)} capabilities: all valid")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "doctor"):
        p = sub.add_parser(name)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("which")
    p.add_argument("capability")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("id")
    p = sub.add_parser("install")
    p.add_argument("id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--allow-unchecked", action="store_true", help=argparse.SUPPRESS)
    p = sub.add_parser("smoke")
    p.add_argument("id", help="a card id, or all (every installed power)")
    p = sub.add_parser("path")
    p.add_argument("id")
    p.add_argument("entry", nargs="?")
    p = sub.add_parser("vendor")
    p.add_argument("id")
    p.add_argument("project")
    p = sub.add_parser("licence", aliases=["license"])
    p.add_argument("id", nargs="?")
    p.add_argument("--online", action="store_true", help="ask the upstream what it says today")
    p.add_argument("--deps", action="store_true", help="also every package the engine and installed powers bring")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("updates")
    p.add_argument("--if-due", action="store_true", help=f"only when the last check is {UPDATE_EVERY_DAYS}+ days old")
    p.add_argument("--try", dest="try_id", help="install the newer version in a scratch folder and run its smoke test")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("pin")
    p.add_argument("id")
    p.add_argument("version", help="a version, or 'card' to go back to the card's pin")
    sub.add_parser("lint")
    args = parser.parse_args(argv)
    handlers = {"list": cmd_list, "doctor": cmd_doctor, "which": cmd_which, "check": cmd_check, "install": cmd_install,
                "smoke": cmd_smoke, "path": cmd_path, "vendor": cmd_vendor, "licence": cmd_licence, "license": cmd_licence,
                "updates": cmd_updates, "pin": cmd_pin, "lint": cmd_lint}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
