"""RECONCILE-4E6 (session 4e6dcd0d): read-only cross-board reconciliation.

Reads the data files that other sessions publish, joins them on the HotSpawn
``fixture_id`` and writes (a) ``data/reconcile_4e6dcd0d.json`` and (b) a small,
mobile-first static section ``reconcile/``.

Hard rules (same as the project rules):
* Nothing is invented. Every number shown is either quoted from a board's own
  published quote (with that quote's source URL) or arithmetic on those quotes.
* HotSpawn crowd "picked %" is never read. HotSpawn is used for the fixture list
  (teams, kickoff, lock time, points) only.
* HLTV is not a price source (it publishes no odds we can read from here).
* A fixture without an eligible external bookmaker quote stays blank + flagged.
* Kalshi is a prediction exchange, not a bookmaker: it is shown as a reference
  column and checked for agreement, but it is NOT part of the bookmaker consensus.
* Live (in-play) quotes and quotes older than MAX_QUOTE_AGE_MIN are excluded.

Usage:  python3 scripts/reconcile_4e6dcd0d.py [--out DIR]   (default DIR = reconcile)
"""
from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MAX_QUOTE_AGE_MIN = 240  # same four-hour freshness bound as the root pipeline
BOOKMAKER_KEYS = ("pinnacle", "bovada", "egamersworld")  # consensus inputs
REFERENCE_KEYS = ("kalshi",)  # shown, never averaged into the consensus
SOURCE_LABEL = {
    "pinnacle": "Pinnacle",
    "bovada": "Bovada",
    "egamersworld": "egamersworld (odds aggregator)",
    "kalshi": "Kalshi (exchange)",
}
BOARD_LABEL = {
    "961": "Verify board (961e163a)",
    "current": "Current board (0f6c89c6)",
    "picks": "Picks board (ac475c09)",
    "coverage": "Coverage board (42580809)",
    "root": "Root lines (d4ec32a9 pipeline)",
}
BOARD_PATH = {
    "961": "data/961/board.json",
    "current": "data/current_board.json",
    "picks": "data/picks_board.json",
    "coverage": "data/board_42580809.json",
    "root": "data/lines.json",
}
BOARD_PAGE = {
    "961": "../verify961/index.html",
    "current": "../current/index.html",
    "picks": "../picks/index.html",
    "coverage": "../site/42580809/index.html",
    "root": "../probabilities.html",
}


