#!/usr/bin/env python3
"""Minimal placeholder site builder (replaced by the full generator in this session)."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "data", "hotspawn_matches.json"), encoding="utf-8") as fh:
    data = json.load(fh)
print("matches available for site build:", data.get("match_count"))
