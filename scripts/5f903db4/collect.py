#!/usr/bin/env python3
"""Live collector for the `5f903db4` every-match pick pipeline (runs in CI, no manual input).

Reads, in this order, and writes `data/5f903db4/snapshot.json`:

  1. HotSpawn fixtures API            - the same public API the lobby calls: open fixtures, kick-off,
                                        lock time and listing status (fixture discovery only).
  2. Kalshi KXCS2GAME (exchange)      - two-sided dollar quotes per team.
  3. Melbet / 1xBet line feed         - two-way decimal prices.
  4. Thunderpick via the bo3.gg API   - two-way decimal coefficients.
  5. Valve VRS standings repository   - newest published global table (API listing), so the ratings
                                        refresh themselves when Valve publishes a new file.

Each source fails independently: a broken source is logged and simply contributes no quotes, which
leaves the row on its documented fallback instead of failing the run.  A quote is only attached to a
fixture when the kick-off agrees within 90 minutes and the team names match exactly after
normalisation, or through the alias table in `scripts/5f903db4/research.json`.
"""
from __future__ import annotations

import base64
import importlib.util as _iu
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_spec = _iu.spec_from_file_location("everpick_core", Path(__file__).resolve().parent / "core.py")
core = _iu.module_from_spec(_spec)
sys.modules["everpick_core"] = core
_spec.loader.exec_module(core)

UA = {"User-Agent": "MaltaProj2-everypick/1.0 (+https://github.com/buffedlizard55-lab/MaltaProj2)",
      "Accept": "application/json"}
TOL = 90 * 60
OUT = "data/5f903db4/snapshot.json"
LOG: dict = {}


def fetch(url, headers=None, timeout=45):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def fixtures() -> list[dict]:
    """Open fixtures as the lobby sees them, from the board the 30-minute collector already wrote."""
    out = []
    for path in ("data/f7279a54/board.json", "data/fe803b80/board.json"):
        board = core.load(path, {}) or {}
        for m in board.get("open") or []:
            out.append({"fixture_id": str(m.get("fixture_id")), "team_a": m.get("team_a"),
                        "team_b": m.get("team_b"), "start_utc": m.get("start_utc"),
                        "competition": m.get("competition")})
    seen, uniq = set(), []
    for f in out:
        if f["fixture_id"] in seen:
            continue
        seen.add(f["fixture_id"])
        uniq.append(f)
    return uniq


def aliases() -> dict:
    """normalised book/exchange team name -> HotSpawn team name."""
    return {"alianzalimaesports": "zetta", "apogeeesports": "apogeebetclic",
            "betclic": "apogeebetclic", "losninos": "losninos"}


def match_fixture(rows, quoted_a, quoted_b, start_utc, team_aliases):
    na = team_aliases.get(core.norm(quoted_a), core.norm(quoted_a))
    nb = team_aliases.get(core.norm(quoted_b), core.norm(quoted_b))
    q_start = ts(start_utc)
    for f in rows:
        fa, fb = core.norm(f["team_a"]), core.norm(f["team_b"])
        straight = (na == fa and nb == fb)
        swapped = (na == fb and nb == fa)
        if not (straight or swapped):
            continue
        f_start = ts(f["start_utc"])
        if q_start and f_start and abs((q_start - f_start).total_seconds()) > TOL:
            continue
        return f, swapped
    return None, None


def quote(rows, source_key, source_name, public_url, api_url, event_id, team_a, team_b,
          decimal_a, decimal_b, start_utc, league, team_aliases):
    f, swapped = match_fixture(rows, team_a, team_b, start_utc, team_aliases)
    if not f:
        return None
    if swapped:
        decimal_a, decimal_b = decimal_b, decimal_a
    return {"fixture_id": f["fixture_id"], "source_key": source_key, "source_name": source_name,
            "public_url": public_url, "api_url": api_url, "event_id": str(event_id),
            "team_a": f["team_a"], "team_b": f["team_b"],
            "decimal_a": float(decimal_a), "decimal_b": float(decimal_b),
            "raw_format": "decimal", "start_utc": start_utc or f["start_utc"],
            "league": league, "retrieved_utc": now(), "declared_order": "ab",
            "join_note": ("automatic join: team names match after normalisation"
                          + (" (sides swapped)" if swapped else "")),
            "evidence_urls": [public_url]}


