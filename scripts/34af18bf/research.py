#!/usr/bin/env python3
"""Dated, source-linked research ledger for session 34af18bf.

Rules for this file (enforced by tests/test_34af18bf.py):

* every entry carries the exact URL it was read from and the UTC read time;
* nothing is inferred: a value that could not be read from a source is ``None``
  and appears on the Flagged-for-review page instead of being filled in;
* a crowd/pick percentage is ownership, never a probability.

The read times below are this session's own page reads (2026-10-17, UTC). The
live market numbers the runner re-reads on every refresh come from
``data/34af18bf/snapshot.json``, not from here; this file holds the facts that
do not move (results, rosters, head-to-heads, kick-offs) plus the dated
line readings this desk made before the automated sources opened.
"""
from __future__ import annotations

READ_UTC = "2026-10-17T00:45:00Z"
SESSION = "34af18bf"

# --------------------------------------------------------------------------- sources
SOURCES = {
    "hltv_event": ("HLTV — Thunderpick World Championship 2026 event page (bracket, schedule)",
                   "https://www.hltv.org/events/8932/thunderpick-world-championship-2026"),
    "hltv_day1_9z_aurora": ("HLTV — 9z vs Aurora TWC 2026 (map scores, veto, match stats)",
                            "https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026"),
    "hltv_news_45718": ("HLTV — “9z beat Aurora 2-0 to kick off TWC 2026” (14 Oct 2026)",
                        "https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026"),
    "hltv_news_45736": ("HLTV — “Aurora beat 9z to secure third consecutive top-four appearance” (16 Oct 2026)",
                        "https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance"),
    "hltv_news_45739": ("HLTV — “BETBOOM qualify for TWC playoffs over Legacy” (16 Oct 2026)",
                        "https://www.hltv.org/news/45739/betboom-qualify-for-twc-playoffs-over-legacy"),
    "hltv_sf1": ("HLTV — FURIA vs Aurora, semi-final 1 (17 Oct 2026, match page + odds/prediction page)",
                 "https://www.hltv.org/matches/2399414/furia-vs-aurora-thunderpick-world-championship-2026"),
    "hltv_sf2": ("HLTV — Falcons vs BETBOOM, semi-final 2 (17 Oct 2026, match page)",
                 "https://www.hltv.org/matches/2399415/falcons-vs-betboom-thunderpick-world-championship-2026"),
    "hltv_aurora_team": ("HLTV — Aurora team overview (active five, coach, roster timeline, transfers)",
                         "https://www.hltv.org/team/11861/aurora"),
    "hltv_news_45082": ("HLTV — “Official: Aurora complete rebuild with kyxsan” (8 Jul 2026)",
                        "https://www.hltv.org/news/45082/official-aurora-complete-rebuild-with-kyxsan"),
    "liquipedia_twc": ("Liquipedia — Thunderpick World Championship 2026 (bracket, remaining schedule)",
                       "https://liquipedia.net/counterstrike/Thunderpick/World_Championship/2026"),
    "liquipedia_aurora": ("Liquipedia — Aurora Gaming (active roster and join dates)",
                          "https://liquipedia.net/counterstrike/Aurora_Gaming"),
    "liquipedia_transfers": ("Liquipedia — Transfers/2026 (deko to Aurora, inactive, 2026-09-17)",
                             "https://liquipedia.net/counterstrike/Transfers/2026"),
    "hs_preview": ("HotSpawn — “Can BetBoom Upset Favorites Falcons?” semi-final preview (16 Oct 2026)",
                   "https://www.hotspawn.com/counter-strike/news/thunderpick-world-championship-2026-semi-preview"),
    "hs_tournament": ("HotSpawn — Thunderpick World Championship 2026 tournament page (fixtures and scores)",
                      "https://www.hotspawn.com/counter-strike/tournament/thunderpick-world-championship-2026"),
    "hs_lobby_twc": ("HotSpawn Play — pick'em lobby for competition 35859 (the two TWC semi-final cards)",
                     "https://play.hotspawn.com/lobby?competitionId=35859"),
    "egw_aurora_9z": ("EGamersWorld — “Aurora Defeat 9z to Reach the TWC 2026 Semifinals” (Cache 13:11, Inferno 13:4)",
                      "https://egamersworld.com/counterstrike/news/37859/aurora-defeat-9z-to-reach-the-thunderpick-world-ch-eTQEyTXgU"),
    "flm_day1": ("Field Level Media / Miami Herald — day-1 and day-2 map-by-map wrap (Falcons, FURIA advance to semis)",
                 "https://www.miamiherald.com/sports/article317644856.html"),
    "pley_semis": ("Pley.gg — “Aurora and Legacy face elimination as Falcons and FURIA wait in Thunderpick semi-finals”",
                   "https://pley.gg/cs2/aurora-and-legacy-face-elimination-as-falcons-and-furia-wait-in-thunderpick-semi-finals/"),
    "esport_vision": ("esport.vision — TWC 2026 schedule, bracket and results (semi-finals 14:00 / 17:00)",
                      "https://esport.vision/cs2/tournament/11069-thunderpick-world-championship-2026"),
    "valve_vrs": ("Valve — official Counter-Strike regional standings (counter-strike_regional_standings repo)",
                  "https://github.com/ValveSoftware/counter-strike_regional_standings"),
    "bo3gg_semis": ("bo3.gg — Thunderpick coefficient feed (semis priced FURIA 1.85/Aurora 1.85 and Falcons 1.20/BetBoom 4.00)",
                    "https://bo3.gg/matches"),
    "kalshi_semis": ("Kalshi exchange — KXCS2GAME markets for both semi-finals (Aurora 2.11/FURIA 1.94; BetBoom 5.00/Falcons 1.27)",
                     "https://kalshi.com/markets/kxcs2game"),
}

