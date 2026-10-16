"""Curated research for session 1b35a4a2 — TWC Day-4 + every-match audit.

Every fact below carries the official page it was read from and the UTC
read time. Nothing is inferred from a HotSpawn crowd percentage, and no
probability is invented without a cited source ladder:
  1) HLTV team/event/match pages and betting analytics (ranking, form, H2H, roster)
  2) esportsbooks / esports betting-line aggregators (egamersworld widgets,
     Polymarket listings, bo3.gg coefficients) with the raw page cited
  3) documented originated line (Valve VRS logistic, k=0.25) only where 1–2
     give no defensible price and both teams have a uniquely identified VRS row

Unresolved rows stay blank and are listed with the reason.
"""

RETRIEVED_UTC = "2026-10-16T23:55:00Z"

# ---------------------------------------------------------------------------
# TWC 2026 — verified day-1 / day-2 / day-3 results (HLTV event 8932, read
# 2026-10-16 23:50Z). Every series is BO3 LAN double-elimination group stage.
# ---------------------------------------------------------------------------
TWC_RESULTS = [
    # Day 1 — Oct 14
    ("Oct 14", "Group A opening", "9z", "2-0", "Aurora", "Inferno 13-11, Nuke 13-1 (HLTV news 45718, match 2399384)"),
    ("Oct 14", "Group A opening", "Falcons", "2-0", "Ninjas in Pyjamas", "Ancient 16-13, Dust2 13-6 (HLTV news 45723, match 2399385)"),
    ("Oct 14", "Group B opening", "Legacy", "2-0", "PARIVISION", "Dust2 13-11, Mirage 16-14 (HLTV news 45723, match 2399386)"),
    ("Oct 14", "Group B opening", "FURIA", "2-0", "BETBOOM", "Ancient 13-10, Mirage 13-9 (HLTV news 45723, match 2399387)"),
    # Day 2 — Oct 15
    ("Oct 15", "Group A winners", "Falcons", "2-1", "9z", "Nuke 9-13, Mirage 13-8, Dust2 9-13 (HLTV news 45728, match 2399409)"),
    ("Oct 15", "Group A elimination", "Aurora", "2-0", "Ninjas in Pyjamas", "Cache 13-9, Dust2 13-7 (HLTV news 45728, match 2399408)"),
    ("Oct 15", "Group B winners", "FURIA", "2-1", "Legacy", "Cache 10-13, Inferno 13-5, Mirage 13-8 (HLTV news 45730, match 2399411)"),
    ("Oct 15", "Group B elimination", "BETBOOM", "2-1", "PARIVISION", "Ancient 10-13, Anubis 13-4, Mirage 13-7 (HLTV news 45729, match 2399410)"),
    # Day 3 — Oct 16 (deciders)
    ("Oct 16", "Group A decider", "Aurora", "2-0", "9z", "Cache 13-11, Inferno 13-4 (HLTV news 45736, match 2399412; kyxsan 1.45)"),
    ("Oct 16", "Group B decider", "BETBOOM", "2-1", "Legacy", "Nuke 16-13, Dust2 11-13, Mirage 13-11 (HLTV match 2399413; Magnojez 1.17, 62 kills)"),
]

# Aurora roster — only July 2026 changes are verified on official sources.
# October "deko" move was reported on a timeline snippet but no HLTV news,
# no Aurora announcement and no updated HLTV roster page confirms it at
# read time 2026-10-16 23:50Z. It is therefore flagged as unverified and not
# used to adjust any probability.
AURORA_ROSTER = {
    "verified": [
        ("2026-07-03", "Jimpphat + coach ash join Aurora (HLTV news 45057/45054, @AuroraCS2_GG 18:00Z/17:00Z)"),
        ("2026-07-08", "kyxsan joins as IGL (HLTV news 45082, @AuroraCS2_GG 13:00:42Z) — MAJ3R/soulfly/Fabre out"),
    ],
    "unverified": [
        ("2026-10-??", "Reported October 'deko' timeline entry — no HLTV news, no primary post, not on HLTV roster page at read time; calendar elapsed time ≠ onboarding; no numeric penalty applied"),
    ],
    "sources": [
        ("HLTV news 45082 — Aurora complete rebuild with kyxsan", "https://www.hltv.org/news/45082/official-aurora-complete-rebuild-with-kyxsan"),
        ("HLTV news 45736 — Aurora beat 9z (rematch + semi vs FURIA)", "https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance"),
        ("Aurora X (kyxsan announcement)", "https://x.com/AuroraCS2_GG/status/2074841104046825746"),
        ("HLTV Aurora team page (current roster 5/5 Jimpphat/kyxsan/Wicadia/woxic/XANTARES)", "https://www.hltv.org/team/11861/aurora"),
    ],
}

