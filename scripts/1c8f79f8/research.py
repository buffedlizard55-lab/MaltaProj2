#!/usr/bin/env python3
"""Curated research ledger for session 1c8f79f8 (TWC day-4 desk).

Every number here was read line-by-line from a retained external source on
2026-10-16 between ~19:35Z and ~20:45Z and is stored with its source URL and
read time. Nothing is copied from HotSpawn crowd percentages: those are stored
as ownership context only (asserted by tests/test_1c8f79f8.py).

Probability bases:
  market  = de-vigged two-sided price from a real venue (Polymarket exchange,
            bc.game / bookmaker averages via egamersworld, stavka.tv Russian
            bookmaker consensus, kushvsporte.ru bookmaker aggregator)
  model   = Valve VRS glicko model, canonical site formula (k=0.25 fitted on
            bookmaker pairs; copied from scripts/fe803b80/core.py)
  blank   = no eligible evidence -> probability stays BLANK, pick may still be
            given directionally from verified context and is flagged

TWC semifinals are NOT listed on HotSpawn (verified: no Thunderpick World
Championship Malta competition_id exists in the fixtures API response); they
are originated externally and flagged not-listed.
"""
from __future__ import annotations

RETRIEVED_UTC = "2026-10-16T20:45:00Z"

# ---------------------------------------------------------------------------
# Valve VRS points (ValveSoftware/counter-strike_regional_standings,
# live/2026/standings_global_2026_10_05.md, read 2026-10-16 ~19:50Z) and the
# fresher HLTV valve-ranking pages of 2026-10-14/15 where noted.
# ---------------------------------------------------------------------------
VRS = {
    "HEROIC": {"points": 1550, "standing": 15, "snapshot": "2026_10_05"},
    "Ninjas in Pyjamas": {"points": 1534, "standing": 18, "snapshot": "2026_10_05"},
    "BET-M": {"points": 1149, "standing": 71, "snapshot": "2026_10_05"},
    "Just Players": {"points": 974, "standing": 118, "snapshot": "2026_10_05"},
    "Eternal Fire": {"points": 1429, "standing": 33, "snapshot": "2026_10_05"},
    "Nuclear TigeRES": {"points": 1324, "standing": 46, "snapshot": "2026_10_05"},
    "GenOne": {"points": 1185, "standing": 66, "snapshot": "2026_10_05"},
    "Butterfly": {"points": 1082, "standing": 88, "snapshot": "2026_10_05"},
    "Bebop": {"points": 702, "standing": 212, "snapshot": "2026_10_05"},
    "DONSTU": {"points": 732, "standing": 197, "snapshot": "2026_10_05"},
    "Betclic": {"points": 1333, "standing": 45, "snapshot": "2026_10_05",
                "note": "Valve table name for Betclic Apogee Esports (Polish org; "
                        "Demho/Prism carried over from the PGL Bucharest 2025 roster)"},
    "Nemesis": {"points": 1455, "standing": 29, "snapshot": "2026_10_05"},
    "BAKS": {"points": 1044, "standing": 100, "snapshot": "2026_10_05"},
    "Fire Flux": {"points": 907, "standing": 131, "snapshot": "2026_10_05"},
    "Banda Chuya": {"points": 801, "standing": 165, "snapshot": "2026_10_05"},
    "Enjoy": {"points": 871, "standing": 138, "snapshot": "2026_10_05",
              "note": "roster changed after this snapshot (see fixture flags)"},
    "ex-6666": {"points": 1007, "standing": 107, "snapshot": "2026-10-15 HLTV valve-ranking",
                "note": "freshest reading; the Oct-5 Valve file lists the same players "
                        "under the 6666 name at #127 / 923 pt"},
    "Privateer": {"points": 641, "standing": 241, "snapshot": "2026-10-15 HLTV valve-ranking",
                  "note": "freshest reading; Oct-5 file has #271 / 608 pt"},
    "Phantom Academy": {"points": 760, "standing": 121, "snapshot": "2026-10-15 HLTV valve-ranking (EU region)"},
    "antidaun": {"points": 602, "standing": 186, "snapshot": "2026-10-15 HLTV valve-ranking (EU region)"},
    "INFINITE": {"points": 1259, "standing": 56, "snapshot": "2026_10_05"},
    "aimclub": {"points": 1113, "standing": 77, "snapshot": "2026_10_05"},
    "BASEMENT BOYS": {"points": 1036, "standing": 102, "snapshot": "2026_10_05"},
    "BC.Game": {"points": 1318, "standing": 50, "snapshot": "2026_10_05"},
    "Drama": {"points": 845, "standing": 148, "snapshot": "2026_10_05"},
    "WBT": {"points": 1201, "standing": 60, "snapshot": "2026_10_05",
            "note": "WhiteBIT Team; HotSpawn API renders the name as WROTBERRY "
                    "(egamersworld slug 'wrotberry')"},
    "Nexus": {"points": 1008, "standing": 111, "snapshot": "2026_10_05"},
    "Iberian Soul": {"points": 1218, "standing": 59, "snapshot": "2026_10_05"},
    "HYPERSPIRIT": {"points": 803, "standing": 162, "snapshot": "2026_10_05"},
    "Sashi": {"points": 1131, "standing": 73, "snapshot": "2026_10_05"},
    "MOUZ NXT": {"points": 877, "standing": 137, "snapshot": "2026_10_05"},
    "ASTRAL": {"points": 1072, "standing": 91, "snapshot": "2026_10_05"},
    "Leo": {"points": 1001, "standing": 112, "snapshot": "2026_10_05"},
    "Lynn Vision": {"points": 1190, "standing": 64, "snapshot": "2026_10_05"},
    "Rare Atom": {"points": 906, "standing": 133, "snapshot": "2026_10_05"},
    "Alter Ego": {"points": 819, "standing": 155, "snapshot": "2026_10_05",
                  "note": "roster changed after this snapshot (see fixture flags)"},
    "Chinggis Warriors": {"points": 1084, "standing": 87, "snapshot": "2026_10_05"},
    "NEXVOID": {"points": 995, "standing": 113, "snapshot": "2026_10_05"},
    "Vitalem Aerem": {"points": 721, "standing": 204, "snapshot": "2026_10_05",
                      "note": "one player differs from the current egamersworld lineup"},
    # TWC teams
    "FURIA": {"points": 1829, "standing": 7, "snapshot": "2026_10_05"},
    "Aurora": {"points": 1716, "standing": 9, "snapshot": "2026_10_05",
               "note": "HLTV live VRS forecast on match day reads Aurora 1848 pt (#5) "
                       "vs FURIA 1824 pt (#6) after group play"},
    "Falcons": {"points": 1843, "standing": 6, "snapshot": "2026_10_05"},
    "BETBOOM": {"points": 1596, "standing": 11, "snapshot": "2026_10_05"},
    "Legacy": {"points": 1931, "standing": 2, "snapshot": "2026_10_05"},
    "9z": {"points": 1543, "standing": 17, "snapshot": "2026_10_05"},
}

# Teams verified absent from the Valve global table (origination blocked).
VRS_ABSENT = ["Insiders Esport", "Morningstar", "WXM", "Insiders"]

# Display-name -> VRS-key aliases (verified identities; see flagged page).
VRS_ALIASES = {
    "WROTBERRY": "WBT",
    "Apogee Betclic": "Betclic",
    "Banda chuya": "Banda Chuya",
    "Donstu": "DONSTU",
    "BakS": "BAKS",
    "HyperSpirit": "HYPERSPIRIT",
    "mouz NXT": "MOUZ NXT",
    "Insiders": "Insiders Esport",
}


def vrs_key(team: str) -> str | None:
    """Resolve a fixture display name to its Valve VRS table key."""
    if team in VRS:
        return team
    if team in VRS_ALIASES and VRS_ALIASES[team] in VRS:
        return VRS_ALIASES[team]
    for key in VRS:
        if key.casefold() == team.casefold():
            return key
    return None

