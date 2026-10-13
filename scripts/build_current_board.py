#!/usr/bin/env python3
"""T-CURRENT (session 0f6c89c6): current open-for-picks CS2 board.

Inputs (all produced by the existing CI pipeline / verified capture scripts):
  data/hotspawn_matches.json   Hotspawn fixtures API snapshot (scheduled, lock time, teams)
  data/lines.json              Pinnacle + Bovada moneyline quotes joined to fixtures (build_lines.py)
  data/cs2_odds_egamersworld.json  EGamersWorld odds-widget quotes (write_cs2_odds.py)

Outputs:
  data/current_board.json      one row per open CS2 fixture (machine-readable)
  current/index.html           mobile-first board: pick + probability per match
  current/flagged.html         rows without a verified line + every irregularity found

Rules (strict, nothing inferred):
  * "Open" = Hotspawn status scheduled AND lock_time strictly after the snapshot time.
  * Hotspawn crowd pick % is shown for reference only and never enters a probability.
  * Named-bookmaker consensus = arithmetic mean of per-source proportional no-vig
    probabilities over Pinnacle and/or Bovada (one quote per source; duplicates removed).
  * Fallback = EGamersWorld odds-widget quote, only when no named-bookmaker line exists.
    The widget does not name its bookmaker in the capture, so it is labelled as such.
  * EGW rows are excluded when: the match had already started at capture time, the two
    prices are an identical 1.80/1.80 pair (widget placeholder pattern), or the capture
    flags the side order as reversed (orientation not resolved).
  * No value is filled in when no source qualifies: probability blank + flagged.
"""

import html
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "current")

HS_CS2 = "https://play.hotspawn.com/cs2-pickems"


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def parse_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_utc(s):
    return parse_utc(s).strftime("%d %b %H:%M UTC")


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def confidence(p):
    if p is None:
        return None
    if p >= 0.65:
        return "Strong lean"
    if p >= 0.55:
        return "Lean"
    return "Toss-up"