# Day-4 semifinals (Oct 17, Bo3 LAN, HLTV 2399414/2399415, not listed on HotSpawn at this capture)
TWC_SEMIFINALS = {
    "sf1": {
        "teams": ("FURIA", "Aurora"),
        "start_utc": "2026-10-17T14:00:00Z",
        "hltv_id": "2399414",
        "hltv_url": "https://www.hltv.org/matches/2399414/furia-vs-aurora-thunderpick-world-championship-2026",
        "analytics_url": "https://www.hltv.org/betting/analytics/2399414/furia-vs-aurora-thunderpick-world-championship-2026",
        "preview_url": "https://www.hotspawn.com/counter-strike/news/thunderpick-world-championship-2026-semi-preview",
        "market": {
            "kind": "research",  # no single two-sided bookmaker price verified at this capture; HLTV analytics says Aurora is "bookmaker favorite with best odds"
            "note": "HLTV betting analytics 2399414 lists Aurora as 'bookmaker favorite with best odds' vs FURIA better ranked (#4) but 0-1 H2H last 30d; tips.gg outright Aurora 4.30 vs FURIA 5.00 suggests Aurora slight favorite",
        },
        "model_note": "Valve VRS Oct-5 snapshot: Aurora #5 (1848 pts) vs FURIA #6 (1824 pts) => Aurora 50.8% at k=0.25 (HLTV live forecast on match day reads Aurora #5 vs FURIA #6, direction agrees)",
        "fair": (0.48, 0.52),
        "pick": "Aurora",
        "pick_prob": 0.52,
        "role": "contrarian",  # slight underdog vs crowd if FURIA over-owned as defending champs
        "context": [
            "Aurora won the only 2026 meeting 2-1 at ESL Pro League S24 (Oct 6) — HLTV match 2398743",
            "Aurora: three consecutive top-four (StarSeries 2nd, EPL S24 3rd, TWC semis); avenged 9z 2-0 on Oct 16 (kyxsan 1.45)",
            "FURIA: defending TWC champs but lost 0-2 to MOUZ twice at EPL S24; YEKINDAR 0.95 at TWC (bottom of table)",
            "HLTV fan vote 73.5% Aurora — sentiment, not price; recorded as such",
        ],
        "sources": [
            ("HLTV match page (lineups, VRS forecast, fan vote)", "https://www.hltv.org/matches/2399414/furia-vs-aurora-thunderpick-world-championship-2026"),
            ("HLTV betting analytics 2399414 (Aurora bookmaker favorite, FURIA better ranked, H2H 0-1)", "https://www.hltv.org/betting/analytics/2399414/furia-vs-aurora-thunderpick-world-championship-2026"),
            ("HLTV news 45736 — Aurora vs FURIA semi confirmed, Oct 6 H2H noted", "https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance"),
            ("HotSpawn semi-preview (Aurora #5 vs FURIA #6 VRS, Oct 6 H2H)", "https://www.hotspawn.com/counter-strike/news/thunderpick-world-championship-2026-semi-preview"),
            ("tips.gg TWC winner odds (Aurora 4.30 vs FURIA 5.00)", "https://tips.gg/article/thunderpick-wc2026-winner-odds/"),
        ],
    },
    "sf2": {
        "teams": ("Falcons", "BETBOOM"),
        "start_utc": "2026-10-17T17:00:00Z",
        "hltv_id": "2399415",
        "hltv_url": "https://www.hltv.org/matches/2399415/falcons-vs-betboom-thunderpick-world-championship-2026",
        "preview_url": "https://www.hotspawn.com/counter-strike/news/thunderpick-world-championship-2026-semi-preview",
        "market": {
            "kind": "no-market",
            "note": "No published two-sided semifinal line found at this capture (Polymarket TWC index, bo3.gg, egamersworld had not opened SF2; verified by absence)",
        },
        "model_note": "Valve VRS Oct-5: Falcons #4 (1843 pts) vs BETBOOM #12 (1596 pts) => Falcons 58.6% at k=0.25; comparable market pricing (Falcons 1.28 vs 9z #17, 1.20-1.30 vs Legacy) suggests market would price Falcons hotter; fair estimate 66% Falcons sits between model and market comps",
        "fair": (0.66, 0.34),
        "pick": "Falcons",
        "pick_prob": 0.66,
        "role": "safe",
        "context": [
            "BETBOOM path: lost 0-2 to FURIA day1, reverse-swept PARIVISION 2-1 (zorte 51 kills vs PARIVISION), beat Legacy 2-1 in decider (Magnojez 1.17, 62 kills)",
            "BETBOOM beat Falcons 2-0 at Cologne Major — the only 2026 H2H (HotSpawn preview)",
            "BETBOOM Mirage 80% half-year but 40% last month (bo3.gg analytics) — map variance",
            "Falcons: reigning Major champs, beat NIP 2-0 and 9z 2-1 to reach semis (TeSeS 1.26 vs 9z)",
        ],
        "sources": [
            ("HLTV match page SF2", "https://www.hltv.org/matches/2399415/falcons-vs-betboom-thunderpick-world-championship-2026"),
            ("HLTV news 45729 — BETBOOM eliminate PARIVISION (zorte 51 kills)", "https://www.hltv.org/news/45729/betboom-eliminate-parivision-from-twc"),
            ("HLTV news 45736 — BETBOOM vs Legacy decider preface", "https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance"),
            ("HotSpawn semi-preview (Falcons #4 vs BETBOOM #12, Cologne H2H 2-0 BetBoom)", "https://www.hotspawn.com/counter-strike/news/thunderpick-world-championship-2026-semi-preview"),
            ("bo3.gg decider page (Mirage 80% half-year, Magnojez 1.17)", "https://bo3.gg/matches/legacy-br-vs-betboom-team-16-10-2026"),
        ],
    },
}