# ---------------------------------------------------------------------------
# The 21 open HotSpawn fixtures (fixtures API capture, competition_id
# filter, read 2026-10-16T20:50Z — the verbatim rows are retained in
# data/1c8f79f8/fixtures_raw.json and re-captured by collect.py).
# crowd_* is HotSpawn pick'em ownership — context only, never a
# probability input. Crowd ownership moved during the capture session
# (e.g. 1081888 flipped 56/44 -> 43/57; 1081862 flipped 29/71 -> 56/44);
# the values below are the final read at 20:50Z.
# ---------------------------------------------------------------------------
FIXTURES = [
    dict(fixture_id="1081888", competition="Stake Pulse Beat III", competition_id=36197,
         tier="B", stage="Semi-final", best_of=3, points=3,
         start_utc="2026-10-17T08:00:00Z", lock_utc="2026-10-17T07:54:00Z",
         team_a="Ninjas in Pyjamas", team_b="HEROIC",
         crowd_a=43, crowd_b=57, total_picks=14,
         participants_a_id="367", participants_b_id="347",
         hltv_match_id="2399266",
         hltv_url="https://www.hltv.org/matches/2399266/ninjas-in-pyjamas-vs-heroic-stake-pulse-beat-iii",
         hotspawn_url="https://www.hotspawn.com/matches/ninjas-in-pyjamas-vs-heroic-stake-pulse-beat-iii-1081888"),
    dict(fixture_id="1079170", competition="NODWIN Clutch Series #13", competition_id=36038,
         tier="B", stage="Swiss round 2 (0-1 bracket)", best_of=3, points=3,
         start_utc="2026-10-17T08:00:00Z", lock_utc="2026-10-17T07:54:00Z",
         team_a="BET-M", team_b="Just Players",
         crowd_a=91, crowd_b=9, total_picks=34,
         participants_a_id="246163", participants_b_id="253241",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9440/nodwin-clutch-series-13",
         hotspawn_url="https://www.hotspawn.com/matches/bet-m-vs-just-players-nodwin-clutch-series-13-1079170"),
    dict(fixture_id="1081510", competition="PGL Bucharest 2027: Closed Qualifier", competition_id=34962,
         tier="B", stage="Lower-bracket round 1 (elimination)", best_of=3, points=3,
         start_utc="2026-10-17T08:00:00Z", lock_utc="2026-10-17T07:54:00Z",
         team_a="Eternal Fire", team_b="Nuclear TigeRES",
         crowd_a=43, crowd_b=57, total_picks=21,
         participants_a_id="41017", participants_b_id="192865",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9449/pgl-bucharest-2027-closed-qualifier",
         hotspawn_url="https://www.hotspawn.com/matches/eternal-fire-vs-nuclear-tigeres-pgl-bucharest-2027-closed-qualifier-1081510"),
    dict(fixture_id="1079171", competition="NODWIN Clutch Series #13", competition_id=36038,
         tier="B", stage="Swiss round 2 (0-1 bracket)", best_of=3, points=3,
         start_utc="2026-10-17T11:00:00Z", lock_utc="2026-10-17T10:54:00Z",
         team_a="GenOne", team_b="Butterfly",
         crowd_a=28, crowd_b=72, total_picks=29,
         participants_a_id="29155", participants_b_id="242538",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9440/nodwin-clutch-series-13",
         hotspawn_url="https://www.hotspawn.com/matches/genone-vs-butterfly-nodwin-clutch-series-13-1079171"),
    dict(fixture_id="1081513", competition="CCT Europe 2026 Challengers #8", competition_id=35827,
         tier="C", stage="Opening round", best_of=3, points=2,
         start_utc="2026-10-17T11:00:00Z", lock_utc="2026-10-17T10:54:00Z",
         team_a="Bebop", team_b="Donstu",
         crowd_a=90, crowd_b=10, total_picks=30,
         participants_a_id="243715", participants_b_id="251634",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9453/cct-2026-challengers-europe-series-8",
         hotspawn_url="https://www.hotspawn.com/matches/bebop-vs-donstu-cct-europe-2026-challengers-8-1081513"),
    dict(fixture_id="1081515", competition="PGL Bucharest 2027: Closed Qualifier", competition_id=34962,
         tier="B", stage="Upper-bracket semifinal", best_of=3, points=3,
         start_utc="2026-10-17T14:00:00Z", lock_utc="2026-10-17T13:54:00Z",
         team_a="Apogee Betclic", team_b="Nemesis",
         crowd_a=14, crowd_b=86, total_picks=21,
         participants_a_id="180765", participants_b_id="232951",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9449/pgl-bucharest-2027-closed-qualifier",
         hotspawn_url="https://www.hotspawn.com/matches/apogee-betclic-vs-nemesis-pgl-bucharest-2027-closed-qualifier-1081515"),
    dict(fixture_id="1079173", competition="NODWIN Clutch Series #13", competition_id=36038,
         tier="B", stage="Swiss round 2 (1-1 bracket)", best_of=3, points=3,
         start_utc="2026-10-17T17:00:00Z", lock_utc="2026-10-17T16:54:00Z",
         team_a="BakS", team_b="Fire Flux",
         crowd_a=96, crowd_b=4, total_picks=28,
         participants_a_id="66740", participants_b_id="188383",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9440/nodwin-clutch-series-13",
         hotspawn_url="https://www.hotspawn.com/matches/baks-vs-fire-flux-nodwin-clutch-series-13-1079173"),
    dict(fixture_id="1081126", competition="CCT Europe 2026 Series #12 Play-In", competition_id=34938,
         tier="C", stage="Play-in", best_of=3, points=2,
         start_utc="2026-10-18T08:00:00Z", lock_utc="2026-10-18T07:54:00Z",
         team_a="Banda chuya", team_b="Enjoy",
         crowd_a=84, crowd_b=16, total_picks=25,
         participants_a_id="253221", participants_b_id="210272",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9456/cct-2026-europe-series-12-closed-qualifier",
         hotspawn_url="https://www.hotspawn.com/matches/banda-chuya-vs-enjoy-cct-europe-2026-series-12-play-in-1081126"),
    dict(fixture_id="1081521", competition="CCT Europe 2026 Challengers #8", competition_id=35827,
         tier="C", stage="Opening round", best_of=3, points=2,
         start_utc="2026-10-18T13:45:00Z", lock_utc="2026-10-18T13:39:00Z",
         team_a="ex-6666", team_b="Privateer",
         crowd_a=96, crowd_b=4, total_picks=25,
         participants_a_id="265446", participants_b_id="261821",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9453/cct-2026-challengers-europe-series-8",
         hotspawn_url="https://www.hotspawn.com/matches/ex-6666-vs-privateer-cct-europe-2026-challengers-8-1081521"),
    dict(fixture_id="1081522", competition="CCT Europe 2026 Challengers #8", competition_id=35827,
         tier="C", stage="Opening round", best_of=3, points=2,
         start_utc="2026-10-18T13:45:00Z", lock_utc="2026-10-18T13:39:00Z",
         team_a="antidaun", team_b="Phantom Academy",
         crowd_a=8, crowd_b=92, total_picks=25,
         participants_a_id="265009", participants_b_id="249840",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9453/cct-2026-challengers-europe-series-8",
         hotspawn_url="https://www.hotspawn.com/matches/antidaun-vs-phantom-academy-cct-europe-2026-challengers-8-1081522"),
    dict(fixture_id="1081526", competition="Digital Crusade DraculaN Season 7", competition_id=35437,
         tier="B", stage="Group A (Bo1)", best_of=1, points=3,
         start_utc="2026-10-19T09:00:00Z", lock_utc="2026-10-19T08:54:00Z",
         team_a="Infinite", team_b="Insiders",
         crowd_a=100, crowd_b=0, total_picks=27,
         participants_a_id="33036", participants_b_id="228359",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9312/digital-crusade-draculan-season-7",
         hotspawn_url="https://www.hotspawn.com/matches/infinite-vs-insiders-digital-crusade-draculan-season-7-1081526"),
    dict(fixture_id="1081527", competition="Digital Crusade DraculaN Season 7", competition_id=35437,
         tier="B", stage="Group A (Bo1)", best_of=1, points=3,
         start_utc="2026-10-19T09:00:00Z", lock_utc="2026-10-19T08:54:00Z",
         team_a="aimclub", team_b="BASEMENT BOYS",
         crowd_a=84, crowd_b=16, total_picks=25,
         participants_a_id="7162", participants_b_id="207048",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9312/digital-crusade-draculan-season-7",
         hotspawn_url="https://www.hotspawn.com/matches/aimclub-vs-basement-boys-digital-crusade-draculan-season-7-1081527"),
    dict(fixture_id="1081528", competition="Digital Crusade DraculaN Season 7", competition_id=35437,
         tier="B", stage="Group B (Bo1)", best_of=1, points=3,
         start_utc="2026-10-19T09:00:00Z", lock_utc="2026-10-19T08:54:00Z",
         team_a="BC.Game", team_b="Drama",
         crowd_a=100, crowd_b=0, total_picks=27,
         participants_a_id="177219", participants_b_id="251058",
         hltv_match_id="2399592",
         hltv_url="https://www.hltv.org/matches/2399592/bcgame-vs-drama-digital-crusade-draculan-season-7",
         hotspawn_url="https://www.hotspawn.com/matches/bc-game-vs-drama-digital-crusade-draculan-season-7-1081528"),
    dict(fixture_id="1081529", competition="Digital Crusade DraculaN Season 7", competition_id=35437,
         tier="B", stage="Group B (Bo1)", best_of=1, points=3,
         start_utc="2026-10-19T09:00:00Z", lock_utc="2026-10-19T08:54:00Z",
         team_a="Nexus", team_b="WROTBERRY",
         crowd_a=88, crowd_b=12, total_picks=25,
         participants_a_id="373", participants_b_id="250181",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9312/digital-crusade-draculan-season-7",
         hotspawn_url="https://www.hotspawn.com/matches/nexus-vs-wrotberry-digital-crusade-draculan-season-7-1081529",
         alias_note="HotSpawn 'WROTBERRY' = WBT = WhiteBIT Team (egamersworld team slug "
                    "'wrotberry'; Liquipedia and HLTV team 13683 list WhiteBIT Team in "
                    "DraculaN Season 7 Group B; same event, group, date and slot)."),
    dict(fixture_id="1081530", competition="Digital Crusade DraculaN Season 7", competition_id=35437,
         tier="B", stage="Group C (Bo1)", best_of=1, points=3,
         start_utc="2026-10-19T10:45:00Z", lock_utc="2026-10-19T10:39:00Z",
         team_a="Iberian Soul", team_b="HyperSpirit",
         crowd_a=85, crowd_b=15, total_picks=26,
         participants_a_id="202590", participants_b_id="190983",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9312/digital-crusade-draculan-season-7",
         hotspawn_url="https://www.hotspawn.com/matches/iberian-soul-vs-hyperspirit-digital-crusade-draculan-season-7-1081530"),
    dict(fixture_id="1081531", competition="Digital Crusade DraculaN Season 7", competition_id=35437,
         tier="B", stage="Group C (Bo1)", best_of=1, points=3,
         start_utc="2026-10-19T10:45:00Z", lock_utc="2026-10-19T10:39:00Z",
         team_a="Sashi", team_b="mouz NXT",
         crowd_a=84, crowd_b=16, total_picks=25,
         participants_a_id="67300", participants_b_id="38361",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9312/digital-crusade-draculan-season-7",
         hotspawn_url="https://www.hotspawn.com/matches/sashi-vs-mouz-nxt-digital-crusade-draculan-season-7-1081531"),
    dict(fixture_id="1081532", competition="Digital Crusade DraculaN Season 7", competition_id=35437,
         tier="B", stage="Group D (Bo1)", best_of=1, points=3,
         start_utc="2026-10-19T10:45:00Z", lock_utc="2026-10-19T10:39:00Z",
         team_a="ASTRAL", team_b="Leo",
         crowd_a=24, crowd_b=76, total_picks=25,
         participants_a_id="225028", participants_b_id="57057",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9312/digital-crusade-draculan-season-7",
         hotspawn_url="https://www.hotspawn.com/matches/astral-vs-leo-digital-crusade-draculan-season-7-1081532"),
    dict(fixture_id="1081861", competition="MaceMedia VOID Autumn Cup 2026", competition_id=36412,
         tier="C", stage="Opening round", best_of=3, points=2,
         start_utc="2026-10-20T03:00:00Z", lock_utc="2026-10-20T02:54:00Z",
         team_a="Lynn Vision", team_b="Morningstar",
         crowd_a=100, crowd_b=0, total_picks=9,
         participants_a_id="7887", participants_b_id="244112",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026",
         hotspawn_url="https://www.hotspawn.com/matches/lynn-vision-vs-morningstar-macemedia-void-autumn-cup-2026-1081861"),
    dict(fixture_id="1081862", competition="MaceMedia VOID Autumn Cup 2026", competition_id=36412,
         tier="C", stage="Opening round", best_of=3, points=2,
         start_utc="2026-10-20T05:00:00Z", lock_utc="2026-10-20T04:54:00Z",
         team_a="Rare Atom", team_b="Alter Ego",
         crowd_a=56, crowd_b=44, total_picks=9,
         participants_a_id="59131", participants_b_id="11144",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026",
         hotspawn_url="https://www.hotspawn.com/matches/rare-atom-vs-alter-ego-macemedia-void-autumn-cup-2026-1081862"),
    dict(fixture_id="1081863", competition="MaceMedia VOID Autumn Cup 2026", competition_id=36412,
         tier="C", stage="Opening round", best_of=3, points=2,
         start_utc="2026-10-20T07:00:00Z", lock_utc="2026-10-20T06:54:00Z",
         team_a="Chinggis Warriors", team_b="WXM",
         crowd_a=100, crowd_b=0, total_picks=8,
         participants_a_id="146827", participants_b_id="263852",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026",
         hotspawn_url="https://www.hotspawn.com/matches/chinggis-warriors-vs-wxm-macemedia-void-autumn-cup-2026-1081863",
         alias_note="WXM = Wept Xyloid Melancholy (Mais Esports VOID Autumn Cup 2026 team list)."),
    dict(fixture_id="1081864", competition="MaceMedia VOID Autumn Cup 2026", competition_id=36412,
         tier="C", stage="Opening round", best_of=3, points=2,
         start_utc="2026-10-20T09:00:00Z", lock_utc="2026-10-20T08:54:00Z",
         team_a="NEXVOID", team_b="Vitalem Aerem",
         crowd_a=88, crowd_b=13, total_picks=8,
         participants_a_id="249811", participants_b_id="262966",
         hltv_match_id=None,
         hltv_url="https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026",
         hotspawn_url="https://www.hotspawn.com/matches/nexvoid-vs-vitalem-aerem-macemedia-void-autumn-cup-2026-1081864"),
]

