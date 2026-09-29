#!/usr/bin/env python3
"""Kit to Clip asset search: find a brand asset before anyone says it doesn't exist.

  python3 assets.py search <brand kit dir> <word> [<word> ...] [--no-remote] [--json]
  python3 assets.py sheet  <brand kit dir> --out <dir>      numbered contact sheets of EVERY picture, to look at

Names mislead (a device shot may be called upload.png), so a search is never the whole job: `sheet` makes numbered
thumbnails of every raster image in the kit and every picture embedded in its office files (.pptx, .docx, .xlsx,
.key: their media folders), tiled 6x4 per sheet, plus index.json mapping each number to its file. Look at every sheet.

Searches, in order, and reports every place it looked:
  1. every file in the kit and its companion skills (folders inside it), originals included (source-assets/ etc.):
     file names and folder names
  2. every JSON manifest and index in the kit (asset-index.json, media-manifest.json, ...): keys, paths, "use",
     "avoid" and descriptions
  3. SVG titles and descriptions, and Markdown references that mention the words
  4. official press-kit ZIPs the manifests link (https://.../*.zip): the file list only, read from the ZIP's table of
     contents with HTTP range requests (no full download); --no-remote skips this
A hit needs every word (case-insensitive, in any order) in the same name or entry. Exit 0 with hits, 1 without hits
(the "searched" list is the evidence to show), 2 on bad arguments.
"""
import argparse
import json
import re
import struct
import sys
import urllib.request
from pathlib import Path

SKIP = {"node_modules", ".git", "__pycache__", "dist"}
MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".tif", ".tiff", ".psd", ".mp4", ".mov", ".webm", ".pdf", ".fig"}


def words_in(text, words):
    t = text.lower()
    return all(w in t for w in words)


def walk(kit):
    for f in sorted(kit.rglob("*")):
        rel = f.relative_to(kit)
        if any(p in SKIP for p in rel.parts):
            continue
        yield f, rel


def zip_listing(url):
    """File names in a remote ZIP, from its central directory only (two small range requests)."""
    head = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20)
    size = int(head.headers.get("Content-Length") or 0)
    if not size:
        raise ValueError("no Content-Length")

    def rng(a, b):
        return urllib.request.urlopen(urllib.request.Request(url, headers={"Range": f"bytes={a}-{b}"}), timeout=30).read()
    tail = rng(max(0, size - 65536), size - 1)
    i = tail.rfind(b"PK\x05\x06")
    if i < 0:
        raise ValueError("no ZIP end record")
    cd_size, cd_off = struct.unpack("<II", tail[i + 12:i + 20])
    cd = rng(cd_off, cd_off + cd_size - 1)
    p, names = 0, []
    while p + 46 <= len(cd) and cd[p:p + 4] == b"PK\x01\x02":
        n, e, c = struct.unpack("<HHH", cd[p + 28:p + 34])
        names.append(cd[p + 46:p + 46 + n].decode("utf8", "replace"))
        p += 46 + n + e + c
    return size, names


def json_strings(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from json_strings(v, f"{path}.{k}" if path else k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from json_strings(v, f"{path}[{i}]")
    elif isinstance(x, str):
        yield path, x


def search(kit, words, remote=True):
    hits, searched, zips = [], [], set()
    files = list(walk(kit))
    media = [r for f, r in files if f.is_file() and f.suffix.lower() in MEDIA]
    searched.append(f"{len(files)} files and folders in {kit} ({len(media)} images, video, PDF or design files), originals included")
    for f, rel in files:
        if words_in(str(rel), words):
            hits.append({"where": "file" if f.is_file() else "folder", "path": str(rel)})
    manifests = [(f, r) for f, r in files if f.is_file() and f.suffix == ".json" and f.stat().st_size < 5_000_000]
    searched.append(f"{len(manifests)} JSON manifests and indexes (keys, paths, use and avoid notes)")
    for f, rel in manifests:
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        entries = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), None) if isinstance(data, dict) else None
        for path, s in json_strings(data):
            for u in re.findall(r"https?://[^\s\"')]+\.zip", s):
                zips.add(u)
        for i, entry in enumerate(entries or []):
            if isinstance(entry, dict) and words_in(json.dumps(entry), words):
                hits.append({"where": "manifest", "path": f"{rel} entry {i}", "entry": {k: entry[k] for k in list(entry)[:6]}})
    texts = [(f, r) for f, r in files if f.is_file() and f.suffix.lower() in (".svg", ".md") and f.stat().st_size < 2_000_000]
    searched.append(f"{len(texts)} SVG and Markdown files (titles, descriptions, references)")
    for f, rel in texts:
        try:
            t = f.read_text(errors="replace")
        except OSError:
            continue
        chunks = re.findall(r"<(?:title|desc)>(.*?)</(?:title|desc)>", t, re.S) if f.suffix.lower() == ".svg" else t.splitlines()
        for c in chunks:
            if words_in(c, words):
                hits.append({"where": "text", "path": str(rel), "line": c.strip()[:160]})
                break
    for u in sorted(zips):
        if not remote:
            searched.append(f"official ZIP {u}: skipped (--no-remote)")
            continue
        try:
            size, names = zip_listing(u)
        except Exception as e:                      # network or format: say so, never pretend it was searched
            searched.append(f"official ZIP {u}: could not read its file list ({e})")
            continue
        searched.append(f"official ZIP {u}: {len(names)} files ({size / 1e6:.0f} MB, file list only)")
        hits += [{"where": "official zip", "path": f"{u} :: {n}"} for n in names if words_in(n, words)]
    # media first (what a video can use), then everything else; many hits in one manifest collapse into one line
    is_media = lambda h: h["where"] in ("file", "official zip") and Path(h["path"].split(" :: ")[-1]).suffix.lower() in MEDIA
    ordered, per_file = [h for h in hits if is_media(h)], {}
    for h in hits:
        if is_media(h):
            continue
        key = (h["where"], h["path"].split(" entry ")[0])
        per_file.setdefault(key, []).append(h)
    for (where, path), group in per_file.items():
        ordered.append(group[0] if len(group) == 1 else {"where": where, "path": f"{path} ({len(group)} entries)"})
    return ordered, searched