# ------------------------------------------------------------------------------- collectors
def collect_kalshi(rows, team_aliases) -> list:
    quotes = []
    events = fetch(core.KALSHI_EVENTS)
    ev_list = (events or {}).get("events") or []
    LOG["kalshi"] = {"events": len(ev_list)}
    for ev in ev_list:
        title = str(ev.get("title") or "")
        if " vs. " not in title:
            continue
        a, b = [x.strip() for x in title.split(" vs. ", 1)]
        fixture, _ = match_fixture(rows, a, b, None, team_aliases)
        if not fixture:
            continue
        data = fetch(core.KALSHI_MARKETS.format(event=urllib.parse.quote(ev["event_ticker"])))
        mkts = (data or {}).get("markets") or []
        if len(mkts) != 2:
            continue
        mids = {}
        for m in mkts:
            bid, ask = m.get("yes_bid_dollars"), m.get("yes_ask_dollars")
            try:
                mid = (float(bid) + float(ask)) / 2.0
            except (TypeError, ValueError):
                continue
            if mid <= 0 or mid >= 1:
                continue
            mids[str(m.get("no_sub_title") or m.get("yes_sub_title"))] = (mid, m)
        if len(mids) != 2:
            continue
        (name1, (mid1, m1)), (name2, (mid2, m2)) = list(mids.items())
        q = quote(rows, "kalshi", "Kalshi (regulated prediction-market exchange)",
                  f"https://kalshi.com/markets/kxcs2game/{str(ev['event_ticker']).lower()}",
                  core.KALSHI_MARKETS.format(event=urllib.parse.quote(ev["event_ticker"])),
                  ev["event_ticker"], name1, name2, 1.0 / mid1, 1.0 / mid2,
                  m1.get("occurrence_datetime"), str(ev.get("title")), team_aliases)
        if q:
            q["raw"] = {"volume_dollars": float(m1.get("volume_fp") or 0),
                        "open_interest": float(m1.get("open_interest_fp") or 0),
                        "market_updated_time": m1.get("updated_time")}
            q["raw_format"] = "yes bid/ask mid in USD (1 contract pays $1)"
            quotes.append(q)
    LOG["kalshi"]["quotes"] = len(quotes)
    return quotes


def collect_melbet(rows, team_aliases) -> list:
    quotes = []
    data = fetch(core.MELBET_FEED)
    events = (data or {}).get("Value") or []
    LOG["melbet"] = {"events": len(events)}
    for ev in events:
        try:
            a, b = ev["O1"], ev["O2"]
        except (KeyError, TypeError):
            continue
        q = quote(rows, "melbet", "Melbet (1xBet platform)", "https://melbet.com/en/line/esports",
                  core.MELBET_FEED, ev.get("I"), a, b,
                  ev.get("C"), ev.get("C2"), ev.get("S"), str(ev.get("L") or ""), team_aliases)
        if q:
            quotes.append(q)
    LOG["melbet"]["quotes"] = len(quotes)
    return quotes


def collect_thunderpick(rows, team_aliases) -> list:
    quotes = []
    base = (f"{core.BO3_API}/matches/?filter%5Bmatches.discipline_id%5D%5Beq%5D=1"
            "&filter%5Bmatches.status%5D%5Bin%5D=upcoming")
    seen = 0
    for page in range(4):
        data = fetch(f"{base}&page%5Boffset%5D={page * 100}")
        results = (data or {}).get("results") if isinstance(data, dict) else None
        if not results:
            break
        seen += len(results)
        for m in results:
            bu = m.get("bet_updates") or {}
            t1, t2 = bu.get("team_1") or {}, bu.get("team_2") or {}
            try:
                da, db = float(t1.get("coeff")), float(t2.get("coeff"))
            except (TypeError, ValueError):
                continue
            if da <= 1.0 or db <= 1.0:
                continue
            q = quote(rows, "thunderpick", "Thunderpick (published through bo3.gg)",
                      f"https://bo3.gg/matches/{m.get('slug')}",
                      f"{core.BO3_API}/matches/?filter%5Bmatches.id%5D%5Beq%5D={m.get('id')}",
                      m.get("id"), t1.get("name") or "", t2.get("name") or "", da, db,
                      m.get("start_date"), "", team_aliases)
            if q:
                quotes.append(q)
        if len(results) < 100:
            break
    LOG["thunderpick"] = {"matches_seen": seen, "quotes": len(quotes)}
    return quotes


def _b64(blob):
    if isinstance(blob, dict) and blob.get("content"):
        return base64.b64decode(blob["content"]).decode("utf-8", "replace")
    return ""


