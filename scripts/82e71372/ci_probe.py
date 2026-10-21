#!/usr/bin/env python3
"""Observe repository test health and record it for the audit.

Runs the full unittest discovery inside a throwaway git worktree checked out at the
current HEAD, plus a watch-list of drift-prone individual tests, and writes
data/82e71372/ci-status.json. The worktree isolation matters: other desks' tests
rebuild their own HTML/data on import, and those regenerations must never touch the
auditing desk's working tree or end up in its commits. This script only records what
happened; it never edits the tests, the boards they check, or other sessions' files.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "82e71372"

WATCHLIST = [
    "tests.test_e1b48771.Coverage.test_exactly_the_open_hotspawn_fixtures_and_nothing_else",
    "tests.test_verify_7cd2e67a.PublishedArithmetic.test_live_board_picks_and_edges_reproduce",
]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          timeout=120, check=True)


def run_suite(cwd, *targets):
    proc = subprocess.run([sys.executable, "-m", "unittest", *targets],
                          cwd=cwd, capture_output=True, text=True, timeout=1800)
    out = (proc.stderr or "") + (proc.stdout or "")
    ran = re.search(r"Ran (\d+) tests?", out)
    # unittest prints "FAIL: <method> (<full dotted id>)" in this repo's runner;
    # prefer the parenthesised full id when present, fall back to the bare method.
    reds = sorted({
        (full or method)
        for method, full in re.findall(
            r"^(?:FAIL|ERROR):\s*(\S+)(?:\s*\(([^)]+)\))?\s*$", out, re.MULTILINE)
    })
    return proc.returncode, int(ran.group(1)) if ran else None, reds, out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    head = git("rev-parse", "HEAD").stdout.strip()
    tmp = Path(tempfile.mkdtemp(prefix="pickaudit-ci-"))
    wt = tmp / "wt"
    try:
        git("worktree", "add", "--quiet", "--detach", str(wt), head)
        rc, ran, reds, _ = run_suite(wt, "discover", "-s", "tests")
        watched = []
        for dotted in WATCHLIST:
            wrc, _, _, wout = run_suite(wt, dotted)
            watched.append({
                "test": dotted,
                "passed": wrc == 0,
                "returncode": wrc,
                "tail": wout.strip().splitlines()[-8:],
            })
    finally:
        git("worktree", "remove", "--force", str(wt))
        shutil.rmtree(tmp, ignore_errors=True)

    doc = {
        "checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "probe_head": head,
        "full_suite": {
            "ran": ran,
            "passed": rc == 0,
            "failures_and_errors": reds,
        },
        "watchlist": watched,
        # audit.py reads this key: every currently-red test name, whoever owns it
        "known_red_tests": reds,
        "all_known_green": rc == 0,
        "note": ("pickaudit only observes the suite inside a detached worktree at HEAD; "
                 "red tests belong to their owning scopes and are never patched here. "
                 "An empty known_red_tests list means the full suite is green at probe_head."),
    }
    (OUT / "ci-status.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps({"checked_utc": doc["checked_utc"], "probe_head": head[:10],
                      "ran": ran, "red": reds,
                      "watchlist_green": [w["test"].split(".")[-1]
                                          for w in watched if w["passed"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
