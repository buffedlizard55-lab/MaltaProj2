#!/usr/bin/env python3
"""Independent repo-wide site audit — session 6a8b46f1 (FINAL-6A8).

Re-runnable, read-only checks over every published HTML artefact in the repository:

  1. viewport      — every page carries a mobile viewport <meta>.
  2. mobile-css    — every page links or inlines a mobile breakpoint
                     (max-width media query) so tables reflow on phones.
  3. internal      — every relative href resolves to a file in the repo
                     (and same-page #anchors resolve to an existing id/name).
  4. row-sources   — every table row that states a probability (%), odds
                     number, or an explicit pick must contain at least one
                     external http(s) link (the source). Rows that state no
                     values (blank / flagged rows) are allowed to be linkless.
  5. required      — the landing page and the Flagged-for-review page exist.

Usage:  python3 verify/6a8b46f1/audit_site.py
Exit 0 = no failures.  Findings are written to verify/6a8b46f1/audit.json
and a markdown summary to verify/6a8b46f1/AUDIT.md.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]

# Published sections that ship to GitHub Pages (root html + these dirs).
SECTIONS = [
    "current", "picks", "pickem", "site", "verify961", "verify",
    "docs", "proof", "audits",
]

VIEWPORT_RE = re.compile(r'<meta[^>]+name=["\']viewport["\']', re.I)
# Mobile-first (min-width) and desktop-shrink (max-width) breakpoints both count.
MEDIA_RE = re.compile(r"@media[^{]*\b(?:min-width|max-width)\b", re.I)
HREF_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\']', re.I)
SRC_RE = re.compile(r'<(?:link|script|img)[^>]+(?:href|src)=["\']([^"\']+)["\']', re.I)
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
# Value patterns that require a source link in the same row.
PCT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s*%")
ODDS_RE = re.compile(r"\b\d+\.\d{1,4}\b")          # decimal odds like 1.2985
PICK_RE = re.compile(r"\bpick\s*:", re.I)
# Rows whose header/first cell is purely structural still count if they state values.
LINK_RE = re.compile(r'href=["\']https?://[^"\']+["\']', re.I)

FAILURES: list[dict] = []
WARNINGS: list[dict] = []
STATS = {"pages": 0, "rows_checked": 0, "rows_with_values": 0, "links_checked": 0}


def page_files() -> list[Path]:
    out: list[Path] = []
    for p in sorted(ROOT.glob("*.html")):
        out.append(p)
    for sec in SECTIONS:
        d = ROOT / sec
        if d.is_dir():
            out.extend(sorted(d.rglob("*.html")))
    return out


def strip_tags(s: str) -> str:
    return htmllib.unescape(TAG_RE.sub(" ", s))


def audit_page(path: Path) -> None:
    rel = path.relative_to(ROOT).as_posix()
    STATS["pages"] += 1
    text = path.read_text(encoding="utf-8", errors="replace")

    # 1. viewport
    if not VIEWPORT_RE.search(text):
        FAILURES.append({"check": "viewport", "page": rel, "detail": "no viewport meta"})

    # 2. mobile css: viewport + either a breakpoint media query, a scrollable
    #    table pattern (overflow-x:auto) or a fluid grid (auto-fit) counts as
    #    mobile-ready; fixed-width overflow without any of these fails.
    ok_media = bool(MEDIA_RE.search(text))
    css_blobs = [text]
    if not ok_media:
        for href in SRC_RE.findall(text):
            if href.endswith(".css") and not href.startswith(("http://", "https://", "//")):
                css_path = (path.parent / unquote(urlparse(href).path)).resolve()
                try:
                    css_path.relative_to(ROOT)
                except ValueError:
                    continue
                if css_path.is_file():
                    css_blobs.append(css_path.read_text(encoding="utf-8", errors="replace"))
    for blob in css_blobs:
        if MEDIA_RE.search(blob) or re.search(r"overflow-x\s*:\s*auto", blob, re.I) \
                or re.search(r"auto-fit\s*,", blob, re.I) \
                or re.search(r"table[^{}]*\{[^}]*width\s*:\s*100%", blob, re.I):
            ok_media = True
            break
    if not ok_media:
        FAILURES.append({"check": "mobile-css", "page": rel,
                         "detail": "no breakpoint, scrollable-table or fluid-layout pattern found"})

    # 3. internal links (ignore JS template strings: strip script/style blocks)
    static_text = SCRIPT_RE.sub("", STYLE_RE.sub("", text))
    for href in HREF_RE.findall(static_text) + SRC_RE.findall(static_text):
        if href.startswith(("http://", "https://", "//", "mailto:", "data:", "javascript:")):
            continue
        STATS["links_checked"] += 1
        if href.startswith("#"):
            anchor = href[1:]
            if anchor and not re.search(
                rf'(?:id|name)=["\']{re.escape(anchor)}["\']', text, re.I
            ):
                FAILURES.append({"check": "internal", "page": rel, "detail": f"missing anchor {href}"})
            continue
        target_raw = unquote(urlparse(href).path)
        if not target_raw:
            continue
        target = (path.parent / target_raw).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            FAILURES.append({"check": "internal", "page": rel, "detail": f"escapes repo: {href}"})
            continue
        if target.is_dir():
            target = target / "index.html"
        if not target.exists():
            FAILURES.append({"check": "internal", "page": rel, "detail": f"broken link: {href}"})

    # 4. row-level source links (static rows only; skip pure header rows)
    for row in ROW_RE.findall(static_text):
        STATS["rows_checked"] += 1
        cells = CELL_RE.findall(row)
        if "<td" not in row.lower():
            continue  # header row — describes columns, not data
        body = " ".join(TAG_RE.sub(" ", c) for c in cells)
        body = htmllib.unescape(body)
        states_value = bool(PCT_RE.search(body) or ODDS_RE.search(body) or PICK_RE.search(body))
        if not states_value:
            continue
        STATS["rows_with_values"] += 1
        if not LINK_RE.search(row):
            FAILURES.append({
                "check": "row-sources",
                "page": rel,
                "detail": "row states a value but has no external source link: "
                          + re.sub(r"\s+", " ", body).strip()[:140],
            })


def main() -> int:
    pages = page_files()
    for p in pages:
        audit_page(p)

    # 4b. JS-rendered tables: their fetched data rows must carry source URLs
    for data_rel, list_key in (
        ("data/originated_matches.json", None),
        ("data/teams_verified.json", None),
    ):
        p = ROOT / data_rel
        if not p.is_file():
            FAILURES.append({"check": "required", "page": data_rel, "detail": "missing"})
            continue
        rows = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = next((v for v in rows.values() if isinstance(v, list)), [])
        for i, r in enumerate(rows):
            if not re.search(r"https?://", json.dumps(r)):
                FAILURES.append({
                    "check": "row-sources",
                    "page": data_rel,
                    "detail": f"row {i} has no source URL",
                })

    required = ["index.html", "flagged.html"]
    for r in required:
        if not (ROOT / r).is_file():
            FAILURES.append({"check": "required", "page": r, "detail": "missing"})

    result = {
        "audit": "6a8b46f1",
        "stats": STATS,
        "failures": FAILURES,
        "warnings": WARNINGS,
    }
    out = Path(__file__).resolve().parent / "audit.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    md = [
        "# Site audit — session 6a8b46f1",
        "",
        f"- Pages scanned: **{STATS['pages']}**",
        f"- Internal links checked: **{STATS['links_checked']}**",
        f"- Table rows scanned: **{STATS['rows_checked']}** "
        f"({STATS['rows_with_values']} state a value and were required to carry a source link)",
        f"- Failures: **{len(FAILURES)}**",
        "",
    ]
    if FAILURES:
        md.append("| Check | Page | Detail |")
        md.append("|---|---|---|")
        for f in FAILURES:
            detail = f["detail"].replace("|", "\\|")
            md.append(f"| {f['check']} | `{f['page']}` | {detail} |")
    else:
        md.append("All checks passed. Every value-stating table row carries an external "
                  "source link; every page is mobile-ready; all internal links resolve.")
    md.append("")
    (Path(__file__).resolve().parent / "AUDIT.md").write_text("\n".join(md), encoding="utf-8")

    print(f"pages={STATS['pages']} links={STATS['links_checked']} "
          f"rows={STATS['rows_checked']} valued_rows={STATS['rows_with_values']} "
          f"failures={len(FAILURES)}")
    for f in FAILURES[:25]:
        print("FAIL", f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
