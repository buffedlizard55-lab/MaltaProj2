#!/usr/bin/env python3
"""Keep the shared root landing page's start-here block fresh without rewriting other desks.

`scripts/build_site.py` (owned by the integration step) publishes the block with
`<!-- everypick:start -->` / `<!-- everypick:end -->` markers. This script re-renders just that
block from the current board, or inserts it at the top of `<main>` when it is missing, so the
four-hour refresh can update the numbers on the front door without touching any other page.
"""
from __future__ import annotations

import importlib.util as iu
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "index.html"
BUILD_SITE = ROOT / "scripts" / "build_site.py"
START, END = "<!-- everypick:start -->", "<!-- everypick:end -->"


def hero() -> str:
    spec = iu.spec_from_file_location("build_site_for_hero", BUILD_SITE)
    module = iu.module_from_spec(spec)
    spec.loader.exec_module(module)  # module-level only: main() is not called on import
    return module.everypick_hero_html().strip()


def main() -> int:
    if not INDEX.exists():
        print("index.html missing - nothing to stage")
        return 0
    text = INDEX.read_text(encoding="utf-8")
    block = hero()
    if not block:
        print("no every-match board yet - leaving index.html untouched")
        return 0
    if START in text and END in text:
        text = re.sub(rf"{re.escape(START)}.*?{re.escape(END)}", block, text, flags=re.S)
    else:
        marker = '<main class="wrap" id="main-content" tabindex="-1">'
        if marker not in text:
            print("unexpected layout - leaving index.html untouched")
            return 0
        text = text.replace(marker, marker + "\n  " + block, 1)
    INDEX.write_text(text, encoding="utf-8")
    print("root start-here block updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
