#!/usr/bin/env python3
"""
Runner task — reference data used to originate our own lines for unpriced fixtures.

Source: Valve's official Counter-Strike Regional Standings (VRS), published by Valve at
https://github.com/ValveSoftware/counter-strike_regional_standings — the ranking Valve itself
uses for invitations. The raw monthly markdown snapshots are mirrored here so every rating
behind an originated line can be checked byte for byte.

Outputs: evidence/vrs_<region>_<snapshot>.md for global/europe/americas/asia, plus a compact
parsed index in evidence/vrs_index.json (standing, points, team name as published).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "evidence"))
RAW = "https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/live/2026"
SNAPSHOT = "2026_10_05"
REGIONS = ["global", "europe", "americas", "asia"]
UA = "MaltaProj2-research/1.0 (+https://github.com/buffedlizard55-lab/MaltaProj2)"
ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", re.M)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}".encode()


def main() -> int:
    index = {"retrieved_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "snapshot": SNAPSHOT, "regions": {}}
    for region in REGIONS:
        url = f"{RAW}/standings_{region}_{SNAPSHOT}.md"
        st, body = get(url)
        rec = {"url": url, "status": st, "bytes": len(body)}
        if st == 200 and body:
            path = os.path.join(OUT, f"vrs_{region}_{SNAPSHOT}.md")
            with open(path, "wb") as fh:
                fh.write(body)
            text = body.decode("utf-8", "replace")
            rows = ROW_RE.findall(text)
            rec["teams"] = len(rows)
            rec["as_of"] = (re.search(r"Standings as of ([0-9_]+)", text) or [None, None])[1]
            index["regions"][region] = rec
        else:
            index["regions"][region] = rec
    with open(os.path.join(OUT, "vrs_index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=1, ensure_ascii=False)
    print(json.dumps(index, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
