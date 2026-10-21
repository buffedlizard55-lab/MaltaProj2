#!/usr/bin/env python3
"""Keep one compact verification-desk card on the shared root page fresh.

Only the text between ``<!-- bce97e13:start -->`` and ``<!-- bce97e13:end -->`` is touched. The
block is inserted directly after the everypick start-here block (or after the ``<main>`` marker as a
fallback) so other sessions' root blocks and generated sections are never modified.
"""
from __future__ import annotations

import importlib.util as _iu
import re
import sys
from pathlib import Path

_spec = _iu.spec_from_file_location("bce97e13_core", Path(__file__).resolve().parent / "core.py")
core = _iu.module_from_spec(_spec)
sys.modules["bce97e13_core"] = core
_spec.loader.exec_module(core)

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "index.html"
START, END = "<!-- bce97e13:start -->", "<!-- bce97e13:end -->"
EVERYPICK_END = "<!-- everypick:end -->"
MAIN_MARKER = '<main class="wrap" id="main-content" tabindex="-1">'


def block() -> str:
    """Render via the shared build_site hook so the markup has one source of truth."""
    build_site = ROOT / "scripts" / "build_site.py"
    if not build_site.exists():
        return ""
    spec = _iu.spec_from_file_location("build_site_bce97e13", build_site)
    module = _iu.module_from_spec(spec)
    spec.loader.exec_module(module)  # module-level only: main() is not called on import
    return module.bce97e13_hero_html().strip()


def main() -> int:
    if not INDEX.exists():
        print("index.html missing - nothing to stage")
        return 0
    text = INDEX.read_text(encoding="utf-8")
    rendered = block()
    if not rendered:
        print("no verified board yet - leaving index.html untouched")
        return 0
    if START in text and END in text:
        text = re.sub(rf"{re.escape(START)}.*?{re.escape(END)}", rendered, text, flags=re.S)
    elif EVERYPICK_END in text:
        text = text.replace(EVERYPICK_END, EVERYPICK_END + "\n\n" + rendered, 1)
    elif MAIN_MARKER in text:
        text = text.replace(MAIN_MARKER, MAIN_MARKER + "\n  " + rendered, 1)
    else:
        print("unexpected root layout - leaving index.html untouched")
        return 0
    INDEX.write_text(text, encoding="utf-8")
    print("root verification-desk block updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