RASTER = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp", ".emf", ".wmf"}
OFFICE = {".pptx", ".potx", ".docx", ".dotx", ".xlsx", ".key"}


def sheet(kit, out):
    """Numbered thumbnails of every picture (files and office-embedded media), tiled 6x4 per sheet."""
    import subprocess
    import zipfile
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "thumbs"
    tmp.mkdir(exist_ok=True)
    items = []
    for f, rel in walk(kit):
        if not f.is_file():
            continue
        if f.suffix.lower() in RASTER and f.suffix.lower() not in (".emf", ".wmf"):
            items.append((str(rel), f))
        elif f.suffix.lower() in OFFICE:
            try:
                with zipfile.ZipFile(f) as z:
                    for n in z.namelist():
                        if "/media/" in n or n.startswith("Data/"):
                            if Path(n).suffix.lower() in RASTER - {".emf", ".wmf"}:
                                dst = tmp / f"embedded-{len(items):04d}{Path(n).suffix.lower()}"
                                dst.write_bytes(z.read(n))
                                items.append((f"{rel} :: {n}", dst))
            except zipfile.BadZipFile:
                continue
    index, n_ok = [], 0
    for i, (label, src) in enumerate(items, 1):
        th = tmp / f"t{i:04d}.png"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-frames:v", "1", "-vf",
                            "scale=300:190:force_original_aspect_ratio=decrease,pad=300:190:(ow-iw)/2:(oh-ih)/2:color=0x808080,"
                            f"pad=300:222:0:32:color=white,drawtext=text='{i}':x=6:y=6:fontsize=22:fontcolor=black",
                            str(th)], capture_output=True, text=True)
        ok = r.returncode == 0 and th.exists()
        n_ok += ok
        index.append({"n": i, "file": label, "thumb": str(th) if ok else None})
    thumbs = [x for x in index if x["thumb"]]
    # one explicit grid per sheet (xstack places every input at a fixed spot, so no picture can be dropped)
    sheets, tw, th_ = [], 300, 222
    for k in range(0, len(thumbs), 24):
        page = thumbs[k:k + 24]
        cols = 6
        inputs = []
        for x in page:
            inputs += ["-i", x["thumb"]]
        layout = "|".join(f"{(i % cols) * (tw + 6)}_{(i // cols) * (th_ + 6)}" for i in range(len(page)))
        graph = "".join(f"[{i}:v]" for i in range(len(page))) + f"xstack=inputs={len(page)}:layout={layout}:fill=white" \
            if len(page) > 1 else "[0:v]null"
        dst = out / f"sheet-{k // 24 + 1:02d}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-frames:v", "1", str(dst)], capture_output=True)
        sheets.append(str(dst))
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return index, sheets, n_ok


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "sheet":
        sp = argparse.ArgumentParser()
        sp.add_argument("command"); sp.add_argument("kit"); sp.add_argument("--out", required=True)
        a = sp.parse_args()
        kit = Path(a.kit).expanduser()
        if not kit.is_dir():
            print(f"assets: {kit} is not a folder", file=sys.stderr)
            sys.exit(2)
        index, sheets, ok = sheet(kit, Path(a.out))
        print(f"assets: {len(index)} pictures ({ok} thumbnailed) in {len(sheets)} sheet(s); numbers map to files in {Path(a.out) / 'index.json'}")
        for sh in sheets:
            print(f"  look at: {sh}")
        sys.exit(0 if index else 1)
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["search"])
    ap.add_argument("kit")
    ap.add_argument("words", nargs="+")
    ap.add_argument("--no-remote", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    kit = Path(a.kit).expanduser()
    if not kit.is_dir():
        print(f"assets: {kit} is not a folder", file=sys.stderr)
        sys.exit(2)
    words = [w.lower() for w in a.words]
    hits, searched = search(kit, words, remote=not a.no_remote)
    if a.json:
        print(json.dumps({"words": words, "hits": hits, "searched": searched}, indent=1))
    else:
        print(f"assets: {len(hits)} hit(s) for {' + '.join(words)} in {kit}")
        for h in hits:
            print(f"  ✓ [{h['where']}] {h['path']}" + (f"  {h.get('line', '')}" if h.get("line") else ""))
        if hits and not any(Path(h["path"].split(" :: ")[-1]).suffix.lower() in MEDIA and h["where"] in ("file", "official zip") for h in hits):
            print("  (no image, video or design file among the hits: icons, manifests and docs only)")
        print("  searched:")
        for s in searched:
            print(f"    - {s}")
        if not hits:
            print("  not found in this kit. Before saying it does not exist, name the likely home (a design library, "
                  "the brand team) and ask; never swap in a lookalike without saying so.")
    sys.exit(0 if hits else 1)


if __name__ == "__main__":
    main()
