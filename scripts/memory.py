#!/usr/bin/env python3
"""Kit to Clip's local memory: the brands this person used, what they made, what they liked and what they did not.

  memory.py recall [--repo <path>] [--brand <id>] [--json]   what to offer first (exit 0, or 3 when there is no memory yet)
  memory.py record --brand <id> [--brand-name N] [--brand-path P] [--source pack|pointer|kit|neutral]
                   [--format F] [--platforms a,b] [--powers p,q] [--repo R] [--outcome delivered|draft|abandoned] [--note T]
  memory.py prefer (--like | --dislike) "<what>" [--reason "<why>"] [--topic motion|sound|type|colour|format|platform|pace|general] [--brand <id>]
  memory.py lesson add "<what worked or failed>" [--power <id>] | memory.py lesson list
  memory.py show [--json]                          everything remembered, in plain words
  memory.py forget (--all | --brand <id> | --pref <n> | --lessons | --history)

It lives on this computer only: $KIT_TO_CLIP_MEMORY, else <engine>/memory (the engine is $REEL_STUDIO, else
$REEL_STUDIO_HOME, else ~/.kit-to-clip). It is never written into a repo, never exported, never uploaded. Defaults it
suggests are always shown to the person as a choice ("the same brand as last time?"), never applied silently.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path

TOPICS = ("motion", "sound", "type", "colour", "format", "platform", "pace", "general")


def memory_dir() -> Path:
    if os.environ.get("KIT_TO_CLIP_MEMORY"):
        return Path(os.environ["KIT_TO_CLIP_MEMORY"]).expanduser()
    for key in ("REEL_STUDIO", "REEL_STUDIO_HOME"):
        if os.environ.get(key):
            return Path(os.environ[key]).expanduser() / "memory"
    return Path.home() / ".kit-to-clip" / "memory"


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def load_profile() -> dict:
    try:
        data = json.loads((memory_dir() / "profile.json").read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("brands", {})
            data.setdefault("preferences", [])
            return data
    except (OSError, ValueError):
        pass
    return {"schema": 1, "brands": {}, "preferences": []}


def save_profile(profile: dict) -> None:
    folder = memory_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "profile.json.tmp"
    tmp.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(folder / "profile.json")


def history() -> list[dict]:
    rows = []
    try:
        for line in (memory_dir() / "history.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


def lessons() -> list[str]:
    try:
        return [l[2:] for l in (memory_dir() / "lessons.md").read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
    except OSError:
        return []


def split(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def repo_key(path: str | None) -> str | None:
    if not path:
        return None
    return str(Path(path).expanduser().resolve())


# ── recall ────────────────────────────────────────────────────────────────
def recall(repo: str | None = None, brand: str | None = None) -> dict:
    profile, rows = load_profile(), history()
    repo = repo_key(repo)
    brands = sorted(profile["brands"].items(), key=lambda kv: (kv[1].get("last", ""), kv[1].get("uses", 0)), reverse=True)
    last = rows[-1] if rows else None
    in_repo = [r for r in rows if repo and r.get("repo") == repo]
    repo_brand = Counter(r.get("brand") for r in in_repo if r.get("brand")).most_common(1)
    focus = brand or (repo_brand[0][0] if repo_brand else (last or {}).get("brand"))
    scoped = [r for r in rows if not focus or r.get("brand") == focus] or rows
    platforms = Counter(p for r in scoped for p in r.get("platforms", []))
    formats = Counter(r.get("format") for r in scoped if r.get("format"))
    prefs = [p for p in profile["preferences"] if not p.get("brand") or not focus or p.get("brand") == focus]
    return {
        "has_memory": bool(rows or profile["brands"] or profile["preferences"]),
        "last_job": last,
        "this_repo_brand": repo_brand[0][0] if repo_brand else None,
        "suggested_brand": focus,
        "brands": [{"id": k, **v} for k, v in brands],
        "usual_platforms": [p for p, _ in platforms.most_common(3)],
        "usual_formats": [f for f, _ in formats.most_common(3)],
        "likes": [p for p in prefs if p.get("like")][-6:],
        "dislikes": [p for p in prefs if not p.get("like")][-6:],
        "lessons": len(lessons()),
    }


def say_recall(r: dict) -> str:
    if not r["has_memory"]:
        return "No memory yet: this is the first video made with Kit to Clip on this computer."
    lines = []
    if r["last_job"]:
        j = r["last_job"]
        what = j.get("format") or "a video"
        where = f" for {', '.join(j['platforms'])}" if j.get("platforms") else ""
        lines.append(f"Last time ({j.get('date', '?')[:10]}): {what} with the {j.get('brand_name') or j.get('brand')} brand{where}.")
    if r["this_repo_brand"]:
        lines.append(f"In this repo you used: {r['this_repo_brand']}.")
    if r["brands"]:
        lines.append("Brands used here: " + "; ".join(
            f"{b.get('name') or b['id']} ({b.get('uses', 0)}×, last {b.get('last', '?')[:10]})" for b in r["brands"][:5]) + ".")
    if r["suggested_brand"]:
        lines.append(f"Offer first: the {r['suggested_brand']} brand (\"same as last time?\"), then the others, then something new.")
    if r["usual_platforms"]:
        lines.append("Usual platforms: " + ", ".join(r["usual_platforms"]) + ".")
    if r["usual_formats"]:
        lines.append("Usual formats: " + ", ".join(r["usual_formats"]) + ".")
    for label, items in (("Liked", r["likes"]), ("Avoid", r["dislikes"])):
        if items:
            lines.append(f"{label}: " + "; ".join(p["text"] + (f" ({p['reason']})" if p.get("reason") else "") for p in items) + ".")
    if r["lessons"]:
        lines.append(f"{r['lessons']} local lesson(s): memory.py lesson list.")
    return "\n".join(lines)


# ── commands ──────────────────────────────────────────────────────────────
def cmd_recall(args) -> int:
    r = recall(args.repo, args.brand)
    print(json.dumps(r, indent=2, ensure_ascii=False) if args.json else say_recall(r))
    return 0 if r["has_memory"] else 3


def cmd_record(args) -> int:
    profile = load_profile()
    entry = profile["brands"].setdefault(args.brand, {"uses": 0, "formats": {}, "platforms": {}, "repos": []})
    if args.brand_name:
        entry["name"] = args.brand_name
    if args.brand_path:
        entry["path"] = str(Path(args.brand_path).expanduser())
    if args.source:
        entry["source"] = args.source
    entry["uses"] = entry.get("uses", 0) + 1
    entry["last"] = now()
    if args.format:
        entry.setdefault("formats", {})[args.format] = entry.get("formats", {}).get(args.format, 0) + 1
    for p in split(args.platforms):
        entry.setdefault("platforms", {})[p] = entry.get("platforms", {}).get(p, 0) + 1
    repo = repo_key(args.repo)
    if repo and repo not in entry.setdefault("repos", []):
        entry["repos"].append(repo)
    save_profile(profile)
    row = {"date": now(), "repo": repo, "brand": args.brand, "brand_name": entry.get("name"), "format": args.format,
           "platforms": split(args.platforms), "powers": split(args.powers), "outcome": args.outcome, "note": args.note}
    folder = memory_dir()
    with open(folder / "history.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps({k: v for k, v in row.items() if v not in (None, [], "")}, ensure_ascii=False) + "\n")
    print(f"remembered: {args.format or 'a video'} with {entry.get('name') or args.brand} ({args.outcome})")
    return 0


def cmd_prefer(args) -> int:
    profile = load_profile()
    pref = {"n": max([p.get("n", 0) for p in profile["preferences"]] + [0]) + 1, "like": bool(args.like),
            "text": args.like or args.dislike, "topic": args.topic, "date": now()}
    if args.reason:
        pref["reason"] = args.reason
    if args.brand:
        pref["brand"] = args.brand
    same = [p for p in profile["preferences"] if p["text"].lower() == pref["text"].lower() and p.get("brand") == pref.get("brand")]
    for p in same:  # the newest word on the same thing wins
        profile["preferences"].remove(p)
    profile["preferences"].append(pref)
    save_profile(profile)
    print(f"remembered ({'likes' if pref['like'] else 'avoids'}, {pref['topic']}): {pref['text']}")
    return 0


def cmd_lesson(args) -> int:
    folder = memory_dir()
    if args.action == "list":
        items = lessons()
        print("\n".join(f"- {l}" for l in items) if items else "no local lessons yet")
        return 0
    if not args.text:
        print("❌ say what was learned: memory.py lesson add \"…\"", file=sys.stderr)
        return 2
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "lessons.md"
    if not path.exists():
        path.write_text("# Local lessons (this computer only)\n\n", encoding="utf-8")
    tag = f"[{args.power}] " if args.power else ""
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"- {dt.date.today().isoformat()} {tag}{args.text}\n")
    print("lesson saved")
    return 0


def cmd_show(args) -> int:
    data = {"where": str(memory_dir()), "profile": load_profile(), "history": history(), "lessons": lessons()}
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    print(f"Memory on this computer: {data['where']}")
    print(say_recall(recall()))
    prefs = data["profile"]["preferences"]
    if prefs:
        print("\nPreferences (forget one with memory.py forget --pref <n>):")
        for p in prefs:
            scope = f" [{p['brand']}]" if p.get("brand") else ""
            print(f"  {p['n']}. {'likes' if p['like'] else 'avoids'} ({p['topic']}){scope}: {p['text']}" + (f" ({p['reason']})" if p.get("reason") else ""))
    print(f"\nJobs remembered: {len(data['history'])}. Local lessons: {len(data['lessons'])}.")
    return 0


def cmd_forget(args) -> int:
    folder = memory_dir()
    profile = load_profile()
    if args.all:
        for name in ("profile.json", "history.jsonl", "lessons.md"):
            try:
                (folder / name).unlink()
            except OSError:
                pass
        print("forgot everything")
        return 0
    if args.brand:
        profile["brands"].pop(args.brand, None)
        profile["preferences"] = [p for p in profile["preferences"] if p.get("brand") != args.brand]
        rows = [r for r in history() if r.get("brand") != args.brand]
        save_profile(profile)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "history.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(f"forgot the {args.brand} brand and its jobs and preferences")
    if args.pref is not None:
        before = len(profile["preferences"])
        profile["preferences"] = [p for p in profile["preferences"] if p.get("n") != args.pref]
        save_profile(profile)
        print("forgot that preference" if len(profile["preferences"]) < before else f"no preference number {args.pref}")
    if args.lessons:
        try:
            (folder / "lessons.md").unlink()
        except OSError:
            pass
        print("forgot the local lessons")
    if args.history:
        try:
            (folder / "history.jsonl").unlink()
        except OSError:
            pass
        print("forgot the job history")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("recall")
    p.add_argument("--repo")
    p.add_argument("--brand")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("record")
    p.add_argument("--brand", required=True)
    p.add_argument("--brand-name")
    p.add_argument("--brand-path")
    p.add_argument("--source", choices=("pack", "pointer", "kit", "neutral"))
    p.add_argument("--format")
    p.add_argument("--platforms")
    p.add_argument("--powers")
    p.add_argument("--repo")
    p.add_argument("--outcome", default="delivered", choices=("delivered", "draft", "abandoned"))
    p.add_argument("--note")
    p = sub.add_parser("prefer")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--like")
    group.add_argument("--dislike")
    p.add_argument("--reason")
    p.add_argument("--topic", default="general", choices=TOPICS)
    p.add_argument("--brand")
    p = sub.add_parser("lesson")
    p.add_argument("action", choices=("add", "list"))
    p.add_argument("text", nargs="?")
    p.add_argument("--power")
    p = sub.add_parser("show")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("forget")
    p.add_argument("--all", action="store_true")
    p.add_argument("--brand")
    p.add_argument("--pref", type=int)
    p.add_argument("--lessons", action="store_true")
    p.add_argument("--history", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "forget" and not (args.all or args.brand or args.pref is not None or args.lessons or args.history):
        parser.error("forget needs --all, --brand, --pref, --lessons or --history")
    handlers = {"recall": cmd_recall, "record": cmd_record, "prefer": cmd_prefer, "lesson": cmd_lesson,
                "show": cmd_show, "forget": cmd_forget}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