def main():
    hs = load("hotspawn_matches.json")
    snap = parse_utc(hs["generated_at_utc"])
    lines = {f["fixture_id"]: f for f in load("lines.json")["fixtures"]}
    egw = {r["fixture_id"]: r for r in load("cs2_odds_egamersworld.json")["rows"]}
    egw_capture = parse_utc(load("cs2_odds_egamersworld.json")["generated_at_utc"])

    open_fx = [
        m for m in hs["matches"]
        if m.get("sport") == "cs2" and m.get("status") == "scheduled"
        and parse_utc(m["lock_time"]) > snap
    ]
    open_fx.sort(key=lambda m: m["scheduled_start_time"])

    rows, irregularities = [], []
    for m in open_fx:
        fid = m["fixture_id"]
        a, b = m["team_a"], m["team_b"]
        sources = []

        # 1) named bookmakers (Pinnacle / Bovada) from lines.json, one quote per source
        seen = set()
        f = lines.get(fid, {})
        for bl in f.get("bookmaker_lines", []):
            key = bl["source_key"]
            if key in seen:
                irregularities.append({
                    "fixture_id": fid, "match": f"{a} vs {b}",
                    "issue": f"duplicate {key} quote in lines.json; first kept, duplicate ignored",
                })
                continue
            seen.add(key)
            # derived_probability_a is for the bookmaker's first listed side
            if bl.get("order_as_quoted") == "reversed":
                p_a = bl["derived_probability_b"]
            else:
                p_a = bl["derived_probability_a"]
            url = bl.get("source_public_url") or bl.get("source_api_url")
            sources.append({
                "source": bl["source_name"],
                "kind": bl["source_kind"],
                "decimal_a": bl["decimal_odds_a"] if bl.get("order_as_quoted") != "reversed" else bl["decimal_odds_b"],
                "decimal_b": bl["decimal_odds_b"] if bl.get("order_as_quoted") != "reversed" else bl["decimal_odds_a"],
                "p_a": round(p_a, 4),
                "url": url,
                "retrieved_at_utc": bl["retrieved_at_utc"],
                "market": bl.get("market_type"),
                "join": ("start time agrees with fixture" if bl.get("start_time_agrees_with_fixture")
                         else "joined by team names + tournament (no start time from source)"),
            })

        named = [s for s in sources]
        fallback = None
        e = egw.get(fid)
        egw_excluded = None
        if e:
            e_start = parse_utc(e["official_start_utc"])
            if e_start <= egw_capture:
                egw_excluded = "match had started before the EGW capture; widget price may be in-play"
            elif e["decimal_odds_a"] == 1.8 and e["decimal_odds_b"] == 1.8:
                egw_excluded = "identical 1.80/1.80 pair: widget placeholder pattern, not a market price"
            elif "side_order_reversed" in (e.get("join_note") or ""):
                egw_excluded = "side order reversed in capture: orientation not resolved"
            else:
                pa = 1 / e["decimal_odds_a"]
                pb = 1 / e["decimal_odds_b"]
                fallback = {
                    "source": "EGamersWorld odds widget (bookmaker not named in capture)",
                    "kind": "odds aggregator widget",
                    "decimal_a": e["decimal_odds_a"], "decimal_b": e["decimal_odds_b"],
                    "p_a": round(pa / (pa + pb), 4),
                    "url": e["source_url"],
                    "retrieved_at_utc": e["retrieved_at_utc"],
                    "market": "match winner (widget)",
                    "join": e.get("join_note") or "fixture id join recorded in capture",
                }
            if egw_excluded:
                irregularities.append({
                    "fixture_id": fid, "match": f"{a} vs {b}",
                    "issue": f"EGW quote excluded: {egw_excluded}", "url": e["source_url"],
                })

        if named:
            p_a = round(sum(s["p_a"] for s in named) / len(named), 4)
            quality = "High (2 named bookmakers)" if len(named) >= 2 else "Medium (1 named bookmaker)"
            basis = " + ".join(s["source"] for s in named)
            used = named
        elif fallback:
            p_a = fallback["p_a"]
            quality = "Low (single unnamed-bookmaker widget quote)"
            basis = fallback["source"]
            used = [fallback]
        else:
            p_a = None
            quality = None
            basis = None
            used = []

        p_b = round(1 - p_a, 4) if p_a is not None else None
        pick = None
        if p_a is not None:
            pick = a if p_a >= p_b else b
        pick_p = max(p_a, p_b) if p_a is not None else None

        flags = []
        if not used:
            flags.append("no external line: probability left blank")
        if quality and quality.startswith("Low"):
            flags.append("single quote from unnamed bookmaker widget; may be stale")
        if named and fallback and abs(named[0]["p_a"] - fallback["p_a"]) > 0.10:
            flags.append("EGW fallback differs from named consensus by more than 10 points")
        if any(s["join"].startswith("joined by team names") for s in used):
            flags.append("Pinnacle join by team names + tournament (no start time in source)")
        if egw_excluded:
            flags.append("EGW quote excluded (see irregularities)")
        if any(s["source"] == "Bovada" for s in used):
            flags.append("Bovada: source page not re-openable in verification (Not Found / reCAPTCHA); quote is from the CI capture only")
        if any(s["source"] == "Pinnacle" for s in used):
            flags.append("Pinnacle: series moneyline (period 0) per official guest API; spot-checked for 9z vs Aurora only")
        if m.get("tier") in ("c",):
            flags.append("tier C event")

        rows.append({
            "fixture_id": fid,
            "kickoff_utc": m["scheduled_start_time"],
            "lock_utc": m["lock_time"],
            "event": m["competition_name"],
            "tier": (m.get("tier") or "").upper(),
            "points": m.get("offered_points"),
            "team_a": a, "team_b": b,
            "hotspawn_url": f"https://www.hotspawn.com/matches/{fid}",
            "hotspawn_pick_pct_reference_only": {"team_a": m.get("team_a_pick_pct"), "team_b": m.get("team_b_pick_pct")},
            "probability_a": p_a, "probability_b": p_b,
            "pick": pick, "pick_probability": pick_p,
            "pick_confidence": confidence(pick_p),
            "quality": quality, "basis": basis,
            "sources": used,
            "flags": flags,
            "quote_captured": bool(used),
            "verified_against_source_this_session": False,
        })

    # Board-level irregularities found during this session's verification
    irregularities.extend([
        {"fixture_id": None, "match": "board-wide",
         "issue": "Hotspawn lobby text says '68 matches this week' but the fixtures API holds 30 open CS2 fixtures (lock time after snapshot); the 68 figure is not reconciled to CS2 fixtures",
         "url": HS_CS2},
        {"fixture_id": None, "match": "board-wide",
         "issue": "EGamersWorld match pages list several named bookmakers (SpinAlto, RedSport, Spinbetter, 22bet, 1xBit, Herospin, Kinbet, Vave); the capture stores one unnamed price per match, so the 'bc.game via EGamersWorld' label used on /pickem/ is NOT verified",
         "url": "https://egamersworld.com/counterstrike/match/0U32SId-H/gremio-vs-los-ninos-ZbETIr-WFL"},
        {"fixture_id": None, "match": "board-wide",
         "issue": "EGamersWorld capture time 19:10 UTC is 2h+ before the snapshot; widget prices are not re-checked and may be stale",
         "url": "https://egamersworld.com/counterstrike/matches"},
        {"fixture_id": None, "match": "board-wide",
         "issue": "Bovada event URLs in lines.json (e.g. Astralis vs Sashi, 9z vs Aurora) returned 'Not Found' with reCAPTCHA when re-opened in verification; the Bovada quotes could not be re-checked",
         "url": "https://www.bovada.lv/esports/counter-strike-2/pulse-beat-iii/astralis-sashi-esport-202610140600"},
        {"fixture_id": None, "match": "board-wide",
         "issue": "Quote availability changes between refreshes: the 21:27 UTC capture had Pinnacle and Bovada for FURIA vs BetBoom and Bovada for 9z vs Aurora; the 21:29 UTC capture has no Pinnacle or Bovada quote for FURIA vs BetBoom and only Pinnacle for 9z vs Aurora. The board follows the latest capture; the EGamersWorld fallback is shown for FURIA vs BetBoom",
         "url": "https://www.bovada.lv/esports/counter-strike-2/thunderpick-world-championship-26/9z-globant-team-aurora-202610140430"},
        {"fixture_id": None, "match": "board-wide",
         "issue": "Pinnacle moneyline 9z vs Aurora re-checked against the official guest API: period 0 (series) home +261 / away -335 = 3.61 / 1.2985 decimal, identical to the capture; period 1 (Map 1) is +216/-272 and is not used",
         "url": "https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638111785/markets/related/straight"},
    ])

    summary = {
        "open_cs2_fixtures": len(rows),
        "with_named_bookmaker_line": sum(1 for r in rows if r["quality"] and r["quality"].startswith(("High", "Medium"))),
        "with_egw_fallback_only": sum(1 for r in rows if r["quality"] and r["quality"].startswith("Low")),
        "without_any_line": sum(1 for r in rows if not r["quote_captured"]),
    }
    doc = {
        "generated_at_utc": hs["generated_at_utc"],
        "snapshot_basis": {
            "hotspawn_api_snapshot_utc": hs["generated_at_utc"],
            "hotspawn_api": hs.get("source_api"),
            "lines_collected_utc": load("lines.json")["odds_collected_at_utc"],
            "egw_capture_utc": load("cs2_odds_egamersworld.json")["generated_at_utc"],
        },
        "scope": "CS2 fixtures from the Hotspawn fixtures API with status scheduled and lock time after the snapshot. LoL fixtures are not priced on this board.",
        "rules": [
            "Hotspawn crowd pick % is reference only and never a probability input.",
            "Named-bookmaker consensus (Pinnacle, Bovada) is preferred; EGamersWorld widget is a labelled fallback only.",
            "Probability is proportional no-vig normalization per source, then arithmetic mean across named sources.",
            "Blank probability + flag when no qualifying quote exists. Nothing is inferred.",
        ],
        "summary": summary,
        "rows": rows,
        "irregularities": irregularities,
    }
    with open(os.path.join(DATA, "current_board.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    os.makedirs(OUT, exist_ok=True)
    from current_site import render  # noqa: E402  (same folder)
    render(doc, OUT)
    print("current board:", summary)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
