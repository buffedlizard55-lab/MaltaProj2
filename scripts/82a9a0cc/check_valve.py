#!/usr/bin/env python3
"""Record which global Valve VRS file is currently newest in the official GitHub repo."""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "82a9a0cc" / "official_check.json"
API = "https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings"


def get_json(url: str):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "MaltaProj2-82a9a0cc"}
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
        return json.load(response)


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tree_url = API + "/git/trees/main?recursive=1"
    try:
        tree = get_json(tree_url)
        pattern = re.compile(r"^live/2026/standings_global_(\d{4}_\d{2}_\d{2})\.md$")
        choices = sorted((m.group(1), item["path"]) for item in tree.get("tree", [])
                         if (m := pattern.match(item.get("path", ""))))
        if not choices:
            raise RuntimeError("No official 2026 global standings file found")
        snapshot, path = choices[-1]
        content_url = API + "/contents/" + path
        meta = get_json(content_url)
        commits_url = API + "/commits?" + urllib.parse.urlencode({"path": path, "per_page": 1})
        commits = get_json(commits_url)
        commit = commits[0] if commits else {}
    except Exception as exc:
        # A workflow installation token can be rejected across repositories; never relabel a
        # failed request as a fresh verification. Keep the last successful official check visible.
        try:
            retained = json.loads(OUT.read_text())
        except (OSError, ValueError):
            raise RuntimeError(f"official Valve check failed with no retained verification: {exc}") from exc
        if not retained.get("page_url") or not retained.get("blob_sha"):
            raise RuntimeError(f"official Valve check failed and retained verification is incomplete: {exc}") from exc
        retained["last_attempt_utc"] = now
        retained["last_attempt_status"] = "retained_previous_after_network_error"
        retained["last_attempt_error"] = f"{type(exc).__name__}: {exc}"
        OUT.write_text(json.dumps(retained, indent=2) + "\n")
        print(f"WARNING: retained prior official Valve verification after network error: {exc}")
        return 0
    result = {
        "checked_utc": now,
        "repository": "ValveSoftware/counter-strike_regional_standings",
        "tree_url": tree_url,
        "latest_global_snapshot": snapshot,
        "path": path,
        "blob_sha": meta.get("sha"),
        "size": meta.get("size"),
        "page_url": meta.get("html_url"),
        "download_url": meta.get("download_url"),
        "commit_sha": commit.get("sha"),
        "commit_url": commit.get("html_url"),
        "commit_utc": ((commit.get("commit") or {}).get("committer") or {}).get("date"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