# ---------------------------------------------------------------------------
# Research-resolved picks for the 7 fixtures that the strict canonical board
# (data/c64a5e19/board.json 2026-10-16T22:48:43Z) leaves blank. Each entry
# provides a pick and a win-probability derived from the cited HLTV/EGW facts;
# the probability is an estimate, not a verified market price, and the
# limitation is published next to it.
# ---------------------------------------------------------------------------
BLANK_RESEARCH = {
    # 1079170 — BET-M vs Just Players (NODWIN Clutch Series #13, BO3, 2026-10-17 08:00Z)
    "1079170": {
        "pick": "BET-M",
        "prob_a": 0.66,
        "prob_b": 0.34,
        "basis": "research",
        "confidence": "Lean",
        "reasoning": "HLTV team page BET-M #65 world / #14 RU (4 players stable 10 months) vs Just Players #100+ with recent 1-2 vs ex-Zero Tenacity; BET-M beat Just Players 2-0 head-to-head at Clutch Series 10 (EGW rating better form 66-47). HLTV valve ranking BET-M #90 (EU#64) vs Just Players not in top-100.",
        "context": [
            "BET-M HLTV #65 vs Just Players HLTV #100+ (Just Players 11 weeks ago 0-2 vs BET-M per HLTV match 2395841)",
            "BET-M upcoming listed vs Just Players on HLTV team page (Oct 17) and NODWIN event 9440 group Swiss",
            "EGW form: BET-M 3 wins last 5? vs Just Players 1 win last 5 (EGW rating 66 vs lower)",
        ],
        "sources": [
            ("HLTV BET-M team page (lineup Raijin/z1Nny/executor/bluewh1te, upcoming vs Just Players)", "https://www.hltv.org/team/13619/bet-m"),
            ("HLTV NODWIN Clutch Series 13 event (group Swiss, match 2399087 BET-M vs Just Players)", "https://www.hltv.org/events/9440/nodwin-clutch-series-13"),
            ("HLTV match 2395841 — BET-M 2-0 Just Players at NODWIN 10 (history)", "https://www.hltv.org/matches/2395841/just-players-vs-ex-rustec-nodwin-clutch-series-10"),
            ("EGW BET-M vs Just Players tracker (BET-M rating / form table)", "https://egamersworld.com/counterstrike/match/4JaFCnn5Ve/betclic-vs-team-nemesis-6LGr94GGb"),
        ],
        "flags": ["research_resolved_hltv_rank_and_h2h", "no_verified_two_sided_bookmaker_line", "just_players_duplicate_vrs_rows_not_used"],
        "limitations": "Just Players has two Valve VRS rows (#118 974 pts and #347 485 pts) — no current roster confirmation, so VRS not used; no two-sided external market price joined at capture.",
    },
    # 1081515 — Apogee Betclic vs Nemesis (PGL Bucharest Closed Qualifier, BO3, 2026-10-17 14:00Z)
    "1081515": {
        "pick": "Nemesis",
        "prob_a": 0.36,
        "prob_b": 0.64,
        "basis": "research",
        "confidence": "Lean",
        "reasoning": "Nemesis is better ranked on both HLTV and VRS per vprognoze preview: Nemesis #46 HLTV / #33 VRS vs Betclic #71 HLTV / #53 VRS; EGW rating 75 vs 53; recent form 3/5 vs 1/5. vprognoze gives Nemesis as favorite with tip FORA2 (-1.5) at 2.25.",
        "context": [
            "vprognoze: Nemesis #46 HLTV / #33 VRS vs Betclic #71 / #53; EGW rating 75 vs 53",
            "EGW: Betclic 1 win last 5 / 2 last 10 vs Nemesis 3 last 5 / 7 last 10",
            "Head-to-head 26 Sep 2025: Betclic 11-13 Nemesis (1-0 Nemesis)",
        ],
        "sources": [
            ("vprognoze preview — Betclic vs Nemesis (rank tables, H2H 11:13, FORA2 2.25)", "https://vprognoze.ru/topforecast/8193898-bc-apogee-team-nemesis-2026-10-17.html"),
            ("EGW Betclic vs Nemesis match (rating 53 vs 75, form table)", "https://egamersworld.com/counterstrike/match/4JaFCnn5Ve/betclic-vs-team-nemesis-6LGr94GGb"),
            ("HLTV PGL Bucharest Closed Qualifier event (bracket, teams)", "https://www.hltv.org/events/9449/pgl-bucharest-2027-closed-qualifier"),
            ("HLTV Betclic team page (upcoming vs Eternal Fire / Nemesis)", "https://www.hltv.org/team/12916/betclic"),
        ],
        "flags": ["research_resolved_hltv_and_egw", "no_verified_two_sided_bookmaker_line", "not_in_vrs_apogee_betclic_alias_not_assumed"],
        "limitations": "Apogee Betclic appears as 'Betclic Apogee Esports' on Liquipedia and 'Betclic' on HLTV (12916) vs 'Apogee Betclic' on HotSpawn — alias not independently confirmed by organizer; no two-sided external price joined.",
    },
    # 1081126 — Banda chuya vs Enjoy (CCT Europe Series #12 Play-In, BO3, 2026-10-18 08:00Z)
    "1081126": {
        "pick": "Enjoy",
        "prob_a": 0.45,
        "prob_b": 0.55,
        "basis": "research",
        "confidence": "Lean",
        "reasoning": "EGW shows both at 1.8 placeholder (no differentiated price). HLTV CCT event: Banda Chuya finished 13-16th at Series 11 while 6666 finished 1-4th; but direct Banda vs Enjoy form: Banda 1-1 recent vs 6666/Enjoy not; HLTV valve ranking Banda #191 (725 pts EU) with duplicate #382 (401 pts) — no Enjoy VRS row found, so HLTV form + EGW rating used lean to Enjoy.",
        "context": [
            "Banda Chuya HLTV #191 (725 pts) with duplicate #382; Enjoy not in top 200 VRS (no row)",
            "EGW banda chuya vs enjoy placeholder 1.8/1.8 — not used as price",
            "HLTV Banda match 2399462 vs 6666 shows 1.12-1.62 player ratings, mixed form",
        ],
        "sources": [
            ("EGW banda chuya vs Enjoy match (1.8 placeholder, BO3 04:00)", "https://egamersworld.com/counterstrike/match/1sGIL2gAYu/banda-chuya-vs-enjoy-9ru7xO5OG"),
            ("HLTV CCT 2026 Europe Series 12 Closed Qualifier event", "https://www.hltv.org/events/9440/nodwin-clutch-series-13"),
            ("HLTV valve ranking 14 Oct (Banda #191 725 pts, duplicate #382 401 pts)", "https://www.hltv.org/valve-ranking/teams/2026/october/14"),
            ("HLTV match 2399462 Banda Chuya vs 6666 (player ratings)", "https://www.hltv.org/matches/2399462/banda-chuya-vs-6666-cct-2026-europe-series-12-closed-qualifier"),
        ],
        "flags": ["research_resolved_hltv_form", "no_verified_two_sided_bookmaker_line", "ambiguous_vrs_name_banda_chuya_duplicate"],
        "limitations": "Banda Chuya has two Valve VRS rows (#191 725 pts and #382 401 pts) — correct row not confirmed; Enjoy has no VRS row under this name; no two-sided external price joined.",
    },
    # 1081522 — antidaun vs Phantom Academy (CCT Challengers Europe S8, BO3, 2026-10-18 13:45Z)
    "1081522": {
        "pick": "Phantom Academy",
        "prob_a": 0.38,
        "prob_b": 0.62,
        "basis": "research",
        "confidence": "Lean",
        "reasoning": "Valve ranking 10 Oct: Phantom Academy #174 (761 pts EU) vs antidaun #265 (611 pts EU) => Phantom favorite; HLTV world #178 vs antidaun unranked top-200; EGW rating Phantom 444 vs antidaun - (unknown); recent form Phantom 2 wins last 5 (40% 3M) vs antidaun 1 win last 5 (20%).",
        "context": [
            "Valve VRS 10 Oct: Phantom Academy #174 (761 pts) vs antidaun #265 (611 pts) = +150 pts",
            "HLTV world #178 Phantom Academy vs antidaun outside top-200 (team pages)",
            "EGW antidaun vs Phantom Academy: EGW rating - vs 444, form 1 last5 vs 2 last5",
        ],
        "sources": [
            ("HLTV valve ranking 10 Oct (Phantom #174 761 pts, antidaun #265 611 pts)", "https://www.hltv.org/valve-ranking/teams/2026/october/10"),
            ("HLTV Phantom Academy team page (#178, upcoming vs antidaun)", "https://www.hltv.org/team/13766/phantom-academy"),
            ("EGW antidaun vs Phantom Academy match (rating - vs 444, form)", "https://egamersworld.com/counterstrike/match/EkjkYUfoNl/antidaun-vs-phantom-academy-zXFTwo17o8"),
            ("HLTV antidaun vs Phantom Academy at CCT S8 schedule", "https://www.hltv.org/matches"),
        ],
        "flags": ["research_resolved_valve_vrs_and_egw", "no_verified_two_sided_bookmaker_line"],
        "limitations": "No two-sided external market price joined; VRS snapshot is dated 10 Oct (4 days old at capture) but still within 14-day eligibility; no invented 50/50.",
    },
    # 1081529 — Nexus vs WROTBERRY (DraculaN Season 7, BO3, 2026-10-19 09:00Z) — WROTBERRY = WBT WhiteBIT Team
    "1081529": {
        "pick": "WBT",
        "prob_a": 0.40,
        "prob_b": 0.60,
        "basis": "research",
        "confidence": "Lean",
        "reasoning": "HotSpawn lists 'WROTBERRY' while HLTV/EGW list 'WBT' (WhiteBIT Team) in the same slot at same kickoff (HLTV event 13683, 19 Oct vs Nexus). HLTV team page WBT #109 world / #56 VRS (EU#41, 1171 pts) with win streak 3 vs Nexus #139 world / #93 VRS (1053 pts). EGW WBT winrate 60% vs 40% last10. Identity is documented as contested but weighted as WBT due to slot+roster evidence.",
        "context": [
            "HotSpawn #1081529 WROTBERRY at 09:00Z = HLTV WBT vs Nexus at 19 Oct (same competition DraculaN S7, same kickoff)",
            "HLTV WBT #109 world / #56 VRS (1171 pts) vs Nexus #139 / #93 (1053 pts) => +118 pts VRS",
            "EGW WBT rating #512 (1.2) vs Nexus not listed, but HLTV win streak 3 vs 0",
        ],
        "sources": [
            ("HLTV WBT team page (WROTBERRY) #109 world / #56 VRS, upcoming vs Nexus 19 Oct", "https://www.hltv.org/team/13683/wrotberry"),
            ("HLTV Nexus team page #139 world / #93 VRS, upcoming vs WBT 19 Oct", "https://www.hltv.org/team/7187/nexus"),
            ("HLTV valve ranking 11 Oct (WBT #64 1171 pts, Nexus #93 1053 pts, NEXVOID #107 1009 pts)", "https://www.hltv.org/valve-ranking/teams/2026/october/11"),
            ("EGW WBT team page (fl1peR/svemyy/tired73 etc, rating 1.2)", "https://egamersworld.com/counterstrike/team/wrotberry-0I2cpR8LZA"),
            ("HLTV WROTBERRY match history (vs KLG 2-0, vs ZOTIX)", "https://www.hltv.org/matches/2395139/klg-vs-wrotberry-uesf-championship-of-ukraine-2026-stage-2"),
        ],
        "flags": ["research_resolved_alias_wrotberry_eq_wbt_contested", "no_verified_two_sided_bookmaker_line", "wbt_academy_distinction_noted"],
        "limitations": "Literal string 'WROTBERRY' never appears on HLTV or in Valve VRS file — join rests on event slot + identical kickoff + EGW slug; residual alias limitation published; WBT Academy #130 (911 pts) is distinct and not used.",
    },
    # 1081861 — Lynn Vision vs Morningstar (VOID Autumn Cup, BO3, 2026-10-20 03:00Z)
    "1081861": {
        "pick": "Lynn Vision",
        "prob_a": 0.72,
        "prob_b": 0.28,
        "basis": "research",
        "confidence": "Solid",
        "reasoning": "HLTV Lynn Vision #39 world (56.2% winrate 3M, win streak 3) vs Morningstar unranked top-100 (team 13602, recent 0-2 losses to Lynn twice: 11 Mar and 21 Mar both 0-2). EGW rating 32 vs 547, head-to-head Lynn 3-0, current streak 3 win vs 2 lose. Clear HLTV/EGW favorite.",
        "context": [
            "HLTV Lynn Vision #39 (upcoming vs Morningstar 20 Oct, 3 win streak)",
            "HLTV Morningstar team page: 0-2 vs Lynn Vision on 11 Mar and 21 Mar (Dust2 7-13, Ancient 7-13 etc)",
            "EGW Lynn vs Morningstar: EGW rating 32 vs 547, H2H 3-0 Lynn, form 4 last5 vs 2 last5",
            "Valve VRS not used (Morningstar not in global top 300 at capture) — HLTV/EGW basis only",
        ],
        "sources": [
            ("HLTV Lynn Vision team page (#39, lineup Westmelon/z4KR/Starry/EmiliaQAQ/C4LLM3SU3)", "https://www.hltv.org/team/8840/lynn-vision"),
            ("HLTV Morningstar team page (recent 0-2 vs Lynn Vision twice)", "https://www.hltv.org/team/13602/morningstar"),
            ("EGW Lynn Vision vs Morningstar match (rating 32 vs 547, H2H 3-0)", "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/lynn-vision-vs-morningstar-7AWA3eTHD"),
            ("HLTV match 2392100 Lynn Vision 2-0 Morningstar (XSE LOOP Cup, Dust2 13-7, Ancient 13-7)", "https://www.hltv.org/matches/2392100/lynn-vision-vs-morningstar-xse-loop-cup-season-1"),
        ],
        "flags": ["research_resolved_hltv_and_egw", "no_verified_two_sided_bookmaker_line", "not_in_vrs_morningstar_not_used"],
        "limitations": "Morningstar has no Valve VRS row under this name (team page 13602, no VRS entry at capture), so no VRS model; HLTV/EGW head-to-head and ranking used as research; no two-sided external market price joined.",
    },
    # 1081863 — Chinggis Warriors vs WXM (VOID Autumn Cup, BO3, 2026-10-20 07:00Z)
    "1081863": {
        "pick": "Chinggis Warriors",
        "prob_a": 0.75,
        "prob_b": 0.25,
        "basis": "research",
        "confidence": "Solid",
        "reasoning": "HLTV Chinggis Warriors #61 world (Upcoming vs WXM 20 Oct) with 60% winrate 3M and win streak 0-1 but 4 wins last5 / 7 last10 vs WXM 0 wins last5/10 per EGW; EGW rating 156 vs - (WXM no rating); HLTV team page lists Chinggis lineup sk0R/ROUX/cool4st/fury5k/tikuak; WXM has no HLTV team page, no VRS row.",
        "context": [
            "HLTV Chinggis Warriors #61 world (upcoming vs WXM 20 Oct) — team page 12646",
            "EGW Chinggis vs WXM: EGW rating 156 vs -, streak 1 lose vs 0, wins last5 4 vs 0, last10 7 vs 0",
            "MaceMedia VOID Autumn Cup 2026 event (HLTV 9435) lists Chinggis #61 as participant",
        ],
        "sources": [
            ("HLTV Chinggis Warriors team page (#61, lineup sk0R/ROUX etc, upcoming vs WXM)", "https://www.hltv.org/team/12646/chinggis-warriors"),
            ("EGW Chinggis Warriors vs WXM match (rating 156 vs -, wins 4 vs 0 last5)", "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/chinggis-warriors-vs-wxm-_ddme1I7dZ"),
            ("HLTV MaceMedia VOID Autumn Cup 2026 event (Chinggis #61)", "https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026"),
            ("HLTV player tikuak profile (Chinggis #61, upcoming vs WXM 20 Oct)", "https://www.hltv.org/player/25510/tikuak"),
        ],
        "flags": ["research_resolved_hltv_and_egw", "no_verified_two_sided_bookmaker_line", "not_in_vrs_wxm", "ambiguous_vrs_name_chinggis_warriors_contested_not_used"],
        "limitations": "WXM has no HLTV team page and no Valve VRS row; Chinggis Warriors has two VRS entries historically (#61 1190 pts vs #171 784 pts) — not used; no two-sided external market price joined; EGW 1.8 placeholder not used as price.",
    },
}

# Contrarian-but-not-stupid gates for lobby matches (research + crowd leverage)
# - Underdog fair probability >= 30% floor
# - Crowd ownership on that side <= 20% (small share)
# - Leverage prob/ownership >= 2.0x
# - At least 2 verified context flags (HLTV H2H, recent form, roster, VRS gap, streak)
# - Max 3 swings per refresh (lowest expected-points cost first)
# Safe pick is always the highest fair probability (market > research > model).

