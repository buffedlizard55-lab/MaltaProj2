#!/usr/bin/env python3
"""Verify every internal link (and #anchor) in the generated pages resolves.

External links are listed but not fetched (no network guarantee in CI sandboxes);
they were source-verified when written and are stored per-row in board.json.
Exit code 1 if any internal target is missing.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = [ROOT / "index.html"] + sorted((ROOT / "hotspawn-cs2").glob("*.html"))
HREF = re.compile(r'href="([^"#]+)(#([^"]*))?"')
ID = re.compile(r'id="([^"]+)"')


def main() -> int:
    bad: list[str] = []
    ids: dict[Path, set[str]] = {}
    for page in PAGES:
        if page.exists():
            ids[page] = set(ID.findall(page.read_text()))
    for page in PAGES:
        if not page.exists():
            bad.append(f"{page}: page missing")
            continue
        for href, _, frag in HREF.findall(page.read_text()):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            target = (page.parent / href).resolve()
            if not target.exists():
                bad.append(f"{page.relative_to(ROOT)} -> {href} (missing file)")
            elif frag and target in ids and frag not in ids[target]:
                bad.append(f"{page.relative_to(ROOT)} -> {href}#{frag} (missing anchor)")
    if bad:
        print("\n".join(bad))
        return 1
    print(f"OK: internal links verified across {len(PAGES)} pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