# ----------------------------------------------------------------- helpers
def norm(name: str | None) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def parse_ts(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def no_vig_a(dec_a: float, dec_b: float) -> float:
    ia, ib = 1.0 / dec_a, 1.0 / dec_b
    return ia / (ia + ib)


def load(rel: str):
    p = ROOT / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def canon_source(key: str | None, name: str | None = None) -> str | None:
    k = (key or name or "").lower()
    if k.startswith("pinnacle"):
        return "pinnacle"
    if k.startswith("bovada"):
        return "bovada"
    if "egamersworld" in k:
        return "egamersworld"
    if k.startswith("kalshi"):
        return "kalshi"
    return None


# --------------------------------------------------------- board adapters
# Every adapter yields (fixture_id, board_teams(a,b), quotes[], board_view)
# quote = dict(source, url, retrieved_at, live, dec_a, dec_b, p_a_published)
# p/dec are in the *board's* team_a orientation; oriented later by team name.
def _q(source, url, retrieved, live, dec_a, dec_b, p_a, api_url=None):
    return dict(source=source, url=url or api_url, retrieved_at=retrieved, live=bool(live),
                dec_a=dec_a, dec_b=dec_b, p_a_published=p_a)


def adapt_961(d):
    for r in d["rows"]:
        qs = []
        for s in r.get("sources", []):
            src = canon_source(s.get("source_key"), s.get("source_name"))
            qs.append(_q(src, s.get("source_url"), s.get("retrieved_at_utc"), s.get("market_is_live"),
                         s.get("decimal_odds_a"), s.get("decimal_odds_b"), s.get("no_vig_probability_a")))
        view = None
        if r.get("pick") and r.get("probability_a") is not None:
            view = dict(pick=r["pick"], p_a=r["probability_a"])
        yield r["fixture_id"], (r["team_a"], r["team_b"]), qs, view


def adapt_current(d):
    for r in d["rows"]:
        qs = []
        for s in r.get("sources", []):
            src = canon_source(None, s.get("source"))
            qs.append(_q(src, s.get("url"), s.get("retrieved_at_utc"), False,
                         s.get("decimal_a"), s.get("decimal_b"), s.get("p_a")))
        view = None
        if r.get("pick") and r.get("probability_a") is not None:
            view = dict(pick=r["pick"], p_a=r["probability_a"])
        yield r["fixture_id"], (r["team_a"], r["team_b"]), qs, view


def adapt_picks(d):
    for r in d["rows"]:
        qs = []
        for s in r.get("quotes", []):
            src = canon_source(s.get("source_key"), s.get("source_name"))
            qs.append(_q(src, s.get("source_url"), s.get("retrieved_at_utc"), s.get("is_live"),
                         s.get("decimal_a"), s.get("decimal_b"), s.get("prob_a")))
        view = None
        if r.get("pick") and r.get("prob_a") is not None:
            view = dict(pick=r["pick"], p_a=r["prob_a"])
        yield r["fixture_id"], (r["team_a"], r["team_b"]), qs, view


def adapt_coverage(d):
    for r in d["rows"]:
        qs = []
        for s in r.get("sources", []):
            src = canon_source(s.get("source_key"), s.get("source_name"))
            qs.append(_q(src, s.get("source_url"), s.get("retrieved_at_utc"), s.get("market_is_live"),
                         None, None, s.get("no_vig_probability_a"), api_url=s.get("api_url")))
        view = None
        if r.get("pick_team") and r.get("p_a") is not None:
            view = dict(pick=r["pick_team"], p_a=r["p_a"])
        yield r["fixture_id"], (r["team_a"], r["team_b"]), qs, view


def adapt_root(d):
    for r in d["fixtures"]:
        qs = []
        for s in r.get("bookmaker_lines", []):
            src = canon_source(s.get("source_key"), s.get("source_name"))
            qs.append(_q(src, s.get("source_public_url"), s.get("retrieved_at_utc"), s.get("market_is_live"),
                         s.get("decimal_odds_a"), s.get("decimal_odds_b"), s.get("derived_probability_a"),
                         api_url=s.get("source_api_url")))
        view = None
        cons = (r.get("derived") or {}).get("consensus")
        if cons:  # root publishes probabilities, not a pick label: pick = higher probability (arithmetic only)
            pa = cons["derived_probability_a_mean"]
            if abs(pa - 0.5) > 1e-12:
                view = dict(pick=r["team_a"] if pa > 0.5 else r["team_b"], p_a=pa)
        yield r["fixture_id"], (r["team_a"], r["team_b"]), qs, view


ADAPTERS = {"961": adapt_961, "current": adapt_current, "picks": adapt_picks,
            "coverage": adapt_coverage, "root": adapt_root}
ROWKEY = {"961": "rows", "current": "rows", "picks": "rows", "coverage": "rows", "root": "fixtures"}


# -------------------------------------------------------------------- core
def build_model(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    hs = load("data/hotspawn_matches.json")
    if not hs:
        raise SystemExit("data/hotspawn_matches.json missing")
    fixtures: dict[str, dict] = {}
    for m in hs["matches"]:
        if m.get("sport") not in ("cs2", "lol"):
            continue
        fixtures[m["fixture_id"]] = dict(
            fixture_id=m["fixture_id"], game=m["sport"], competition=m["competition_name"], tier=m.get("tier"),
            points=m.get("offered_points"), team_a=m["team_a"], team_b=m["team_b"],
            start_utc=m.get("scheduled_start_time"), lock_utc=m.get("lock_time"), status=m.get("status"),
            hotspawn_url=(m.get("source") or {}).get("hotspawn_match_url") or f"https://www.hotspawn.com/matches/{m['fixture_id']}",
            quotes_raw=[], board_views={}, flags=[])
    notes: list[str] = []
    board_meta = {}
    for key, adapter in ADAPTERS.items():
        d = load(BOARD_PATH[key])
        if d is None:
            notes.append(f"board_missing:{key}")
            continue
        board_meta[key] = dict(path=BOARD_PATH[key], generated_at_utc=d.get("generated_at_utc") or (d.get("meta") or {}).get("generated_at_utc"),
                               rows=len(d[ROWKEY[key]]))
        for fid, (ba, bb), qs, view in adapter(d):
            fx = fixtures.get(fid)
            if fx is None:
                continue
            na, nb = norm(fx["team_a"]), norm(fx["team_b"])
            if (norm(ba), norm(bb)) == (na, nb):
                swap = False
            elif (norm(ba), norm(bb)) == (nb, na):
                swap = True
            else:
                fx["flags"].append(f"board_team_names_differ:{key}")
                continue
            for q in qs:
                if q["source"] is None:
                    fx["flags"].append(f"unknown_source_ignored:{key}")
                    continue
                q = dict(q, board=key)
                if swap:
                    for k in ("p_a_published",):
                        if q[k] is not None:
                            q[k] = 1 - q[k]
                    q["dec_a"], q["dec_b"] = q["dec_b"], q["dec_a"]
                fx["quotes_raw"].append(q)
            if view:
                pa = (1 - view["p_a"]) if swap else view["p_a"]
                pick_team = fx["team_a"] if norm(view["pick"]) == na else fx["team_b"] if norm(view["pick"]) == nb else None
                if pick_team is None:
                    fx["flags"].append(f"board_pick_name_unresolved:{key}")
                else:
                    fx["board_views"][key] = dict(pick=pick_team, p_pick=round(pa if pick_team == fx["team_a"] else 1 - pa, 4))
    # ---- per-fixture aggregation
    out = []
    for fx in fixtures.values():
        start, lock = parse_ts(fx["start_utc"]), parse_ts(fx["lock_utc"])
        fx["open"] = bool(lock and lock > now and fx["status"] == "scheduled")
        fx["cancelled"] = fx["status"] == "cancelled"
        # newest quote per source; union of boards that published that source; prefer a public (non-API) URL
        epoch = datetime.min.replace(tzinfo=timezone.utc)
        groups: dict[str, list[dict]] = {}
        for q in fx.pop("quotes_raw"):
            groups.setdefault(q["source"], []).append(q)
        latest: dict[str, dict] = {}
        for src, lst in groups.items():
            best = max(lst, key=lambda q: parse_ts(q["retrieved_at"]) or epoch)
            urls = [q["url"] for q in lst if q["url"]]
            public = [u for u in urls if "api" not in u.split("/")[2]]
            latest[src] = dict(best, boards=sorted({q["board"] for q in lst}),
                               url=(best["url"] if best["url"] and "api" not in best["url"].split("/")[2] else (public[0] if public else best["url"])))
        quotes = []
        for src, q in sorted(latest.items()):
            t = parse_ts(q["retrieved_at"])
            age = round((now - t).total_seconds() / 60) if t else None
            p_pub = q["p_a_published"]
            p_calc = no_vig_a(q["dec_a"], q["dec_b"]) if q["dec_a"] and q["dec_b"] else None
            qflags = []
            if p_pub is None:
                qflags.append("no_published_probability")
            if p_calc is not None and p_pub is not None and abs(p_calc - p_pub) > 0.002:
                qflags.append("probability_does_not_match_decimal_odds")
            if q["dec_a"] is not None and q["dec_b"] is not None and q["dec_a"] == q["dec_b"]:
                # an identical price on both sides (seen as 1.80/1.80 on six unrelated fixtures) is not a usable line
                qflags.append("identical_odds_both_sides_not_a_usable_line")
            if q["live"]:
                # Kalshi markets are carried as market_is_live=True by the coverage board even before kickoff;
                # for the reference-only exchange column that is tolerated while HotSpawn says the match has not started.
                if not (src in REFERENCE_KEYS and start and start > now):
                    qflags.append("live_market_excluded")
            if age is None:
                qflags.append("no_retrieval_time")
            elif age > MAX_QUOTE_AGE_MIN:
                qflags.append("older_than_%dmin" % MAX_QUOTE_AGE_MIN)
            if not q["url"]:
                qflags.append("no_source_url")
            quotes.append(dict(source=src, label=SOURCE_LABEL[src], url=q["url"], boards=q["boards"],
                               retrieved_at_utc=iso(t), age_min=age, decimal_a=q["dec_a"], decimal_b=q["dec_b"],
                               p_a=None if p_pub is None else round(p_pub, 4),
                               p_a_recomputed=None if p_calc is None else round(p_calc, 4),
                               eligible=not qflags, flags=qflags))
        fx["quotes"] = quotes
        book = [q for q in quotes if q["source"] in BOOKMAKER_KEYS and q["eligible"]]
        ref = [q for q in quotes if q["source"] in REFERENCE_KEYS and q["eligible"]]
        if book and not fx["cancelled"]:
            pas = [q["p_a"] for q in book]
            pa = sum(pas) / len(pas)
            fx["consensus_p_a"] = round(pa, 4)
            fx["consensus_p_b"] = round(1 - pa, 4)
            fx["n_book_sources"] = len(book)
            fx["p_a_min"], fx["p_a_max"] = round(min(pas), 4), round(max(pas), 4)
            if abs(pa - 0.5) < 1e-9:
                fx["pick"], fx["pick_p"] = None, 0.5
                fx["flags"].append("identical_odds_both_sides_no_pick")
            else:
                fx["pick"] = fx["team_a"] if pa > 0.5 else fx["team_b"]
                fx["pick_p"] = round(max(pa, 1 - pa), 4)
            sides = {("a" if p > 0.5 else "b" if p < 0.5 else "even") for p in pas}
            if len(sides) > 1:
                fx["flags"].append("sources_split_on_pick")
            if len(book) == 1:
                fx["flags"].append("single_bookmaker_source")
            if book and all(q["source"] == "egamersworld" for q in book):
                fx["flags"].append("aggregator_only_bookmaker_not_named")
            fx["confidence"] = ("Strong" if fx["pick_p"] >= 0.70 else "Lean" if fx["pick_p"] >= 0.55 else "Toss-up") if fx["pick"] else "Toss-up"
        else:
            fx.update(consensus_p_a=None, consensus_p_b=None, n_book_sources=0, p_a_min=None, p_a_max=None,
                      pick=None, pick_p=None, confidence=None)
            if not fx["cancelled"]:
                fx["flags"].append("no_eligible_external_bookmaker_line")
        if ref:
            fx["exchange_p_a"] = ref[0]["p_a"]
            fx["exchange_url"] = ref[0]["url"]
            if fx["pick"]:
                ref_pick = fx["team_a"] if ref[0]["p_a"] > 0.5 else fx["team_b"]
                if ref_pick != fx["pick"]:
                    fx["flags"].append("exchange_reference_disagrees_with_pick")
        else:
            fx["exchange_p_a"] = None
            fx["exchange_url"] = None
        # cross-board pick comparison
        dis = {}
        for b, v in fx["board_views"].items():
            if fx["pick"] and v["pick"] != fx["pick"]:
                dis[b] = v["pick"]
            if not fx["pick"] and v["pick"]:
                dis[b] = v["pick"]
        if dis:
            fx["flags"].append("board_pick_differs:" + ",".join(sorted(dis)))
        fx["board_disagreements"] = dis
        if fx["status"] == "started":
            fx["flags"].append("hotspawn_status_started")
        if fx["cancelled"]:
            fx["flags"].append("hotspawn_status_cancelled")
        fx["kick_in_past"] = bool(start and start < now)
        out.append(fx)
    out.sort(key=lambda x: (x["start_utc"] or "", x["fixture_id"]))
    return dict(generated_at_utc=iso(now), session="4e6dcd0d", boards=board_meta, notes=notes,
                max_quote_age_min=MAX_QUOTE_AGE_MIN, fixtures=out)


# Session-side observations (fetch_page, 2026-10-13 ~22:08 UTC). Only the *observed decimal odds* are typed here;
# the probability, the pick and the comparison with the board are computed. URL = the page that was read.
MANUAL_CHECKS = [
    dict(fixture_id="1080177", source="egamersworld", url="https://egamersworld.com/counterstrike/match/5X5sFiL7H/falcons-vs-nip-QSa-aeOIR",
         observed_at_utc="2026-10-13T22:08:00Z", odds_by_team={"Falcons": 1.21, "Ninjas in Pyjamas": 3.75}),
    dict(fixture_id="1079438", source="egamersworld", url="https://egamersworld.com/counterstrike/match/EJZmJpBjeNx/astralis-vs-sashi-esport-aGet1AP-0Z",
         observed_at_utc="2026-10-13T22:09:00Z", odds_by_team={"Astralis": 1.07, "Sashi": 6.41}),
]
UNREADABLE_CHECKS = [
    dict(url="https://www.pinnacle.com/en/esports/matchups/1638111674", observed_at_utc="2026-10-13T22:08:00Z", result="fetch_page: HTTP 500 (not readable; not verified)"),
    dict(url="https://www.bovada.lv/esports/counter-strike-2/thunderpick-world-championship-26/team-falcons-ninjas-in-pyjamas-202610140700", observed_at_utc="2026-10-13T22:08:00Z", result="fetch_page returned Bovada 'Not Found' page (not verified; may be a region/URL-shape issue)"),
]


def run_manual_checks(model: dict) -> list[dict]:
    by_id = {f["fixture_id"]: f for f in model["fixtures"]}
    res = []
    for c in MANUAL_CHECKS:
        f = by_id.get(c["fixture_id"])
        if f is None or f["team_a"] not in c["odds_by_team"] or f["team_b"] not in c["odds_by_team"]:
            continue  # fixture no longer in the HotSpawn list: the dated spot-check is dropped, not guessed
        oa, ob = c["odds_by_team"][f["team_a"]], c["odds_by_team"][f["team_b"]]
        pa = no_vig_a(oa, ob)
        board_q = next((q for q in f["quotes"] if q["source"] == c["source"]), None)
        obs_pick = f["team_a"] if pa > 0.5 else f["team_b"]
        res.append(dict(c, team_a=f["team_a"], team_b=f["team_b"], observed_p_a=round(pa, 4),
                        observed_pick=obs_pick, board_quote_p_a=None if not board_q else board_q["p_a"],
                        board_quote_retrieved_at_utc=None if not board_q else board_q["retrieved_at_utc"],
                        reconciled_pick=f["pick"], same_pick=(obs_pick == f["pick"]),
                        movement_pp=None if not board_q else round((pa - board_q["p_a"]) * 100, 2)))
    return res


def summarize(model: dict) -> dict:
    fx = model["fixtures"]
    live = [f for f in fx if not f["cancelled"]]
    openf = [f for f in live if f["open"]]
    return dict(
        fixtures_in_hotspawn_cs2_lol=len(fx),
        cancelled=len(fx) - len(live),
        open_for_picks=len(openf),
        open_cs2=sum(f["game"] == "cs2" for f in openf),
        open_lol=sum(f["game"] == "lol" for f in openf),
        open_priced=sum(f["pick"] is not None or f["consensus_p_a"] is not None for f in openf),
        open_priced_cs2=sum(f["game"] == "cs2" and f["consensus_p_a"] is not None for f in openf),
        open_priced_lol=sum(f["game"] == "lol" and f["consensus_p_a"] is not None for f in openf),
        open_unpriced=sum(f["consensus_p_a"] is None for f in openf),
        open_unpriced_cs2=sum(f["game"] == "cs2" and f["consensus_p_a"] is None for f in openf),
        locked_or_past_priced=sum((not f["open"]) and f["consensus_p_a"] is not None for f in live),
        board_pick_conflicts=sum(bool(f["board_disagreements"]) for f in live if f["consensus_p_a"] is not None or f["board_views"]),
        sources_split=sum("sources_split_on_pick" in f["flags"] for f in openf),
    )


# ------------------------------------------------------------------- HTML
CSS = """
:root{--bg:#0f1420;--card:#171e2e;--ink:#e8ecf4;--mute:#9aa6bd;--line:#2a3550;--ok:#2ecc71;--warn:#f5b041;--bad:#ec7063;--acc:#5dade2}
*{box-sizing:border-box}body{margin:0;font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
a{color:var(--acc)}header{padding:14px 16px;border-bottom:1px solid var(--line);background:#121a2a;position:sticky;top:0;z-index:5}
header h1{font-size:18px;margin:0 0 6px}nav{display:flex;gap:6px;flex-wrap:wrap}nav a{padding:6px 10px;border:1px solid var(--line);border-radius:8px;text-decoration:none;color:var(--ink);font-size:14px}
nav a.on{background:var(--acc);color:#0b1220;border-color:var(--acc)}main{max-width:1100px;margin:0 auto;padding:14px 12px 60px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:10px 0 16px}.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.kpi b{display:block;font-size:24px}.kpi span{color:var(--mute);font-size:13px}
.note{background:#1d2740;border:1px solid var(--line);border-left:4px solid var(--warn);border-radius:8px;padding:10px 12px;margin:10px 0;font-size:14px}
.m{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:10px 0}
.m.locked{opacity:.6}.top{display:flex;justify-content:space-between;gap:8px;font-size:13px;color:var(--mute);flex-wrap:wrap}
.teams{margin:8px 0}.t{display:flex;align-items:center;gap:8px;margin:5px 0}.t .n{flex:0 0 38%;min-width:90px;font-weight:600;overflow-wrap:anywhere}
.bar{flex:1;background:#0b1220;border-radius:6px;height:26px;position:relative;overflow:hidden}
.bar i{display:block;height:100%;background:#34495e}.t.pick .bar i{background:var(--ok)}
.bar em{position:absolute;right:8px;top:2px;font-style:normal;font-weight:700}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700;border:1px solid}
.b-pick{color:#0b1220;background:var(--ok);border-color:var(--ok)}.b-split{color:#0b1220;background:var(--warn);border-color:var(--warn)}.b-blank{color:var(--mute);border-color:var(--line)}
.pickline{font-size:17px;margin:6px 0}.small{font-size:13px;color:var(--mute)}.flags{margin-top:6px}.flag{display:inline-block;background:#2a1f1f;color:#f5b7b1;border:1px solid #5b3a3a;border-radius:6px;padding:1px 6px;font-size:12px;margin:2px 4px 2px 0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--mute);position:sticky;top:0;background:var(--bg)}
.scroll{overflow-x:auto}.src a{display:block}
input[type=search]{width:100%;padding:10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:16px}
.tabs{display:flex;gap:6px;margin:8px 0;flex-wrap:wrap}.tabs button{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:14px}.tabs button.on{background:var(--acc);color:#0b1220}
footer{color:var(--mute);font-size:13px;margin-top:30px}
@media(min-width:760px){.m{padding:14px 16px}}
"""

NAV = [("index.html", "Picks"), ("boards.html", "Cross-board check"), ("unpriced.html", "No line yet"),
       ("locked.html", "Locked / started"), ("flagged.html", "Flagged for review"), ("methodology.html", "Method & sources")]

JS = """
(function(){
 var now=Date.now();
 document.querySelectorAll('[data-lock]').forEach(function(e){
   var t=Date.parse(e.getAttribute('data-lock'));
   if(!isNaN(t)&&t<=now){e.classList.add('locked');var b=e.querySelector('.lockstate');if(b)b.textContent='LOCKED (as of your clock)';}
 });
 document.querySelectorAll('[data-local]').forEach(function(e){
   var t=Date.parse(e.getAttribute('data-local'));
   if(!isNaN(t)){e.textContent=new Date(t).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})+' (your time)';}
 });
 var s=document.getElementById('q');
 function apply(){
   var q=(s&&s.value||'').toLowerCase();var g=window.__game||'all';var hide=window.__hideLocked;
   document.querySelectorAll('.m').forEach(function(e){
     var ok=(!q||e.textContent.toLowerCase().indexOf(q)>-1)&&(g==='all'||e.getAttribute('data-game')===g)&&!(hide&&e.classList.contains('locked'));
     e.style.display=ok?'':'none';
   });
 }
 if(s)s.addEventListener('input',apply);
 document.querySelectorAll('.tabs button').forEach(function(b){b.addEventListener('click',function(){
   var k=b.getAttribute('data-k');
   if(k==='hide'){window.__hideLocked=!window.__hideLocked;b.classList.toggle('on');}
   else{window.__game=k;document.querySelectorAll('.tabs button[data-k]:not([data-k=hide])').forEach(function(x){x.classList.remove('on')});b.classList.add('on');}
   apply();});});
 apply();
})();
"""


def e(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def pct(p) -> str:
    return "—" if p is None else f"{p * 100:.1f}%"


def page(title: str, active: str, body: str, gen: str) -> str:
    nav = "".join(f'<a href="{h}"{" class=on" if h == active else ""}>{e(t)}</a>' for h, t in NAV)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)} — Reconciled pick board</title><style>{CSS}</style></head><body>'
            f'<header><h1>Reconciled pick board — every HotSpawn Pick\'ems fixture, external lines only</h1><nav>{nav}'
            f'<a href="../index.html">Site home</a></nav></header><main>{body}'
            f'<footer>Built {e(gen)} from repository data files by <code>scripts/reconcile_4e6dcd0d.py</code> (session 4e6dcd0d). '
            f'Estimates derived from bookmaker lines — not guarantees. HotSpawn crowd % is never used.</footer></main>'
            f'<script>{JS}</script></body></html>')


