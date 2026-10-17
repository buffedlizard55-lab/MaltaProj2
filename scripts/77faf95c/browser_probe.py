#!/usr/bin/env python3
"""Report what a GitHub-hosted runner offers the repository's Playwright smoke tests.

Written because the shared ``Browser smoke tests`` step in ``.github/workflows/pages.yml`` went
from success to failure on the *unchanged* commit ``36c18d08`` between 00:15:51Z and 00:19:36Z on
2026-10-17, which rules out a code regression and points at the runner environment. The Actions
log blob host is not reachable from the agent sandbox, so this script writes its findings to a
file in the repository instead of to stdout.

It only observes. It changes nothing on the runner and it is not a dependency of any page.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CANDIDATES = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    out = root / "data" / "77faf95c" / "browser_diagnosis.txt"
    lines = []
    lines.append("diagnosed_utc: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    lines.append("python: %s" % sys.version.split()[0])
    lines.append("platform: %s" % platform.platform())
    lines.append("ImageOS: %s" % os.environ.get("ImageOS", "<unset>"))
    lines.append("CHROME_BIN: %s" % os.environ.get("CHROME_BIN", "<unset>"))

    lines.append("--- candidate browser binaries ---")
    for c in CANDIDATES:
        if os.path.exists(c):
            try:
                ver = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=30)
                lines.append("PRESENT %s -> %s" % (c, (ver.stdout or ver.stderr).strip()[:120]))
            except Exception as exc:  # noqa: BLE001 - a probe must report, not raise
                lines.append("PRESENT %s -> version probe failed: %s" % (c, type(exc).__name__))
        else:
            lines.append("MISSING %s" % c)
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        lines.append("which %s: %s" % (name, found or "<not on PATH>"))

    lines.append("--- playwright browser cache ---")
    cache = Path.home() / ".cache" / "ms-playwright"
    if cache.exists():
        lines.extend("  %s" % p.name for p in sorted(cache.iterdir()))
    else:
        lines.append("  none (%s does not exist)" % cache)

    lines.append("--- pip playwright ---")
    try:
        import playwright
        from playwright.sync_api import sync_playwright

        lines.append("playwright %s imported" % getattr(playwright, "__version__", "?"))
    except Exception as exc:  # noqa: BLE001
        lines.append("playwright import FAILED: %s: %s" % (type(exc).__name__, exc))
        sync_playwright = None  # type: ignore[assignment]
    if sync_playwright is not None:
        lines.append("--- launch attempts ---")
        attempts = [("bundled chromium (no executable_path)", None)]
        for c in CANDIDATES:
            if os.path.exists(c):
                attempts.append(("explicit %s" % c, c))
        for label, path in attempts:
            try:
                with sync_playwright() as p:
                    kw = {"headless": True, "args": ["--no-sandbox"]}
                    if path:
                        kw["executable_path"] = path
                    browser = p.chromium.launch(**kw)
                    lines.append("OK   %s -> %s" % (label, browser.version))
                    browser.close()
            except Exception as exc:  # noqa: BLE001
                lines.append("FAIL %s -> %s: %s" % (label, type(exc).__name__, str(exc)[:300]))

    text = "\n".join(lines) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
