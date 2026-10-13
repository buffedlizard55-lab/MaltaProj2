#!/usr/bin/env python3
"""T2/T3: external odds dataset + probability derivation for the Hotspawn pick'em.

Policy (per project brief):
- Win probabilities are derived ONLY from external bookmaker lines
  (decimal odds captured from EGamersWorld's bookmaker widgets — GG.BET,
  BC.GAME or N1 Bet per event — plus GG.bet/Polymarket cross-checks where noted).
- Hotspawn community pick percentages are NEVER used to derive probabilities.
- Matches with no external line stay blank and are flagged "unverified".
  Values are never inferred or filled.

Method: proportional de-vig of a two-way decimal-odds market:
    p_i = (1/o_i) / (1/o_1 + 1/o_2)

Usage: python3 tools/build_odds.py   (from repo root)
Writes: data/odds.csv, data/probabilities.csv
"""

import csv
import os
import sys

CAPTURED_ON = "2026-10-13"

EGW = {
    "twc": "https://egamersworld.com/counterstrike/event/thunderpick-world-championship-2026-5X5sFiL7H",
    "stake": "https://egamersworld.com/counterstrike/event/stake-pulse-beat-iii-EJZmJpBjeNx",
    "cct": "https://egamersworld.com/counterstrike/event/cct-europe-2026-series-11-_rW8GEyWK",
    "na_cup": "https://egamersworld.com/counterstrike/event/esl-challenger-league-season-52-north-america-cup--41yion_ONx",
    "elisa": "https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
    "keyd_gal": "https://egamersworld.com/counterstrike/match/Nylyio3_OEx/ex-keyd-stars-vs-galorys-0LRbemybp",
    "worlds": "https://egamersworld.com/lol/event/2026-world-championship-q8qUtLA6g",
    "demacia": "https://egamersworld.com/lol/match/FqxSssBfV/fearx-vs-kt-rolster-tW-gg6CEW",
    "em_summer": "https://egamersworld.com/lol/match/z27dDLdCP/solary-vs-anubis-gaming-iwRXElWJ9",
    "c9_kc": "https://egamersworld.com/lol/match/q8qUtLA6g/cloud9-vs-karmine-corp-WI4DQTvQri",
}