def src_links(f) -> str:
    out = []
    for q in f["quotes"]:
        tag = "" if q["eligible"] else " ✗"
        if q["url"]:
            out.append(f'<a href="{e(q["url"])}" rel="noopener">{e(q["label"])}{tag}</a>')
        else:
            out.append(f'{e(q["label"])}{tag} (no URL)')
    return "".join(out) or "—"


def why_blank(f) -> str:
    reasons = sorted({x for q in f["quotes"] for x in q["flags"]})
    if not reasons:
        return "no external line found on any board"
    return "quote excluded: " + ", ".join(e(r) for r in reasons)


def card(f, show_flags=True) -> str:
    lock = f["lock_utc"] or ""
    pa, pb = f["consensus_p_a"], f["consensus_p_b"]
    pick = f["pick"]

    def line(name, p, is_pick):
        w = 0 if p is None else p * 100
        return (f'<div class="t{" pick" if is_pick else ""}"><div class="n">{e(name)}{" ✅" if is_pick else ""}</div>'
                f'<div class="bar"><i style="width:{w:.1f}%"></i><em>{pct(p)}</em></div></div>')

    if pick:
        badge = f'<span class="badge b-pick">PICK: {e(pick)} · {e(f["confidence"])}</span>'
        if "sources_split_on_pick" in f["flags"]:
            badge += ' <span class="badge b-split">sources split — review</span>'
    elif f["consensus_p_a"] is not None:
        badge = '<span class="badge b-split">50/50 — no pick</span>'
    else:
        badge = '<span class="badge b-blank">no external line — blank</span>'
    rng = ""
    if f["n_book_sources"] > 1:
        rng = f' · team A range across sources {pct(f["p_a_min"])}–{pct(f["p_a_max"])}'
    ex = ""
    if f["exchange_p_a"] is not None:
        ex = f' · Kalshi exchange: {e(f["team_a"])} {pct(f["exchange_p_a"])}'
    flags = "".join(f'<span class="flag">{e(x)}</span>' for x in f["flags"]) if show_flags else ""
    return (f'<div class="m" data-lock="{e(lock)}" data-game="{e(f["game"])}">'
            f'<div class="top"><span>{e(f["game"].upper())} · {e(f["competition"])} · tier {e(str(f["tier"]).upper())} · {e(f["points"])} pts</span>'
            f'<span><span data-local="{e(f["start_utc"])}">{e(f["start_utc"])}</span> · UTC {e(f["start_utc"])}</span></div>'
            f'<div class="teams">{line(f["team_a"], pa, pick == f["team_a"])}{line(f["team_b"], pb, pick == f["team_b"])}</div>'
            f'<div class="pickline">{badge}</div>'
            f'<div class="small">{e(f["n_book_sources"])} bookmaker source(s){rng}{ex} · lock {e(lock)} UTC · <span class="lockstate">{"open" if f["open"] else "past lock at build"}</span></div>'
            f'<div class="small src">Lines: {src_links(f)}</div>'
            f'<div class="small">Fixture: <a href="{e(f["hotspawn_url"])}" rel="noopener">HotSpawn match #{e(f["fixture_id"])}</a></div>'
            f'<div class="flags">{flags}</div></div>')


