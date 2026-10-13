#!/usr/bin/env python3
"""Placeholder for the T-EXPAND line collector.

Real implementation lands after the raw payload samples from capture_samples.py /
capture_browser_samples.py have been reviewed against their sources. Until then this
exits 0 without writing data, so a capture-only run never publishes an empty dataset.
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-out", default="data/expanded/lines.json")
    args = ap.parse_args()
    print("collect_lines.py: no parser implemented yet — nothing written to "
          f"{args.capture_out} (capture-only run).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
