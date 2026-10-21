#!/usr/bin/env python3
"""Run the repository tests known to drift with stale boards and record their status.

Writes data/82e71372/ci-status.json, which audit.py merges into its CI section. This script
only records what happened; it never edits the tests or the boards they check.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "82e71372"

KNOWN = [
    "tests.test_e1b48771.Coverage.test_exactly_the_open_hotspawn_fixtures_and_nothing_else",
    "tests.test_verify_7cd2e67a.PublishedArithmetic.test_live_board_picks_and_edges_reproduce",
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for dotted in KNOWN:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", dotted],
            cwd=ROOT, capture_output=True, text=True, timeout=300)
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-8:]
        results.append({"test": dotted, "passed": proc.returncode == 0,
                        "returncode": proc.returncode, "tail": tail})
    doc = {"checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "known_red_tests": [r["test"] for r in results if not r["passed"]],
           "all_known_green": all(r["passed"] for r in results),
           "results": results,
           "note": ("pickaudit only observes these tests; their boards belong to other scopes. "
                    "An empty known_red_tests list means the drift has been fixed upstream.")}
    (OUT / "ci-status.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("checked_utc", "known_red_tests", "all_known_green")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
