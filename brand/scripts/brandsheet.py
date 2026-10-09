#!/usr/bin/env python3
"""Kit to Clip brand sheet: turn a captured website into a brand sheet and a proposed token set, never a guess.

  npx hyperframes capture <url> --skip-vision -o <capture-dir>        (after env.sh; --skip-vision keeps it local)
  python3 brandsheet.py <capture-dir> --out <brand-sheet.md> [--json <proposal.json>] [--kit <brand kit dir>]

Reads capture's extracted/tokens.json, design-styles.json, fonts-manifest.json and animations.json, and the logo
candidates in assets/. Writes: Overview, Colours (with the roles they play on the page and how often), Typography
(faces per role, and whether font files were captured), Shape (radii, shadows), Components (buttons), Logo
candidates, Motion, and "To confirm" (what a website cannot tell: rules, claims, the motif, licences). Every proposed
--reel-* value in the JSON names where it came from. With --kit, values that differ from that kit's video pack (or its
CSS) are listed as conflicts for the brand owner. Brand onboarding (references/brand-onboarding.md) starts here when
a brand is known only from its website. Exit 0 written, 2 when the capture folder is incomplete.
"""
import argparse
import colorsys
import json
import re
import sys
from pathlib import Path


def fail(msg):
    print(f"brandsheet: {msg}", file=sys.stderr)
    sys.exit(2)


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) if len(h) >= 6 else (0, 0, 0)


def sat_light(h):
    r, g, b = rgb(h)
    hh, l, s = colorsys.rgb_to_hls(r, g, b)
    return s, l


