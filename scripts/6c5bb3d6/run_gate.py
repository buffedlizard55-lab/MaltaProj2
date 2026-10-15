#!/usr/bin/env python3
"""Run the repository's shared publication gate and record the result as evidence.

The Pages workflow (`.github/workflows/pages.yml`) gates deployment on
`python -m unittest discover -s tests`, so a red module anywhere in the repository stops the
site from publishing for every session. This script runs that same command and writes the
outcome to data/6c5bb3d6/gate.json, which check C11 of the audit reports.

Session 6c5bb3d6 scope: writes only data/6c5bb3d6/gate.json.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "6c5bb3d6", "gate.json")
COMMAND = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]


def main() -> int:
    proc = subprocess.run(COMMAND, cwd=ROOT, capture_output=True, text=True)
    out = proc.stdout + "\n" + proc.stderr
    failing = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\S+)", out, re.M)))
    counts = {}
    m = re.search(r"^Ran (\d+) tests", out, re.M)
    counts["ran"] = int(m.group(1)) if m else None
    m = re.search(r"^OK(?: \(skipped=(\d+)\))?", out, re.M)
    counts["ok"] = bool(m)
    counts["skipped"] = int(m.group(1)) if m and m.group(1) else 0
    m = re.search(r"failures=(\d+)", out)
    counts["failures"] = int(m.group(1)) if m else 0
    m = re.search(r"errors=(\d+)", out)
    counts["errors"] = int(m.group(1)) if m else 0
    record = {
        "session": "6c5bb3d6",
        "ran_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": " ".join(os.path.relpath(c, ROOT) if c.endswith(".py") else c for c in COMMAND),
        "gate": "the first and sixth steps of .github/workflows/pages.yml (deployment gate)",
        "returncode": proc.returncode,
        "green": proc.returncode == 0,
        "failing_tests": failing,
        "counts": counts,
        "tail": out.strip().splitlines()[-12:],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1)
    print(f"publication gate: {'GREEN' if record['green'] else 'RED'} "
          f"({counts.get('ran')} tests, {counts.get('failures')} failures, {counts.get('errors')} errors)")
    for name in failing[:10]:
        print(f"  red: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
