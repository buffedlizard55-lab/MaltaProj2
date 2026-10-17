#!/usr/bin/env python3
"""Run the repository's shared browser-smoke scripts and write the output into the repository.

Why this exists: the ``Browser smoke tests`` step of ``.github/workflows/pages.yml`` started
failing on the *unchanged* commit ``36c18d08`` between 2026-10-17 00:15:51Z and 00:19:36Z. The
failure therefore is not a code regression, but nobody could read the log: the Actions log blob
host is not reachable from the agent sandbox, and ``gh run view --log-failed`` returns EOF.

This script reproduces that step on a GitHub-hosted runner and writes every script's exit code,
stdout and stderr to ``data/77faf95c/smoke_probe.txt``, which the workflow commits so the result
can be read straight out of the repository. It only observes: it does not modify any page, and
it edits no file outside ``data/77faf95c/``.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SMOKE_SCRIPTS = [
    "scripts/browser_smoke.py",
    "scripts/build_site.py",
    "scripts/browser_current_smoke.py",
    "scripts/browser_479ef53e.py",
    "scripts/ae75c5c3/browser_smoke.py",
    "scripts/c64a5e19/browser_smoke.py",
    "scripts/browser_778756a1.py",
    "scripts/69e4c06a/browser_smoke.py",
]


def main() -> int:
    out = ROOT / "data" / "77faf95c" / "smoke_probe.txt"
    lines = ["probe_utc: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "python: %s" % sys.version.split()[0], ""]
    for rel in SMOKE_SCRIPTS:
        lines.append("=" * 70)
        lines.append("RUN %s" % rel)
        if not (ROOT / rel).exists():
            lines.append("  SKIPPED (file not present in this checkout)")
            continue
        try:
            proc = subprocess.run([sys.executable, rel], cwd=str(ROOT),
                                  capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            lines.append("  TIMEOUT after 900s")
            continue
        except Exception as exc:  # noqa: BLE001 - a probe reports, it does not raise
            lines.append("  RAISED %s: %s" % (type(exc).__name__, exc))
            continue
        lines.append("  exit=%s" % proc.returncode)
        if proc.stdout.strip():
            lines.append("  --- stdout (tail) ---")
            lines.extend("  " + x for x in proc.stdout.strip().splitlines()[-40:])
        if proc.stderr.strip():
            lines.append("  --- stderr (tail) ---")
            lines.extend("  " + x for x in proc.stderr.strip().splitlines()[-40:])
        lines.append("")
    text = "\n".join(lines) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
