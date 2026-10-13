#!/usr/bin/env python3
"""Write data/cs2_odds_egamersworld.json — external match odds captured from
egamersworld.com/counterstrike/matches (chunks 1-6, fetched 2026-10-13 ~19:05 UTC).

Rules:
- Odds are raw decimal quotes shown by egamersworld's odds widget; source_url per row
  is the egamersworld match page (official page for that quote). Times on egw are CEST
  (UTC+2), verified against play API UTC times.
- Hotspawn crowd pick % is never used.
- Joins to official fixtures use event name + both teams + time (side order may differ;
  name variants documented per row). Nothing is inferred beyond the documented join.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
EV = {
    "sa7": "CCT South America 2026 Series #7",
    "esl_sa": "ESL Challenger League Season 52: South America - Cup #3",
    "esl_na": "ESL Challenger League Season 52: North America - Cup #3",
    "eu11": "CCT Europe 2026 Series #11",
    "eu12pi": "CCT Europe 2026 Series #12 Play-In",
    "thp": "Thunderpick World Championship 2026",
    "sp": "Stake Pulse Beat III",
    "elisa": "Elisa BreakOut Series #2",
}
EVSLUG = {
    "CCT South America 2026 Series #7": "0U32SId-H",
    "ESL Challenger League Season 52: South America - Cup #3": "Nylyio3_OEx",
    "ESL Challenger League Season 52: North America - Cup #3": "41yion_ONx",
    "CCT Europe 2026 Series #11": "_rW8GEyWK",
    "CCT Europe 2026 Series #12 Play-In": "1sGIL2gAYu",
    "Thunderpick World Championship 2026": "5X5sFiL7H",
    "Stake Pulse Beat III": "EJZmJpBjeNx",
    "Elisa BreakOut Series #2": "4yn491uUVl",
}
# (fixture official pair, egw displayed pair, egw odds [a, b], egw time CEST, egw match url, notes)
ROWS = [
    ("Grêmio", "LOS NINOS", "Grêmio", "LOS NINOS", [1.75, 1.96], "13.10.26 21:00", "gremio-vs-los-ninos-ZbETIr-WFL", EV["sa7"], None),
    ("SUKEBAN", "your end", "your end", "SUKEBAN", [1.52, 2.3], "14.10.26 00:00", "your-end-vs-sukeban-uZgmpQMyd7", EV["sa7"], "side_order_reversed"),
    ("ex-Keyd Stars", "Galorys", "ex-Keyd Stars", "Galorys", [2.43, 1.48], "13.10.26 23:00", "ex-keyd-stars-vs-galorys-0LRbemybp", EV["esl_sa"], None),
    ("Zomblers", "Overtake Sector", "Zomblers", "Overtake Sector", [2.49, 1.45], "14.10.26 03:00", "zomblers-vs-overtake-sector-3aN5jQsN_", EV["esl_na"], None),
    ("Gothic", "Lavked", "Gothic", "Lavked", [1.881, 1.782], "14.10.26 10:00", "gothic-vs-lavked-GGmfuJ1n4B", EV["eu11"], None),
    ("ex-RUSTEC", "mellren", "ex-RUSTEC", "mellren", [1.39, 2.66], "14.10.26 13:00", "ex-rustec-vs-mellren-ZGVCwI7MK", EV["eu11"], None),
    ("G2 Ares", "The Last Resort", "G2 Ares", "The Last Resort", [1.465, 2.436], "14.10.26 16:00", "g2-ares-vs-the-last-resort-7GWb9EDd9L", EV["eu11"], None),
    ("FORZE Reload", "LFO 10", "FORZE Reload", "(blank)", [1.8, 1.8], "14.10.26 19:00", "forze-reload-vs-Gr_YhyKi3", EV["eu11"], "egw opponent field blank; joined via event+time+team_a against official fixture 1079624"),
    ("Enjoy", "B8 Academy", "ENJOY", "B8 Academy", [1.55, 2.25], "14.10.26 10:00", "enjoy-vs-b8-academy-qwO9cEnL7", EV["eu12pi"], None),
    ("Banda chuya", "6666", "banda chuya", "6666", [1.8, 1.8], "14.10.26 13:00", "banda-chuya-vs-6666-JdPgKgp5y", EV["eu12pi"], None),
    ("PCIFIC", "Ryvex", "PCIFIC Espor", "Ryvex", [1.8, 1.8], "14.10.26 16:00", "pcific-espor-vs-ryvex-WPw_DghZr3", EV["eu12pi"], "team name variant: PCIFIC Espor ~ PCIFIC"),
    ("mellren", "Privateer", "mellren", "Privateer Gaming", [1.8, 1.8], "16.10.26 16:00", "mellren-vs-privateer-gaming-ASh_MyDBS", EV["eu12pi"], "team name variant: Privateer Gaming ~ Privateer"),
    ("9z", "Aurora", "9z", "Aurora", [3.8, 1.2], "14.10.26 10:30", "9z-vs-aurora-Es9rrnIhb", EV["thp"], None),
    ("Falcons", "Ninjas in Pyjamas", "Falcons", "NiP", [1.2, 3.77], "14.10.26 13:00", "falcons-vs-nip-QSa-aeOIR", EV["thp"], "team name variant: NiP ~ Ninjas in Pyjamas"),
    ("Legacy", "PARIVISION", "Legacy", "PARIVISION", [1.64, 2.09], "14.10.26 15:30", "legacy-vs-parivision--TTc59QUDJ", EV["thp"], None),
    ("FURIA", "BetBoom", "FURIA", "BetBoom Team", [1.37, 2.73], "14.10.26 18:00", "furia-vs-betboom-team-ZeSbzy91oH", EV["thp"], "team name variant: BetBoom Team ~ BetBoom"),
    ("Astralis", "Sashi", "Astralis", "Sashi Esport", [1.08, 6.19], "14.10.26 12:00", "astralis-vs-sashi-esport-aGet1AP-0Z", EV["sp"], "team name variant: Sashi Esport ~ Sashi"),
    ("HOTU", "Fnatic", "HOTU", "fnatic", [1.93, 1.81], "14.10.26 12:00", "hotu-vs-fnatic-KjM3caFTC", EV["sp"], None),
    ("MIBR", "BC.Game", "MIBR", "BC.Game Esports", [1.64, 2.1], "15.10.26 12:00", "mibr-vs-bcgame-esports-X8nMpUjAX", EV["sp"], "team name variant: BC.Game Esports ~ BC.Game"),
    ("Heroic", "Envy", "Heroic", "Team Envy", [1.48, 2.55], "15.10.26 12:00", "heroic-vs-team-envy-NcCqzpPZdC", EV["sp"], "team name variant: Team Envy ~ Envy"),
    ("WROTBERRY", "EAC", "WBT", "EA Copenhagen", [2.01, 1.69], "15.10.26 10:00", "wbt-vs-ea-copenhagen-hSC7a2mtP", EV["elisa"], "team name variants: WBT ~ WROTBERRY, EA Copenhagen ~ EAC (joined via event+time+opponent double match)"),
    ("ENCE", "BOJONG", "ENCE", "BOJONG", [1.32, 3.2], "15.10.26 12:00", "ence-vs-bojong-qV78OzvXFg", EV["elisa"], None),
    ("WROTBERRY", "ENCE", "WBT", "ENCE", [1.62, 2.107], "15.10.26 14:00", "wbt-vs-ence-GQ0xieRgQS", EV["elisa"], "team name variant: WBT ~ WROTBERRY"),
    ("EAC", "BOJONG", "EA Copenhagen", "BOJONG", [1.19, 4.02], "15.10.26 16:00", "ea-copenhagen-vs-bojong-vBsvfnHU5", EV["elisa"], "team name variant: EA Copenhagen ~ EAC"),
    ("WROTBERRY", "BOJONG", "WBT", "BOJONG", [1.21, 3.99], "15.10.26 18:00", "wbt-vs-bojong-r7kNL0-LX6", EV["elisa"], "team name variant: WBT ~ WROTBERRY"),
    ("EAC", "ENCE", "EA Copenhagen", "ENCE", [1.51, 2.35], "15.10.26 20:00", "ea-copenhagen-vs-ence-kTR_sMK3PT", EV["elisa"], "team name variant: EA Copenhagen ~ EAC"),
    ("Voca", "Phantom", "Voca", "Phantom Esports", [1.87, 1.77], "16.10.26 10:00", "voca-vs-phantom-esports-zby52fbAja", EV["elisa"], "team name variant: Phantom Esports ~ Phantom"),
    ("HAVU", "RoundsGG", "HAVU", "Rounds", [1.2, 4.01], "16.10.26 12:00", "havu-vs-rounds-rg48QwsiJ9", EV["elisa"], "team name variant: Rounds ~ RoundsGG"),
    ("Voca", "HAVU", "Voca", "HAVU", [1.38, 2.7], "16.10.26 14:00", "voca-vs-havu-nQn6IrZXP", EV["elisa"], None),
    ("Phantom", "RoundsGG", "Phantom Esports", "Rounds", [1.05, 6.89], "16.10.26 16:00", "phantom-esports-vs-rounds-m6Cnk4tOxU", EV["elisa"], "team name variants: Phantom Esports ~ Phantom, Rounds ~ RoundsGG"),
    ("RoundsGG", "Voca", "Voca", "Rounds", [1.063, 6.4], "16.10.26 18:00", "voca-vs-rounds-_dTpdE0K7U", EV["elisa"], "side_order_reversed; variants: Rounds ~ RoundsGG"),
    ("Phantom", "HAVU", "Phantom Esports", "HAVU", [1.36, 2.85], "16.10.26 20:00", "phantom-esports-vs-havu-H8whr4r586", EV["elisa"], "team name variant: Phantom Esports ~ Phantom"),
]

# official fixture ids from data/cs2_matches.json (join by competition + team pair)
cs2 = json.loads((ROOT / "data" / "cs2_matches.json").read_text())
by_pair = {}
for m in cs2["matches"]:
    by_pair[(m["competition"], m["team_a"], m["team_b"])] = m
    by_pair[(m["competition"], m["team_b"], m["team_a"])] = m  # allow side swap lookup

out_rows = []
unmatched = []
for oa, ob, wa, wb, odds, cest, slug, comp, note in ROWS:
    m = by_pair.get((comp, oa, ob)) or by_pair.get((comp, ob, oa))
    if not m:
        unmatched.append([comp, oa, ob])
        continue
    # align odds to official side order (per-side compare with name-variant normalization)
    ALIAS = {
        "wbt": "wrotberry", "ea copenhagen": "eac", "rounds": "roundsgg",
        "nip": "ninjas in pyjamas", "pcific espor": "pcific", "privateer gaming": "privateer",
        "sashi esport": "sashi", "betboom team": "betboom", "bc.game esports": "bc.game",
        "team envy": "envy", "phantom esports": "phantom", "forze reload": "forze reload",
        "": "", "(blank)": "",
    }

    def norm(s):
        s = (s or "").lower().strip()
        return ALIAS.get(s, s)

    nw, nb = norm(wa), norm(wb)
    na, nbb = norm(m["team_a"]), norm(m["team_b"])
    if nw == na:
        oa_odds, ob_odds = odds
    elif nw == nbb:
        oa_odds, ob_odds = odds[1], odds[0]
    elif nb == nbb:
        oa_odds, ob_odds = odds
    elif nb == na:
        oa_odds, ob_odds = odds[1], odds[0]
    else:
        unmatched.append([comp, oa, ob, "side align fail", wa, wb])
        continue
    out_rows.append({
        "fixture_id": m["fixture_id"],
        "competition": comp,
        "team_a": m["team_a"], "team_b": m["team_b"],
        "decimal_odds_a": oa_odds, "decimal_odds_b": ob_odds,
        "egw_time_display": f"{cest} CEST",
        "official_start_utc": m["scheduled_start_time_utc"],
        "source_name": "egamersworld.com odds widget",
        "source_kind": "esports odds aggregator (external to Hotspawn)",
        "source_url": f"https://egamersworld.com/counterstrike/match/{EVSLUG[comp]}/{slug}",
        "join_note": note,
        "retrieved_at_utc": "2026-10-13T19:05:00Z",
        "hotspawn_pick_pct_used": False,
    })


doc = {
    "generated_at_utc": "2026-10-13T19:10:00Z",
    "source_page": "https://egamersworld.com/counterstrike/matches",
    "source_page_chunks_fetched": [1, 2, 3, 4, 5, 6],
    "rules": [
        "Raw decimal quotes from egamersworld's odds widget; not originated by Hotspawn.",
        "egamersworld times are CEST (UTC+2), verified against official play API UTC times.",
        "Hotspawn crowd pick percentages are never used as probabilities.",
        "Joins documented per row; name variants and side-order swaps recorded, nothing inferred.",
    ],
    "coverage": {
        "cs2_future_pickable": 32,
        "rows_with_egw_odds": len(out_rows),
        "unmatched": unmatched,
    },
    "rows": out_rows,
}
(ROOT / "data" / "cs2_odds_egamersworld.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print("rows:", len(out_rows), "unmatched:", unmatched)