# --------------------------------------------------------------------------- results
# Every series of the 2026 TWC group stage, in order, with the map scores this
# session could read on an official/primary page. A ``None`` map score means the
# value was not read from a source and is published blank, never guessed.
TWC_RESULTS = [
    {"day": "Day 1 — 14 Oct", "stage": "Group A opening", "winner": "9z", "loser": "Aurora",
     "score": "2-0", "winner_a": True,
     "maps": [("Inferno", 13, 11, "(8:4; 5:7)"), ("Nuke", 13, 1, "(11:1; 2:0)")],
     "source": "hltv_day1_9z_aurora",
     "note": "The day-1 upset: 9z (VRS #17 at the time) beat Aurora (VRS #5). Aurora picked Nuke "
             "and lost it 1-13; 9z picked Inferno and closed it 13-11. HLTV match stats: luchov 1.61."},
    {"day": "Day 1 — 14 Oct", "stage": "Group A opening", "winner": "Falcons", "loser": "Ninjas in Pyjamas",
     "score": "2-0", "winner_a": True,
     "maps": [("Ancient", 16, 13, "overtime"), ("Dust2", 13, 6, "")],
     "source": "flm_day1", "note": "m0NESY 40 kills, +17; stavn 31 kills for NIP."},
    {"day": "Day 1 — 14 Oct", "stage": "Group B opening", "winner": "Legacy", "loser": "PARIVISION",
     "score": "2-0", "winner_a": True, "maps": None, "source": "flm_day1",
     "note": "Two tight maps; the per-map scores were not read from a primary source in this session "
             "and are therefore blank (flagged)."},
    {"day": "Day 1 — 14 Oct", "stage": "Group B opening", "winner": "FURIA", "loser": "BETBOOM",
     "score": "2-0", "winner_a": True,
     "maps": [("Ancient", 13, 10, ""), ("Mirage", 13, 9, "")],
     "source": "flm_day1", "note": "KSCERATO 40 kills, +16."},
    {"day": "Day 2 — 15 Oct", "stage": "Group A winners' match", "winner": "Falcons", "loser": "9z",
     "score": "2-1", "winner_a": True,
     "maps": [("Nuke", 13, 9, ""), ("Mirage", 8, 13, ""), ("Dust2", 13, 9, "")],
     "source": "pley_semis", "note": "TeSeS 1.26, 47 kills; luchov matched him for 9z."},
    {"day": "Day 2 — 15 Oct", "stage": "Group A elimination", "winner": "Aurora", "loser": "Ninjas in Pyjamas",
     "score": "2-0", "winner_a": True,
     "maps": [("Cache", 13, 9, ""), ("Dust2", 13, 7, "")],
     "source": "flm_day1", "note": "Wicadia 45 kills, +20; NIP eliminated."},
    {"day": "Day 2 — 15 Oct", "stage": "Group B winners' match", "winner": "FURIA", "loser": "Legacy",
     "score": "2-1", "winner_a": True,
     "maps": [("Cache", 10, 13, ""), ("Inferno", 13, 5, ""), ("Mirage", 13, 8, "")],
     "source": "flm_day1", "note": "molodoy 48 kills, +13; FURIA to the semi-finals."},
    {"day": "Day 2 — 15 Oct", "stage": "Group B elimination", "winner": "BETBOOM", "loser": "PARIVISION",
     "score": "2-1", "winner_a": True,
     "maps": [("Ancient", 10, 13, ""), ("Anubis", 13, 4, ""), ("Mirage", 13, 7, "")],
     "source": "flm_day1", "note": "zorte 51 kills, +17; PARIVISION eliminated."},
    {"day": "Day 3 — 16 Oct", "stage": "Group A decider", "winner": "Aurora", "loser": "9z",
     "score": "2-0", "winner_a": True,
     "maps": [("Cache", 13, 11, ""), ("Inferno", 13, 4, "")],
     "source": "hltv_news_45736",
     "note": "The day-1 result avenged. kyxsan 1.45 rating, MVP of the match (EGamersWorld). "
             "9z eliminated and extended their run of group-stage exits to five events."},
    {"day": "Day 3 — 16 Oct", "stage": "Group B decider", "winner": "BETBOOM", "loser": "Legacy",
     "score": "2-1", "winner_a": True,
     "maps": [("Nuke", 16, 13, "overtime, from 4-10 down"), ("Dust2", 11, 13, ""), ("Mirage", 13, 11, "")],
     "source": "hltv_news_45739",
     "note": "BETBOOM took the last play-off slot; Magnojez 62 kills across the three maps (HotSpawn)."},
]

