"""Session 36495748 — best-effort refresher for the resolution ladder (runner-side).

Runs inside GitHub Actions before build.py. It only machines the *checkable* rungs:
  * Kalshi: list the KXCS2GAME series from Kalshi's public trade API (the same endpoint the
    upstream collectors use) and join to open fixtures that have no strict-board market price,
    requiring (a) both names to match after the project's normalisation and (b) the start time
    embedded in the event ticker (e.g. KXCS2GAME-26OCT211000ILLG2A = 2026-10-21 10:00 Eastern)
    to equal the HotSpawn start within 60 minutes. Mid prices are recorded, never computed picks.
  * bo3.gg: scan the public upcoming-match API (bounded) for the same fixtures and record
    whether Thunderpick publishes a two-way coefficient (bet_updates). A PRICED match is recorded
    as an observation for the audit ledger; the desk's market rung only consumes prices through
    the strict board's stored quotes, so a bo3 price found here becomes visible once the
    upstream board (which scans the same feed) joins it — this probe exists to document the
    re-check, per 'the site should regularly check for updates'.
  * Valve VRS: check whether a global standings file newer than the pinned one exists in
    ValveSoftware/counter-strike_regional_standings; if so, download it next to the pin so the
    builder uses the newest official file. Old pins are kept.
  * HLTV: probe the search page once per unresolved team and log the HTTP status/title only.
    HLTV content is never parsed into a number by automation; identity reasoning stays manual
    (data/36495748/overrides.json).

All failures are recorded in probe.json; the script never raises for a network problem and
never overwrites a previous probe on total failure.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

DATA = ROOT / "data" / "36495748"
UA = {"User-Agent": "Mozilla/5.0 (compatible; hotspawn-picks-research/36495748)", "Accept": "application/json,*/*"}
KALSHI_EVENTS = "https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME&status=open&with_nested_markets=true&limit=200"
BO3 = "https://api.bo3.gg/api/v1/matches?filter%5Bmatches.status%5D%5Bin%5D=upcoming&page%5Boffset%5D={off}"
GITHUB_TREE = "https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/2026"
RAW = "https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/live/2026/{name}"

LOG: dict = {}


def fetch(url: str, want_json=True, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return (json.loads(raw) if want_json else raw.decode("utf-8", "replace")), {"status": resp.status, "bytes": len(raw), "error": None, "url": url}
    except Exception as exc:  # recorded, never raised
        return None, {"status": None, "bytes": 0, "error": f"{type(exc).__name__}: {exc}"[:300], "url": url}


def unresolved_fixtures() -> list[dict]:
    """Open fixtures (union of both boards) with no strict-board market price."""
    our = json.loads((ROOT / "data" / "f7279a54" / "board.json").read_text(encoding="utf-8"))
    cov = json.loads((ROOT / "data" / "fe803b80" / "board.json").read_text(encoding="utf-8"))
    o = {str(r["fixture_id"]): r for r in our.get("open") or []}
    out = []
    for src in list(o.items()) + [(str(r["fixture_id"]), r) for r in cov.get("open") or [] if str(r["fixture_id"]) not in o]:
        fid, r = src
        if (o.get(fid) or {}).get("market"):
            continue
        out.append({"fixture_id": fid, "team_a": r["team_a"], "team_b": r["team_b"], "start_utc": r.get("start_utc")})
    return out


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def ticker_start_utc(ticker: str):
    """KXCS2GAME-26OCT211000XXX -> 2026-10-21 10:00 Eastern -> UTC datetimes for EST/EDT candidates.

    2026 US DST ends 2026-11-01, so Oct 21 is EDT (UTC-4). We accept a fixture match if the
    HotSpawn start is within 60 min of the EDT reading OR the EST reading, and record which.
    """
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})", ticker or "")
    if not m:
        return {}
    yy, mon, dd, hh, mm = int(m.group(1)), _MONTHS.get(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
    if not mon:
        return {}
    base = datetime(2000 + yy, mon, dd, hh, mm, tzinfo=timezone.utc)
    return {"EDT(UTC-4)": base + timedelta(hours=4), "EST(UTC-5)": base + timedelta(hours=5)}


def kalshi_probe(want: list[dict]) -> dict:
    joins = {}
    data, meta = fetch(KALSHI_EVENTS)
    LOG["kalshi"] = meta
    events = (data or {}).get("events") or []
    for w in want:
        hs = core.parse_iso(w.get("start_utc"))
        for ev in events:
            ticker = ev.get("event_ticker") or ""
            title = f"{ev.get('title', '')} {ev.get('sub_title', '')}"
            markets = ev.get("markets") or []
            names = [mk.get("yes_sub_title") or mk.get("subtitle") or "" for mk in markets]
            pair_ok = len(names) >= 2 and core.same_name(names[0], w["team_a"]) is not core.same_name(names[0], w["team_b"]) \
                and core.same_name(names[0] if core.same_name(names[1], w["team_a"]) else names[1], w["team_b"] if core.same_name(names[1], w["team_a"]) else w["team_a"])
            if not pair_ok:
                continue
            starts = ticker_start_utc(ticker)
            hit = None
            if hs:
                for label, cand in starts.items():
                    if abs((cand - hs).total_seconds()) <= 3600:
                        hit = f"ticker time as {label} = {cand.strftime('%Y-%m-%dT%H:%M:%SZ')}, HotSpawn start {w['start_utc']}"
                        break
            if not hit:
                continue
            mids = {}
            for mk in markets[:2]:
                nm = mk.get("yes_sub_title") or mk.get("subtitle") or ""
                bid, ask = mk.get("yes_bid"), mk.get("yes_ask")
                if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and ask > 0:
                    mids[nm] = round((float(bid) + float(ask)) / 2.0, 2)
            if len(mids) == 2:
                joins[w["fixture_id"]] = {
                    "source_name": "Kalshi (exchange, runner probe)", "event_ticker": ticker,
                    "url": "https://kalshi.com/markets/kxcs2game/" + ticker.lower(),
                    "start_verified": hit, "mid_cents": mids,
                    "note": "Joined by the 36495748 refresher: both names matched after normalisation and the ticker-embedded start equals the HotSpawn start. Verify on the event page.",
                    "read_ref": None, "title_seen": title[:120]}
    LOG["kalshi_joins"] = sorted(joins)
    return joins


def bo3_probe(want: list[dict], pages=40) -> dict:
    seen, found = 0, {}
    listed_unpriced: set = set()
    want_keys = {tuple(sorted((core.norm(w["team_a"]), core.norm(w["team_b"])))): w for w in want}
    for off in range(0, pages * 10, 10):
        data, meta = fetch(BO3.format(off=off))
        if meta.get("error"):
            LOG["bo3gg"] = {**meta, "matches_seen": seen}
            break
        results = (data or {}).get("results") or []
        seen += len(results)
        for mk in results:
            bu = mk.get("bet_updates") or {}
            t1, t2 = (bu.get("team_1") or {}), (bu.get("team_2") or {})
            key = tuple(sorted((core.norm(t1.get("name")), core.norm(t2.get("name")))))
            w = want_keys.get(key)
            c1, c2 = t1.get("coeff"), t2.get("coeff")
            if w and isinstance(c1, (int, float)) and isinstance(c2, (int, float)) and c1 > 1 and c2 > 1:
                found[w["fixture_id"]] = {"slug": mk.get("slug"), "start_date": mk.get("start_date"),
                                          "coeff_first": c1, "coeff_second": c2,
                                          "names": [t1.get("name"), t2.get("name")],
                                          "url": "https://bo3.gg/matches/" + str(mk.get("slug"))}
        if len(found) >= len(want_keys):
            break
    LOG["bo3gg"] = {"matches_seen": seen, "priced_observations": sorted(found)}
    return found


def vrs_refresh() -> None:
    pinned = sorted(p.name for p in DATA.glob("vrs_standings_global_*.md"))
    items, meta = fetch(GITHUB_TREE)
    LOG["valve_vrs"] = {**meta, "pinned_before": pinned}
    if not isinstance(items, list):
        return
    names = sorted(i.get("name", "") for i in items if (i.get("name") or "").startswith("standings_global_"))
    if not names:
        return
    newest = "vrs_" + names[-1]
    LOG["valve_vrs"]["upstream_newest"] = names[-1]
    if newest not in pinned:
        text, m2 = fetch(RAW.format(name=names[-1]), want_json=False)
        if text and "Standings as of" in text:
            (DATA / newest).write_text(text, encoding="utf-8")
            LOG["valve_vrs"]["downloaded"] = newest


def hltv_probe(want: list[dict]) -> None:
    teams = sorted({w["team_a"] for w in want} | {w["team_b"] for w in want})[:8]
    probes = {}
    for t in teams:
        url = "https://www.hltv.org/search?query=" + urllib.request.quote(t)
        text, meta = fetch(url, want_json=False, timeout=20)
        title = None
        if text:
            m = re.search(r"<title>([^<]+)</title>", text)
            title = m.group(1)[:120] if m else None
        probes[t] = {**meta, "title": title}
    LOG["hltv"] = probes


def main() -> int:
    try:
        want = unresolved_fixtures()
    except Exception as exc:
        print(f"cannot read upstream boards: {exc}")
        return 0  # never block the build on probe failures
    probe = {"session": "36495748", "generated_utc": core.now_iso(),
             "fixtures_without_strict_market": [w["fixture_id"] for w in want],
             "kalshi_joins": {}, "bo3_observations": {}}
    if want:
        probe["kalshi_joins"] = kalshi_probe(want)
        probe["bo3_observations"] = bo3_probe(want)
        hltv_probe(want)
    vrs_refresh()
    probe["log"] = LOG
    any_ok = any((v or {}).get("status") == 200 for v in LOG.values() if isinstance(v, dict))
    out = DATA / "probe.json"
    if any_ok or not out.exists():
        out.write_text(json.dumps(probe, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"probe written: {len(want)} unpriced fixtures, kalshi joins {sorted(probe['kalshi_joins'])}, "
              f"bo3 priced {sorted(probe['bo3_observations'])}")
    else:
        print("all probes failed; previous probe.json kept")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