# ---------------------------------------------------------------------------
# External lines, verbatim from the retained sources. decimals are the raw
# two-sided prices; prob_* is the de-vigged fair share computed in build.py.
# ---------------------------------------------------------------------------
LINES = {
    # Polymarket exchange moneylines (series markets; retrieved 2026-10-16 ~20:05Z)
    "1081888": dict(kind="market", basis="polymarket",
        decimals=(2.33, 1.72), volume_usd=79.24,
        url="https://polymarket.com/esports/cs2/stake-pulse/cs2-nip-hero-2026-10-17",
        note="Polymarket series moneyline, $79.24 traded volume (thin but real). "
             "Map-1 line NIP 49c/HEROIC 54c agrees on direction."),
    "1079170": dict(kind="market", basis="polymarket+stavka",
        decimals=(1.41, 3.13), volume_usd=12.91,
        url="https://polymarket.com/esports/cs2/nodwin-clutch-series/cs2-33-justpl-2026-10-17",
        url2="https://stavka.tv/matches/csgo/17-10-2026-bet-m-33-just-players",
        decimals2=(1.38, 2.70),
        note="Polymarket BET-M 71c / Just Players 32c ($12.91 vol); stavka.tv Russian "
             "bookmaker consensus P1 1.38 / P2 2.70 independently agrees (de-vig 66.2/33.8)."),
    "1081510": dict(kind="market", basis="polymarket+kushvsporte",
        decimals=(1.85, 2.13), volume_usd=13.63,
        url="https://polymarket.com/esports/cs2/pgl/cs2-ef1-ntr-2026-10-17",
        url2="https://kushvsporte.ru/event/6977300-eternal-fire-nuclear-tigeres",
        decimals2=(1.75, 1.96),
        note="Polymarket Eternal Fire 54c / Nuclear TigeRES 47c ($13.63 vol); kushvsporte "
             "bookmaker aggregate P1 1.75 / P2 1.96 independently agrees (de-vig 52.8/47.2)."),
    "1081513": dict(kind="market", basis="bc.game via egamersworld",
        decimals=(1.71, 2.02), volume_usd=None,
        url="https://egamersworld.com/counterstrike/event/cct-europe-2026-challengers-8-rW6Ymkl0D",
        note="bc.game average odds carried on the egamersworld event page: Bebop 1.71 / "
             "Donstu 2.02. Real two-sided bookmaker line."),
    "1081515": dict(kind="market", basis="polymarket",
        decimals=(2.94, 1.39), volume_usd=0.0,
        url="https://polymarket.com/esports/cs2/pgl/cs2-bca-nem-2026-10-17",
        note="Polymarket Betclic Apogee 34c / Team Nemesis 72c but $0.00 traded volume — "
             "an untrained AMM seed price, treated as a weak prior only; the Valve-VRS "
             "model runs materially cooler (see flags)."),
    "1079173": dict(kind="market", basis="stavka",
        decimals=(1.54, 2.24), volume_usd=None,
        url="https://stavka.tv/matches/csgo/17-10-2026-baks-esports-fire-flux-esports",
        note="stavka.tv Russian bookmaker consensus BakS 1.54 / Fire Flux 2.24. Polymarket "
             "lists 77c/37c but with $0.00 volume (untrained seed) — recorded, not weighted."),
    "1081526": dict(kind="market", basis="polymarket",
        decimals=(1.45, 3.23), volume_usd=1.03,
        url="https://polymarket.com/esports/cs2/draculan/cs2-inf6-ins-2026-10-19",
        note="Polymarket Infinite 69c / Insiders Esport 31c, $1.03 traded volume (thin). "
             "Insiders Esport is absent from the Valve VRS global table, so no model cross-check."),
    "1081527": dict(kind="market", basis="polymarket-untrained",
        decimals=(2.00, 2.00), volume_usd=0.0,
        url="https://polymarket.com/esports/cs2/draculan/cs2-aim1-bmb-2026-10-19",
        note="Polymarket aimclub 50c / BASEMENT BOYS 50c with $0.00 volume — untrained "
             "placeholder, uninformative; the Valve-VRS model is the basis instead."),
    "1081528": dict(kind="market", basis="polymarket",
        decimals=(1.33, 4.00), volume_usd=1.03,
        url="https://polymarket.com/esports/cs2/draculan/cs2-bcg-drama-2026-10-19",
        note="Polymarket BC.Game 75c / Drama 25c, $1.03 traded volume (thin)."),
    "1081529": dict(kind="market", basis="egamersworld+polymarket",
        decimals=(1.96, 1.72), volume_usd=None,
        url="https://egamersworld.com/counterstrike/match/V1JAWhPomg/wbt-vs-nexus-gaming-A-jHKvluZk",
        url2="https://polymarket.com/esports/cs2/draculan/cs2-wbt-nxs1-2026-10-19",
        decimals2=(1.92, 1.67),
        note="Stored in fixture order (Nexus first). egamersworld bookmaker average "
             "WBT 1.72 / Nexus Gaming 1.96 (EGW bot: 'majority of bookmakers unanimously "
             "see WBT as the favorite'). Polymarket WBT 60c/Nexus 52c (1.67x/1.92x) is "
             "$0-volume untrained."),
    "1081530": dict(kind="market", basis="polymarket",
        decimals=(1.41, 2.70), volume_usd=21.39,
        url="https://polymarket.com/esports/cs2/draculan/cs2-is-hs2-2026-10-19",
        note="Polymarket Iberian Soul 71c / HyperSpirit 37c, $21.39 traded volume."),
    "1081531": dict(kind="market", basis="polymarket",
        decimals=(1.47, 2.27), volume_usd=274.22,
        url="https://polymarket.com/esports/cs2/draculan/cs2-sashi-mouzn-2026-10-19",
        note="Polymarket Sashi 68c / MOUZ NXT 44c, $274.22 traded volume — the most liquid "
             "DraculaN market and the exchange's best-priced row in this section."),
    "1081532": dict(kind="model-only", basis=None,
        decimals=None, volume_usd=0.0,
        url="https://polymarket.com/esports/cs2/draculan/cs2-ast-leo2-2026-10-19",
        note="Polymarket lists ASTRAL 96c / Leo 97c (193c total) with $0.00 volume — a "
             "stale, untraded seed; rejected as a price. Valve-VRS model is the basis."),
    "1081862": dict(kind="market", basis="egamersworld",
        decimals=(1.62, 2.15), volume_usd=None,
        url="https://egamersworld.com/counterstrike/matches",
        note="egamersworld matches-index average odds Rare Atom 1.62 / Alter Ego 2.15. The "
             "match-page widget still shows the 1.8/1.8 placeholder — index feed is fresher; "
             "discrepancy flagged."),
}