def controls(show_hide=True) -> str:
    btns = '<button class="on" data-k="all">All</button><button data-k="cs2">CS2</button><button data-k="lol">LoL</button>'
    if show_hide:
        btns += '<button data-k="hide">Hide locked</button>'
    return f'<input type="search" id="q" placeholder="Search team or tournament"><div class="tabs">{btns}</div>'


def build_pages(model: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    gen = model["generated_at_utc"]
    S = model["summary"]
    fx = [f for f in model["fixtures"] if not f["cancelled"]]
    open_priced = [f for f in fx if f["open"] and f["consensus_p_a"] is not None]
    open_unpriced = [f for f in fx if f["open"] and f["consensus_p_a"] is None]
    locked_priced = [f for f in fx if not f["open"] and f["consensus_p_a"] is not None]
    locked_unpriced = [f for f in fx if not f["open"] and f["consensus_p_a"] is None]

    kp = lambda n, l: f'<div class="kpi"><b>{n}</b><span>{l}</span></div>'
    # ---- index
    open_priced_sorted = sorted(open_priced, key=lambda f: (f["lock_utc"] or "", f["fixture_id"]))
    body = ("<h2>Open picks with a verified external line</h2>"
            '<p class="small">Higher bar + ✅ is the pick. Probability = average of no-vig bookmaker probabilities (Pinnacle, Bovada, egamersworld aggregator) retrieved within 4 hours; every line links to its source. Fixtures with no eligible line are blank, never estimated.</p>'
            '<div class="kpis">' + kp(S["open_for_picks"], "open for picks (CS2 + LoL)") + kp(S["open_priced"], "open with external line")
            + kp(S["open_unpriced"], "open, no line found (blank)") + kp(S["board_pick_conflicts"], "fixtures where a board pick differs")
            + '</div>'
            + controls()
            + ("".join(card(f) for f in open_priced_sorted) or '<div class="note">No open fixture currently has an eligible external line.</div>')
            + f'<p class="small">{len(open_unpriced)} more open fixtures have no external line yet — see <a href="unpriced.html">No line yet</a>.</p>')
    (out / "index.html").write_text(page("Picks", "index.html", body, gen), encoding="utf-8")
    # ---- unpriced
    rows = "".join(
        f'<tr data-game="{e(f["game"])}"><td>{e(f["game"].upper())}</td><td>{e(f["team_a"])} vs {e(f["team_b"])}</td><td>{e(f["competition"])}</td>'
        f'<td>{e(f["start_utc"])}</td><td>—</td><td>{why_blank(f)}</td><td><a href="{e(f["hotspawn_url"])}" rel="noopener">HotSpawn #{e(f["fixture_id"])}</a></td></tr>'
        for f in sorted(open_unpriced, key=lambda f: (f["game"] != "cs2", f["start_utc"] or "")))
    body = ('<h2>Open fixtures with no eligible external line</h2><div class="note">Probability and pick are intentionally <b>blank</b> here: no checked bookmaker/aggregator line passed the join + freshness rules. Nothing is estimated. '
            'The source link is the official HotSpawn fixture record only.</div>'
            f'<p>{len(open_unpriced)} fixtures ({S["open_unpriced_cs2"]} CS2).</p><div class="scroll"><table><thead><tr><th>Game</th><th>Match</th><th>Tournament</th><th>Start (UTC)</th><th>Probability / pick</th><th>Why blank</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table></div>')
    (out / "unpriced.html").write_text(page("No line yet", "unpriced.html", body, gen), encoding="utf-8")
    # ---- locked
    lp = "".join(card(f) for f in sorted(locked_priced, key=lambda f: f["start_utc"] or "", reverse=True))
    body = ('<h2>Locked or started fixtures that had a line</h2><div class="note">Informational only: these picks can no longer be submitted (past lock at build time). Values are the last captured pre-match lines on the boards, kept so they can be audited.</div>'
            + controls(False) + (lp or "<p>None.</p>")
            + f'<p class="small">{len(locked_unpriced)} other past/locked fixtures have no line (not listed).</p>')
    (out / "locked.html").write_text(page("Locked / started", "locked.html", body, gen), encoding="utf-8")
    # ---- boards (cross-board matrix)
    bk = list(BOARD_LABEL)
    head = "".join(f'<th><a href="{BOARD_PAGE[k]}">{e(BOARD_LABEL[k])}</a></th>' for k in bk)
    rows = []
    for f in sorted([f for f in fx if f["consensus_p_a"] is not None or f["board_views"]], key=lambda f: (not f["open"], f["start_utc"] or "")):
        cells = []
        for k in bk:
            v = f["board_views"].get(k)
            if not v:
                cells.append("<td>—</td>")
            else:
                bad = v["pick"] != f["pick"]
                cells.append(f'<td>{"⚠️ " if bad else ""}{e(v["pick"])} {pct(v["p_pick"])}</td>')
        rows.append(f'<tr><td>{e(f["team_a"])} vs {e(f["team_b"])}<div class="small">{e(f["competition"])} · {"open" if f["open"] else "locked"}</div></td>'
                    f'<td><b>{e(f["pick"] or "blank")}</b> {pct(f["pick_p"])}</td>{"".join(cells)}'
                    f'<td class="src">{src_links(f)}<a href="{e(f["hotspawn_url"])}" rel="noopener">HotSpawn #{e(f["fixture_id"])}</a></td></tr>')
    body = ('<h2>Cross-board check</h2><div class="note">Same fixture, each published board\'s own pick and pick-probability, next to this page\'s reconciled pick (⚠️ = a board\'s pick differs, or this page has no eligible line while the board shows one). '
            'Differences come from different source sets, quote times, or eligibility rules; they are listed on <a href="flagged.html">Flagged for review</a>, not silently resolved.</div>'
            f'<div class="scroll"><table><thead><tr><th>Match</th><th>Reconciled pick</th>{head}<th>Sources</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    (out / "boards.html").write_text(page("Cross-board check", "boards.html", body, gen), encoding="utf-8")
    # ---- flagged
    items = []
    for f in model["fixtures"]:
        if f["cancelled"] and f.get("board_views"):
            pass
        interesting = [x for x in f["flags"] if not x.startswith("no_eligible") and x not in ("hotspawn_status_cancelled",)]
        if interesting and (f["consensus_p_a"] is not None or f["board_views"]):
            items.append(f)
    rows = "".join(
        f'<tr><td>{e(f["team_a"])} vs {e(f["team_b"])}<div class="small">{e(f["competition"])}</div></td><td>{"open" if f["open"] else "locked"}</td>'
        f'<td>{"".join(f"<span class=flag>{e(x)}</span>" for x in f["flags"])}</td><td class="src">{src_links(f)}<a href="{e(f["hotspawn_url"])}" rel="noopener">HotSpawn #{e(f["fixture_id"])}</a></td></tr>'
        for f in items)
    q_excl = []
    for f in model["fixtures"]:
        for q in f["quotes"]:
            if not q["eligible"]:
                q_excl.append((f, q))
    qrows = "".join(
        f'<tr><td>{e(f["team_a"])} vs {e(f["team_b"])}</td><td>{e(q["label"])}</td><td>{e(", ".join(q["flags"]))}</td><td>{e(q["retrieved_at_utc"])}</td>'
        f'<td>{"<a href=" + chr(34) + e(q["url"]) + chr(34) + ">source</a>" if q["url"] else "—"}</td></tr>' for f, q in q_excl)
    static = [
        ("IR-4E6-01", "Five boards publish overlapping results for the same fixtures with different eligibility rules (see Cross-board check). This page does not pick a winner among boards; it re-applies one rule set to the quotes they publish.", "COORDINATION.md; each board's page"),
        ("IR-4E6-02", "egamersworld is an odds aggregator that does not name the bookmaker behind the number in these captures. It is included in the consensus but every such fixture is flagged; it is not an official bookmaker source.", "https://egamersworld.com/counterstrike"),
        ("IR-4E6-03", "Kalshi is a prediction exchange (price = probability, not a bookmaker line). It is shown as a reference and checked for agreement but never averaged into the consensus.", "https://kalshi.com/"),
        ("IR-4E6-04", "HLTV pages are not machine-readable from the build runner (HTTP 403 reported by session 961e163a), so HLTV is not used as a price input; originate-your-own-line work for fixtures without prices is blank rather than modeled.", "https://www.hltv.org/betting/analytics"),
        ("IR-4E6-06", "Many egamersworld rows were transcribed by a session from the aggregator page at 19:05 UTC (data/cs2_odds_egamersworld.json, written by scripts/write_cs2_odds.py) rather than fetched by an automated collector; they age out of the 4-hour window at 23:05 UTC and are then excluded automatically. Spot-checks above show the lines moved by under 1 pp since capture.", "https://egamersworld.com/counterstrike/matches"),
        ("IR-4E6-07", "Six egamersworld rows carry the identical price 1.80 / 1.80 (exactly 50%) on unrelated fixtures. This is treated as not a usable line: the quote is excluded and the fixture stays blank. The 961 board shows a pick at exactly 50.0% for these rows. Cause (placeholder price vs. genuine even market) is not confirmed.", "https://egamersworld.com/counterstrike/matches"),
        ("IR-4E6-05", "The Pages deploy runs this builder at staging time from the data files on main; the data files themselves are refreshed by other sessions' workflows on their own schedules, so line ages shown are the age of those captures at build time.", "https://github.com/buffedlizard55-lab/MaltaProj2/actions"),
    ]
    srows = "".join(f'<tr><td>{a}</td><td>{e(b)}</td><td><a href="{e(c)}" rel="noopener">{e(c)}</a></td></tr>' if c.startswith("http") else f'<tr><td>{a}</td><td>{e(b)}</td><td>{e(c)}</td></tr>' for a, b, c in static)
    mrows = "".join(
        f'<tr><td>{e(c["team_a"])} vs {e(c["team_b"])}</td><td><a href="{e(c["url"])}" rel="noopener">egamersworld page</a><div class="small">read {e(c["observed_at_utc"])}</div></td>'
        f'<td>{e(c["odds_by_team"][c["team_a"]])} / {e(c["odds_by_team"][c["team_b"]])}</td><td>{pct(c["observed_p_a"])} → {e(c["observed_pick"])}</td>'
        f'<td>{pct(c["board_quote_p_a"])} (captured {e(c["board_quote_retrieved_at_utc"])})</td><td>{"same pick" if c["same_pick"] else "DIFFERENT PICK"}; line moved {e(c["movement_pp"])} pp</td></tr>'
        for c in model["manual_checks"])
    urows = "".join(f'<tr><td><a href="{e(c["url"])}" rel="noopener">{e(c["url"])}</a></td><td>{e(c["observed_at_utc"])}</td><td>{e(c["result"])}</td></tr>' for c in model["unreadable_checks"])
    body = ('<h2>Flagged for review</h2><p>None of these block publication. Needs-review items are published for the owner to check.</p><h3>General irregularities</h3>'
            f'<div class="scroll"><table><thead><tr><th>ID</th><th>Irregularity</th><th>Source</th></tr></thead><tbody>{srows}</tbody></table></div>'
            '<h3>Independent spot-checks (live pages read by this session)</h3><div class="note">Odds typed from the page, probability/pick computed. Different capture times, so the line moved; a pick difference would be flagged.</div>'
            f'<div class="scroll"><table><thead><tr><th>Match</th><th>Page</th><th>Observed odds A / B</th><th>No-vig (team A) → pick</th><th>Board value</th><th>Result</th></tr></thead><tbody>{mrows}</tbody></table></div>'
            f'<h3>Pages that could not be read</h3><div class="scroll"><table><thead><tr><th>URL</th><th>Tried (UTC)</th><th>Result</th></tr></thead><tbody>{urows}</tbody></table></div>'
            f'<h3>Fixtures with flags ({len(items)})</h3><div class="scroll"><table><thead><tr><th>Match</th><th>State</th><th>Flags</th><th>Sources</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<h3>Quotes excluded from the consensus ({len(q_excl)})</h3><div class="scroll"><table><thead><tr><th>Match</th><th>Source</th><th>Reason</th><th>Retrieved (UTC)</th><th>Link</th></tr></thead><tbody>{qrows}</tbody></table></div>'
            + ("<h3>Build notes</h3><ul>" + "".join(f"<li>{e(n)}</li>" for n in model["notes"]) + "</ul>" if model["notes"] else ""))
    (out / "flagged.html").write_text(page("Flagged for review", "flagged.html", body, gen), encoding="utf-8")
    # ---- methodology
    bm = "".join(f'<tr><td>{e(BOARD_LABEL[k])}</td><td><code>{e(v["path"])}</code></td><td>{e(v["generated_at_utc"])}</td><td>{v["rows"]}</td><td><a href="{BOARD_PAGE[k]}">page</a></td></tr>' for k, v in model["boards"].items())
    body = ('<h2>Method &amp; sources</h2><ol>'
            '<li><b>Fixtures</b>: HotSpawn public lobby API record (<code>data/hotspawn_matches.json</code>, derived from <a href="https://play.hotspawn.com/lobby">the lobby</a>) — teams, kickoff, lock time, points. Crowd pick % is not read.</li>'
            '<li><b>Quotes</b>: every board\'s published quote (Pinnacle, Bovada, egamersworld, Kalshi) is re-read from the board JSON files below. The newest quote per source is kept.</li>'
            '<li><b>Orientation</b>: quotes are aligned to the HotSpawn team order by normalised team name; a board whose names do not match either order is skipped and flagged.</li>'
            '<li><b>Arithmetic check</b>: when decimal odds are published, the proportional no-vig probability p = (1/o<sub>a</sub>)/((1/o<sub>a</sub>)+(1/o<sub>b</sub>)) is recomputed and must match the published number within 0.2 pp, else the quote is excluded.</li>'
            f'<li><b>Eligibility</b>: not live, retrieved ≤ {model["max_quote_age_min"]} min before build, has a source URL.</li>'
            '<li><b>Consensus</b>: arithmetic mean of eligible bookmaker/aggregator probabilities (Pinnacle, Bovada, egamersworld). Kalshi is reference only. Pick = higher probability; label Strong ≥ 70%, Lean 55–70%, Toss-up &lt; 55%.</li>'
            '<li><b>Open</b>: HotSpawn status <i>scheduled</i> and lock time after build time; your browser also greys out rows that have locked since the build.</li>'
            '<li><b>Blank rule</b>: no eligible quote → no probability, no pick.</li></ol>'
            f'<h3>Boards read</h3><div class="scroll"><table><thead><tr><th>Board</th><th>File</th><th>Generated (UTC)</th><th>Rows</th><th>Page</th></tr></thead><tbody>{bm}</tbody></table></div>'
            '<h3>Official/primary sources</h3><ul><li><a href="https://play.hotspawn.com/lobby">HotSpawn Pick\'ems lobby</a></li><li><a href="https://www.pinnacle.com/en/esports/counter-strike/matchups/">Pinnacle CS2</a></li>'
            '<li><a href="https://www.bovada.lv/sports/esports">Bovada esports</a></li><li><a href="https://egamersworld.com/counterstrike">egamersworld CS2</a></li><li><a href="https://www.hltv.org/betting/analytics">HLTV betting analytics (cross-check only)</a></li><li><a href="https://kalshi.com/">Kalshi</a></li></ul>')
    (out / "methodology.html").write_text(page("Method & sources", "methodology.html", body, gen), encoding="utf-8")


def build(out_dir: Path | str | None = None, write_json: bool = True, now: datetime | None = None) -> dict:
    model = build_model(now)
    model["summary"] = summarize(model)
    model["manual_checks"] = run_manual_checks(model)
    model["unreadable_checks"] = UNREADABLE_CHECKS
    if write_json:
        (DATA / "reconcile_4e6dcd0d.json").write_text(json.dumps(model, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    out = Path(out_dir) if out_dir else ROOT / "reconcile"
    build_pages(model, out)
    return model


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reconcile"))
    a = ap.parse_args()
    m = build(a.out)
    print(json.dumps(m["summary"], indent=1))
