#!/usr/bin/env python3
"""Session 7177d07f collector: evidence for HotSpawn CS2 fixtures the featured route cannot price.

Reads, in the order the brief requires:
  1. HLTV ..................... identity / ranking research (probe; the committed dated research in
                                data/7177d07f/hltv_research.json supplies the values themselves)
  2. esportsbooks / esports
     betting lines ............ Melbet LineFeed JSON, Thunderpick coefficients as published by
                                bo3.gg, Kalshi exchange books
  3. official Valve VRS ....... ValveSoftware/counter-strike_regional_standings via the GitHub API

Every probe records its URL, HTTP status (or error), byte count, parsed-row count and UTC read time.
Nothing is inferred: a source that cannot be read is recorded as unread, and a quote that cannot be
joined to a fixture is stored unmatched rather than assigned.

Writes data/7177d07f/snapshot.json. Fails soft by design - a later build must still be able to run
from the committed snapshot when every external source is unreachable.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "7177d07f"
OUT = DATA / "snapshot.json"

UA = "MaltaProj2-7177d07f/1.0 (research collector; contact via repository issues)"
TIMEOUT = 20

VALVE_REPO = "ValveSoftware/counter-strike_regional_standings"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, accept: str = "application/json", headers: dict | None = None):
    """Return (status, body_bytes, error). Never raises."""
    hdrs = {"User-Agent": UA, "Accept": accept}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return int(resp.status), resp.read(), None
    except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
        return int(exc.code), b"", f"HTTPError {exc.code}"
    except Exception as exc:  # pragma: no cover - network dependent
        return None, b"", f"{type(exc).__name__}: {exc}"


def _preview(body: bytes, limit: int = 700) -> str:
    """Short, printable preview of a raw response, published as parser diagnostics."""
    try:
        return body[:limit].decode("utf-8", "replace")
    except Exception:  # pragma: no cover
        return ""


# --------------------------------------------------------------------- Valve VRS
ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*\[details\]\(([^)]+)\)\s*\|\s*$"
)


def valve_latest_path():
    """Newest live/2026/standings_global_*.md in the official repository (GitHub API)."""
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{VALVE_REPO}/contents/live/2026"],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return None, f"gh api exited {proc.returncode}: {proc.stderr.strip()[:200]}"
        names = [
            entry.get("name")
            for entry in json.loads(proc.stdout)
            if isinstance(entry, dict)
            and re.fullmatch(r"standings_global_\d{4}_\d{2}_\d{2}\.md", entry.get("name") or "")
        ]
        if not names:
            return None, "no standings_global_*.md listed in live/2026"
        return sorted(names)[-1], None
    except Exception as exc:  # pragma: no cover
        return None, f"{type(exc).__name__}: {exc}"


def _github_contents(path: str):
    """Read one file from a public GitHub repository.

    Tries the GitHub CLI (which uses GH_TOKEN when it is set) and falls back to the public REST API,
    so the collector works both on a runner (with a token) and anywhere else without one.
    """
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        try:
            proc = subprocess.run(
                ["gh", "api", f"repos/{VALVE_REPO}/contents/{path}"],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return json.loads(proc.stdout), None
            err = f"gh api exited {proc.returncode}: {proc.stderr.strip()[:200]}"
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
    else:
        err = "no GH_TOKEN/GITHUB_TOKEN in the environment"
    status, body, api_err = fetch(f"https://api.github.com/repos/{VALVE_REPO}/contents/{path}")
    if body:
        try:
            return json.loads(body.decode("utf-8", "replace")), None
        except Exception as exc:
            return None, f"{err}; REST parse failed: {type(exc).__name__}: {exc}"
    return None, f"{err}; REST failed: {api_err}"


def valve_latest_path_rest():
    status, body, err = fetch(f"https://api.github.com/repos/{VALVE_REPO}/contents/live/2026")
    if not body:
        return None, f"REST listing failed: {err}"
    try:
        names = [
            entry.get("name")
            for entry in json.loads(body.decode("utf-8", "replace"))
            if isinstance(entry, dict)
            and re.fullmatch(r"standings_global_\d{4}_\d{2}_\d{2}\.md", entry.get("name") or "")
        ]
    except Exception as exc:
        return None, f"REST listing parse failed: {type(exc).__name__}: {exc}"
    if not names:
        return None, "no standings_global_*.md listed in live/2026"
    return sorted(names)[-1], None


def collect_valve():
    name, err = valve_latest_path()
    if not name:
        name, err2 = valve_latest_path_rest()
        err = f"{err}; {err2}" if (err and err2) else (err or err2)
    if not name:
        return {
            "key": "valve_vrs",
            "url": f"https://github.com/{VALVE_REPO}",
            "http_status": None,
            "error": err,
            "bytes": 0,
            "rows": 0,
            "retrieved_utc": now_iso(),
            "standings": [],
            "snapshot": None,
        }
    payload, perr = _github_contents(f"live/2026/{name}")
    if not payload:
        return {
            "key": "valve_vrs",
            "url": f"https://github.com/{VALVE_REPO}/blob/main/live/2026/{name}",
            "api_url": f"https://api.github.com/repos/{VALVE_REPO}/contents/live/2026/{name}",
            "http_status": None,
            "error": perr,
            "bytes": 0,
            "rows": 0,
            "retrieved_utc": now_iso(),
            "standings": [],
            "snapshot": None,
        }
    try:
        raw = base64.b64decode(payload.get("content") or "")
        text = raw.decode("utf-8", "replace")
    except Exception as exc:
        return {
            "key": "valve_vrs",
            "url": f"https://github.com/{VALVE_REPO}/blob/main/live/2026/{name}",
            "api_url": f"https://api.github.com/repos/{VALVE_REPO}/contents/live/2026/{name}",
            "http_status": None,
            "error": f"{type(exc).__name__}: {exc}",
            "bytes": 0,
            "rows": 0,
            "retrieved_utc": now_iso(),
            "standings": [],
            "snapshot": None,
        }
    standings = []
    for line in text.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        standings.append({
            "standing": int(m.group(1)),
            "points": int(m.group(2)),
            "team": m.group(3).strip(),
            "roster": m.group(4).strip(),
            "details_path": m.group(5).strip(),
        })
    return {
        "key": "valve_vrs",
        "url": f"https://github.com/{VALVE_REPO}/blob/main/live/2026/{name}",
        "api_url": f"https://api.github.com/repos/{VALVE_REPO}/contents/live/2026/{name}",
        "http_status": 200,
        "error": None,
        "bytes": len(raw),
        "rows": len(standings),
        "retrieved_utc": now_iso(),
        "snapshot": name.replace("standings_global_", "").replace(".md", ""),
        "standings": standings,
    }


# --------------------------------------------------------------- esportsbook feeds
def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


def collect_melbet():
    """Melbet (1xBet platform) public LineFeed - two-sided 1x2 esports prices."""
    url = ("https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40"
           "&count=1000&lng=en&mode=4&country=1")
    status, body, err = fetch(url, accept="*/*")
    quotes, parse_error = [], None
    if body:
        try:
            payload = json.loads(body.decode("utf-8", "replace"))
            events = ((payload.get("Value") or []) if isinstance(payload, dict) else payload) or []
            for ev in events:
                name = ev.get("O1") or ev.get("N") or ev.get("O1N") or ""
                if " vs " not in str(name):
                    continue
                a, b = [part.strip() for part in str(name).split(" vs ", 1)]
                prices = ev.get("E") or []
                if len(prices) < 2:
                    continue
                win = [p for p in prices if p.get("T") == 1]
                if len(win) < 2:
                    continue
                try:
                    da, db = float(win[0].get("C")), float(win[1].get("C"))
                except (TypeError, ValueError):
                    continue
                if da <= 1.0 or db <= 1.0:
                    continue
                quotes.append({
                    "source_key": "melbet",
                    "source_name": "Melbet (esportsbook LineFeed)",
                    "public_url": "https://melbet.com/en/line/esports",
                    "api_url": url,
                    "event_id": str(ev.get("I") or ev.get("CI") or ""),
                    "team_a": a, "team_b": b,
                    "start_utc": None,
                    "decimal_a": da, "decimal_b": db,
                })
        except Exception as exc:
            parse_error = f"{type(exc).__name__}: {exc}"
    return {
        "key": "melbet",
        "url": "https://melbet.com/en/line/esports",
        "api_url": url,
        "http_status": status,
        "error": err or parse_error,
        "bytes": len(body),
        "rows": len(quotes),
        "retrieved_utc": now_iso(),
        "body_preview": _preview(body) if (body and not quotes) else "",
    }, quotes


def collect_bo3gg():
    """bo3.gg upcoming matches - publishes two-sided Thunderpick coefficients per fixture."""
    url = "https://bo3.gg/api/v1/matches?status=upcoming&limit=100"
    status, body, err = fetch(url)
    quotes, parse_error = [], None
    if body:
        try:
            payload = json.loads(body.decode("utf-8", "replace"))
            items = payload.get("data") if isinstance(payload, dict) else payload
            for item in items or []:
                t1 = ((item.get("team1") or {}).get("name")) or item.get("team1_name")
                t2 = ((item.get("team2") or {}).get("name")) or item.get("team2_name")
                updates = item.get("bet_updates") or []
                coeffs = None
                for upd in updates:
                    if isinstance(upd, dict) and upd.get("coefficients"):
                        coeffs = upd["coefficients"]
                if not (t1 and t2) or not isinstance(coeffs, list) or len(coeffs) < 2:
                    continue
                try:
                    da, db = float(coeffs[0]), float(coeffs[1])
                except (TypeError, ValueError):
                    continue
                if da <= 1.0 or db <= 1.0:
                    continue
                quotes.append({
                    "source_key": "thunderpick_via_bo3gg",
                    "source_name": "Thunderpick (coefficients as published by bo3.gg)",
                    "public_url": "https://bo3.gg/matches",
                    "api_url": url,
                    "event_id": str(item.get("id") or ""),
                    "team_a": t1, "team_b": t2,
                    "start_utc": item.get("start_date"),
                    "decimal_a": da, "decimal_b": db,
                })
        except Exception as exc:
            parse_error = f"{type(exc).__name__}: {exc}"
    return {
        "key": "thunderpick_via_bo3gg",
        "url": "https://bo3.gg/matches",
        "api_url": url,
        "http_status": status,
        "error": err or parse_error,
        "bytes": len(body),
        "rows": len(quotes),
        "retrieved_utc": now_iso(),
        "body_preview": _preview(body) if (body and not quotes) else "",
    }, quotes


def collect_kalshi():
    """Kalshi KXCS2GAME exchange series - two-sided order books."""
    url = "https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXCS2GAME&limit=200&status=open"
    status, body, err = fetch(url)
    books, parse_error = [], None
    if body:
        try:
            payload = json.loads(body.decode("utf-8", "replace"))
            for mkt in payload.get("markets") or []:
                books.append({
                    "source_key": "kalshi",
                    "source_name": "Kalshi (regulated exchange)",
                    "public_url": f"https://kalshi.com/markets/kxcs2game/{str(mkt.get('event_ticker') or '').lower()}",
                    "api_url": url,
                    "event_id": mkt.get("event_ticker") or mkt.get("ticker") or "",
                    "ticker": mkt.get("ticker") or "",
                    "title": mkt.get("title") or "",
                    "subtitle": mkt.get("subtitle") or mkt.get("yes_sub_title") or "",
                    "yes_bid_dollars": mkt.get("yes_bid_dollars"),
                    "yes_ask_dollars": mkt.get("yes_ask_dollars"),
                    "close_time": mkt.get("close_time"),
                })
        except Exception as exc:
            parse_error = f"{type(exc).__name__}: {exc}"
    return {
        "key": "kalshi",
        "url": "https://kalshi.com/markets/kxcs2game",
        "api_url": url,
        "http_status": status,
        "error": err or parse_error,
        "bytes": len(body),
        "rows": len(books),
        "retrieved_utc": now_iso(),
    }, books


def collect_hltv_probe():
    """HLTV is the first information source the brief names. Probe it and record the result."""
    url = "https://www.hltv.org/betting/analytics"
    status, body, err = fetch(url, accept="text/html")
    return {
        "key": "hltv_probe",
        "url": url,
        "http_status": status,
        "error": err,
        "bytes": len(body),
        "rows": 0,
        "retrieved_utc": now_iso(),
        "note": ("HLTV numeric pricing is not parsed by this collector: the 'Best Odds' columns for "
                 "the unpriced fixtures were empty when read manually on 2026-10-14. HLTV is used for "
                 "identity and ranking evidence, archived in data/7177d07f/hltv_research.json."),
    }


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    valve = collect_valve()
    melbet_meta, melbet_quotes = collect_melbet()
    bo3_meta, bo3_quotes = collect_bo3gg()
    kalshi_meta, kalshi_books = collect_kalshi()
    hltv = collect_hltv_probe()

    snapshot = {
        "session": "7177d07f",
        "collected_utc": now_iso(),
        "sources": [hltv, melbet_meta, bo3_meta, kalshi_meta, valve],
        "quotes": melbet_quotes + bo3_quotes,
        "exchange_books": kalshi_books,
        "valve": valve,
    }
    OUT.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "collected_utc": snapshot["collected_utc"],
        "quotes": len(snapshot["quotes"]),
        "exchange_books": len(snapshot["exchange_books"]),
        "valve_rows": valve.get("rows"),
        "valve_snapshot": valve.get("snapshot"),
        "sources": {s["key"]: (s.get("http_status"), s.get("error")) for s in snapshot["sources"]},
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