# Fixtures with NO external two-sided price at all (originated model lines or blanks).
NO_LINE = ["1079171", "1081126", "1081521", "1081522", "1081861", "1081863", "1081864"]

# ---------------------------------------------------------------------------
# TWC 2026 Malta playoffs (NOT on HotSpawn — originated externally, flagged).
# ---------------------------------------------------------------------------
TWC = dict(
    sf1=dict(teams=("FURIA", "Aurora"), start_utc="2026-10-17T14:00:00Z",
             hltv_match_id="2399414",
             hltv_url="https://www.hltv.org/matches/2399414/furia-vs-aurora-thunderpick-world-championship-2026",
             market=dict(kind="market", basis="egamersworld+polymarket",
                         decimals=(1.83, 1.90), volume_usd=182.12,
                         url="https://egamersworld.com/counterstrike/match/5X5sFiL7H/furia-vs-aurora-Z00JFz0dG",
                         url2="https://polymarket.com/esports/cs2/thunderpick-world-championship/cs2-furia-aur1-2026-10-17",
                         note="egamersworld bc.game average FURIA 1.83 / Aurora 1.90; Polymarket "
                              "FURIA 53c / Aurora 49c ($182.12 vol). vprognoze.ru carries Aurora 1.85."),
             model_delta=113,  # Oct-5 snapshot FURIA 1829 vs Aurora 1716
             model_note="Oct-5 Valve snapshot favors FURIA by 113 pt, but HLTV's LIVE VRS "
                        "forecast on match day reads Aurora 1848 pt (#5) vs FURIA 1824 pt (#6) "
                        "after group play — direction flips to Aurora.",
             fair=(0.48, 0.52), fair_basis="blend: exchange+bookmaker market (FURIA 51-52%) "
                        "vs live-VRS forecast + head-to-head + form (Aurora); settled at Aurora 52%",
             pick="Aurora", pick_prob=0.52, role="contrarian",
             context=[
                 "Aurora won the only 2026 meeting 2-1 (ESL Pro League S24 group stage, Oct 6) — HLTV news 45736",
                 "Aurora: three consecutive top-four finishes (StarSeries runner-up, EPL S24 third, TWC semis)",
                 "Aurora avenged the day-1 9z upset 2-0 on Oct 16 (Cache 13-11, Inferno 13-4; kyxsan 1.45, MVP)",
                 "FURIA lost 0-2 to MOUZ twice at EPL S24 and exited in the quarterfinals (tribuna.com preview)",
                 "HLTV fan vote on the match page reads Aurora 73.5% — sentiment, not a price; recorded as such",
             ],
             sources=[
                 ("egamersworld match page (bc.game average odds + lineups)", "https://egamersworld.com/counterstrike/match/5X5sFiL7H/furia-vs-aurora-Z00JFz0dG"),
                 ("Polymarket series moneyline", "https://polymarket.com/esports/cs2/thunderpick-world-championship/cs2-furia-aur1-2026-10-17"),
                 ("HLTV match page (live VRS forecast, lineups, fan vote)", "https://www.hltv.org/matches/2399414/furia-vs-aurora-thunderpick-world-championship-2026"),
                 ("HLTV news 45736 — Aurora beat 9z 2-0, semis rematch confirmed", "https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance"),
                 ("tips.gg tournament preview (Aurora 4.30 outright, 'best value on the board')", "https://tips.gg/article/thunderpick-wc2026-winner-odds/"),
             ]),
    sf2=dict(teams=("Falcons", "BETBOOM"), start_utc="2026-10-17T17:00:00Z",
             hltv_match_id="2399415",
             hltv_url="https://www.hltv.org/matches/2399415/falcons-vs-betboom-thunderpick-world-championship-2026",
             market=dict(kind="no-market", basis=None, decimals=None, volume_usd=None,
                         url="https://polymarket.com/esports/cs2/thunderpick-world-championship",
                         note="No published semifinal line exists yet anywhere checked "
                              "(Polymarket TWC index carries only the decider and FURIA-Aurora "
                              "markets; bo3.gg/stavka.tv/egamersworld had not opened the semi "
                              "at read time). Fair probability is a documented estimate."),
             model_delta=247,  # Falcons 1843 vs BETBOOM 1596 (Oct-5 snapshot)
             model_note="Canonical Valve-VRS model (k=0.25) reads Falcons 58.6%. Comparable "
                        "priced lines: Falcons 1.28 vs 9z (VRS #17) on Oct 15 and 1.20-1.30 vs "
                        "Legacy (VRS #2) in August — the market prices Falcons materially hotter "
                        "than the flat k=0.25 model; fair estimate sits between.",
             fair=(0.66, 0.34), fair_basis="estimate between Valve-VRS model (Falcons 58.6%) "
                        "and comparable market pricing (Falcons ~72-78% vs weaker VRS opponents)",
             pick="Falcons", pick_prob=0.66, role="safe",
             context=[
                 "BETBOOM reached the semis by reverse-sweeping PARIVISION 2-1 (zorte 51 kills) and beating Legacy 2-1 in the Mirage decider (Magnojez 1.17 series rating)",
                 "BETBOOM lost 0-2 to FURIA on day one — the same FURIA that just beat Legacy",
                 "bo3.gg analytics: BetBoom 80% Mirage winrate over the last half-year but only 40% winrate last month",
                 "HLTV simulation had BetBoom at 89.1% to reach the PGL Singapore Major before the decider (pley.gg)",
                 "Falcons are the reigning Major champions (beat NiP 2-0 and 9z 2-1 to reach the semis; TeSeS 1.26 vs 9z)",
             ],
             sources=[
                 ("HLTV match page (semifinal 2)", "https://www.hltv.org/matches/2399415/falcons-vs-betboom-thunderpick-world-championship-2026"),
                 ("bo3.gg live decider page (team analytics insights)", "https://bo3.gg/matches/legacy-br-vs-betboom-team-16-10-2026"),
                 ("HLTV news 45729 — BETBOOM eliminate PARIVISION (zorte 51 kills)", "https://www.hltv.org/news/45729/betboom-eliminate-parivision-from-twc"),
                 ("pley.gg day-3 report (HLTV Major simulation 89.1%)", "https://pley.gg/cs2/aurora-and-legacy-face-elimination-as-falcons-and-furia-wait-in-thunderpick-semi-finals/"),
                 ("Polymarket TWC league index (no SF2 market open yet — evidence of absence)", "https://polymarket.com/esports/cs2/thunderpick-world-championship"),
             ]),
    decider=dict(teams=("Legacy", "BETBOOM"), result="BETBOOM 2-1 Legacy",
                 maps=[("Nuke", 16, 13), ("Dust2", 11, 13), ("Mirage", 13, 11)],
                 verified_at="2026-10-16T20:40:00Z",
                 hltv_url="https://www.hltv.org/matches/2399413/betboom-vs-legacy-thunderpick-world-championship-2026",
                 note="Group B decider, verified map-level on the HLTV match page "
                      "(Match over; Magnojez 1.17 series rating, 62-50 K-D, best on the server). "
                      "Pre-match market consensus was Legacy ~1.50-1.54 / BetBoom ~2.50-2.60 "
                      "(stavka.tv 1.52/2.53, cybersport.ru 1.50/2.60, metaratings 1.50-1.54/2.50-2.60, "
                      "Polymarket 62c/39c) — BetBoom was the live underdog that won."),
)

