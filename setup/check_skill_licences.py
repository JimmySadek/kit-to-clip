#!/usr/bin/env python3
"""Every agent skill pinned in skills-lock.json must have a recorded licence that toolbox/policy.json allows.

  check_skill_licences.py [--lock skills-lock.json] [--licences skills-licences.json] [--policy policy.json]

A skill's own entry in skills-licences.json ("skills") wins over its source repo's ("sources"), because a repo can mix
licences (anthropics/skills does). Exit 0 when every pinned skill passes, 1 when one has no record or a licence the
policy does not allow (a non-commercial, AGPL or revenue-capped licence is never allowed)."""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--lock", default=str(HERE / "skills-lock.json"))
ap.add_argument("--licences", default=str(HERE / "skills-licences.json"))
ap.add_argument("--policy", default=str(HERE.parent / "toolbox" / "policy.json"))
a = ap.parse_args()

lock = json.loads(Path(a.lock).read_text())["skills"]
rec = json.loads(Path(a.licences).read_text())
policy = json.loads(Path(a.policy).read_text())
allowed, aliases = set(policy["allow"]), policy.get("aliases", {})

problems = []
for name, entry in sorted(lock.items()):
    src = entry.get("source", "")
    got = rec.get("skills", {}).get(name) or rec.get("sources", {}).get(src)
    if not got:
        problems.append(f"{name} ({src}): no licence recorded in skills-licences.json")
        continue
    lic = aliases.get(got.get("licence", ""), got.get("licence", ""))
    if lic not in allowed:
        problems.append(f"{name} ({src}): licence {lic or 'none'!s} is not allowed by policy.json")

if problems:
    print("✗ skill licences:\n  - " + "\n  - ".join(problems))
    sys.exit(1)
print(f"✓ skill licences: all {len(lock)} pinned skills have an allowed licence")
