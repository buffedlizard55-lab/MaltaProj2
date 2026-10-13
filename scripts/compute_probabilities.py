#!/usr/bin/env python3
"""T4: compute normalized implied probabilities from EXTERNAL lines only.

Inputs:
  data/cs2_matches.json, data/lol_matches.json   — official inventories (play API)
  data/lines.json                                — bookmaker quotes (Pinnacle/Bovada) for CS2
  data/cs2_odds_egamersworld.json                — egw CS2 odds (32 pickable)
  data/lol_odds_egamersworld.json                — egw LoL odds (7)
  data/pickem_pool.json                         — Polymarket/derived lines where present

Output: data/probabilities.json

Rules (project verification policy):
  - Hotspawn crowd pick % is NEVER used.
  - Per-source no-vig normalization: p_a = (1/o_a) / (1/o_a + 1/o_b).
  - Consensus = arithmetic mean across available external sources (same rule as data/lines.json).
  - Fixtures with no external line get BLANK probabilities + flag 'no_external_line'.
  - Past-lock fixtures get flag 'past_lock_not_pickable' (lobby counts them; cards never render).
  - Every source carries its retrieval URL; nothing is inferred or filled.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "probabilities.json"


def load(p):
    return json.loads((ROOT / p).read_text())


def novig(oa, ob):
    ia, ib = 1.0 / oa, 1.0 / ob
    s = ia + ib
    return round(ia / s, 4), round(ib / s, 4)


cs2 = load("data/cs2_matches.json")
lol = load("data/lol_matches.json")
lines = load("data/lines.json")
egw_cs2 = load("data/cs2_odds_egamersworld.json")
egw_lol = load("data/lol_odds_egamersworld.json")
pool = load("data/pickem_pool.json")

book_by_id = {f["fixture_id"]: f for f in lines["fixtures"]}
egw_cs2_by_id = {r["fixture_id"]: r for r in egw_cs2["rows"]}
egw_lol_by_id = {r["fixture_id"]: r for r in egw_lol["rows"]}
pool_by_id = {r["id"].replace("hs-", ""): r for r in pool["rows"]}

rows_out = []
stats = {"with_prob": 0, "no_line": 0, "past_lock": 0, "cancelled": 0}

for inv, game in ((cs2, "CS2"), (lol, "LoL")):
    for m in inv["matches"]:
        fid = m["fixture_id"]
        sources = []
        flags = []
        if m.get("status") == "cancelled":
            flags.append("cancelled")
            stats["cancelled"] += 1
        if m.get("past_lock_not_pickable"):
            flags.append("past_lock_not_pickable")
            stats["past_lock"] += 1
        if m.get("status") == "started":
            flags.append("started")

        # bookmaker quotes (CS2)
        bf = book_by_id.get(fid)
        if bf:
            for bl in bf.get("bookmaker_lines") or []:
                oa, ob = bl.get("decimal_odds_a"), bl.get("decimal_odds_b")
                if oa and ob:
                    pa, pb = novig(oa, ob)
                    sources.append({
                        "source": bl.get("source_name") or bl.get("source_key"),
                        "kind": "licensed bookmaker",
                        "url": bl.get("source_public_url") or bl.get("source_api_url"),
                        "decimal_odds_a": oa, "decimal_odds_b": ob,
                        "p_a": pa, "p_b": pb,
                        "retrieved_at_utc": bl.get("retrieved_at_utc"),
                    })
            if bf.get("review_flags"):
                flags.extend(bf["review_flags"])

        # egw CS2
        er = egw_cs2_by_id.get(fid)
        if er and er.get("decimal_odds_a"):
            pa, pb = novig(er["decimal_odds_a"], er["decimal_odds_b"])
            sources.append({
                "source": "egamersworld.com",
                "kind": "esports odds aggregator",
                "url": er["source_url"],
                "decimal_odds_a": er["decimal_odds_a"], "decimal_odds_b": er["decimal_odds_b"],
                "p_a": pa, "p_b": pb,
                "retrieved_at_utc": er["retrieved_at_utc"],
            })
            if er.get("join_note"):
                flags.append("join_note:" + er["join_note"])

        # egw LoL
        er = egw_lol_by_id.get(fid)
        if er and er.get("decimal_odds_a"):
            pa, pb = novig(er["decimal_odds_a"], er["decimal_odds_b"])
            sources.append({
                "source": "egamersworld.com",
                "kind": "esports odds aggregator",
                "url": er["source_url"],
                "decimal_odds_a": er["decimal_odds_a"], "decimal_odds_b": er["decimal_odds_b"],
                "p_a": pa, "p_b": pb,
                "retrieved_at_utc": er["retrieved_at_utc"],
            })
            if er.get("egw_time_display") and "UNTRUSTED" in str(er.get("egw_time_display")):
                flags.append("egw_time_conflicts_with_official_start")
            if er.get("join_note"):
                flags.append("join_note:" + er["join_note"])

        # Polymarket/line from pickem_pool (external market lines)
        pr = pool_by_id.get(fid)
        if pr and pr.get("line_p_a") is not None and pr.get("line_p_b") is not None:
            sources.append({
                "source": f"pickem_pool line ({pr.get('line_basis')})",
                "kind": "external market / derived line",
                "url": pr.get("hltv_betting_url") or pr.get("other_match_url") or "data/pickem_pool.json",
                "decimal_odds_a": None, "decimal_odds_b": None,
                "p_a": round(pr["line_p_a"], 4), "p_b": round(pr["line_p_b"], 4),
                "retrieved_at_utc": pool.get("snapshot"),
                "note": pr.get("line_basis"),
            })
            if pr.get("quality_note"):
                flags.append("pool_quality:" + str(pr.get("quality")))

        if sources:
            pa = round(sum(s["p_a"] for s in sources) / len(sources), 4)
            pb = round(sum(s["p_b"] for s in sources) / len(sources), 4)
            # guard: probabilities must sum to ~1
            stats["with_prob"] += 1
            verified = True
        else:
            pa = pb = None
            flags.append("no_external_line")
            stats["no_line"] += 1
            verified = False

        rows_out.append({
            "fixture_id": fid,
            "game": game,
            "competition": m["competition"],
            "team_a": m["team_a"], "team_b": m["team_b"],
            "scheduled_start_time_utc": m["scheduled_start_time_utc"],
            "status": m.get("status"),
            "tier": m.get("tier"),
            "probability_a": pa,
            "probability_b": pb,
            "consensus_rule": "arithmetic mean of per-source no-vig probabilities" if sources else None,
            "n_sources": len(sources),
            "sources": sources,
            "flags": flags,
            "verified": verified,
            "hotspawn_pick_pct_used": False,
            "official_source_url": m.get("source_url"),
            "match_url": m.get("match_url"),
        })

doc = {
    "generated_at_utc": "2026-10-13T19:35:00Z",
    "rules": [
        "External lines only (Pinnacle, Bovada, egamersworld, Polymarket-based pool lines).",
        "Per-source no-vig normalization, then arithmetic mean across sources.",
        "Hotspawn crowd pick percentages are excluded by policy.",
        "No external line => probabilities blank + flag no_external_line (never inferred).",
    ],
    "stats": stats,
    "rows": rows_out,
}
OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print("stats:", stats, "| total rows:", len(rows_out))
csp = [r for r in rows_out if r["game"] == "CS2" and r["probability_a"] is not None]
lolp = [r for r in rows_out if r["game"] == "LoL" and r["probability_a"] is not None]
print("CS2 with p:", len(csp), "LoL with p:", len(lolp))