# ---------------------------------------------------------------------------
# Verified TWC group-stage results (HLTV results page event=8932 + strafe bracket,
# read 2026-10-16 ~19:55Z) — the day-1/2/3 record the semifinal picks rest on.
# ---------------------------------------------------------------------------
TWC_RESULTS = [
    ("Oct 14", "Group A opening", "9z", "2-0", "Aurora", "Inferno 13-11, Nuke 13-4"),
    ("Oct 14", "Group A opening", "Falcons", "2-0", "Ninjas in Pyjamas", "Ancient 16-13, Dust2 13-6"),
    ("Oct 14", "Group B opening", "Legacy", "2-0", "PARIVISION", "Dust2 13-11, Mirage 16-14"),
    ("Oct 14", "Group B opening", "FURIA", "2-0", "BETBOOM", "Ancient 13-10, Mirage 13-9"),
    ("Oct 15", "Group A winners' match", "Falcons", "2-1", "9z", "Nuke 13-9, Mirage 8-13, Dust2 13-9"),
    ("Oct 15", "Group A elimination", "Aurora", "2-0", "Ninjas in Pyjamas", "Cache 13-9, Dust2 13-7"),
    ("Oct 15", "Group B winners' match", "FURIA", "2-1", "Legacy", "Cache 10-13, Inferno 13-5, Mirage 13-8"),
    ("Oct 15", "Group B elimination", "BETBOOM", "2-1", "PARIVISION", "Ancient 10-13, Anubis 13-4, Mirage 13-7"),
    ("Oct 16", "Group A decider", "Aurora", "2-0", "9z", "Cache 13-11, Inferno 13-4 (kyxsan 1.45 MVP)"),
    ("Oct 16", "Group B decider", "BETBOOM", "2-1", "Legacy", "Nuke 16-13, Dust2 11-13, Mirage 13-11"),
]

# Remaining TWC schedule (HLTV event 8932 + Liquipedia, read 2026-10-16)
TWC_SCHEDULE = [
    ("Semifinal 1", "FURIA vs Aurora", "2026-10-17T14:00:00Z", "Bo3", "HLTV 2399414"),
    ("Semifinal 2", "Falcons vs BETBOOM", "2026-10-17T17:00:00Z", "Bo3", "HLTV 2399415"),
    ("3rd-place decider", "TBD vs TBD", "2026-10-18T11:30:00Z", "Bo3", "opponents unknown at press time"),
    ("Grand final", "TBD vs TBD", "2026-10-18T15:00:00Z", "Bo5", "opponents unknown at press time"),
]

