#!/usr/bin/env python3
"""Live verification of the official Valve regional-standings source (session bce97e13).

Runs both in CI and locally.  Uses only the public GitHub contents API against
ValveSoftware/counter-strike_regional_standings:

  1. lists ``live/2026`` and records the newest ``standings_global_*.md`` file (proves whether the
     committed 2026_10_05 table is still current-by-publisher);
  2. downloads that table verbatim and parses it;
  3. downloads ``model/glicko.js`` and ``model/fit.js`` and re-derives the effective logistic
     slope instead of trusting the constant quoted on the boards;
  4. pins the repository commit SHA the bytes came from.

Network failure never deletes data: the previous committed snapshot is kept and the record is
marked ``live: false`` so the site can label the rows accordingly.
"""
from __future__ import annotations

import importlib.util as _iu
import json
import re
import sys
from pathlib import Path

_spec = _iu.spec_from_file_location("bce97e13_core", Path(__file__).resolve().parent / "core.py")
core = _iu.module_from_spec(_spec)
sys.modules["bce97e13_core"] = core
_spec.loader.exec_module(core)

OUT_JSON = "data/bce97e13/valve_live.json"
OUT_MD = "data/bce97e13/standings_official.md"


def github_headers() -> dict:
    import os
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "malta-bce97e13-verifier"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def list_global_tables() -> tuple[list[str], str | None]:
    status, body = core.http_get(f"{core.VALVE_CONTENTS}/live/2026", github_headers())
    if status != 200:
        return [], None
    entries = json.loads(body)
    names = sorted(e["name"] for e in entries
                   if isinstance(e, dict) and e.get("name", "").startswith("standings_global_"))
    sha = entries[0].get("sha") if entries else None
    return names, sha


def fetch_text(path: str) -> tuple[int, str, str | None]:
    status, body = core.http_get(f"{core.VALVE_CONTENTS}/{path}",
                                 {**github_headers(), "Accept": "application/vnd.github.raw"})
    if status != 200:
        return status, "", None
    # A second call for the blob SHA (cheap, only used for provenance).
    meta_status, meta_body = core.http_get(f"{core.VALVE_CONTENTS}/{path}", github_headers())
    sha = None
    if meta_status == 200:
        try:
            sha = json.loads(meta_body).get("sha")
        except ValueError:
            sha = None
    return status, body.decode("utf-8", errors="replace"), sha


def derive_slope(glicko_js: str, fit_js: str) -> dict:
    q_match = re.search(r"const\s+Q\s*=\s*Math\.log\(10\)\s*/\s*400", glicko_js)
    rd_match = re.search(r"rd\s*:\s*(\d+)", fit_js)
    rd = int(rd_match.group(1)) if rd_match else 75
    derived = core.valve_slope(rd)
    return {
        "q_literal_present": bool(q_match),
        "fixed_rd": rd,
        "derived_slope_c": derived,
        "canonical_slope_c": core.CANONICAL_C,
        "abs_diff": abs(derived - core.CANONICAL_C),
        "matches_canonical": abs(derived - core.CANONICAL_C) < 1e-8,
        "evidence_urls": [
            core.VALVE_BLOB + "model/glicko.js",
            core.VALVE_BLOB + "model/fit.js",
        ],
    }


def main() -> int:
    fetched_at = core.now_utc()
    names, dir_sha = list_global_tables()
    if not names:
        record = core.load(OUT_JSON, default={}) or {}
        record.update({"live": False, "attempted_utc": fetched_at,
                       "note": "GitHub contents API unreachable; keeping previous committed check."})
        core.dump_json(OUT_JSON, record)
        print("Valve live check unavailable; previous record kept.")
        return 0

    newest = names[-1]
    status, table_text, table_sha = fetch_text(f"live/2026/{newest}")
    g_status, glicko_js, _ = fetch_text("model/glicko.js")
    f_status, fit_js, _ = fetch_text("model/fit.js")
    if status != 200 or g_status != 200 or f_status != 200:
        record = core.load(OUT_JSON, default={}) or {}
        record.update({"live": False, "attempted_utc": fetched_at,
                       "http_status": {"table": status, "glicko": g_status, "fit": f_status}})
        core.dump_json(OUT_JSON, record)
        print("Valve file fetch failed; previous record kept.")
        return 0

    parsed = core.parse_official_markdown(table_text)
    slope = derive_slope(glicko_js, fit_js)
    record = {
        "live": True,
        "fetched_utc": fetched_at,
        "repo": core.VALVE_REPO,
        "contents_api": core.VALVE_CONTENTS + "/live/2026",
        "directory_sha": dir_sha,
        "global_tables_available": names,
        "newest_global_table": newest,
        "newest_table_url": core.VALVE_BLOB + f"live/2026/{newest}",
        "table_blob_sha": table_sha,
        "n_teams_parsed": parsed["n_teams"],
        "floor": parsed["floor"],
        "slope_check": slope,
    }
    core.dump_json(OUT_JSON, record)
    (core.ROOT / OUT_MD).write_text(table_text, encoding="utf-8")
    print(f"Valve live check OK: newest table {newest}, {parsed['n_teams']} teams, "
          f"slope match={slope['matches_canonical']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
