#!/usr/bin/env python3
"""EVERYPICK collector (session 907e9435).

Writes ``data/907e9435/snapshot.json``: the HotSpawn CS2 fixture inventory, every external
two-way price we could observe, the official Valve Regional Standings, and a per-source access log
so that a blocked source is recorded as a failure instead of silently becoming "no price".

Two modes
---------
``--live``      (default, GitHub Actions) fetch every public source directly. The HotSpawn,
                Pinnacle, Bovada and Melbet collectors from session f7279a54 are reused unchanged
                (same public endpoints, same parsing) instead of being duplicated here; the Kalshi
                exchange payload is re-read by this session's own builder so that each quote
                carries the kickoff the exchange states in its own rules text.
``--bootstrap`` (no general internet) build a snapshot from a retained capture
                (``--from data/f7279a54/snapshot.json``) plus the retained raw bookmaker payloads,
                and still fetch the official Valve standings, which are reachable through
                api.github.com. Provenance is recorded in the snapshot so the board can say which
                numbers were captured when and by which path.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import core  # noqa: E402  (local module)

OUT = ROOT / "data" / "907e9435"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
VRS_API = f"https://api.github.com/repos/{core.VRS_REPO}"
LOBBY = "https://play.hotspawn.com/lobby"
KALSHI_URL = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME"
              "&status=open&with_nested_markets=true&limit=200")
LOG: dict = {}


def gh_headers() -> dict:
    import os
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    return headers


def fetch(url: str, headers: dict | None = None, timeout: int = 60) -> tuple[bytes, dict]:
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    meta = {"url": url, "status": None, "bytes": 0, "error": None,
            "at_utc": core.to_iso(core.now_utc())}
    body = b""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context()) as r:
            body = r.read()
            meta["status"] = r.status
    except urllib.error.HTTPError as exc:
        meta["status"], meta["error"] = exc.code, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001 - a failure is evidence
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["bytes"] = len(body)
    if body:
        meta["sha256"] = hashlib.sha256(body).hexdigest()
    return body, meta


def fetch_json(url: str, headers: dict | None = None, timeout: int = 60):
    body, meta = fetch(url, headers, timeout)
    try:
        return (json.loads(body.decode("utf-8", "replace")) if body else None), meta
    except ValueError:
        meta["error"] = (meta["error"] or "") + " invalid JSON"
        return None, meta


# ------------------------------------------------------------------------------- VRS (official)
DETAIL_ROW = re.compile(r"^\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", re.M)


def vrs_details(path: str, cache: dict) -> dict:
    if path in cache:
        return cache[path]
    from urllib.parse import quote
    blob, meta = fetch_json(f"{VRS_API}/contents/{quote(path)}", gh_headers())
    text = ""
    if isinstance(blob, dict) and blob.get("content"):
        text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
    dates = DETAIL_ROW.findall(text)
    cache[path] = {"n_matches": len(dates), "latest_match_date": max(dates) if dates else None,
                   "status": meta.get("status"), "error": meta.get("error")}
    return cache[path]


def collect_vrs(fixture_names: set[str]) -> dict:
    tree, meta = fetch_json(f"{VRS_API}/git/trees/main?recursive=1", gh_headers())
    LOG["valve_vrs_tree"] = meta
    newest = None
    for node in (tree or {}).get("tree", []) if isinstance(tree, dict) else []:
        m = re.match(r"^live/(\d{4})/standings_global_(\d{4}_\d{2}_\d{2})\.md$", str(node.get("path")))
        if m and (newest is None or m.group(2) > newest[1]):
            newest = (m.group(1), m.group(2), node["path"])
    if not newest:
        return {}
    api_url = f"{VRS_API}/contents/{newest[2]}"
    blob, meta2 = fetch_json(api_url, gh_headers())
    LOG["valve_vrs_file"] = meta2
    if not isinstance(blob, dict) or not blob.get("content"):
        return {}
    text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
    base = newest[2].rsplit("/", 1)[0]
    teams = []
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)",
                         text, re.M):
        teams.append({"standing": int(m.group(1)), "points": int(m.group(2)),
                      "team": m.group(3).strip(), "roster": m.group(4).strip(),
                      "details_path": f"{base}/{m.group(5).strip()}",
                      "details_url": core.VRS_BLOB + f"{base}/{m.group(5).strip()}"})
    # Duplicate rows for one organisation: read each candidate's official details file so the
    # builder can decide with evidence instead of picking arbitrarily. Cached per snapshot date.
    OUT.mkdir(parents=True, exist_ok=True)
    cache_path = OUT / "vrs_details_cache.json"
    try:
        cache_all = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cache_all = {}
    cache = cache_all.setdefault(newest[1], {})
    wanted = {core.canon(n)[0] for n in fixture_names}
    by_key: dict[str, list] = {}
    for t in teams:
        by_key.setdefault(core.canon(t["team"])[0], []).append(t)
    fetched = 0
    for key, rows in by_key.items():
        if key not in wanted:
            continue
        if len(rows) < 2:
            detail = vrs_details(rows[0]["details_path"], cache)
            rows[0].update({k: detail[k] for k in ("n_matches", "latest_match_date")})
            fetched += 1
            continue
        for t in rows:
            before = t["details_path"] in cache
            detail = vrs_details(t["details_path"], cache)
            fetched += 0 if before else 1
            t.update({k: detail[k] for k in ("n_matches", "latest_match_date")})
    cache_path.write_text(json.dumps(cache_all, indent=1, sort_keys=True) + "\n")
    points = sorted(t["points"] for t in teams)
    LOG["valve_vrs_file"]["details_files_fetched"] = fetched
    return {
        "snapshot": newest[1], "path": newest[2], "api_url": api_url,
        "page_url": core.VRS_BLOB + newest[2],
        "tree_api_url": f"{VRS_API}/git/trees/main?recursive=1",
        "teams": teams,
        "n_teams": len(teams),
        "floor": {"standing": len(teams), "points": points[0]} if points else None,
    }


# ----------------------------------------------------------------------------- source adapters
def load_f7279a54_collector():
    path = ROOT / "scripts" / "f7279a54" / "collect.py"
    spec = importlib.util.spec_from_file_location("collect_f7279a54", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["collect_f7279a54"] = module
    spec.loader.exec_module(module)
    return module


def live_snapshot() -> dict:
    started = core.to_iso(core.now_utc())
    adapter = load_f7279a54_collector()
    hs = adapter.collect_hotspawn()
    quotes: list = []
    rejected: list = []
    for fn in (adapter.collect_pinnacle, adapter.collect_bovada, adapter.collect_melbet):
        try:
            fn(quotes)
        except Exception as exc:  # noqa: BLE001
            LOG.setdefault(fn.__name__, {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
    try:
        adapter.collect_kalshi(quotes, rejected)
    except Exception as exc:  # noqa: BLE001
        LOG.setdefault("kalshi", {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
    adapter.probe("polymarket_probe",
                  "https://gamma-api.polymarket.com/events?closed=false&limit=200"
                  "&tag_slug=counter-strike", {"Accept": "application/json"})
    adapter.probe("hltv_probe", "https://www.hltv.org/matches", {"Accept": "text/html"})
    # Keep the collectors' own access log, but re-key it into this session's snapshot.
    for key, value in (adapter.LOG or {}).items():
        LOG.setdefault(key, value)
    kalshi_payload = None
    for url, record in (adapter.SOURCE_PAYLOADS or {}).items():
        if "kalshi" in url:
            kalshi_payload = (record or {}).get("payload")
    book_quotes = [q for q in quotes if q.get("source_key") != "kalshi"]
    exchange_quotes, exchange_rejected = (
        core.kalshi_quotes((kalshi_payload or {}).get("events"), started))
    names = {n for f in hs["fixtures"] for n in (f["team_a"], f["team_b"])}
    vrs = collect_vrs(names)
    LOG["kalshi_rebuild"] = {"usable": len(exchange_quotes), "rejected": len(exchange_rejected),
                             "time_basis": "rules_primary stated local time -> UTC"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "source_payloads.json").write_text(json.dumps(
        {"collected_to_utc": core.to_iso(core.now_utc()), "sources": adapter.SOURCE_PAYLOADS or {}},
        indent=1) + "\n")
    return {"mode": "live", "collected_from_utc": started,
            "collected_to_utc": core.to_iso(core.now_utc()),
            "hotspawn": hs, "quotes": book_quotes + exchange_quotes,
            "rejected_quotes": rejected + exchange_rejected, "vrs": vrs,
            "source_payloads_file": "data/907e9435/source_payloads.json",
            "access_log": LOG}


def bootstrap_snapshot(source: Path, payloads_path: Path | None) -> dict:
    base = json.loads(source.read_text())
    payloads = {}
    if payloads_path and payloads_path.exists():
        payloads = json.loads(payloads_path.read_text()).get("sources") or {}
    kalshi_payload = None
    for url, record in payloads.items():
        if "kalshi" in url:
            kalshi_payload = (record or {}).get("payload")
    book_quotes = [q for q in base.get("quotes") or [] if q.get("source_key") != "kalshi"]
    exchange_quotes, exchange_rejected = (
        core.kalshi_quotes((kalshi_payload or {}).get("events"),
                           base.get("collected_to_utc") or ""))
    names = {n for f in (base.get("hotspawn") or {}).get("fixtures", [])
             for n in (f["team_a"], f["team_b"])}
    vrs = collect_vrs(names)
    LOG["bootstrap_source"] = {"path": str(source.relative_to(ROOT)), "status": "read"}
    # Keep the retained capture's own access log so the site's source ledger shows the HTTP status
    # each book answered when the quotes were captured (not a fresh claim about now).
    for key, meta in (base.get("access_log") or {}).items():
        if isinstance(meta, dict) and key not in LOG:
            LOG[key] = {**meta, "retained_capture": True}
    LOG["kalshi_rebuild"] = {"usable": len(exchange_quotes), "rejected": len(exchange_rejected),
                             "time_basis": "rules_primary stated local time -> UTC"}
    return {"mode": "bootstrap", "collected_from_utc": base.get("collected_from_utc"),
            "collected_to_utc": base.get("collected_to_utc"),
            "hotspawn": base.get("hotspawn") or {}, "quotes": book_quotes + exchange_quotes,
            "rejected_quotes": [r for r in (base.get("rejected_quotes") or [])
                                if r.get("source_key") != "kalshi"] + exchange_rejected,
            "vrs": vrs, "source_payloads_file": str(payloads_path.relative_to(ROOT))
            if payloads_path else None, "access_log": LOG,
            "provenance": {"book_quotes_from": str(source.relative_to(ROOT)),
                           "book_quotes_captured_utc": base.get("collected_to_utc"),
                           "vrs_fetched_utc": core.to_iso(core.now_utc()),
                           "note": ("Bookmaker/exchange/Kalshi payloads are the retained capture "
                                    "from the canonical collector; the Valve standings were fetched "
                                    "fresh from Valve's official repository during this build.")}}


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect one everypick snapshot.")
    ap.add_argument("--bootstrap", action="store_true",
                    help="build from a retained capture instead of fetching the books")
    ap.add_argument("--from", dest="source", default=str(ROOT / "data" / "f7279a54" / "snapshot.json"))
    ap.add_argument("--payloads", default=str(ROOT / "data" / "f7279a54" / "source_payloads.json"))
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    snap = (bootstrap_snapshot(Path(args.source), Path(args.payloads)) if args.bootstrap
            else live_snapshot())
    snap["session"] = core.SESSION
    snap["generated_utc"] = core.to_iso(core.now_utc())
    (OUT / "snapshot.json").write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"mode": snap["mode"], "fixtures": len((snap.get("hotspawn") or {}).get("fixtures") or []),
                      "quotes": len(snap.get("quotes") or []),
                      "rejected": len(snap.get("rejected_quotes") or []),
                      "vrs_teams": len((snap.get("vrs") or {}).get("teams") or []),
                      "vrs_snapshot": (snap.get("vrs") or {}).get("snapshot"),
                      "sources": {k: (v.get("status") if isinstance(v, dict) else None)
                                  for k, v in (snap.get("access_log") or {}).items()}}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
