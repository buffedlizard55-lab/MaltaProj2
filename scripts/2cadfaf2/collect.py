#!/usr/bin/env python3
"""Session 2cadfaf2 collector — a **live** capture for the pick centre.

This is the step every earlier every-match desk skipped: instead of re-rendering a frozen
committed snapshot, it re-reads the sources on every run:

  * ``https://play.hotspawn.com/lobby`` — the fixture inventory the lobby lists for the current
    pick'em week (page transfer state: fixtures, week metadata, published match permalinks);
  * ``https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures`` — the same public API
    the lobby page calls, used for status results and fixtures the page cache has not picked up;
  * Pinnacle guest odds API, Bovada coupon JSON, Melbet LineFeed JSON (licensed bookmakers) and
    Kalshi ``KXCS2GAME`` (CFTC-regulated exchange) — external match-winner prices, never HotSpawn;
  * ``ValveSoftware/counter-strike_regional_standings`` via api.github.com — the official Valve
    Regional Standings used to originate a probability where no book prices a fixture.

The head of the previous audited collector (session f7279a54) is imported as a library so the
request headers, the ``no-vig`` maths and the source parsers are byte-for-byte the ones that have
been running in CI. Nothing in ``data/f7279a54`` is written.

When the runner cannot reach a source (sandbox egress, provider block) the collector refuses to
invent anything: it either records the failed source as evidence, or — if the lobby itself is
unreachable — falls back to the committed ``data/f7279a54/snapshot.json`` capture and labels the
whole run ``committed_snapshot_fallback`` with that capture's own timestamp.

Writes ``data/2cadfaf2/snapshot.json`` and ``data/2cadfaf2/vrs_details_cache.json`` only.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "2cadfaf2"
FALLBACK_SNAPSHOT = ROOT / "data" / "f7279a54" / "snapshot.json"
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
ISO = "%Y-%m-%dT%H:%M:%SZ"


def _load_collector():
    name = "collector_f7279a54"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "scripts" / "f7279a54" / "collect.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_col = _load_collector()
_core = _col.core


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).strftime(ISO) if dt else None


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------------------- Valve VRS
def collect_vrs(fixture_names: set[str]) -> dict:
    """Official Valve Regional Standings + active-roster evidence for duplicated names."""
    log = _col.LOG
    tree, meta = _col.fetch_json(f"https://api.github.com/repos/{VRS_REPO}/git/trees/main?recursive=1",
                                 _col.gh_headers())
    log["valve_vrs_tree"] = meta
    newest = None
    if isinstance(tree, dict):
        for node in tree.get("tree") or []:
            m = re.match(r"^live/(\d{4})/standings_global_(\d{4}_\d{2}_\d{2})\.md$", str(node.get("path")))
            if m and (newest is None or m.group(2) > newest[1]):
                newest = (m.group(1), m.group(2), node["path"])
    if not newest:
        return {}
    api_url = f"https://api.github.com/repos/{VRS_REPO}/contents/{newest[2]}"
    blob, meta2 = _col.fetch_json(api_url, _col.gh_headers())
    log["valve_vrs_file"] = meta2
    if not isinstance(blob, dict) or not blob.get("content"):
        return {}
    text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
    base_dir = newest[2].rsplit("/", 1)[0]
    teams = []
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)",
                         text, re.M):
        teams.append({"standing": int(m.group(1)), "points": int(m.group(2)),
                      "team": m.group(3).strip(), "roster": m.group(4).strip(),
                      "details_path": f"{base_dir}/{m.group(5).strip()}"})
    # Only duplicated organisation names need their details file read; that is where Valve keeps
    # the dated record of when each roster last played a counted match.
    by_key: dict[str, list[dict]] = {}
    for t in teams:
        by_key.setdefault(_core.canon(t["team"])[0], []).append(t)
    wanted = {_core.canon(n)[0] for n in fixture_names if n}
    # A fixture team may be joined to Valve under a published alias (HotSpawn "Apogee Betclic" is
    # Valve's "Betclic"), so the alias keys are included when looking for duplicated names.
    try:
        import importlib.util as _iu
        _spec = _iu.spec_from_file_location("core_2cadfaf2", Path(__file__).resolve().parent / "pc_core.py")
        _local = _iu.module_from_spec(_spec)
        _spec.loader.exec_module(_local)
        for name in list(wanted):
            group = _local.KEY_TO_GROUP.get(name)
            if group:
                wanted.update(group["keys"])
    except Exception:  # noqa: BLE001 - alias discovery is an enhancement, never a hard dependency
        pass
    cache_path = OUT / "vrs_details_cache.json"
    cache = load_json(cache_path, {})
    if cache.get("snapshot") != newest[1]:
        cache = {"snapshot": newest[1], "latest_match": {}}
    fetched = 0
    for key, rows in by_key.items():
        if len(rows) < 2 or key not in wanted:
            continue
        for t in rows:
            path = t["details_path"]
            if path not in cache["latest_match"]:
                from urllib.parse import quote
                dblob, _ = _col.fetch_json(
                    f"https://api.github.com/repos/{VRS_REPO}/contents/{quote(path)}", _col.gh_headers())
                md = (base64.b64decode(dblob["content"]).decode("utf-8", "replace")
                      if isinstance(dblob, dict) and dblob.get("content") else "")
                cache["latest_match"][path] = _col.latest_match_date(md)
                fetched += 1
            t["latest_match_date"] = cache["latest_match"][path]
    OUT.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    log["valve_vrs_file"]["details_files_fetched"] = fetched
    log["valve_vrs_file"]["duplicate_names"] = sum(1 for rows in by_key.values() if len(rows) > 1)
    return {"snapshot": newest[1], "path": newest[2], "api_url": api_url,
            "page_url": f"https://github.com/{VRS_REPO}/blob/main/{newest[2]}", "teams": teams}


# ---------------------------------------------------------------------------------- capture
def capture_live() -> dict:
    started = utc_now()
    hs = _col.collect_hotspawn()
    quotes: list = []
    rejected: list = []
    for fn in (_col.collect_pinnacle, _col.collect_bovada, _col.collect_melbet):
        try:
            fn(quotes)
        except Exception as exc:  # noqa: BLE001 - a failing book is evidence, not a crash
            _col.LOG.setdefault(fn.__name__, {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
    try:
        _col.collect_kalshi(quotes, rejected)
    except Exception as exc:  # noqa: BLE001
        _col.LOG.setdefault("kalshi", {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
    _col.probe("polymarket_probe", _col.POLY, {"Accept": "application/json"})
    _col.probe("hltv_probe", _col.HLTV, {"Accept": "text/html"})
    names = {n for f in hs["fixtures"] for n in (f.get("team_a"), f.get("team_b"))}
    vrs = collect_vrs(names)
    log = _col.LOG
    _col.SOURCE_PAYLOADS.clear()  # raw payloads are not published from this session
    return {"collected_from_utc": iso(started), "collected_to_utc": iso(utc_now()),
            "hotspawn": hs, "quotes": quotes, "rejected_quotes": rejected, "vrs": vrs,
            "access_log": log}


def fallback_capture() -> dict | None:
    old = load_json(FALLBACK_SNAPSHOT, None)
    if not isinstance(old, dict) or not old.get("hotspawn"):
        return None
    log = dict(old.get("access_log") or {})
    # Keep the original read times: a fallback must never look like a fresh read.
    log = {"fallback_snapshot": {"url": "https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/data/f7279a54/snapshot.json",
                                 "status": 200, "error": None,
                                 "at_utc": old.get("collected_to_utc"), "bytes": None},
           **log}
    return {"collected_from_utc": old.get("collected_from_utc"),
            "collected_to_utc": old.get("collected_to_utc"),
            "hotspawn": old["hotspawn"], "quotes": old.get("quotes") or [],
            "rejected_quotes": old.get("rejected_quotes") or [], "vrs": old.get("vrs") or {},
            "access_log": log}


def ok(meta: dict | None) -> bool:
    return bool(isinstance(meta, dict) and meta.get("status") == 200 and not meta.get("error")
                and not meta.get("looks_like_challenge"))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    live = capture_live()
    listed = [f for f in live["hotspawn"]["fixtures"] if "lobby_page" in f.get("seen_in", [])]
    books_ok = [k for k, v in (live["access_log"] or {}).items()
                if k in ("pinnacle", "bovada", "melbet", "kalshi") and ok(v)]
    mode = "live"
    fallback = None
    if not listed or not books_ok:
        previous = fallback_capture()
        if previous:
            mode = "committed_snapshot_fallback"
            fallback = {"why": ("the lobby page did not parse" if not listed
                                else "no external book/exchange responded"),
                        "snapshot": "data/f7279a54/snapshot.json",
                        "captured_utc": previous["collected_to_utc"],
                        "live_attempt": {"lobby_fixtures": len(listed), "books_ok": books_ok,
                                         "access_log": live["access_log"]}}
            live = previous
    snapshot = {
        "session": "2cadfaf2",
        "mode": mode,
        "fallback": fallback,
        "collected_from_utc": live["collected_from_utc"],
        "collected_to_utc": live["collected_to_utc"],
        "written_utc": iso(utc_now()),
        "week": live["hotspawn"].get("week"),
        "fixtures": live["hotspawn"]["fixtures"],
        "permalinks": live["hotspawn"].get("permalinks") or {},
        "quotes": live["quotes"],
        "rejected_quotes": live["rejected_quotes"],
        "vrs": live["vrs"],
        "access_log": live["access_log"],
    }
    (OUT / "snapshot.json").write_text(json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    fixture_rows = [f for f in snapshot["fixtures"] if "lobby_page" in f.get("seen_in", [])]
    print(json.dumps({
        "mode": mode,
        "captured_to_utc": snapshot["collected_to_utc"],
        "lobby_fixtures": len(fixture_rows),
        "cs2_rows_kept": len(snapshot["fixtures"]),
        "quotes": len(snapshot["quotes"]),
        "vrs_snapshot": (snapshot.get("vrs") or {}).get("snapshot"),
        "sources": {k: {"status": (v or {}).get("status"), "error": (v or {}).get("error")}
                    for k, v in (snapshot.get("access_log") or {}).items()
                    if isinstance(v, dict)},
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