def parse_standings(text, base_dir):
    """Parse Valve's published markdown table (same row format the official file uses)."""
    import re
    rows = []
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)",
                         text or "", re.M):
        rows.append({"standing": int(m.group(1)), "points": int(m.group(2)),
                     "team": m.group(3).strip(), "roster": m.group(4).strip(),
                     "details_path": f"{base_dir}/{m.group(5).strip()}"})
    return rows


def check_valve(rows) -> dict:
    """Confirm which Valve standings file is newest; cache and parse it when it beats ours.

    Details files are fetched only for duplicate organisation names (the roster rule on Method
    needs their latest_match_date) and for teams the board cannot resolve - a handful of requests.
    """
    out = {"checked_utc": now(), "api_url": core.VRS_TREE_API}
    try:
        listing = fetch(core.VRS_TREE_API)
        names = sorted(x["name"] for x in listing
                       if isinstance(x, dict) and str(x.get("name", "")).endswith(".md"))
        globals_ = [n for n in names if n.startswith("standings_global_")]
        out["files_listed"] = len(names)
        out["newest_published"] = globals_[-1] if globals_ else None
        committed = (core.load("data/19d6c262/vrs_global.json", {}) or {}).get("snapshot") or ""
        out["committed_snapshot"] = committed
        if not globals_:
            return out
        snap = globals_[-1].replace("standings_global_", "").replace(".md", "")
        use_snap, use_name = (snap, globals_[-1]) if snap > committed else (committed, f"standings_global_{committed}.md")
        blob = fetch(f"https://api.github.com/repos/{core.VRS_REPO}/contents/live/2026/{use_name}")
        text = _b64(blob)
        teams = parse_standings(text, "live/2026")
        groups: dict = {}
        for t in teams:
            groups.setdefault(core.norm(t["team"]), []).append(t)
        wanted = {k for k, v in groups.items() if len(v) > 1}
        for f in rows:
            for name in (f.get("team_a"), f.get("team_b")):
                key = core.norm(name)
                if key in groups:
                    wanted.add(key)
        for key in sorted(wanted):
            for t in groups[key]:
                path = t["details_path"]
                quoted = urllib.parse.quote(path)
                try:
                    md = _b64(fetch(f"https://api.github.com/repos/{core.VRS_REPO}/contents/{quoted}"))
                    import re
                    dates = re.findall(r"(20\d{2}-\d{2}-\d{2})", md or "")
                    t["latest_match_date"] = max(dates) if dates else None
                except Exception as exc:  # noqa: BLE001
                    t["latest_match_date"] = None
                    t["details_error"] = type(exc).__name__
                t["details_url"] = f"{core.VRS_BLOB}{path}"
        out["snapshot"] = use_snap
        out["teams"] = len(teams)
        out["details_fetched"] = len(wanted)
        out["cached"] = use_snap > committed
        core.dump_json("data/5f903db4/vrs_global.json",
                       {"snapshot": use_snap, "path": f"live/2026/{use_name}",
                        "page_url": f"{core.VRS_BLOB}live/2026/{use_name}",
                        "api_url": f"https://api.github.com/repos/{core.VRS_REPO}/contents/live/2026/{use_name}",
                        "n_teams": len(teams), "teams": teams,
                        "floor": core.vrs_floor({"teams": teams})})
    except Exception as exc:  # noqa: BLE001 - a failed check must not stop the run
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return out


def collect_hotspawn() -> dict:
    out = {"api_url": core.HOTSPAWN_API, "read_utc": now()}
    try:
        data = fetch(core.HOTSPAWN_API)
        rows = data if isinstance(data, list) else (data or {}).get("data") or []
        out["rows"] = len(rows)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return out


def main() -> int:
    rows = fixtures()
    team_aliases = aliases()
    quotes = []
    snap = {"session": "5f903db4", "generated_utc": now(), "fixtures_read": len(rows),
            "hotspawn": collect_hotspawn()}
    for key, fn in (("kalshi", lambda: collect_kalshi(rows, team_aliases)),
                    ("melbet", lambda: collect_melbet(rows, team_aliases)),
                    ("thunderpick", lambda: collect_thunderpick(rows, team_aliases))):
        try:
            quotes.extend(fn() or [])
        except Exception as exc:  # noqa: BLE001
            LOG[key] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    snap["quotes"] = quotes
    snap["vrs"] = check_valve(rows)
    snap["log"] = LOG
    core.dump_json(OUT, snap)
    print(f"collected {len(quotes)} live quotes for {len(rows)} fixtures -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