# (match_id, expected_team1, expected_team2, odds_t1, odds_t2, bookmaker,
#  source_name, source_url, sec_name, sec_url, sec_odds_t1, sec_odds_t2, notes)
ODDS = [
    # ---- CS2: Thunderpick World Championship 2026 (S tier) ----
    ("1080176", "9z", "Aurora", 3.6, 1.27, "BC.GAME (via EGW)", "EGamersWorld event page", EGW["twc"], "", "", None, None, ""),
    ("1080177", "Falcons", "Ninjas in Pyjamas", 1.23, 3.95, "BC.GAME (via EGW)", "EGamersWorld event page", EGW["twc"], "", "", None, None, ""),
    ("1080178", "Legacy", "PARIVISION", 1.65, 2.18, "BC.GAME (via EGW)", "EGamersWorld event page", EGW["twc"], "", "", None, None, ""),
    ("1080179", "FURIA", "BetBoom", 1.37, 2.96, "BC.GAME (via EGW)", "EGamersWorld event page", EGW["twc"], "", "", None, None, ""),
    # ---- CS2: Stake Pulse Beat III (B tier) ----
    ("1079438", "Astralis", "Sashi", 1.08, 7.5, "GG.BET (via EGW)", "EGamersWorld event page", EGW["stake"], "", "", None, None, ""),
    ("1079439", "HOTU", "Fnatic", 1.97, 1.82, "GG.BET (via EGW)", "EGamersWorld event page", EGW["stake"], "", "", None, None, ""),
    ("1079440", "MIBR", "BC.Game", 1.68, 2.16, "GG.BET (via EGW)", "EGamersWorld event page", EGW["stake"], "", "", None, None, ""),
    ("1079442", "Heroic", "Envy", 1.45, 2.73, "GG.BET (via EGW)", "EGamersWorld event page", EGW["stake"], "", "", None, None, ""),
    # ---- CS2: CCT Europe 2026 Series #11 (B tier) ----
    ("1079621", "Gothic", "Lavked", 1.881, 1.782, "BC.GAME (via EGW)", "EGamersWorld event page", EGW["cct"], "", "", None, None, ""),
    ("1079623", "G2 Ares", "The Last Resort", 1.465, 2.436, "BC.GAME (via EGW)", "EGamersWorld event page", EGW["cct"], "", "", None, None, ""),
    # 1079622 ex-RUSTEC vs mellren — no market published (EGW widget shows 1.8/1.8 placeholder)
    # 1079624 FORZE Reload vs LFO 10 — no market published (opponent absent from EGW database)
    # ---- CS2: ESL Challenger League cups (B tier) ----
    ("1081076", "ex-Keyd Stars", "Galorys", 2.43, 1.46, "EGW bookmaker widget", "EGamersWorld match page", EGW["keyd_gal"],
     "EGWxxxBOT market aggregate (same page)", EGW["keyd_gal"], 2.508, 1.464,
     "earlier same-day widget capture 2.366/1.53; aggregate quotes Galorys 1.464 / ex-Keyd 2.508"),
    ("1079546", "Zomblers", "Overtake Sector", 2.46, 1.48, "BC.GAME (via EGW)", "EGamersWorld event page", EGW["na_cup"], "", "", None, None, ""),
    # ---- CS2: Elisa BreakOut Series #2 (C tier, 12 matches) ----
    ("1080279", "WROTBERRY", "EAC", 2.01, 1.69, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW team names WBT / EA Copenhagen"),
    ("1080280", "ENCE", "BOJONG", 1.29, 3.25, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, ""),
    ("1080281", "WROTBERRY", "ENCE", 1.6, 2.2, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW team name WBT"),
    ("1080282", "EAC", "BOJONG", 1.19, 4.02, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW team name EA Copenhagen"),
    ("1080283", "WROTBERRY", "BOJONG", 1.19, 4.14, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW team name WBT"),
    ("1080284", "EAC", "ENCE", 1.51, 2.35, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW team name EA Copenhagen"),
    ("1080285", "Voca", "Phantom", 1.9, 1.81, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW team name Phantom Esports"),
    ("1080286", "HAVU", "RoundsGG", 1.23, 3.71, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW team name Rounds"),
    ("1080287", "Voca", "HAVU", 1.38, 2.79, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, ""),
    ("1080288", "Phantom", "RoundsGG", 1.08, 6.3, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW team names Phantom Esports / Rounds"),
    ("1080289", "RoundsGG", "Voca", 6.0, 1.09, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW lists as 'Voca VS Rounds' (Voca 1.09 / Rounds 6.0); mapped by team name"),
    ("1080290", "Phantom", "HAVU", 1.37, 2.84, "GG.BET (via EGW)", "EGamersWorld event page", EGW["elisa"], "", "", None, None, "EGW team name Phantom Esports"),
    # ---- LoL ----
    ("1076650", "KT Rolster", "BNK FearX", 1.31, 3.27, "EGW bookmaker widget", "EGamersWorld match page", EGW["demacia"],
     "Polymarket series moneyline", "https://polymarket.com/esports/league-of-legends/demacia-cup-global-invitational/lol-fox1-kt-2026-10-14", 65, 36,
     "Polymarket cents (KT 65c / BNK 36c); earlier same-day widget capture 1.38/2.79; EGW lists teams as 'FearX VS KT Rolster'"),
    ("1079335", "Solary", "Anubis Gaming", 1.14, 5.31, "EGW bookmaker widget", "EGamersWorld match page", EGW["em_summer"], "", "", None, None,
     "odds captured via EGamersWorld LoL tips widget 2026-10-13"),
    ("1075808", "Cloud9", "Karmine Corp", 2.71, 1.41, "N1 Bet (via EGW)", "EGamersWorld match page", EGW["c9_kc"],
     "GG.bet (via tips.gg / win.gg)", "https://tips.gg/article/worlds-championship-2026-play-in-round-1-betting-predictions-tournament-winner-event-story/", 2.41, 1.54,
     "GG.bet C9 2.41 / KC 1.54 (also on win.gg); EGW widget 2.71/1.41"),
    ("1075807", "FURIA", "MVK Esports", 1.26, 3.37, "N1 Bet (via EGW)", "EGamersWorld event page", EGW["worlds"], "", "", None, None, ""),
    # 1076025 Mental Rush vs SK Gaming Avarosa — no market published (EGW widget 1.8/1.8 placeholder)
    # 1076026 Vitality Rising Bees vs G2 Hel — no market published (EGW widget 1.8/1.8 placeholder)
]

NOT_PRICED_NOTES = {
    "1079622": "No external market published 2026-10-13 (EGW widget showed 1.8/1.8 placeholder) - unverified",
    "1079624": "No external market published 2026-10-13; opponent 'LFO 10' absent from EGW database - unverified",
    "1076025": "No external market published 2026-10-13 (EGW widget showed 1.8/1.8 placeholder) - unverified",
    "1076026": "No external market published 2026-10-13 (EGW widget showed 1.8/1.8 placeholder) - unverified",
}


def devig(o1, o2):
    i1, i2 = 1.0 / o1, 1.0 / o2
    s = i1 + i2
    return round(100.0 * i1 / s, 1), round(100.0 * i2 / s, 1)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    matches_path = os.path.join(root, "data", "matches.csv")
    with open(matches_path, newline="", encoding="utf-8") as f:
        matches = {r["match_id"]: r for r in csv.DictReader(f)}

    by_id = {}
    for rec in ODDS:
        mid = rec[0]
        if mid in by_id:
            sys.exit(f"duplicate odds record for {mid}")
        if mid not in matches:
            sys.exit(f"odds record {mid} not found in matches.csv")
        m = matches[mid]
        if (m["team1"], m["team2"]) != (rec[1], rec[2]):
            sys.exit(f"team mismatch {mid}: csv=({m['team1']},{m['team2']}) odds=({rec[1]},{rec[2]})")
        by_id[mid] = rec

    odds_rows = []
    prob_rows = []
    for mid, m in matches.items():
        rec = by_id.get(mid)
        note = rec[12] if rec else NOT_PRICED_NOTES.get(mid, "No external bookmaker line found in T2 source sweep - unverified")
        if rec:
            _, t1, t2, o1, o2, book, sname, surl, secname, securl, so1, so2, _ = rec
            p1, p2 = devig(o1, o2)
            status = "verified"
            sec_txt = ""
            if secname:
                if securl == surl and so1 is not None and so2 is not None and so1 > 10:
                    sec_txt = f"{secname}: {so1}/{so2}"
                elif so1 is not None and so2 is not None:
                    sec_txt = f"{secname}: {so1}/{so2} ({securl})"
            odds_rows.append([
                mid, m["game"], m["tournament"], t1, t2, book,
                f"{o1}", f"{o2}", sname, surl,
                secname, securl, "" if so1 is None else so1, "" if so2 is None else so2,
                CAPTURED_ON, note,
            ])
            prob_rows.append([
                mid, m["game"], m["tournament"], t1, t2, p1, p2,
                f"{o1}", f"{o2}", book, surl,
                "proportional de-vig of external decimal odds (never Hotspawn pick %)",
                status, note,
            ])
        else:
            odds_rows.append([
                mid, m["game"], m["tournament"], m["team1"], m["team2"], "",
                "", "", "", "", "", "", "", "", CAPTURED_ON, note,
            ])
            prob_rows.append([
                mid, m["game"], m["tournament"], m["team1"], m["team2"], "", "",
                "", "", "", "", "no external line - not derived", "unverified", note,
            ])

    with open(os.path.join(root, "data", "odds.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["match_id", "game", "tournament", "team1", "team2", "bookmaker",
                    "odds_team1", "odds_team2", "source_name", "source_url",
                    "secondary_source_name", "secondary_source_url",
                    "secondary_odds_team1", "secondary_odds_team2",
                    "captured_on", "notes"])
        w.writerows(odds_rows)

    with open(os.path.join(root, "data", "probabilities.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["match_id", "game", "tournament", "team1", "team2",
                    "team1_prob_pct", "team2_prob_pct", "odds_team1", "odds_team2",
                    "bookmaker", "source_url", "method", "status", "notes"])
        w.writerows(prob_rows)

    priced = sum(1 for r in odds_rows if r[6])
    cs2_p = sum(1 for r in odds_rows if r[1] == "CS2" and r[6])
    lol_p = sum(1 for r in odds_rows if r[1] == "LoL" and r[6])
    print(f"matches={len(matches)} odds rows={len(odds_rows)} priced={priced} (CS2 {cs2_p}/26, LoL {lol_p}/{sum(1 for m in matches.values() if m['game']=='LoL')})")
    print("unpriced CS2:", [r[0] for r in odds_rows if r[1] == "CS2" and not r[6]])


if __name__ == "__main__":
    main()
