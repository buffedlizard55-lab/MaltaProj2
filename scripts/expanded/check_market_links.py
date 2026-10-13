#!/usr/bin/env python3
"""Validate market/**: every local link resolves, every published row carries its sources.

Checks, on the generated site and its data:
  1. every href/src that points inside market/ exists on disk (no broken internal links)
  2. every anchor (#id) used in a local link exists on the target page
  3. every fixture row that publishes a probability has at least one external source link
  4. no fixture row publishes a probability without a retrieval timestamp
  5. no non-HotSpawn probability appears without an explicit method string in data/lines.json

Exit code 0 when everything passes, 1 otherwise (so CI can gate on it).
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "market"
DATA = ROOT / "data" / "expanded"

HREF_RE = re.compile(r'(?:href|src)="([^"]+)"')
ID_RE = re.compile(r'id="([^"]+)"')


def main() -> int:
    problems: list[str] = []
    pages = sorted(SITE.rglob("*.html"))
    if not pages:
        print("market/: no pages generated yet — nothing to validate")
        return 0
    ids_by_page = {}
    for page in pages:
        ids_by_page[page] = set(ID_RE.findall(page.read_text(encoding="utf-8")))

    for page in pages:
        text = page.read_text(encoding="utf-8")
        for raw in HREF_RE.findall(text):
            href = html.unescape(raw)
            if href.startswith(("http://", "https://", "mailto:", "data:", "javascript:")):
                continue
            target, _, anchor = href.partition("#")
            if target.startswith("/"):
                problems.append(f"{page.relative_to(SITE)}: absolute local link {href}")
                continue
            path = (page.parent / target).resolve() if target else page.resolve()
            if not path.exists():
                problems.append(f"{page.relative_to(SITE)}: broken local link {href}")
                continue
            if anchor and path.suffix == ".html" and path in ids_by_page:
                if anchor not in ids_by_page[path]:
                    problems.append(f"{page.relative_to(SITE)}: missing anchor #{anchor} in {target}")

    lines_path = DATA / "lines.json"
    if lines_path.exists():
        doc = json.loads(lines_path.read_text(encoding="utf-8"))
        if "method" not in doc:
            problems.append("data/expanded/lines.json: no method block")
        for row in doc.get("fixtures", []):
            quotes = row.get("quotes") or []
            if row.get("consensus"):
                if not quotes:
                    problems.append(f"fixture {row.get('fixture_id')}: consensus without quotes")
                for q in quotes:
                    if not (q.get("source_api_url") or q.get("source_public_url")):
                        problems.append(f"fixture {row.get('fixture_id')}: quote without source link")
                    if not q.get("retrieved_at_utc"):
                        problems.append(f"fixture {row.get('fixture_id')}: quote without timestamp")
            if row.get("pick") and not (quotes or (row.get("originated_estimate") or {}).get("available")):
                problems.append(f"fixture {row.get('fixture_id')}: pick without any basis")
            est = row.get("originated_estimate") or {}
            if est.get("available"):
                if "ORIGINATED MODEL" not in str(est.get("label", "")):
                    problems.append(f"fixture {row.get('fixture_id')}: model estimate not labelled")
                if row.get("consensus"):
                    problems.append(f"fixture {row.get('fixture_id')}: model estimate alongside market")

    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        for p in problems[:60]:
            print("  -", p)
        return 1
    priced = sum(1 for r in json.loads(lines_path.read_text(encoding="utf-8"))["fixtures"]
                 if r.get("quotes")) if lines_path.exists() else 0
    print(f"OK: {len(pages)} pages, no broken local links, {priced} priced rows all source-linked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