# Day-4 schedule (play-offs). Kick-offs are read from the official event/match pages;
# HotSpawn does not publish a kick-off of its own for these two rows.
TWC_DAY4 = [
    {"fixture_id": "1080207", "label": "Semi-final 1", "team_a": "FURIA", "team_b": "Aurora",
     "start_utc": "2026-10-17T14:00:00Z", "hltv_match_id": "2399414", "best_of": 3,
     "source": "hltv_sf1", "hotspawn_url": "https://www.hotspawn.com/matches/furia-vs-aurora-thunderpick-world-championship-2026-1080207",
     "crowd_ownership": {"FURIA": 75, "Aurora": 25}, "offered_points": 7, "tier": "S"},
    {"fixture_id": "1080208", "label": "Semi-final 2", "team_a": "Falcons", "team_b": "BETBOOM",
     "start_utc": "2026-10-17T17:00:00Z", "hltv_match_id": "2399415", "best_of": 3,
     "source": "hltv_sf2", "hotspawn_url": "https://www.hotspawn.com/matches/falcons-vs-betboom-thunderpick-world-championship-2026-1080208",
     "crowd_ownership": {"Falcons": 100, "BETBOOM": 0}, "offered_points": 7, "tier": "S"},
]

TWC_REMAINING = [
    {"when_utc": "2026-10-18T11:30:00Z", "label": "Third-place decider (CE(S)T 13:30)", "source": "pley_semis",
     "teams": None, "note": "Bracket place-holder on the official event page; participants not fixed at read time."},
    {"when_utc": "2026-10-18T15:00:00Z", "label": "Grand final (CE(S)T 17:00)", "source": "liquipedia_twc",
     "teams": None, "note": "Winner of both semi-finals; participants not fixed at read time."},
]