# ---------------------------------------------------------------------------
# Pick ledger. fair_a/fair_b are the published fair win probabilities for
# team_a/team_b. basis: market (de-vigged external price), model (Valve VRS
# k=0.25), blend (market weighted toward model), estimate (no market, model
# plus documented judgment), None (blank — no eligible evidence).
# role: safe (expected-points pick) / climb (leaderboard swing) /
#       contrarian (against the market or the crowd, gates documented) /
#       directional (pick without a publishable probability).
# ---------------------------------------------------------------------------
PICKS = {
    "1081888": dict(
        fair_a=0.4479, fair_b=0.5521, basis="blend",
        pick="HEROIC", pick_prob=0.5521, role="safe",
        flags=["market_line_thin_volume", "model_cooler_than_market", "hltv_fan_vote_is_not_a_price"],
        context=[
            "HEROIC won 5 of its last 5 matches; NIP won 3 of 5 (HLTV analytics summary)",
            "Head-to-head HEROIC 13-10 NIP; tips.gg team ratings #8 vs #14",
            "HLTV analytics names HEROIC 'the bookmaker favorite with the best odds'",
             "Valve VRS: HEROIC #15 (1550 pt) vs NIP #18 (1534 pt) — model agrees on direction, cooler on magnitude",
             "NIP beat Liquid 2-1 on Oct 16 in this event (HLTV 2399262); both teams arrive on 3-match league lose streaks per tips.gg",
             "Crowd ownership flipped during the capture session from 56% NIP to 57% HEROIC — the crowd chased the line and now agrees with it (ownership recorded at 20:50Z)",
        ],
        sources=[
            ("Polymarket NIP–Heroic series moneyline (NIP 43c / HEROIC 58c, $79.24 vol)", "https://polymarket.com/esports/cs2/stake-pulse/cs2-nip-hero-2026-10-17"),
            ("HLTV betting analytics — odds & prediction", "https://www.hltv.org/betting/analytics/2399266/ninjas-in-pyjamas-vs-heroic-stake-pulse-beat-iii"),
            ("HLTV match page (lineups, VRS ranks, fan vote)", "https://www.hltv.org/matches/2399266/ninjas-in-pyjamas-vs-heroic-stake-pulse-beat-iii"),
            ("tips.gg head-to-head archive", "https://tips.gg/archive/heroic-csgo-vs-ninjas-in-pyjamas-csgo/"),
        ]),
    "1079170": dict(
        fair_a=0.6756, fair_b=0.3244, basis="market",
        pick="BET-M", pick_prob=0.6756, role="safe",
        flags=["model_cooler_than_market"],
        context=[
            "Two independent market sources agree: Polymarket 71c/32c ($12.91 vol) and stavka.tv bookmaker consensus 1.38/2.70",
            "Valve VRS BET-M #71 (1149 pt) vs Just Players #118 (974 pt) — model direction agrees, magnitude cooler (56%)",
            "Crowd ownership 91% BET-M (moved from 94% during the session) — the crowd agrees with the line, so no contrarian angle exists here",
        ],
        sources=[
            ("Polymarket BET-M 33–Just Players series moneyline", "https://polymarket.com/esports/cs2/nodwin-clutch-series/cs2-33-justpl-2026-10-17"),
            ("stavka.tv match preview with coefficients (P1 1.38 / P2 2.70)", "https://stavka.tv/matches/csgo/17-10-2026-bet-m-33-just-players"),
            ("HLTV NODWIN Clutch Series 13 event page", "https://www.hltv.org/events/9440/nodwin-clutch-series-13"),
        ]),
    "1081510": dict(
        fair_a=0.5318, fair_b=0.4682, basis="market",
        pick="Eternal Fire", pick_prob=0.5318, role="safe",
        flags=["elimination_match", "both_teams_just_lost_openers", "crowd_against_line"],
        context=[
            "Lower-bracket round 1 is elimination: the loser is out of the PGL Bucharest 2027 closed qualifier (HLTV event 9449 bracket)",
            "Both teams lost their Oct 16 openers: Eternal Fire 1-2 Betclic Apogee; Nuclear TigeRES 1-2 Nemesis",
            "Head-to-head 4-3 Eternal Fire; last meeting Sep 26 Eternal Fire won 2-1 (Stake Ranked Ep.5 CQ)",
            "Nuclear TigeRES' five-match win streak ended with the Oct 16 Nemesis loss (stavka.tv had flagged the streak pre-match)",
            "Crowd ownership moved from 65% to 57% Nuclear TigeRES during the capture session but still leans against the line — the crowd remains the contrarian signal, and the line still disagrees with it",
        ],
        sources=[
            ("kushvsporte bookmaker aggregate (EF 1.75 / NTR 1.96, totals 52.5 maps)", "https://kushvsporte.ru/event/6977300-eternal-fire-nuclear-tigeres"),
            ("Polymarket Eternal Fire–Nuclear TigeRES series moneyline", "https://polymarket.com/esports/cs2/pgl/cs2-ef1-ntr-2026-10-17"),
            ("HLTV PGL Bucharest 2027 Closed Qualifier event page (bracket)", "https://www.hltv.org/events/9449/pgl-bucharest-2027-closed-qualifier"),
            ("egamersworld match page (bc.game average EF 1.80)", "https://egamersworld.com/counterstrike/match/4JaFCnn5Ve/eternal-fire-vs-nuclear-tigeres-EbmQD7L0i"),
        ]),
    "1079171": dict(
        fair_a=0.536, fair_b=0.464, basis="model",
        pick="GenOne", pick_prob=0.536, role="contrarian",
        flags=["no_market_line", "originated_vrs_line", "crowd_and_editor_against_pick", "roster_discrepancy_genone"],
        context=[
            "No bookmaker publishes a coefficient for this match (stavka.tv: 'absence of data on coefficients'; egamersworld shows the 1.8/1.8 placeholder pair — rejected as a price)",
            "Valve VRS GenOne #66 (1185 pt) vs Butterfly #88 (1082 pt) — the canonical model reads GenOne 53.6%",
            "AGAINST the pick: Butterfly won the most recent meeting 13-11 on Nuke (Oct 13, PGL Bucharest open qualifier) and beat Fire Flux 2-1 on Oct 15; GenOne lost 4 of its last 5 series",
            "AGAINST the pick: stavka.tv's editor picks Butterfly (map-pool logic: GenOne's 91%-win Anubis gets banned; Butterfly holds 75% Cache / 71% Dust2 / 69% Mirage)",
            "FOR the pick: Butterfly's three most recent losses are to Fire Flux, Nuclear TigeRES and ex-RUSTEC — tougher opposition than GenOne's four losses",
            "Roster flag: egamersworld lists SIXER in GenOne's lineup; the Oct-5 Valve row carries Chucky — one unverified substitution",
        ],
        sources=[
            ("stavka.tv match preview (form, map pools, editor pick — and the no-coefficients statement)", "https://stavka.tv/matches/csgo/17-10-2026-genone-butterfly"),
            ("egamersworld match page (lineups, 1.8/1.8 placeholder evidence)", "https://egamersworld.com/counterstrike/match/Nk9F-Ov54e/genone-vs-butterfly-37ajs9rOg"),
            ("HLTV NODWIN Clutch Series 13 event page (GenOne 1-2 6666 on Oct 14)", "https://www.hltv.org/events/9440/nodwin-clutch-series-13"),
            ("Valve regional standings 2026-10-05 (GenOne #66 / Butterfly #88)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
        ]),
    "1081513": dict(
        fair_a=0.5242, fair_b=0.4758, basis="blend",
        pick="Bebop", pick_prob=0.5242, role="safe",
        climb=dict(pick="Donstu", pick_prob=0.4758, odds_ref=2.02, side="b",
                   gates="fair 47.6% >= 30% floor; crowd ownership 10% <= 20%; "
                         "probability/ownership = 4.8x; 5 verified context flags",
                   swing_cost_pts=0.15),
        flags=["climb_pick", "hltv_core_inactive_30d", "thin_tier_c_market"],
        context=[
            "bc.game line (via egamersworld) Bebop 1.71 / Donstu 2.02 de-vigs to 54.2/45.8 — the only published price",
            "Valve VRS Donstu #197 (732 pt) vs Bebop #212 (702 pt): the model sides with the underdog (51.0%)",
            "HLTV analytics ranks the two #206 and #207 — effectively tied — and flags that one core lineup 'has not played any maps the past 30 days'",
            "Polymarket priced their Jul 18 CCT closed-qualifier meeting with Donstu the 60c favorite (Bebop 41c)",
            "Crowd ownership 90% Bebop / 10% Donstu (moved from 92/8 during the session) — the maximum ownership-versus-model disagreement on the board",
        ],
        sources=[
            ("egamersworld CCT Challengers #8 event page (bc.game odds 1.71/2.02)", "https://egamersworld.com/counterstrike/event/cct-europe-2026-challengers-8-rW6Ymkl0D"),
            ("HLTV betting analytics — Bebop vs Donstu (ranks, inactivity flag)", "https://www.hltv.org/betting/analytics"),
            ("Polymarket archive — Bebop vs Donstu, Jul 18 2026 (Donstu 60c)", "https://polymarket.com/event/cs2-bbp-don-2026-07-18"),
            ("HLTV CCT 2026 Challengers Europe Series 8 event page", "https://www.hltv.org/events/9453/cct-2026-challengers-europe-series-8"),
        ]),
    "1081515": dict(
        fair_a=0.4574, fair_b=0.5426, basis="model",
        pick="Nemesis", pick_prob=0.5426, role="safe",
        flags=["polymarket_untrained_zero_volume", "model_market_divergence_13pt"],
        context=[
            "Polymarket lists Betclic Apogee 34c / Nemesis 72c but with $0.00 traded volume — an untrained AMM seed, so it is a weak prior, not a verified crowd price",
            "Valve VRS Nemesis #29 (1455 pt) vs Betclic #45 (1333 pt) — the model reads Nemesis 54.3%, 13 points cooler than the seed",
            "Both winners from Oct 16's opening round: Apogee Betclic beat Eternal Fire 2-1; Nemesis beat Nuclear TigeRES 2-1",
            "Identity verified: 'Apogee Betclic' = Betclic Apogee Esports, the Polish organization (Prism captain; PGL Bucharest 2025 run incl. wins over NiP and Fnatic in qualifiers) — Valve lists the team as 'Betclic'",
        ],
        sources=[
            ("Polymarket Betclic Apogee–Team Nemesis series moneyline ($0.00 vol — evidence of an untrained market)", "https://polymarket.com/esports/cs2/pgl/cs2-bca-nem-2026-10-17"),
            ("HLTV PGL Bucharest 2027 Closed Qualifier event page (bracket: upper-bracket semifinal)", "https://www.hltv.org/events/9449/pgl-bucharest-2027-closed-qualifier"),
            ("Valve regional standings 2026-10-05 (Nemesis #29 / Betclic #45)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
            ("stavka.tv team page — Betclic Apogee identity and history", "https://stavka.tv/teams/csgo/betclic-apogee-esports-7"),
        ]),
    "1079173": dict(
        fair_a=0.5777, fair_b=0.4223, basis="blend",
        pick="BakS", pick_prob=0.5777, role="safe",
        flags=["polymarket_untrained_zero_volume", "fire_flux_form_poor"],
        context=[
            "stavka.tv bookmaker consensus BakS 1.54 / Fire Flux 2.24 (de-vig 59.3/40.7) — the strongest source here",
            "Valve VRS BakS #100 (1044 pt) vs Fire Flux #131 (907 pt) — model agrees on direction (BakS 54.8%)",
            "BakS beat Bushido Wildcats 2-1 on Oct 14 (HLTV 2399076) and beat G2 Ares in CCT Europe Series 11 on Oct 16",
            "Fire Flux lost 1-2 to Butterfly on Oct 15 and 2-1 to ex-RUSTEC earlier in the week",
            "Polymarket lists BakS 77c / Fire Flux 37c at $0.00 volume — untrained seed, recorded but not weighted",
        ],
        sources=[
            ("stavka.tv match preview with coefficients (BakS 1.54 / Fire Flux 2.24)", "https://stavka.tv/matches/csgo/17-10-2026-baks-esports-fire-flux-esports"),
            ("Polymarket BakS–Fire Flux market ($0.00 vol — untrained seed evidence)", "https://polymarket.com/esports/cs2/nodwin-clutch-series/cs2-baks-ff-2026-10-17"),
            ("HLTV NODWIN Clutch Series 13 event page", "https://www.hltv.org/events/9440/nodwin-clutch-series-13"),
            ("egamersworld match page", "https://egamersworld.com/counterstrike/match/Nk9F-Ov54e/baks-esports-vs-fire-flux-esports-GvFjRQwKO"),
        ]),
    "1081126": dict(
        fair_a=0.475, fair_b=0.525, basis="model",
        pick="Enjoy", pick_prob=0.525, role="climb",
        climb=dict(pick="Enjoy", pick_prob=0.525, odds_ref=None, side="b",
                   gates="fair 52.5% >= 30% floor; crowd ownership 16% <= 20%; "
                         "probability/ownership = 3.3x; 4 verified context flags; "
                         "safe and climb coincide (the model favorite is the crowd-faded side)",
                   swing_cost_pts=0.0),
        flags=["no_market_line", "originated_vrs_line", "enjoy_roster_change_post_snapshot", "climb_pick"],
        context=[
            "No published two-sided price exists (egamersworld shows the 1.8/1.8 placeholder pair; Polymarket lists no CCT Europe Series 12 play-in market) — line originated from the Valve-VRS model",
            "Valve VRS Enjoy #138 (871 pt) vs Banda Chuya #165 (801 pt) — model reads Enjoy 52.4%",
            "HLTV rankings agree: Enjoy #158-162 vs Banda Chuya #179-192 across the October snapshots",
            "Banda Chuya's only recent win came 3-13 on Cache against GenOne (stavka.tv form summary) — a form flag against the crowd favorite",
            "Crowd ownership 84% Banda Chuya / 16% Enjoy (moved from 82/18 during the session) — the crowd is on the model's losing side",
            "Roster flag: egamersworld/HLTV list Enjoy as kurosa, sh1geo, reyoz, nbl + TBD; the Oct-5 Valve row carries roxesz and zazzer instead — two unverified substitutions, so the VRS points may be stale",
        ],
        sources=[
            ("HLTV CCT 2026 Europe Series 12 Closed Qualifier event page (play-in bracket)", "https://www.hltv.org/events/9456/cct-2026-europe-series-12-closed-qualifier"),
            ("egamersworld match page (Enjoy lineup evidence + 1.8/1.8 placeholder)", "https://egamersworld.com/counterstrike/match/1sGIL2gAYu/banda-chuya-vs-enjoy-9ru7xO5OG"),
            ("stavka.tv GenOne–Butterfly preview (Banda Chuya 3-13 Cache form flag)", "https://stavka.tv/matches/csgo/17-10-2026-genone-butterfly"),
            ("Valve regional standings 2026-10-05 (Enjoy #138 / Banda Chuya #165)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
        ]),
    "1081521": dict(
        fair_a=0.625, fair_b=0.375, basis="model",
        pick="ex-6666", pick_prob=0.625, role="safe",
        flags=["no_market_line", "originated_vrs_line", "new_team_entity_oct_14", "privateer_roster_change", "fresher_vrs_snapshot_used"],
        context=[
            "No published price (egamersworld 1.8/1.8 placeholder; no Polymarket market) — line originated from the Valve-VRS model",
            "Identity verified: ex-6666 is the Ukrainian roster (amster, kL1o, rendysky, skcH) that left the 6666 organization on Oct 14 2026 and now plays under the 'ex-' prefix, with stefienson as the fifth player (HLTV team 14100 transfer log)",
            "Freshest Valve reading (HLTV valve-ranking 2026-10-15): ex-6666 #107 with 1007 pt vs Privateer #241 with 641 pt — model reads ex-6666 62.5%",
            "Privateer's current lineup (Frazehh, JAUSTERE, moz, M1n1maL, Prime) differs from its Oct-5 Valve row (Ariant0 out, moz in) — one verified substitution",
            "Both teams lost to mellren on Oct 16 in their respective qualifiers",
        ],
        sources=[
            ("HLTV ex-6666 team overview (roster + Oct 14 transfer log)", "https://www.hltv.org/team/14100/ex-6666"),
            ("HLTV valve-ranking 2026-10-15 (ex-6666 #107 / Privateer #241)", "https://www.hltv.org/valve-ranking/teams/2026/october/15"),
            ("strafe Privateer team page (current roster)", "https://www.strafe.com/team/privateer-cs-go-e7322e/"),
            ("HLTV CCT 2026 Challengers Europe Series 8 event page", "https://www.hltv.org/events/9453/cct-2026-challengers-europe-series-8"),
        ]),
    "1081522": dict(
        fair_a=0.445, fair_b=0.555, basis="model",
        pick="Phantom Academy", pick_prob=0.555, role="safe",
        flags=["no_market_line", "originated_vrs_line", "both_rosters_changed_post_snapshot"],
        context=[
            "No published price (egamersworld 1.8/1.8 placeholder; no Polymarket market) — line originated from the Valve-VRS model",
            "Freshest Valve reading (HLTV valve-ranking 2026-10-15, EU region): Phantom Academy #121 with 760 pt vs antidaun #186 with 602 pt — model reads Phantom Academy 55.5%",
            "Phantom Academy lost stefienson to ex-6666 on Oct 14 and its fifth player is unconfirmed (egamersworld shows a placeholder) — roster instability cuts both ways",
            "antidaun lost to Saint Sinners on Oct 15 (HLTV 2399289); its lineup carries Pedrinho2011 where the Oct-14 Valve row lists maddeN",
            "Phantom Academy's recent results are mixed (W vs Azuolas 2-0 and ROUNDS 2-0; L vs MASONIC, Leo Team, Butterfly)",
        ],
        sources=[
            ("HLTV valve-ranking 2026-10-15 EU region (Phantom Academy #121 / antidaun #186)", "https://www.hltv.org/valve-ranking/teams/2026/october/15/region/Europe"),
            ("egamersworld match page (both lineups + 1.8/1.8 placeholder evidence)", "https://egamersworld.com/counterstrike/match/rW6Ymkl0D/antidaun-vs-phantom-academy-zXFTwo17o8"),
            ("HLTV antidaun vs Saint Sinners, Oct 15 (form + ranks)", "https://www.hltv.org/matches/2399289/antidaun-vs-saint-sinners-cct-2026-europe-series-11-closed-qualifier"),
            ("HLTV Phantom Academy team overview", "https://www.hltv.org/team/13766/phantom-academy"),
        ]),
    "1081526": dict(
        fair_a=0.6902, fair_b=0.3098, basis="market",
        pick="Infinite", pick_prob=0.6902, role="safe",
        flags=["thin_market_volume", "opponent_absent_from_valve_vrs", "crowd_saturation"],
        context=[
            "Polymarket Infinite 69c / Insiders 31c ($1.03 traded volume — thin but real); no Valve-VRS cross-check possible because Insiders Esport is absent from Valve's global table",
            "Crowd ownership is 100% Infinite — maximum saturation; the line and the crowd agree, so there is no contrarian angle",
            "INFINITE (VRS #56, 1259 pt; Blytz, kreaz, kyuubii, sl3nd, volt) beat GenOne 2-1 on Oct 13 per stavka.tv's GenOne form summary",
        ],
        sources=[
            ("Polymarket Infinite–Insiders Esport series moneyline", "https://polymarket.com/esports/cs2/draculan/cs2-inf6-ins-2026-10-19"),
            ("strafe DraculaN Season 7 event page (participants incl. Insiders Esport)", "https://www.strafe.com/event/2026-draculan-season-7-d2a0ac/"),
            ("HLTV Digital Crusade DraculaN Season 7 event page", "https://www.hltv.org/events/9312/digital-crusade-draculan-season-7"),
        ]),
    "1081527": dict(
        fair_a=0.527, fair_b=0.473, basis="model",
        pick="aimclub", pick_prob=0.527, role="safe",
        flags=["polymarket_untrained_zero_volume", "originated_vrs_line"],
        context=[
            "Polymarket lists aimclub 50c / BASEMENT BOYS 50c at $0.00 volume — an untrained placeholder that carries no information; the Valve-VRS model is the basis",
            "Valve VRS aimclub #77 (1113 pt) vs BASEMENT BOYS #102 (1036 pt) — model reads aimclub 52.7%",
            "BASEMENT BOYS lost 1-2 to Eternal Fire earlier this week (stavka.tv EF form summary)",
        ],
        sources=[
            ("Polymarket aimclub–BASEMENT BOYS market ($0.00 vol — untrained seed evidence)", "https://polymarket.com/esports/cs2/draculan/cs2-aim1-bmb-2026-10-19"),
            ("Valve regional standings 2026-10-05 (aimclub #77 / BASEMENT BOYS #102)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
            ("stavka.tv Eternal Fire preview (BASEMENT BOYS 1-2 result)", "https://stavka.tv/matches/csgo/16-10-2026-eternal-fire-betclic-apogee-esports"),
        ]),
    "1081528": dict(
        fair_a=0.7203, fair_b=0.2797, basis="blend",
        pick="BC.Game", pick_prob=0.7203, role="safe",
        flags=["thin_market_volume", "model_cooler_than_market", "crowd_saturation"],
        context=[
            "Polymarket BC.Game 75c / Drama 25c ($1.03 traded volume — thin); the Valve-VRS model runs cooler at 66.0% (BC.Game #50, 1318 pt vs Drama #148, 845 pt); fair estimate is the 2/3 market + 1/3 model blend at 72.0%",
            "BC.Game's lineup (asap, Magisk, mzinho, s1mple, Senzu) verified 5/5 against the Valve row on the HLTV match page — s1mple and Magisk headline the roster",
            "dust2.us reports BC.Game is completing a region switch to Asia ahead of the Major — context for the VRS weighting",
            "Crowd ownership 100% BC.Game — saturation; line and crowd agree",
        ],
        sources=[
            ("Polymarket BC.Game–Drama series moneyline", "https://polymarket.com/esports/cs2/draculan/cs2-bcg-drama-2026-10-19"),
            ("HLTV BC.Game vs Drama match page (lineup verification)", "https://www.hltv.org/matches/2399592/bcgame-vs-drama-digital-crusade-draculan-season-7"),
            ("dust2.us — DraculaN Season 7 team list and BC.Game region switch", "https://www.dust2.us/news/78386/faze-round-out-draculan-season-7-team-list"),
        ]),
    "1081529": dict(
        fair_a=0.4559, fair_b=0.5441, basis="blend",
        pick="WBT (WhiteBIT Team)", pick_prob=0.5441, role="climb",
        climb=dict(pick="WBT (WhiteBIT Team)", pick_prob=0.5441, odds_ref=1.72, side="b",
                   gates="fair 54.4% >= 30% floor; crowd ownership 12% <= 20%; "
                         "probability/ownership = 4.5x; 5 verified context flags; "
                         "safe and climb coincide (the line favorite is the crowd-faded side)",
                   swing_cost_pts=0.0),
        flags=["climb_pick", "identity_alias_resolved", "crowd_against_line"],
        context=[
            "Identity resolved: HotSpawn 'WROTBERRY' = WBT = WhiteBIT Team (egamersworld team slug 'wrotberry'; Liquipedia and HLTV team 13683 list WhiteBIT Team in DraculaN Season 7 Group B — same event, group, date and slot)",
            "egamersworld bookmaker average WBT 1.72 / Nexus 1.96 ('the majority of bookmakers unanimously see WBT as the favorite')",
            "Valve VRS WBT #60 (1201 pt) vs Nexus #111 (1008 pt) — model reads WBT 56.7%; WBT's lineup (Psycho, DemQQ, Smash, s4ltovsk1yy, tyr1k) verified 5/5 against the Valve row",
            "Crowd ownership 88% Nexus / 12% WBT — the crowd is heavily on the model's and the bookmakers' losing side",
            "Nexus arrives on a 0-match win streak with a 54.5% three-month win rate (HLTV team page)",
        ],
        sources=[
            ("egamersworld WBT vs Nexus Gaming match page (bookmaker average 1.72/1.96 + lineups)", "https://egamersworld.com/counterstrike/match/V1JAWhPomg/wbt-vs-nexus-gaming-A-jHKvluZk"),
            ("Polymarket WBT vs Nexus market ($0.00 vol — untrained seed, recorded not weighted)", "https://polymarket.com/esports/cs2/draculan/cs2-wbt-nxs1-2026-10-19"),
            ("HLTV WBT team overview (roster verification)", "https://www.hltv.org/team/13683/wbt"),
            ("Liquipedia DraculaN Season 7 (Group B: WhiteBIT Team)", "https://liquipedia.net/counterstrike/DraculaN/Season_7"),
            ("HLTV Nexus team overview (form, upcoming match listing)", "https://www.hltv.org/team/7187/nexus"),
        ]),
    "1081530": dict(
        fair_a=0.6569, fair_b=0.3431, basis="market",
        pick="Iberian Soul", pick_prob=0.6569, role="safe",
        flags=["thin_market_volume"],
        context=[
            "Polymarket Iberian Soul 71c / HyperSpirit 37c ($21.39 traded volume) de-vigs to 65.7/34.3",
            "Valve VRS Iberian Soul #59 (1218 pt) vs HyperSpirit #162 (803 pt) — model agrees at 64.1%",
            "Iberian Soul beat ex-RUSTEC 2-0 at CCT Europe Series 10 (Esports News UK) — the PGL Bucharest open qualifier champion",
        ],
        sources=[
            ("Polymarket Iberian Soul–HyperSpirit series moneyline", "https://polymarket.com/esports/cs2/draculan/cs2-is-hs2-2026-10-19"),
            ("Esports News UK — ex-RUSTEC's CCT Series 10 run (0-2 Iberian Soul)", "https://esports-news.co.uk/2026/10/14/ex-rustec-beat-nordic-partners-gaming-2-0-en-route-to-pgl-bucharest-qualifier-title/"),
            ("HLTV Digital Crusade DraculaN Season 7 event page", "https://www.hltv.org/events/9312/digital-crusade-draculan-season-7"),
        ]),
    "1081531": dict(
        fair_a=0.6069, fair_b=0.3931, basis="market",
        pick="Sashi", pick_prob=0.6069, role="safe",
        flags=[],
        context=[
            "Polymarket Sashi 68c / MOUZ NXT 44c ($274.22 traded volume — the most liquid DraculaN market) de-vigs to 60.7/39.3",
            "Valve VRS Sashi #73 (1131 pt; acoR, Anlelele, Cabbi, MistR, Zyphon) vs MOUZ NXT #137 (877 pt) — model agrees at 58.8%",
            "Market and model are within 2 points — the most internally consistent row in this section",
        ],
        sources=[
            ("Polymarket Sashi–MOUZ NXT series moneyline", "https://polymarket.com/esports/cs2/draculan/cs2-sashi-mouzn-2026-10-19"),
            ("Valve regional standings 2026-10-05 (Sashi #73 / MOUZ NXT #137)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
            ("HLTV Digital Crusade DraculaN Season 7 event page", "https://www.hltv.org/events/9312/digital-crusade-draculan-season-7"),
        ]),
    "1081532": dict(
        fair_a=0.525, fair_b=0.475, basis="model",
        pick="ASTRAL", pick_prob=0.525, role="contrarian",
        flags=["polymarket_price_rejected_stale", "originated_vrs_line", "crowd_against_pick_but_gate_missed"],
        context=[
            "Polymarket lists ASTRAL 96c / Leo 97c (193c total) at $0.00 volume — a stale, untraded seed; rejected as a price rather than de-vigged",
            "Valve VRS ASTRAL #91 (1072 pt) vs Leo #112 (1001 pt) — model reads ASTRAL 52.5%",
            "Crowd ownership 76% Leo / 24% ASTRAL — the crowd is on the model's losing side, but ASTRAL's 24% ownership misses the 20% climb gate, so this is a documented contrarian lean, not an activated climb swing",
        ],
        sources=[
            ("Polymarket ASTRAL–Leo market ($0.00 vol, 96c/97c — rejected-price evidence)", "https://polymarket.com/esports/cs2/draculan/cs2-ast-leo2-2026-10-19"),
            ("Valve regional standings 2026-10-05 (ASTRAL #91 / Leo #112)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
            ("HLTV Digital Crusade DraculaN Season 7 event page", "https://www.hltv.org/events/9312/digital-crusade-draculan-season-7"),
        ]),
    "1081861": dict(
        fair_a=None, fair_b=None, basis=None,
        pick="Lynn Vision", pick_prob=None, role="directional",
        blank_reason="no_external_price_and_opponent_absent_from_valve_vrs",
        flags=["no_market_line", "opponent_absent_from_valve_vrs", "probability_blank_by_policy"],
        context=[
            "No published two-sided price exists (egamersworld shows the 1.8/1.8 placeholder pair; Polymarket lists no VOID Autumn Cup market)",
            "Morningstar is absent from Valve's global standings table, so the site's VRS-origination policy (both teams unambiguously rated) cannot be satisfied — the probability stays BLANK by policy, not by oversight",
            "Context (directional only): egamersworld ratings #32 Lynn Vision vs #547 Morningstar; head-to-head Lynn Vision 3-0 (Mar 11 CAC closed qualifier 2-0, Mar 21 LOOP Cup playoffs 2-0, Mar 22 Asia Championships playoffs 2-0); Lynn Vision on a 3-match win streak, Morningstar on a 2-match losing streak",
            "Lynn Vision's lineup (C4LLM3SU3, EmiliaQAQ, Starry, Westmelon, z4KR) verified 5/5 against the Oct-5 Valve row (#64, 1190 pt)",
        ],
        sources=[
            ("egamersworld Lynn Vision vs Morningstar match page (H2H, ratings, lineups, placeholder odds)", "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/lynn-vision-vs-morningstar-7AWA3eTHD"),
            ("HLTV MaceMedia VOID Autumn Cup 2026 event page", "https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026"),
            ("Valve regional standings 2026-10-05 (Lynn Vision #64; Morningstar absent)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
        ]),
    "1081862": dict(
        fair_a=0.5570, fair_b=0.4430, basis="blend",
        pick="Rare Atom", pick_prob=0.5570, role="safe",
        flags=["egw_widget_vs_index_odds_discrepancy", "alter_ego_roster_change_post_snapshot", "crowd_against_line"],
        context=[
            "egamersworld matches-index average odds Rare Atom 1.62 / Alter Ego 2.15 (de-vig 57.0/43.0); the match-page widget still shows the 1.8/1.8 placeholder — the index feed is fresher and the discrepancy is flagged",
            "Valve VRS Rare Atom #133 (906 pt) vs Alter Ego #155 (819 pt) — model reads Rare Atom 53.0%",
            "Alter Ego's current lineup (PokemoN, shadiy, adeX, laxiee, BloodyK) differs from its Oct-5 Valve row (BnTeT and Gratisfaction out; shadiy and BloodyK in) — two substitutions, so the Alter Ego VRS points may be stale",
            "Crowd ownership FLIPPED during the capture session from 71% Alter Ego to 56% Rare Atom — the crowd chased the line and at press time it agrees with the bookmakers and the model; the earlier 71% Alter Ego reading is retained as the session's ownership-movement evidence",
        ],
        sources=[
            ("egamersworld matches index (Rare Atom 1.62 / Alter Ego 2.15)", "https://egamersworld.com/counterstrike/matches"),
            ("egamersworld Rare Atom vs Alter Ego match page (lineups — roster-change evidence)", "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/rare-atom-vs-alter-ego-O8GeLuSod4"),
            ("Valve regional standings 2026-10-05 (Rare Atom #133 / Alter Ego #155)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
        ]),
    "1081863": dict(
        fair_a=None, fair_b=None, basis=None,
        pick="Chinggis Warriors", pick_prob=None, role="directional",
        blank_reason="no_external_price_and_opponent_absent_from_valve_vrs",
        flags=["no_market_line", "opponent_absent_from_valve_vrs", "opponent_roster_unknown", "probability_blank_by_policy"],
        context=[
            "No published two-sided price exists (egamersworld 1.8/1.8 placeholder; no Polymarket market)",
            "WXM (Wept Xyloid Melancholy, per the Mais Esports VOID Autumn Cup team list) is absent from Valve's global standings table and egamersworld carries no roster for them (all-noName lineup) — origination is blocked on the opponent side, so the probability stays BLANK by policy",
            "Chinggis Warriors are Valve-rated #87 (1084 pt; cool4st, fury5k, ROUX, sk0R + one unverified substitution: egamersworld lists tikuak where the Oct-5 Valve row carries yAmi)",
        ],
        sources=[
            ("egamersworld Chinggis Warriors vs WXM match page (lineup evidence + placeholder odds)", "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/chinggis-warriors-vs-wxm-_ddme1I7dZ"),
            ("Mais Esports VOID Autumn Cup 2026 (WXM = Wept Xyloid Melancholy identity)", "https://maisesports.com.br/campeonatos/cs-go-void-autumn-cup-2026"),
            ("HLTV MaceMedia VOID Autumn Cup 2026 event page", "https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026"),
        ]),
    "1081864": dict(
        fair_a=0.595, fair_b=0.405, basis="model",
        pick="NEXVOID", pick_prob=0.595, role="safe",
        flags=["no_market_line", "originated_vrs_line", "vitalem_roster_change_post_snapshot"],
        context=[
            "No published price (egamersworld 1.8/1.8 placeholder; no Polymarket market) — line originated from the Valve-VRS model",
            "Valve VRS NEXVOID #113 (995 pt) vs Vitalem Aerem #204 (721 pt) — model reads NEXVOID 59.5%; NEXVOID's lineup (AccuracyTG, erkaSt, MiQ, xerolte, Zesta) verified 5/5 against the Valve row",
            "Vitalem Aerem's current lineup carries ProKiller where the Oct-5 Valve row lists BZA — one unverified substitution",
            "Recent form from egamersworld: Vitalem Aerem lost 0-2 to Lynn Vision; NEXVOID lost 1-2 to Chinggis Warriors",
        ],
        sources=[
            ("egamersworld NEXVOID vs Vitalem Aerem match page (lineups, recent results, placeholder odds)", "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/nexvoid-vs-vitalem-aerem-LHqHITkk7x"),
            ("Valve regional standings 2026-10-05 (NEXVOID #113 / Vitalem Aerem #204)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
            ("HLTV MaceMedia VOID Autumn Cup 2026 event page", "https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026"),
        ]),
}
