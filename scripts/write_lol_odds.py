#!/usr/bin/env python3
"""Write data/lol_odds_egamersworld.json — external LoL odds from
egamersworld.com/lol/matches (chunks 0-2, fetched 2026-10-13 ~19:10 UTC).

Coverage finding: egamersworld's LoL list carries only the marquee events
(Demacia Cup, EMEA Masters, Worlds, LGC Rising). The lobby's regional leagues
(PRM, Tunisian, RIVALS, Komplettligaen, Arabian, LigaGG, Icelandic, Superstrike,
Benelux, FPL, Hitpoint, LIT, POP, MängudeÖÖ) have NO external lines on egw;
no other permitted source (Pinnacle/Bovada quotes already in data/odds.json) covers
them either -> those fixtures stay blank + flagged (nothing inferred).

Time note: the egw list-view times disagree with the widget countdowns and with
official play API times (observed offset ~-4.5h on some rows). Official
start times = play API (data/lol_matches.json); egw time kept verbatim and flagged.
Two quote sets exist (list widget vs match-of-day widget); both recorded.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lol = json.loads((ROOT / "data" / "lol_matches.json").read_text())
by_pair = {}
for m in lol["matches"]:
    by_pair[(m["competition"], m["team_a"].lower(), m["team_b"].lower())] = m
    by_pair[(m["competition"], m["team_b"].lower(), m["team_a"].lower())] = m

# (competition, official team_a, official team_b, egw team_a, egw team_b,
#  list odds [a,b], widget odds [a,b], egw time display, egw match url, event url slug path)
ROWS = [
    ("Demacia Cup Global Invitational 2026", "KT Rolster", "BNK FearX",
     "FearX", "KT Rolster", [3.27, 1.31], [2.71, 1.41], "14.10.26 06:30",
     "https://egamersworld.com/lol/match/FqxSssBfV/fearx-vs-kt-rolster-tW-gg6CEW",
     "side_order_reversed_vs_official; list time conflicts with official start"),
    ("Demacia Cup Global Invitational 2026", "Team WE", "HANJIN BRION",
     "Team WE", "BRION", [1.75, 1.92], [1.73, 1.93], "15.10.26 06:30",
     "https://egamersworld.com/lol/match/FqxSssBfV/team-we-vs-brion-0Ur_S_-WM",
     "opponent variant: BRION ~ HANJIN BRION; list time conflicts with official start"),
    ("EM 2026 Summer Main Event", "Solary", "Anubis Gaming",
     "Solary", "Anubis Gaming", [1.14, 5.31], [1.11, 5.26], "14.10.26 13:30",
     "https://egamersworld.com/lol/match/z27dDLdCP/solary-vs-anubis-gaming-iwRXElWJ9",
     "event variant: EMEA Masters 2026 Summer ~ EM 2026 Summer Main Event; list time conflicts with official start"),
    ("Worlds 2026 Play-In", "FURIA", "MVK Esports",
     "FURIA Esports", "MVK Esports", [1.25, 3.4], [1.25, 3.4], "15.10.26 20:30",
     "https://egamersworld.com/lol/match/q8qUtLA6g/furia-esports-vs-mvk-esports-TK-yMvTub",
     "egw event label: 2026 World Championship; lobby comp: Worlds 2026 Play-In"),
    ("Worlds 2026 Play-In", "Cloud9", "Karmine Corp",
     "Cloud9", "Karmine Corp", [2.71, 1.41], [2.72, 1.42], "15.10.26 15:30",
     "https://egamersworld.com/lol/match/q8qUtLA6g/cloud9-vs-karmine-corp-WI4DQTvQri",
     None),
    ("LGC Rising 2026 Playoffs", None, None, "Mental Rush", "SK Gaming Avarosa",
     [1.8, 1.8], None, "19.10.26 13:30",
     "https://egamersworld.com/lol/match/CVSRRqh2Q/mental-rush-vs-sk-gaming-avarosa-LjRSaW8fgo",
     "no Bo label shown"),
    ("LGC Rising 2026 Playoffs", None, None, "Vitality Rising Bees", "G2 HEL",
     [1.8, 1.8], None, "20.10.26 13:30",
     "https://egamersworld.com/lol/match/CVSRRqh2Q/vitality-rising-bees-vs-g2-hel-YwBkHaImL",
     "no Bo label shown"),
]

out = []
seen = set()
for comp, oa, ob, wa, wb, lo, wo, cest, url, note in ROWS:
    if oa is None:
        # resolve official pair by egw team names (lowercase contains-join)
        cand = [m for m in lol["matches"]
                if m["competition"].startswith(comp.split(" Play")[0])
                and (wa or "").lower()[:6] in (m["team_a"] + m["team_b"]).lower()
                and not m["past_lock_not_pickable"]]
        if not cand:
            out.append({"competition": comp, "team_a": None, "team_b": None,
                        "decimal_odds_a": None, "decimal_odds_b": None,
                        "source_url": url, "status": "UNMATCHED", "note": note})
            continue
        m = cand[0]
    else:
        m = by_pair.get((comp, oa.lower(), ob.lower())) or by_pair.get((comp, ob.lower(), oa.lower()))
        if not m:
            out.append({"competition": comp, "team_a": oa, "team_b": ob, "status": "UNMATCHED", "note": note})
            continue
    if m["fixture_id"] in seen:
        continue
    seen.add(m["fixture_id"])
    # align list odds to official side order using egw display pair
    pair = ((wa or "").lower(), (wb or "").lower())
    na, nb = m["team_a"].lower(), m["team_b"].lower()
    LA = {"fearx": na if "fearx" in na else nb, "brion": na if "brion" in na else nb}
    pair = (LA.get(pair[0], pair[0]), LA.get(pair[1], pair[1]))

    def eq(x, y):
        return x == y or (x and y and (x.startswith(y) or y.startswith(x)))

    if eq(pair[0], na):
        a, b = lo
    elif eq(pair[0], nb):
        a, b = lo[1], lo[0]
    elif eq(pair[1], nb):
        a, b = lo
    elif eq(pair[1], na):
        a, b = lo[1], lo[0]
    else:
        a, b = None, None
    out.append({
        "fixture_id": m["fixture_id"],
        "competition": m["competition"],
        "team_a": m["team_a"], "team_b": m["team_b"],
        "decimal_odds_a": a, "decimal_odds_b": b,
        "widget_odds": wo,
        "official_start_utc": m["scheduled_start_time_utc"],
        "egw_time_display": f"{cest} (UNTRUSTED — differs from official start)" if cest else None,
        "source_name": "egamersworld.com LoL odds widget",
        "source_kind": "esports odds aggregator (external to Hotspawn)",
        "source_url": url,
        "join_note": note,
        "retrieved_at_utc": "2026-10-13T19:10:00Z",
        "hotspawn_pick_pct_used": False,
    })

doc = {
    "generated_at_utc": "2026-10-13T19:20:00Z",
    "source_page": "https://egamersworld.com/lol/matches",
    "coverage_finding": (
        "egamersworld LoL list covers only 8 marquee fixtures (Demacia 2, EM 2, Worlds 2, LGC 2). "
        "The lobby's regional-league fixtures (PRM, Tunisian, RIVALS, Komplettligaen, Arabian, LigaGG, "
        "Icelandic, Superstrike, Benelux, FPL, Hitpoint, LIT, POP, MängudeÖÖ) are absent from egw and from "
        "all collected bookmaker quotes -> left blank + flagged unverified (no external line found)."
    ),
    "time_note": "egw list-view times conflict with widget countdowns and with official play API times on several rows; official times are used, egw times kept verbatim and flagged.",
    "rows": out,
}
(ROOT / "data" / "lol_odds_egamersworld.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print("rows:", len(out), "unmatched:", [r for r in out if r.get("status") == "UNMATCHED"])
for r in out:
    print(" ", r.get("fixture_id"), r.get("team_a"), "vs", r.get("team_b"), "|", r.get("decimal_odds_a"), r.get("decimal_odds_b"))