# --------------------------------------------------------------------------- rosters
ROSTER_AUDIT = {
    "Aurora": {
        "active_five": ["XANTARES", "woxic", "Wicadia", "Jimpphat", "kyxsan"],
        "coach": "ash (Ashley Battye)",
        "last_active_lineup_change": {
            "date": "2026-07-08",
            "what": "kyxsan joins from Falcons as IGL; Jimpphat (MOUZ) and coach ash join on 2026-07-03; "
                    "MAJ3R, soulfly and coach Fabre leave",
            "sources": ["hltv_news_45082", "hltv_aurora_team", "liquipedia_aurora", "liquipedia_transfers"],
        },
        "recent_non_playing_move": {
            "date": "2026-09-17",
            "what": "deko (Denis Zhukov) listed on Aurora's **inactive** roster — not the active five",
            "sources": ["liquipedia_transfers", "hltv_aurora_team"],
            "flag": "The two tracked sources disagree on the month (Liquipedia dates the move 2026-09-17; "
                    "HLTV's roster timeline renders deko in the Oct column). Neither source shows deko in "
                    "the active line-up, and no source shows an Aurora substitution after 8 July 2026. "
                    "Published as an unresolved roster question, not as a line-up change.",
        },
        "rest_before_semi": "Aurora's previous series (Group A decider) was played 2026-10-16 14:00 UTC "
                            "and lasted two maps — about 24 hours before the semi-final.",
        "form": "Three consecutive top-four finishes; beat FURIA 2-1 at ESL Pro League Season 24 on 6 Oct 2026.",
        "sources": ["hltv_news_45736", "hltv_sf1", "hs_preview"],
    },
    "FURIA": {
        "active_five": ["KSCERATO", "yuurih", "YEKINDAR", "molodoy", "FalleN"],
        "coach": None,
        "last_active_lineup_change": None,
        "rest_before_semi": "FURIA's previous series (Group B winners' match) was played 2026-10-15 18:00 UTC "
                            "and lasted three maps — about 44 hours before the semi-final.",
        "form": "Defending TWC champions; KSCERATO 1.43 at the event, YEKINDAR 0.95.",
        "sources": ["hltv_sf1", "hs_preview", "flm_day1"],
    },
    "Falcons": {
        "active_five": ["karrigan", "NiKo", "m0NESY", "TeSeS", "kyousuke"],
        "coach": None,
        "last_active_lineup_change": None,
        "rest_before_semi": "Falcons' previous series (Group A winners' match) was played 2026-10-15 ~13:00 UTC "
                            "— about 52 hours before the semi-final.",
        "form": "Reigning IEM Cologne Major champions; TeSeS 1.26 vs 9z while m0NESY/kyousuke posted 0.98/0.92.",
        "sources": ["hltv_sf2", "hs_preview", "hltv_event"],
    },
    "BETBOOM": {
        "active_five": ["zorte", "Magnojez", "Boombl4", "s1ren", "d1Ledez"],
        "coach": None,
        "last_active_lineup_change": None,
        "rest_before_semi": "BETBOOM's previous series (Group B decider) was played 2026-10-16 17:00 UTC and "
                            "went three maps, ending around 20:00 UTC — under 24 hours before the semi-final.",
        "form": "Beat Falcons 2-0 at the IEM Cologne Major; Magnojez 62 kills across the Legacy decider.",
        "sources": ["hltv_news_45739", "hs_preview", "hs_tournament"],
    },
}

# --------------------------------------------------------------------------- head-to-head
H2H = [
    {"pair": ("Aurora", "FURIA"), "when": "2026-10-06", "event": "ESL Pro League Season 24 (group stage)",
     "result": "Aurora 2-1 FURIA", "source": "hltv_news_45736",
     "note": "11 days before the semi-final, and the only 2026 meeting recorded by HLTV."},
    {"pair": ("Falcons", "BETBOOM"), "when": "IEM Cologne Major 2026", "event": "IEM Cologne Major 2026",
     "result": "BETBOOM 2-0 Falcons", "source": "hs_preview",
     "note": "BETBOOM picked Nuke and Falcons picked Ancient; Falcons lost both maps."},
    {"pair": ("9z", "Aurora"), "when": "2026-10-14 and 2026-10-16", "event": "TWC 2026 Group A",
     "result": "9z 2-0, then Aurora 2-0", "source": "hltv_news_45736",
     "note": "The upset and the avenge; 9z lead 4-2 in maps across three 2026 meetings (HLTV team page)."},
]