def contrast(a, b):
    lum = lambda c: 0.2126 * c[0] ** 2.2 + 0.7152 * c[1] ** 2.2 + 0.0722 * c[2] ** 2.2
    la, lb = sorted([lum(rgb(a)), lum(rgb(b))], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def kit_values(kit):
    """--reel-* values the kit's video pack already sets (templates/brand.css), else colours and faces in its CSS."""
    pack_css = kit / "kit-to-clip" / "templates" / "brand.css"
    text = pack_css.read_text() if pack_css.is_file() else ""
    vals = dict(re.findall(r"--reel-([\w-]+)\s*:\s*([^;]+);", text))
    src = str(pack_css) if text else None
    return vals, src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--out", required=True)
    ap.add_argument("--json")
    ap.add_argument("--kit")
    a = ap.parse_args()
    cap = Path(a.capture)
    ex = cap / "extracted"
    need = ["tokens.json", "design-styles.json"]
    missing = [n for n in need if not (ex / n).is_file()]
    if missing:
        fail(f"{cap} is not a complete capture (missing extracted/{', extracted/'.join(missing)}); run npx hyperframes capture <url> --skip-vision -o <capture-dir> first")
    tok = json.loads((ex / "tokens.json").read_text())
    ds = json.loads((ex / "design-styles.json").read_text())
    fm = json.loads((ex / "fonts-manifest.json").read_text()) if (ex / "fonts-manifest.json").is_file() else {"files": []}
    an = json.loads((ex / "animations.json").read_text()) if (ex / "animations.json").is_file() else {}
    url = (json.loads((cap / "meta.json").read_text()).get("id", "") if (cap / "meta.json").is_file() else "").replace("-video", "")

    stats = tok.get("colorStats", [])
    section_bgs = [s.get("backgroundColor") for s in tok.get("sections", []) if s.get("backgroundColor")]
    bg = max(set(section_bgs), key=section_bgs.count) if section_bgs else (stats[0]["hex"] if stats else "#000000")
    text_c = max(stats, key=lambda s: s.get("textCount", 0))["hex"] if stats else "#FFFFFF"
    chroma = [s for s in stats if sat_light(s["hex"])[0] > 0.45 and 0.25 < sat_light(s["hex"])[1] < 0.75]
    accent = max(chroma, key=lambda s: (s.get("interactiveBg", 0) * 3 + s.get("bgCount", 0) + s.get("textCount", 0)))["hex"] if chroma else None
    # muted text is a mid-grey: a neutral between the background and the main text, not a near-white
    neutrals = [s for s in stats if sat_light(s["hex"])[0] < 0.2 and 0.35 <= sat_light(s["hex"])[1] <= 0.8
                and s["hex"].upper() not in (bg.upper(), text_c.upper())]
    if not neutrals:
        neutrals = [{"hex": v.strip(), "textCount": 1} for k, v in tok.get("cssVariables", {}).items()
                    if re.match(r"#[0-9a-fA-F]{6}$", str(v).strip()) and sat_light(v.strip())[0] < 0.2 and 0.35 <= sat_light(v.strip())[1] <= 0.8]
    muted = max(neutrals, key=lambda s: s.get("textCount", 0))["hex"] if neutrals else None
    surf = [s["hex"] for s in stats if s.get("bgCount", 0) and s["hex"].upper() not in (bg.upper(), (accent or "").upper())
            and abs(sat_light(s["hex"])[1] - sat_light(bg)[1]) < 0.2]
    surface = surf[0] if surf else None
    typo = {t["role"]: t for t in ds.get("typography", [])}
    display, body = typo.get("display") or typo.get("heading"), typo.get("body")
    captured_faces = sorted({f.get("family") for f in fm.get("files", []) if f.get("identified") and not f.get("isIcon")})
    # the brand's own buttons: cookie and consent banners (a third party's UI) and unnamed wrappers are left out
    third = re.compile(r"cookie|consent|accept|reject|decline|privacy settings|^#|^button$", re.I)
    buttons = [b for b in ds.get("buttons", []) if b.get("background") not in (None, "transparent") and not third.search(b.get("label", ""))]
    radius = next((b["borderRadius"] for b in buttons if b.get("background", "").upper() == (accent or "").upper()), None)
    logos = sorted(p.name for p in (cap / "assets").glob("logo-*")) if (cap / "assets").is_dir() else []
    # text on the accent: what the brand's accent buttons actually use; the higher-contrast choice only when none does
    used = [b.get("color") for b in buttons if accent and str(b.get("background", "")).upper() == accent.upper() and b.get("color")]
    if used:
        on_accent = [max(set(used), key=used.count), f"text on the site's accent buttons ({contrast(max(set(used), key=used.count), accent):.1f}:1)"]
    elif accent:
        best = "#FFFFFF" if contrast(accent, "#FFFFFF") >= contrast(accent, "#000000") else "#000000"
        on_accent = [best, "the higher-contrast of white and black on the accent (the site shows none)"]
    else:
        on_accent = [None, "no accent"]

    proposal = {
        "--reel-bg": [bg, "most common section background"],
        "--reel-fg": [text_c, "most used text colour"],
        "--reel-accent": [accent, "most used saturated colour on buttons and links"] if accent else [None, "no saturated colour found: ask"],
        "--reel-on-accent": on_accent,
        "--reel-muted": [muted, "most used neutral text after the main text colour"] if muted else [None, "none found"],
        "--reel-surface": [surface, "a background close to the main one"] if surface else [None, "none found"],
        "--reel-font-display": [display.get("fontFamily") if display else None, f"display text ({display.get('fontSize')} / {display.get('fontWeight')})" if display else "none found"],
        "--reel-weight-display": [display.get("fontWeight") if display else None, "display text"],
        "--reel-font-body": [body.get("fontFamily") if body else None, "body text"],
        "--reel-weight-body": [body.get("fontWeight") if body else None, "body text"],
        "--reel-radius": [radius, "the accent button's corner radius"] if radius else [None, "none found"],
    }
    conflicts, kit_src = [], None
    if a.kit:
        kv, kit_src = kit_values(Path(a.kit).expanduser())
        for k, (v, _) in proposal.items():
            name = k.replace("--reel-", "")
            if v and name in kv:
                kvv = kv[name].strip().strip('"')
                if name.startswith("font-"):
                    differs = v.lower() not in kvv.lower()
                else:
                    differs = kvv.lower() != str(v).lower()
                if differs:
                    conflicts.append((k, v, kv[name].strip()))

    L = [f"# Brand sheet: {tok.get('title', url)}", "",
         f"Captured from {('https://' + url) if url and not url.startswith('http') else url} with `hyperframes capture` (vision off). "
         "A website shows how a brand is used, not its rules: everything below is **proposed** until the brand owner confirms it.", "",
         "## Overview", "", tok.get("description", "(no description)"), "",
         "## Colours", "", "| Hex | Text uses | Backgrounds | Buttons | Proposed role |", "|---|---|---|---|---|"]
    roles = {v[0].upper(): k.replace("--reel-", "") for k, v in proposal.items() if v[0] and str(v[0]).startswith("#")}
    for s in stats[:12]:
        L.append(f"| `{s['hex']}` | {s.get('textCount', 0)} | {s.get('bgCount', 0)} | {s.get('interactiveBg', 0)} | {roles.get(s['hex'].upper(), '')} |")
    if accent:
        L += ["", f"Contrast: text on background {contrast(text_c, bg):.1f}:1; {proposal['--reel-on-accent'][0]} on the accent {contrast(proposal['--reel-on-accent'][0], accent):.1f}:1."]
    cv = tok.get("cssVariables", {})
    if cv:
        L += ["", "Colour variables the site defines: " + ", ".join(f"`{k}: {v}`" for k, v in cv.items() if re.match(r"#[0-9a-fA-F]{3,8}$", str(v).strip()))[:900]]
    L += ["", "## Typography", "", "| Role | Face | Size | Weight | Sample |", "|---|---|---|---|---|"]
    for t in ds.get("typography", []):
        L.append(f"| {t['role']} | {t.get('fontFamily')} | {t.get('fontSize')} | {t.get('fontWeight')} | {str(t.get('sampleText', ''))[:48]} |")
    L += ["", f"Font files captured: {', '.join(captured_faces) or 'none'}. Web font files are not a licence: confirm the faces and "
          "their licences with the brand owner, or use a clearly marked free substitute."]
    L += ["", "## Shape", "", f"Radii: {', '.join(ds.get('radius', [])) or 'none'}. Shadows: "
          + ("; ".join(f"`{s['value']}` x{s['count']}" for s in ds.get("shadows", [])[:3]) or "none") + "."]
    L += ["", "## Components", "", "| Button | Background | Text | Radius | Weight |", "|---|---|---|---|---|"]
    for b in buttons[:6]:
        L.append(f"| {b.get('label', '')[:30]} | `{b.get('background')}` | `{b.get('color')}` | {b.get('borderRadius')} | {b.get('fontWeight')} |")
    L += ["", "## Logo candidates", "", ("Files capture marked as likely logos (look at each before use; never redraw a logo): "
          + ", ".join(f"`assets/{n}`" for n in logos)) if logos else "No logo candidates: ask for the official files."]
    s = an.get("summary", {})
    L += ["", "## Motion on the site", "", f"{s.get('cssDeclarations', 0)} CSS animation declarations, {s.get('webAnimations', 0)} running animations, "
          f"{s.get('scrollTargets', 0)} scroll-triggered elements. Named: {', '.join(an.get('namedAnimations', [])) or 'none'}. "
          "A site's UI motion rarely is the brand's video motion: propose directions in onboarding."]
    if a.kit:
        L += ["", "## Conflicts with the brand kit", ""]
        if not kit_src:
            L.append("The kit has no video pack yet, so nothing to compare.")
        elif conflicts:
            L += [f"The kit's video pack (`{kit_src}`) says otherwise for these; the kit wins unless the brand owner says the site is newer:", "",
                  "| Token | Website | Kit |", "|---|---|---|"] + [f"| `{k}` | {v} | {kv} |" for k, v, kv in conflicts]
        else:
            L.append(f"None: the website agrees with `{kit_src}` on every value both define.")
    L += ["", "## To confirm (a website cannot tell)", "",
          "- The rules: what the brand never does, what it may claim, tone of voice.",
          "- The signature motif (the brand's most reduced shape or line) and the motion feel (calm, steady, punchy).",
          "- Official logo files per background, and font files with licences.", ""]
    Path(a.out).write_text("\n".join(L))
    if a.json:
        Path(a.json).write_text(json.dumps({"source": url, "proposed": {k: {"value": v, "from": why} for k, (v, why) in proposal.items()},
                                            "conflicts": [{"token": k, "website": v, "kit": kv} for k, v, kv in conflicts],
                                            "logo_candidates": logos, "captured_fonts": captured_faces}, indent=1))
    print(f"brandsheet: wrote {a.out}" + (f" and {a.json}" if a.json else "") + f" (accent {accent}, display {proposal['--reel-font-display'][0]}"
          + (f", {len(conflicts)} conflict(s) with the kit" if a.kit else "") + ")")


if __name__ == "__main__":
    main()
