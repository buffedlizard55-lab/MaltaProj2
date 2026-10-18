#!/usr/bin/env python3
"""b3871d16 collector - crowd/ownership refresh, a price probe for the unpriced rows, VRS freshness.

Runs on a GitHub-hosted runner (the sandbox has no general internet). Everything here is
best-effort: a failed request is recorded as a failure in the access log and the previous file on
disk is left untouched, so the published page can say "collector: partial" instead of quietly
losing coverage.

Written only under data/b3871d16/ :
  crowd_live.json   HotSpawn's own fixture rows: ownership and pick counts, plus lock times.
  prices_live.json  two-way winner markets found for fixtures the canonical board could not price.
  vrs_status.json   the newest snapshot published in Valve's official standings repo.

HotSpawn percentages are copied as ownership data only. They are never read as a probability and
nothing in this file feeds a line: the builder uses crowd_live.json for leverage/lock context and
prices_live.json only where a bookmaker coefficient was actually returned.
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "b3871d16"
BOARD_PATH = ROOT / "data" / "fe803b80" / "board.json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
LOBBY = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
BO3 = "https://api.bo3.gg/api/v1"
BO3_MATCHES = f"{BO3}/matches/"
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
CTX = ssl.create_default_context()
LOG: dict[str, dict] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, headers: dict | None = None, timeout: int = 45, tries: int = 3) -> tuple[bytes | None, dict]:
    meta = {"url": url, "status": None, "bytes": 0, "error": None, "attempts": 0}
    hdrs = {"User-Agent": UA, "Accept": "application/json", **dict(headers or {})}
    for i in range(tries):
        meta["attempts"] = i + 1
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                body = r.read()
                meta["status"] = r.status
                meta["bytes"] = len(body)
                return body, meta
        except urllib.error.HTTPError as e:      # noqa: PERF203
            meta["status"], meta["error"] = e.code, f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (i + 1))
                continue
            return None, meta
        except Exception as e:                    # noqa: BLE001 - any transport error is recorded, not raised
            meta["error"] = f"{type(e).__name__}: {e}"
            time.sleep(1.5 * (i + 1))
    return None, meta


def fetch_json(url, headers=None, timeout=45):
    body, meta = fetch(url, headers, timeout)
    if body is None:
        return None, meta
    try:
        return json.loads(body.decode("utf-8", "replace")), meta
    except ValueError:
        meta["error"] = (meta["error"] or "") + " invalid JSON"
        return None, meta


def norm(name) -> str:
    import unicodedata
    folded = unicodedata.normalize("NFKD", str(name or "").lower())
    return "".join(c for c in folded if c.isascii() and c.isalnum())


def write(path: Path, payload: dict, usable: bool = True) -> None:
    """Never let a failed run replace a good snapshot with an empty one."""
    OUT.mkdir(parents=True, exist_ok=True)
    if not usable and path.exists():
        return
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------- HotSpawn inventory
def collect_hotspawn() -> dict:
    data, meta = fetch_json(HS_API, {"Referer": LOBBY}, timeout=90)
    meta["source"] = HS_API
    rows_src = data if isinstance(data, list) else (data or {}).get("data") or []
    meta["rows_returned"] = len(rows_src)
    rows, skipped = [], 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for raw in rows_src:
        if not isinstance(raw, dict) or raw.get("sport_alias") != "cs2":
            continue
        status = str(raw.get("status") or "")
        ms = raw.get("scheduled_start_time")
        try:
            start = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
        except (TypeError, ValueError):
            skipped += 1
            continue
        start_utc = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        if status not in ("scheduled", "started") or start_utc[:10] < today:
            continue                                    # stale rows keep status=scheduled forever
        p0, p1 = raw.get("participants0_name"), raw.get("participants1_name")
        if not p0 or not p1:
            skipped += 1
            continue
        rows.append({
            "fixture_id": str(raw.get("id")), "team_a": p0, "team_b": p1,
            "crowd_a": raw.get("participants0_picked_percent"), "crowd_b": raw.get("participants1_picked_percent"),
            "total_picks": raw.get("total_picks"),
            "league": (raw.get("league_info") or {}).get("name"), "tier": (raw.get("league_info") or {}).get("tier"),
            "status": status, "start_utc": start_utc,
            "lock_utc": datetime.fromtimestamp(int(raw.get("lock_time") or ms) / 1000, tz=timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ") if raw.get("lock_time") or ms else None,
            "points": raw.get("offered_points"), "best_of": raw.get("best_of"),
            "stage": raw.get("stage"),
        })
    meta["cs2_rows_kept"] = len(rows)
    meta["rows_skipped"] = skipped
    LOG["hotspawn_api"] = meta
    return {"session": "b3871d16", "read_utc": now_iso(), "source_url": LOBBY, "source_api": HS_API,
            "source_kind": "api",
            "method": ("participantsN_picked_percent and total_picks copied as served from HotSpawn's public "
                       "fixtures API. OWNERSHIP ONLY: never a probability, never an input to any line. Rows "
                       "whose status is not scheduled/started, or whose start date is before today, are "
                       "dropped because HotSpawn leaves stale rows marked scheduled."),
            "rows": sorted(rows, key=lambda r: (r["start_utc"], r["fixture_id"])),
            "access": meta}


# ------------------------------------------------------------------- price probe for the gaps
def find_pair(bet_updates: dict) -> tuple[float | None, float | None, dict]:
    """Pull a two-way decimal pair out of a bo3.gg bet_updates block, whatever key it uses."""
    seen: dict[str, object] = {}
    out: list[float | None] = []
    for side in ("team_1", "team_2"):
        block = bet_updates.get(side) or {}
        val = None
        for key in ("coefficient", "odd", "odds", "value", "decimal", "price", "bet"):
            cand = block.get(key)
            if isinstance(cand, (int, float)) and 1.01 <= float(cand) <= 1000:
                val = float(cand)
                seen[f"{side}.{key}"] = cand
                break
        if val is None:
            seen[f"{side}.keys"] = sorted(block.keys())
        out.append(val)
    return out[0], out[1], seen


def collect_prices(open_rows: list[dict]) -> dict:
    unpriced = [r for r in open_rows if not r.get("market")]
    want: dict[tuple[str, str], list[str]] = {}
    for r in unpriced:
        want.setdefault(tuple(sorted((norm(r["team_a"]), norm(r["team_b"])))), []).append(str(r["fixture_id"]))
    found: dict[str, dict] = {}
    attempted: dict[str, dict] = {}
    pages, total = 0, 0
    for page in range(12):
        url = f"{BO3_MATCHES}?filter%5Bmatches.status%5D%5Bin%5D=upcoming&page%5Boffset%5D={page * 100}"
        data, meta = fetch_json(url)
        if meta.get("error"):
            LOG.setdefault("bo3gg_matches", {"errors": []})["errors"].append(meta["error"])
            break
        results = (data or {}).get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            break
        pages += 1
        total += len(results)
        for m in results:
            if not isinstance(m, dict):
                continue
            key = tuple(sorted((norm((m.get("team1") or {}).get("name") or (m.get("team_1") or {}).get("name")),
                                norm((m.get("team2") or {}).get("name") or (m.get("team_2") or {}).get("name")))))
            fids = want.get(key) or []
            if not fids:
                continue
            da, db, diag = find_pair(m.get("bet_updates") or {})
            for fid in fids:
                attempted[fid] = {"bo3_match_id": m.get("id"), "slug": m.get("slug"),
                                  "start_date": m.get("start_date"),
                                  "bo3_url": f"https://bo3.gg/matches/{m.get('slug')}" if m.get("slug") else None,
                                  "coefficient_a": da, "coefficient_b": db, "diagnostic": diag}
                if da and db:
                    found[fid] = {"fixture_id": fid, "source_key": "bo3gg_thunderpick",
                                  "source_name": "Thunderpick via bo3.gg",
                                  "decimal_a": da, "decimal_b": db,
                                  "url": f"https://bo3.gg/matches/{m.get('slug')}" if m.get("slug") else url,
                                  "read_utc": now_iso(),
                                  "raw_bet_updates": m.get("bet_updates")}
        if len(results) < 100:
            break
    LOG["bo3gg_matches"] = {"pages": pages, "matches_scanned": total,
                            "gap_fixtures": len(unpriced), "joins": len(attempted), "prices": len(found),
                            "errors": (LOG.get("bo3gg_matches") or {}).get("errors", [])}
    return {"session": "b3871d16", "read_utc": now_iso(),
            "method": ("For every open CS2 fixture the canonical board has no book price for, the public bo3.gg "
                       "upcoming-match list is scanned and matched on a normalised team-name pair. A price is "
                       "recorded only when a numeric two-way coefficient pair is actually returned; an empty "
                       "diagnostic entry means the book does not list that fixture, which is a coverage fact and "
                       "is published as one."),
            "prices": sorted(found.values(), key=lambda r: r["fixture_id"]),
            "attempted_without_price": sorted({k: v for k, v in attempted.items() if k not in found}.keys()),
            "probe": {k: v for k, v in sorted(attempted.items())},
            "access": LOG.get("bo3gg_matches", {})}


# ------------------------------------------------------------------------- VRS snapshot freshness
def collect_vrs(pinned: str | None) -> dict:
    url = f"https://api.github.com/repos/{VRS_REPO}/contents/live/2026"
    body, meta = fetch(url, {"Accept": "application/vnd.github+json", "Authorization": "Bearer "}, timeout=30)
    out = {"checked_utc": now_iso(), "repo": f"https://github.com/{VRS_REPO}", "pinned_file": pinned,
           "newest_global_file": None, "newer_than_pinned": None, "access": meta}
    if body:
        try:
            entries = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            entries = []
            meta["error"] = (meta["error"] or "") + " invalid JSON"
        names = [e.get("name", "") for e in entries if isinstance(e, dict)]
        globals_ = sorted(n for n in names if n.startswith("standings_global_"))
        if globals_:
            newest = globals_[-1]
            out["newest_global_file"] = newest
            out["global_files_seen"] = globals_[-4:]
            if pinned:
                out["newer_than_pinned"] = newest > pinned
                out["action_needed"] = bool(out["newer_than_pinned"])
    LOG["vrs_repo"] = meta
    return out


def main() -> int:
    started = time.time()
    crowd = collect_hotspawn()
    write(OUT / "crowd_live.json", crowd, usable=bool(crowd["rows"]))

    board = None
    try:
        board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    except Exception as e:                                # noqa: BLE001
        LOG["canonical_board"] = {"error": f"{type(e).__name__}: {e}"}
    open_rows = [r for r in (board or {}).get("open", []) if str(r.get("status")) in ("scheduled", "started")]
    prices = collect_prices(open_rows) if open_rows else {"prices": [], "read_utc": now_iso(),
                                                          "method": "skipped - canonical board unavailable"}
    prices["access"] = LOG.get("bo3gg_matches", {})
    write(OUT / "prices_live.json", prices,
          usable=not (LOG.get("bo3gg_matches") or {}).get("errors"))
    write(OUT / "vrs_status.json", collect_vrs(((board or {}).get("vrs") or {}).get("file")
                                               or (board or {}).get("notes", {}).get("vrs_file") if isinstance((board or {}).get("notes"), dict) else None))
    ok = all(x.get("error") in (None, "") for x in LOG.values() if isinstance(x, dict))
    status = "ok" if ok else "partial"
    if not crowd["rows"]:
        status = "failed"
    (OUT / "collector_status.json").write_text(json.dumps({
        "session": "b3871d16", "run_utc": now_iso(), "status": status,
        "seconds": round(time.time() - started, 1),
        "crowd_rows": len(crowd["rows"]), "new_prices": len(prices.get("prices", [])),
        "gap_fixtures_probed": len(prices.get("attempted_without_price", []) or []),
        "open_fixtures_on_board": len(open_rows),
        "access": LOG}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"collect: {status} - {len(crowd['rows'])} crowd rows, {len(prices.get('prices', []))} new prices, "
          f"{len(open_rows)} open fixtures on the board", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