# --------------------------------------------------------------------------- map pool
MAP_POOL_NOTES = [
    {"team": "Aurora", "map": "Nuke", "fact": "77.8% win rate over three months (HLTV map stats), but lost it 1-13 to 9z on day 1.",
     "source": "hltv_aurora_team"},
    {"team": "FURIA", "map": "Cache", "fact": "Lost Cache to Legacy (10-13) then won Inferno and Mirage comfortably.",
     "source": "flm_day1"},
    {"team": "BETBOOM", "map": "Nuke", "fact": "Won Nuke 16-13 from 4-10 down in the Legacy decider.",
     "source": "hltv_news_45739"},
    {"team": "Falcons", "map": "Mirage / Ancient", "fact": "Lost Mirage 8-13 to 9z and, at the Cologne Major, lost both "
     "Ancient and Nuke to BETBOOM.", "source": "hs_preview"},
]

# --------------------------------------------------------------------------- dated market readings
# Read by this session before the automated collector opened. The runner replaces
# these with live quotes every four hours; they are kept as a dated cross-check and
# to show what the market looked like when the day-4 decision was written.
DATED_MARKET_READINGS = [
    {"match": ("FURIA", "Aurora"), "source": "bo3gg_semis", "kind": "esportsbook (Thunderpick coefficients)",
     "decimal": (1.85, 1.85), "read_utc": "2026-10-17T00:40:00Z",
     "note": "Two-sided 1.85/1.85 — a pure coin flip before the vig."},
    {"match": ("FURIA", "Aurora"), "source": "kalshi_semis", "kind": "exchange (Kalshi KXCS2GAME)",
     "decimal": (1.94, 2.11), "read_utc": "2026-10-17T00:40:00Z",
     "note": "FURIA 1.94 / Aurora 2.11 with a 0.01 spread — the tightest book on the board."},
    {"match": ("Falcons", "BETBOOM"), "source": "bo3gg_semis", "kind": "esportsbook (Thunderpick coefficients)",
     "decimal": (1.20, 4.00), "read_utc": "2026-10-17T00:40:00Z",
     "note": "Falcons a heavy favourite; BETBOOM the longest price on the slate."},
    {"match": ("Falcons", "BETBOOM"), "source": "kalshi_semis", "kind": "exchange (Kalshi KXCS2GAME)",
     "decimal": (1.27, 5.00), "read_utc": "2026-10-17T00:40:00Z",
     "note": "Exchange agrees with the bookmaker within ~2 points of no-vig probability."},
]

# --------------------------------------------------------------------------- line-up of the desk's rules
CONTRARIAN_RULES = [
    {"id": "C1", "rule": "Not stupid: a climb pick must keep at least a 20% win probability from the external "
                         "market consensus — never below one win in five. Below that it is a lottery ticket, not a pick. "
                         "The market must also be the one that gives it that chance: a crowd-only underdog with no book price "
                         "is not eligible."},
    {"id": "C2", "rule": "Real differential: the pick's market probability must exceed its HotSpawn crowd "
                         "ownership share. Expected differential = offered points × (probability − ownership)."},
    {"id": "C3", "rule": "Two verified context flags before a climb pick is activated: a head-to-head result, "
                         "a roster/onboarding change, a rest/back-to-back edge, or a veto/map-pool edge — each "
                         "with its own dated source."},
    {"id": "C4", "rule": "Maximum three activated climb picks per day; every other match gets the market "
                         "favourite as the safe pick."},
    {"id": "C5", "rule": "A crowd percentage is ownership only. It never enters a probability, and HotSpawn is "
                         "never used as a source of win probability."},
]

# --------------------------------------------------------------------------- limitation text
LIMITATIONS = [
    "HLTV, EGamersWorld, GG.bet, Stake, Betano, VBet and Thunderpick's own site refuse the GitHub runner's IP "
    "range (HTTP 403). Their pages are therefore read by the agent (dated, quoted above) and re-checked manually, "
    "while the four-hourly refresh relies on the sources that do answer the runner.",
    "HotSpawn's own kick-off timestamps for the two semi-finals are rendered in the viewer's timezone; the desk uses "
    "the official match-page kick-offs (14:00Z and 17:00Z) and keeps HotSpawn's lock time from the fixtures API.",
    "A pick is a model output from market prices, not a guarantee. Rows whose only basis is the originated "
    "Valve-VRS transform are labelled ORIGINATED on every page.",
    "Where no external two-sided price exists and the ratings are missing or ambiguous, the probability stays blank "
    "and the row appears in the Unresolved picks & limitations section — never as an invented 50/50.",
]
