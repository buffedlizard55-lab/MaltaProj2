#!/usr/bin/env python3
"""
MaltaProj2 - Hotspawn Pick'em betting-line reconstruction.

Builds:
  data/*.json                 machine-readable dataset (canonical)
  docs/**                     static GitHub Pages site (dashboard + subpages)

Design rules enforced by this script:
  * Every row carries source links.
  * Values that were not captured from a source stay empty (None) and are
    listed on the "Flagged for review" page. Nothing is inferred or filled in.
  * Hotspawn crowd pick % is displayed but NEVER used in any probability.
  * Our own line ("consensus market line") is a documented, reproducible
    de-margin of captured market prices only.

Run:  python3 scripts/build.py
"""

import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DOCS = os.path.join(ROOT, "docs")

SNAPSHOT = "2026-10-13 (UTC); site re-verified 2026-10-13"
HS_LOBBY = "https://play.hotspawn.com/lobby"
HS_CS2 = "https://play.hotspawn.com/cs2-pickems"

# --------------------------------------------------------------------------
# 1. Hotspawn Pick'em entries (open-for-picks window), captured from
#    https://play.hotspawn.com/lobby and https://play.hotspawn.com/cs2-pickems
# --------------------------------------------------------------------------
MATCHES = [
    dict(
        id="hs-1081076", event="ESL Challenger League Season 52: South America - Cup #3",
        tier="B", points=3, stage="Waiting For Information", section="Closing Soon",
        kickoff_utc="2026-10-13T17:00:00Z", fmt="Bo3 (bo3 on HLTV/bo3.gg)",
        team_a="ex-Keyd Stars", team_b="Galorys",
        hotspawn_url="https://www.hotspawn.com/matches/ex-keyd-stars-vs-galorys-esl-challenger-league-season-52-south-america-cup-3-1081076",
        pick_pct_a=86, pick_pct_b=14,
        pick_pct_note="86/14 at 14:15 UTC snapshot; 83/17 at 13:56 UTC snapshot (live-ticking).",
        hltv_match_url=None,
        hltv_event_url="https://www.hltv.org/matches?event=2635",
        hltv_note="Per-match HLTV page not captured; match confirmed inside HLTV event 2635 listing (ESL CL S52 Cup 3, playoffs).",
        other_match_url="https://bo3.gg/matches/ex-keyd-stats-vs-galorys-cs-13-10-2026",
        other_match_note="bo3.gg shows the fixture (Oct 13, 17:00, Bo3, playoffs/lower-bracket final) and partial book lines: 'Winner Galorys 1.54', 'Galorys handicap +1.5 maps 1.48', 'ex-Keyd Stars handicap +1.5 maps 2.13'. The 1.17 figure on the page could not be tied to the match-winner market, so no complete two-sided line was usable.",
    ),
    dict(
        id="hs-1079546", event="ESL Challenger League Season 52: North America - Cup #3",
        tier="B", points=3, stage="Waiting For Information", section="Closing Soon",
        kickoff_utc="2026-10-13T21:00:00Z", fmt="Bo3",
        team_a="Zomblers", team_b="Overtake Sector",
        hotspawn_url="https://www.hotspawn.com/matches/zomblers-vs-overtake-sector-esl-challenger-league-season-52-north-america-cup-3-1079546",
        pick_pct_a=11, pick_pct_b=89,
        pick_pct_note="Live-ticking (11/89 at 14:15 UTC snapshot).",
        hltv_match_url=None,
        hltv_event_url="https://www.hltv.org/matches?event=2635",
        hltv_note="Per-match HLTV page not captured; fixture appears in HLTV event 2635 listing (North America Cup 3, upper final, 03:00 in HLTV's display timezone).",
        other_match_url="https://bo3.gg/matches/zomblers-vs-overtake-14-10-2026",
        other_match_note="bo3.gg lists the fixture (21:00). No two-sided book line captured.",
    ),
    dict(
        id="hs-1079621", event="CCT Europe 2026 Series #11",
        tier="B", points=3, stage="Waiting For Information", section="Closing Soon",
        kickoff_utc="2026-10-14T04:00:00Z", fmt="Bo3",
        team_a="Gothic", team_b="Lavked",
        hotspawn_url="https://www.hotspawn.com/matches/gothic-vs-lavked-cct-europe-2026-series-11-1079621",
        pick_pct_a=10, pick_pct_b=90, pick_pct_note="10/90 at 13:56 UTC; 13/88 earlier.",
        hltv_match_url="https://www.hltv.org/matches/2399298/gothic-vs-lavked-cct-2026-europe-series-11",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399298/gothic-vs-lavked-cct-2026-europe-series-11",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080176", event="Thunderpick World Championship 2026",
        tier="S", points=7, stage="Group Stage And Playoffs", section="Closing Soon",
        kickoff_utc="2026-10-14T04:30:00Z", fmt="Bo3 (LAN, Group A opening match)",
        team_a="9z", team_b="Aurora",
        hotspawn_url="https://www.hotspawn.com/matches/9z-vs-aurora-thunderpick-world-championship-2026-1080176",
        pick_pct_a=5, pick_pct_b=95, pick_pct_note="Live-ticking (0/100 at 13:56 UTC).",
        hltv_match_url="https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399384/9z-vs-aurora-thunderpick-world-championship-2026",
        other_match_url="https://bo3.gg/matches/9z-vs-aurora-gaming-14-10-2026",
        other_match_note="bo3.gg fixture listing confirmed by search index (Oct 14, 04:30).",
    ),
    dict(
        id="hs-1079438", event="Stake Pulse Beat III",
        tier="B", points=3, stage="Waiting For Information", section="Closing Soon",
        kickoff_utc="2026-10-14T06:00:00Z", fmt="Bo3 (LAN)",
        team_a="Astralis", team_b="Sashi",
        hotspawn_url="https://www.hotspawn.com/matches/astralis-vs-sashi-stake-pulse-beat-iii-1079438",
        pick_pct_a=95, pick_pct_b=5, pick_pct_note="95/5 at 14:15 UTC.",
        hltv_match_url="https://www.hltv.org/matches/2399134/astralis-vs-sashi-stake-pulse-beat-iii",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399134/astralis-vs-sashi-stake-pulse-beat-iii",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1079439", event="Stake Pulse Beat III",
        tier="B", points=3, stage="Waiting For Information", section="Closing Soon",
        kickoff_utc="2026-10-14T06:00:00Z", fmt="Bo3 (LAN)",
        team_a="HOTU", team_b="Fnatic",
        hotspawn_url="https://www.hotspawn.com/matches/hotu-vs-fnatic-stake-pulse-beat-iii-1079439",
        pick_pct_a=9, pick_pct_b=91, pick_pct_note="9/91 at 14:15 UTC.",
        hltv_match_url="https://www.hltv.org/matches/2399135/hotu-vs-fnatic-stake-pulse-beat-iii",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399135/hotu-vs-fnatic-stake-pulse-beat-iii",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1079622", event="CCT Europe 2026 Series #11",
        tier="B", points=3, stage="Waiting For Information", section="Closing Soon",
        kickoff_utc="2026-10-14T07:00:00Z", fmt="Bo3",
        team_a="ex-RUSTEC", team_b="mellren",
        hotspawn_url="https://www.hotspawn.com/matches/ex-rustec-vs-mellren-cct-europe-2026-series-11-1079622",
        pick_pct_a=89, pick_pct_b=11, pick_pct_note="89/11 at 14:15 UTC.",
        hltv_match_url="https://www.hltv.org/matches/2399299/ex-rustec-vs-mellren-cct-2026-europe-series-11",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399299/ex-rustec-vs-mellren-cct-2026-europe-series-11",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080177", event="Thunderpick World Championship 2026",
        tier="S", points=7, stage="Group Stage And Playoffs", section="Closing Soon",
        kickoff_utc="2026-10-14T07:00:00Z", fmt="Bo3 (LAN)",
        team_a="Falcons", team_b="Ninjas in Pyjamas",
        hotspawn_url="https://www.hotspawn.com/matches/falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026-1080177",
        pick_pct_a=89, pick_pct_b=11, pick_pct_note="Live-ticking (94/6 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399385/falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399385/falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080178", event="Thunderpick World Championship 2026",
        tier="S", points=7, stage="Group Stage And Playoffs", section="Closing Soon",
        kickoff_utc="2026-10-14T09:30:00Z", fmt="Bo3 (LAN)",
        team_a="Legacy", team_b="PARIVISION",
        hotspawn_url="https://www.hotspawn.com/matches/legacy-vs-parivision-thunderpick-world-championship-2026-1080178",
        pick_pct_a=83, pick_pct_b=17, pick_pct_note="Live-ticking (88/12 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399386/legacy-vs-parivision-thunderpick-world-championship-2026",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399386/legacy-vs-parivision-thunderpick-world-championship-2026",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1079623", event="CCT Europe 2026 Series #11",
        tier="B", points=3, stage="Waiting For Information", section="Closing Soon",
        kickoff_utc="2026-10-14T10:00:00Z", fmt="Bo3",
        team_a="G2 Ares", team_b="The Last Resort",
        hotspawn_url="https://www.hotspawn.com/matches/g2-ares-vs-the-last-resort-cct-europe-2026-series-11-1079623",
        pick_pct_a=100, pick_pct_b=0, pick_pct_note="100/0 at 14:15 UTC.",
        hltv_match_url="https://www.hltv.org/matches/2399300/g2-ares-vs-the-last-resort-cct-2026-europe-series-11",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399300/g2-ares-vs-the-last-resort-cct-2026-europe-series-11",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080179", event="Thunderpick World Championship 2026",
        tier="S", points=7, stage="Group Stage And Playoffs", section="Closing Soon",
        kickoff_utc="2026-10-14T12:00:00Z", fmt="Bo3 (LAN)",
        team_a="FURIA", team_b="BetBoom",
        hotspawn_url="https://www.hotspawn.com/matches/furia-vs-betboom-thunderpick-world-championship-2026-1080179",
        pick_pct_a=89, pick_pct_b=11, pick_pct_note="Live-ticking (94/6 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399387/furia-vs-betboom-thunderpick-world-championship-2026",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399387/furia-vs-betboom-thunderpick-world-championship-2026",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1079624", event="CCT Europe 2026 Series #11",
        tier="B", points=3, stage="Waiting For Information", section="Closing Soon",
        kickoff_utc="2026-10-14T13:00:00Z", fmt="Bo3",
        team_a="FORZE Reload", team_b="LFO 10",
        hotspawn_url="https://www.hotspawn.com/matches/forze-reload-vs-lfo-10-cct-europe-2026-series-11-1079624",
        pick_pct_a=89, pick_pct_b=11, pick_pct_note="Live-ticking (100/0 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399301/forze-reload-vs-lfo-10-cct-2026-europe-series-11",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399301/forze-reload-vs-lfo-10-cct-2026-europe-series-11",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080279", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-15T04:00:00Z", fmt="Bo1",
        team_a="WROTBERRY", team_b="EAC",
        alias_note="Hotspawn 'WROTBERRY' occupies the same fixture slot as HLTV/Polymarket 'WBT' (Ukraine); Hotspawn 'EAC' = HLTV 'EAC' = Polymarket 'Esport Academy Copenhagen'/'EA Copenhagen'.",
        hotspawn_url="https://www.hotspawn.com/matches/wrotberry-vs-eac-elisa-breakout-series-2-1080279",
        pick_pct_a=73, pick_pct_b=27, pick_pct_note="Live-ticking (71/29 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399418/wbt-vs-eac-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399418/wbt-vs-eac-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1079440", event="Stake Pulse Beat III",
        tier="B", points=3, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-15T06:00:00Z", fmt="Bo3 (LAN)",
        team_a="MIBR", team_b="BC.Game",
        hotspawn_url="https://www.hotspawn.com/matches/mibr-vs-bc-game-stake-pulse-beat-iii-1079440",
        pick_pct_a=30, pick_pct_b=70, pick_pct_note="Live-ticking (32/68 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399136/mibr-vs-bcgame-stake-pulse-beat-iii",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399136/mibr-vs-bcgame-stake-pulse-beat-iii",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1079442", event="Stake Pulse Beat III",
        tier="B", points=3, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-15T06:00:00Z", fmt="Bo3 (LAN)",
        team_a="Heroic", team_b="Envy",
        hotspawn_url="https://www.hotspawn.com/matches/heroic-vs-envy-stake-pulse-beat-iii-1079442",
        pick_pct_a=90, pick_pct_b=10, pick_pct_note="Live-ticking (95/5 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399137/heroic-vs-envy-stake-pulse-beat-iii",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399137/heroic-vs-envy-stake-pulse-beat-iii",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080280", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-15T06:00:00Z", fmt="Bo1",
        team_a="ENCE", team_b="BOJONG",
        hotspawn_url="https://www.hotspawn.com/matches/ence-vs-bojong-elisa-breakout-series-2-1080280",
        pick_pct_a=94, pick_pct_b=6, pick_pct_note="Live-ticking (100/0 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399419/ence-vs-bojong-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399419/ence-vs-bojong-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080281", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-15T08:00:00Z", fmt="Bo1",
        team_a="WROTBERRY", team_b="ENCE",
        alias_note="Hotspawn 'WROTBERRY' = HLTV 'WBT' (same fixture slot/time; not independently confirmed as the same org).",
        hotspawn_url="https://www.hotspawn.com/matches/wrotberry-vs-ence-elisa-breakout-series-2-1080281",
        pick_pct_a=29, pick_pct_b=71, pick_pct_note="Live-ticking (31/69 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399420/wbt-vs-ence-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399420/wbt-vs-ence-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080282", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-15T10:00:00Z", fmt="Bo1",
        team_a="EAC", team_b="BOJONG",
        hotspawn_url="https://www.hotspawn.com/matches/eac-vs-bojong-elisa-breakout-series-2-1080282",
        pick_pct_a=93, pick_pct_b=7, pick_pct_note="Live-ticking (100/0 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399421/eac-vs-bojong-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399421/eac-vs-bojong-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080283", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-15T12:00:00Z", fmt="Bo1",
        team_a="WROTBERRY", team_b="BOJONG",
        alias_note="Hotspawn 'WROTBERRY' = HLTV 'WBT' (same fixture slot/time; not independently confirmed as the same org).",
        hotspawn_url="https://www.hotspawn.com/matches/wrotberry-vs-bojong-elisa-breakout-series-2-1080283",
        pick_pct_a=87, pick_pct_b=13, pick_pct_note="Live-ticking (93/7 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399422/wbt-vs-bojong-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399422/wbt-vs-bojong-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080284", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-15T14:00:00Z", fmt="Bo1",
        team_a="EAC", team_b="ENCE",
        hotspawn_url="https://www.hotspawn.com/matches/eac-vs-ence-elisa-breakout-series-2-1080284",
        pick_pct_a=27, pick_pct_b=73, pick_pct_note="Live-ticking (29/71 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399423/eac-vs-ence-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399423/eac-vs-ence-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080285", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-16T04:00:00Z", fmt="Bo1",
        team_a="Voca", team_b="Phantom",
        hotspawn_url="https://www.hotspawn.com/matches/voca-vs-phantom-elisa-breakout-series-2-1080285",
        pick_pct_a=27, pick_pct_b=73, pick_pct_note="Live-ticking (21/79 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399424/voca-vs-phantom-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399424/voca-vs-phantom-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080286", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-16T06:00:00Z", fmt="Bo1",
        team_a="HAVU", team_b="RoundsGG",
        alias_note="Hotspawn 'RoundsGG' = HLTV 'ROUNDS' (same fixture slot/time).",
        hotspawn_url="https://www.hotspawn.com/matches/havu-vs-roundsgg-elisa-breakout-series-2-1080286",
        pick_pct_a=93, pick_pct_b=7, pick_pct_note="Live-ticking (100/0 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399425/havu-vs-rounds-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399425/havu-vs-rounds-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080287", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-16T08:00:00Z", fmt="Bo1",
        team_a="Voca", team_b="HAVU",
        hotspawn_url="https://www.hotspawn.com/matches/voca-vs-havu-elisa-breakout-series-2-1080287",
        pick_pct_a=64, pick_pct_b=36, pick_pct_note="Live-ticking (69/31 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399426/voca-vs-havu-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399426/voca-vs-havu-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080288", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-16T10:00:00Z", fmt="Bo1",
        team_a="Phantom", team_b="RoundsGG",
        alias_note="Hotspawn 'RoundsGG' = HLTV 'ROUNDS' (same fixture slot/time).",
        hotspawn_url="https://www.hotspawn.com/matches/phantom-vs-roundsgg-elisa-breakout-series-2-1080288",
        pick_pct_a=93, pick_pct_b=7, pick_pct_note="Live-ticking (100/0 earlier same day).",
        hltv_match_url="https://www.hltv.org/matches/2399427/phantom-vs-rounds-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399427/phantom-vs-rounds-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080289", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-16T12:00:00Z", fmt="Bo1",
        team_a="RoundsGG", team_b="Voca",
        alias_note="Hotspawn team order (RoundsGG vs Voca) differs from HLTV (Voca vs ROUNDS) for the same slot; Polymarket lists Voca vs RoundsGG.",
        hotspawn_url="https://www.hotspawn.com/matches/roundsgg-vs-voca-elisa-breakout-series-2-1080289",
        pick_pct_a=0, pick_pct_b=100, pick_pct_note="Live-ticking.",
        hltv_match_url="https://www.hltv.org/matches/2399428/voca-vs-rounds-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399428/voca-vs-rounds-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
    dict(
        id="hs-1080290", event="Elisa BreakOut Series #2",
        tier="C", points=2, stage="Waiting For Information", section="Upcoming",
        kickoff_utc="2026-10-16T14:00:00Z", fmt="Bo1",
        team_a="Phantom", team_b="HAVU",
        hotspawn_url="https://www.hotspawn.com/matches/phantom-vs-havu-elisa-breakout-series-2-1080290",
        pick_pct_a=100, pick_pct_b=0, pick_pct_note="Live-ticking.",
        hltv_match_url="https://www.hltv.org/matches/2399429/phantom-vs-havu-elisa-breakout-series-2",
        hltv_betting_url="https://www.hltv.org/betting/analytics/2399429/phantom-vs-havu-elisa-breakout-series-2",
        other_match_url=None, other_match_note=None,
    ),
]

# --------------------------------------------------------------------------
# 2. Captured external market prices (raw, exactly as displayed)
# --------------------------------------------------------------------------
# odds_egw: decimal odds shown in EGamersWorld's "Bets on <event> by bc.game" module
# pm:       Polymarket displayed price in cents (== %), [team_a_side, team_b_side]
EGW_CAP = "2026-10-13"
PM_CAP = "2026-10-13"

MARKETS = {
    "hs-1081076": dict(
        odds_egw=None,
        odds_egw_note="No two-sided EGamersWorld line captured for this fixture at capture time.",
        egw_url=None,
        pm=dict(prices=[33, 68], url="https://polymarket.com/esports/cs2/esl-challenger-league/cs2-keydst-gls1-2026-10-13",
                volume="$2.0K", note="Market price 33c / 68c. Opposite lean to the Hotspawn crowd (86% ex-Keyd Stars)."),
    ),
    "hs-1079546": dict(
        odds_egw=None,
        odds_egw_note="No two-sided EGamersWorld line captured for this fixture at capture time.",
        egw_url=None,
        pm=dict(prices=[34, 67], url="https://polymarket.com/esports/cs2/esl-challenger-league/cs2-zomb-ot2-2026-10-13",
                volume="$1.5K", note="Market price 34c / 67c."),
    ),
    "hs-1079621": dict(
        odds_egw=dict(a=1.881, b=1.782, url="https://egamersworld.com/counterstrike/event/cct-europe-2026-series-11-_rW8GEyWK",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP),
        pm=dict(prices=[53, 47], url="https://polymarket.com/esports/cs2/cct-europe/cs2-gothic-lavked-2026-10-14",
                volume="$220", note="Headline 53c/47c; the detail list showed 56c/50c (wide spread). Market leans Gothic, bc.game via EGW leans Lavked."),
    ),
    "hs-1080176": dict(
        odds_egw=dict(a=3.6, b=1.27, url="https://egamersworld.com/counterstrike/event/thunderpick-world-championship-2026-5X5sFiL7H",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP,
                      note="Same page also displayed 3.8/1.22 in its schedule list, and the EGW match page showed 3.3/1.26 at an earlier capture."),
        pm=dict(prices=[26, 75], url="https://polymarket.com/esports/cs2/thunderpick-world-championship/cs2-9z-aur1-2026-10-14",
                volume="$28.9K", note="Market price 26c / 75c."),
    ),
    "hs-1079438": dict(
        odds_egw=dict(a=1.11, b=6.2, url="https://egamersworld.com/counterstrike/event/stake-pulse-beat-iii-EJZmJpBjeNx",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP),
        pm=None,
    ),
    "hs-1079439": dict(
        odds_egw=dict(a=1.93, b=1.83, url="https://egamersworld.com/counterstrike/event/stake-pulse-beat-iii-EJZmJpBjeNx",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP,
                      note="Market has fnatic as narrow favourite; Hotspawn crowd has fnatic at 91%."),
        pm=None,
    ),
    "hs-1079622": dict(
        odds_egw=None,
        odds_egw_note="Not present in the EGamersWorld 'Bets on' module at capture time.",
        egw_url="https://egamersworld.com/counterstrike/event/cct-europe-2026-series-11-_rW8GEyWK",
        pm=dict(prices=[67, 38], url="https://polymarket.com/esports/cs2/cct-europe/cs2-rustec-mellre-2026-10-14",
                volume="$55", note="Detail-list price 67c/38c; headline showed 65c/36c."),
    ),
    "hs-1080177": dict(
        odds_egw=dict(a=1.23, b=3.95, url="https://egamersworld.com/counterstrike/event/thunderpick-world-championship-2026-5X5sFiL7H",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP,
                      note="Schedule list on the same page showed 1.22/3.8."),
        pm=dict(prices=[77, 24], url="https://polymarket.com/esports/cs2/thunderpick-world-championship/cs2-fal2-nip-2026-10-14",
                volume="$105K", note="Market price 77c / 24c."),
    ),
    "hs-1080178": dict(
        odds_egw=dict(a=1.65, b=2.18, url="https://egamersworld.com/counterstrike/event/thunderpick-world-championship-2026-5X5sFiL7H",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP),
        pm=dict(prices=[59, 42], url="https://polymarket.com/esports/cs2/thunderpick-world-championship/cs2-lgc-prv-2026-10-14",
                volume="$15.9K", note="Market price 59c / 42c."),
    ),
    "hs-1079623": dict(
        odds_egw=dict(a=1.465, b=2.436, url="https://egamersworld.com/counterstrike/event/cct-europe-2026-series-11-_rW8GEyWK",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP),
        pm=dict(prices=[81, 41], url="https://polymarket.com/esports/cs2/cct-europe/cs2-g2a-tlr-2026-10-14",
                volume="$55.78", note="Market price 81c / 41c."),
    ),
    "hs-1080179": dict(
        odds_egw=dict(a=1.37, b=2.96, url="https://egamersworld.com/counterstrike/event/thunderpick-world-championship-2026-5X5sFiL7H",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP),
        pm=None,
    ),
    "hs-1079624": dict(
        odds_egw=None,
        odds_egw_note="Not present in the EGamersWorld 'Bets on' module at capture time.",
        egw_url="https://egamersworld.com/counterstrike/event/cct-europe-2026-series-11-_rW8GEyWK",
        pm=dict(prices=[95, 12], url="https://polymarket.com/esports/cs2/cct-europe/cs2-forzer-skr2-2026-10-14",
                volume="$0.00", note="Polymarket lists the same slot as FORZE Reload vs Sokerorg, not LFO 10. Not used for the line - see flagged list.",
                usable=False),
    ),
    "hs-1080279": dict(
        odds_egw=dict(a=2.0, b=1.72, url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP,
                      note="Fixture listed as WBT vs EA Copenhagen. The EGW match page later showed 1.8/1.8 (looks like a placeholder)."),
        pm=dict(prices=[49, 52], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-wbt-eac-2026-10-15",
                volume="$0.00", note="Headline 49c/52c; detail list showed 56c/59c (wide spread); $0 volume."),
    ),
    "hs-1079440": dict(
        odds_egw=dict(a=1.64, b=2.2, url="https://egamersworld.com/counterstrike/event/stake-pulse-beat-iii-EJZmJpBjeNx",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP),
        pm=None,
    ),
    "hs-1079442": dict(
        odds_egw=dict(a=1.48, b=2.58, url="https://egamersworld.com/counterstrike/event/stake-pulse-beat-iii-EJZmJpBjeNx",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP),
        pm=None,
    ),
    "hs-1080280": dict(
        odds_egw=dict(a=1.3, b=3.2, url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP),
        pm=dict(prices=[64, 36], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-ence-bojong-2026-10-15",
                volume="$0.00", note="Headline 64c/36c; detail list showed 75c/47c (wide spread); $0 volume."),
    ),
    "hs-1080281": dict(
        odds_egw=dict(a=1.62, b=2.15, url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP,
                      note="Fixture listed as WBT vs ENCE. The EGW match page showed 1.8/1.8 (placeholder)."),
        pm=dict(prices=[57, 43], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-wbt-ence-2026-10-15",
                volume="$0.00", note="Headline 57c/43c; detail list showed 62c/48c; $0 volume."),
    ),
    "hs-1080282": dict(
        odds_egw=dict(a=1.2, b=4.0, url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP,
                      note="Fixture listed as EA Copenhagen vs BOJONG."),
        pm=dict(prices=[86, 46], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-eac-bojong-2026-10-15",
                volume="$304.98", note="Detail list 86c/46c (sum 132 -> very wide spread)."),
    ),
    "hs-1080283": dict(
        odds_egw=dict(a=1.2, b=4.0, url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
                      book="bc.game (via EGamersWorld)", captured=EGW_CAP,
                      note="Fixture listed as WBT vs BOJONG."),
        pm=dict(prices=[87, 48], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-wbt-bojong-2026-10-15",
                volume="$0.00", note="Detail list 87c/48c (sum 135 -> very wide spread); $0 volume."),
    ),
    "hs-1080284": dict(
        odds_egw=None,
        odds_egw_note="Not present in the EGamersWorld 'Bets on' module at capture time (later fixtures listed as schedule only).",
        egw_url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
        pm=dict(prices=[71, 46], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-eac-ence-2026-10-15",
                volume="$3.08", note="Detail list 71c/46c (sum 117); headline 71c/46c."),
    ),
    "hs-1080285": dict(
        odds_egw=None,
        odds_egw_note="Not captured (Group B fixtures were schedule-only on the EGW event page at capture time).",
        egw_url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
        pm=dict(prices=[47, 54], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-voc-pha-2026-10-16",
                volume="$0.00", note="Headline 47c/54c (sum 101)."),
    ),
    "hs-1080286": dict(
        odds_egw=None,
        odds_egw_note="Not captured on the event page; the EGW match page displayed 1.8/1.8 which looks like a placeholder and is not used.",
        egw_url="https://egamersworld.com/counterstrike/match/4yn491uUVl/havu-vs-rounds-rg48QwsiJ9",
        pm=dict(prices=[83, 46], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-havu-rgg-2026-10-16",
                volume="$0.00", note="Detail list 83c/46c (sum 129 -> very wide spread); $0 volume."),
    ),
    "hs-1080287": dict(
        odds_egw=None,
        odds_egw_note="Not captured (Group B fixtures were schedule-only on the EGW event page at capture time).",
        egw_url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
        pm=dict(prices=[74, 37], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-voc-havu-2026-10-16",
                volume="$0.00", note="Detail list 74c/37c (sum 111)."),
    ),
    "hs-1080288": dict(
        odds_egw=None,
        odds_egw_note="Not captured (Group B fixtures were schedule-only on the EGW event page at capture time).",
        egw_url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
        pm=dict(prices=[93, 46], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-pha-rgg-2026-10-16",
                volume="$0.00", note="Detail list 93c/46c (sum 139 -> very wide spread); $0 volume."),
    ),
    "hs-1080289": dict(
        odds_egw=None,
        odds_egw_note="Not captured (Group B fixtures were schedule-only on the EGW event page at capture time).",
        egw_url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
        pm=dict(prices=[47, 91], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-voc-rgg-2026-10-16",
                volume="$0.00", note="Polymarket lists Voca vs RoundsGG (Voca priced 91c, RoundsGG 47c). Hotspawn lists the fixture as RoundsGG vs Voca, so team order differs - prices mapped by team name, not position.",
                reversed=True),
    ),
    "hs-1080290": dict(
        odds_egw=None,
        odds_egw_note="Not captured (Group B fixtures were schedule-only on the EGW event page at capture time).",
        egw_url="https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl",
        pm=dict(prices=[79, 46], url="https://polymarket.com/esports/cs2/elisa-breakout/cs2-pha-havu-2026-10-16",
                volume="$0.00", note="Detail list 79c/46c (sum 125 -> very wide spread); $0 volume."),
    ),
}

# --------------------------------------------------------------------------
# 3. Tournament pool as listed by the Pick'em filter (context; 85-86 entries)
# --------------------------------------------------------------------------
TOURNAMENTS = [
    ("CCT Europe 2026 Challengers #4", 8, "https://www.hltv.org/events/9441/cct-2026-europe-series-11-closed-qualifier",
     "Matches in this filter group were not open for picks in the captured lobby window."),
    ("CCT Europe 2026 Series #11", 4, "https://www.hltv.org/events/9442/cct-2026-europe-series-11", "4 open matches covered."),
    ("CCT South America 2026 Series #3", 8, "https://egamersworld.com/counterstrike/event/cct-south-america-2026-series-7-0U32SId-H",
     "EGW's live index shows 'CCT South America 2026 Series #7' running; the Pick'em filter counted 8 entries for Series #3. Not resolved."),
    ("DACH CS Masters Season 5", 1, "https://polymarket.com/esports/cs2/dach-cs-masters", "Not open for picks at capture; Polymarket lists 4 markets."),
    ("DraculaN Season 7", 6, "https://polymarket.com/esports/cs2/draculan", "Not open for picks at capture; Polymarket lists 8 markets."),
    ("Elisa BreakOut Series #2", 12, "https://www.hltv.org/events/9332/elisa-breakout-series-2", "12 open matches covered (8 captured in the lobby text, 12 in the filter count)."),
    ("ESL Challenger League Season 52: North America - Cup #3", 1, "https://www.hltv.org/matches?event=2635", "1 open match covered."),
    ("ESL Challenger League Season 52: South America - Cup #3", 1, "https://www.hltv.org/matches?event=2635", "1 open match covered."),
    ("European Pro League Series 8", 1, None, "Not open for picks at capture; no source page captured."),
    ("European Pro League Series 8 Play-In", 6, None, "Not open for picks at capture; no source page captured."),
    ("LG UltraGear Tournament 2026", 1, None, "Not open for picks at capture; no source page captured."),
    ("Rainhas do Clutch 2026", 2, None, "Not open for picks at capture; no source page captured."),
    ("Stake Pulse Beat III", 4, "https://www.hltv.org/events/9223/stake-pulse-beat-iii", "4 open matches covered."),
    ("Svenska CS-Ligan 2026", 6, None, "Not open for picks at capture; no source page captured."),
    ("Thunderpick World Championship 2026", 4, "https://www.hltv.org/events/8932/thunderpick-world-championship-2026", "4 open matches covered."),
    ("Thunderpick World Championship 2026: South American Series #1", 8, None, "Not open for picks at capture; no source page captured."),
    ("Urban Riga Open #5", 12, None, "Not open for picks at capture; no source page captured."),
]

# --------------------------------------------------------------------------
# 4. Flagged items (do not block publication)
# --------------------------------------------------------------------------
FLAGS = [
    dict(title="Two ESL Challenger League rows lack a per-match HLTV page", rows=["hs-1081076", "hs-1079546"],
         detail="HLTV's per-match URLs for ex-Keyd Stars vs Galorys and Zomblers vs Overtake Sector were not captured. Both fixtures were confirmed inside HLTV event 2635 (ESL Challenger League Season 52 Cup 3) and on bo3.gg; EGamersWorld did not list a two-sided line for either at capture time.",
         action="Reviewer: open https://www.hltv.org/matches?event=2635 and add the per-match URLs."),
    dict(title="Hotspawn crowd vs market disagreement (largest gaps)", rows=["hs-1081076", "hs-1079439", "hs-1079440", "hs-1079621"],
         detail="ex-Keyd Stars vs Galorys: crowd 86% ex-Keyd Stars vs Polymarket 33c/68c (market favours Galorys). HOTU vs Fnatic: crowd 91% Fnatic vs bc.game 1.93/1.83 (near coin-flip). MIBR vs BC.Game: crowd 70% BC.Game vs bc.game 1.64/2.20 (market favours MIBR). Gothic vs Lavked: crowd 90% Lavked and bc.game 1.881/1.782 (favours Lavked) vs Polymarket 53c/47c (favours Gothic).",
         action="These are genuine source disagreements, not errors in this dataset. Both numbers are shown with links."),
    dict(title="Team-name aliases between sources", rows=["hs-1080279", "hs-1080281", "hs-1080283", "hs-1080286", "hs-1080288"],
         detail="Hotspawn 'WROTBERRY' occupies the same fixture slots/times as HLTV/Polymarket 'WBT'; Hotspawn 'RoundsGG' corresponds to HLTV 'ROUNDS' and Polymarket 'RoundsGG'; Hotspawn 'EAC' appears on EGW as 'EA Copenhagen' and on Polymarket as 'Esport Academy Copenhagen'. Slot-for-slot correspondence is exact, but no official statement that WROTBERRY is WBT was captured.",
         action="Reviewer: confirm the WROTBERRY / WBT identity before trusting the odds mapping for those 4 fixtures."),
    dict(title="FORZE Reload opponent mismatch in the prediction market", rows=["hs-1079624"],
         detail="Hotspawn and HLTV both list FORZE Reload vs LFO 10 at 2026-10-14 13:00 UTC. Polymarket lists the same slot as 'FORZE Reload vs Sokerorg' (FORZE 95c / opponent 12c). Because the opponent identity does not match, the Polymarket price was NOT used for this row's line.",
         action="Reviewer: confirm whether LFO 10 and Sokerorg are the same roster."),
    dict(title="Fixture team order differs between Hotspawn and HLTV", rows=["hs-1080289"],
         detail="Hotspawn: RoundsGG vs Voca. HLTV: Voca vs ROUNDS. Polymarket: Voca vs RoundsGG. Prices were mapped by team name, not position.",
         action="Reviewer: confirm home/away ordering does not affect the pick'em entry."),
    dict(title="EGamersWorld placeholder-looking odds", rows=["hs-1080286", "hs-1080279", "hs-1080281"],
         detail="Several EGW match pages displayed identical 1.8 / 1.8 decimals for both teams (a pattern consistent with an unset/placeholder line, e.g. HAVU vs Rounds). These values were excluded; only the event-page 'Bets on ... by bc.game' module was used.",
         action="Reviewer: spot-check those EGW match pages."),
    dict(title="Odds move between components and between captures", rows=["hs-1080176", "hs-1080177"],
         detail="9z vs Aurora was displayed as 3.3/1.26 (EGW match page), 3.6/1.27 (EGW event odds module) and 3.8/1.22 (EGW event schedule list). Falcons vs NiP showed 1.23/3.95 and 1.22/3.8. Every captured price in this dataset is a point-in-time snapshot, timestamped 2026-10-13.",
         action="Reviewer: treat all prices as snapshots; re-pull before acting."),
    dict(title="Prediction-market spreads are wide on low-liquidity fixtures", rows=["hs-1080282", "hs-1080283", "hs-1080286", "hs-1080288"],
         detail="Polymarket detail prices on several Elisa BreakOut Group B/A fixtures sum to 125-139 cents, indicating wide bid/ask and near-zero volume. Those prices were normalised before use and are marked low quality.",
         action="Reviewer: prefer the bc.game line where both exist."),
    dict(title="Hotspawn pick percentages tick continuously", rows=[],
         detail="Captured crowd percentages moved between two snapshots 20 minutes apart (e.g. ex-Keyd Stars 83% -> 86%, Falcons 94% -> 89%). All displayed percentages are one snapshot and are never used in any probability.",
         action="None - informational."),
    dict(title="Coverage boundary: locked/completed matches are not in the table", rows=[],
         detail="The lobby's tournament filter counts 85-86 pool entries for the week ('60 matches this week'), while the lobby itself listed 26 open-for-picks fixtures at capture. Matches that had already locked/completed were not enumerated (they cannot be picked any more). Tournament-group counts are reproduced on the Tournaments page.",
         action="Reviewer: say if completed matches should be back-filled as well."),
    dict(title="HLTV betting-analytics pages do not expose numeric odds to this pipeline", rows=["hs-1079438"],
         detail="HLTV's '/betting/analytics/<id>/<slug>' pages render analytics (form, head-to-head, handicap distributions, map stats) but the numeric decimal odds table did not render as machine-readable text (values such as '1.23eOddset' appear to be parsing artefacts). HLTV figures were therefore used for verification/support only, not as a price source.",
         action="None - informational; documented in Methodology."),
    dict(title="League of Legends pick'em tab not covered", rows=[],
         detail="play.hotspawn.com/lol-pickems exists (per sitemap). This dataset covers the CS2 pick'em lobby only.",
         action="Reviewer: say if LoL should be added."),
    dict(title="Pool-size counts differ between renders", rows=[],
         detail="The lobby filter showed 'All tiers (86), B (27), C (55), S (4)' in one render and 'All tiers (85), B (26), C (55), S (4)' minutes later (matches starting drop out of the pool).",
         action="None - informational."),
]

# --------------------------------------------------------------------------
# 5. Source register
# --------------------------------------------------------------------------
SOURCES = [
    ("Hotspawn Play - Pick'em lobby (entry list, crowd %, tier/points, lock times)", HS_LOBBY, "Primary (entries only)"),
    ("Hotspawn Play - CS2 Pick'ems lobby (same pool, CS2 view)", HS_CS2, "Primary (entries only)"),
    ("Hotspawn Play - Thunderpick World Championships tournament hub (8 teams, 14 matches, scoring)", "https://play.hotspawn.com/tournaments/thunderpick-world-championships", "Primary (entries only)"),
    ("Hotspawn Play - sitemap", "https://play.hotspawn.com/sitemap.xml", "Supporting"),
    ("EGamersWorld - CS2 events index", "https://egamersworld.com/counterstrike/events", "Supporting"),
    ("EGamersWorld - Thunderpick World Championship 2026 (bc.game odds module)", "https://egamersworld.com/counterstrike/event/thunderpick-world-championship-2026-5X5sFiL7H", "Market prices"),
    ("EGamersWorld - Stake Pulse Beat III (bc.game odds module)", "https://egamersworld.com/counterstrike/event/stake-pulse-beat-iii-EJZmJpBjeNx", "Market prices"),
    ("EGamersWorld - CCT Europe 2026 Series #11 (bc.game odds module)", "https://egamersworld.com/counterstrike/event/cct-europe-2026-series-11-_rW8GEyWK", "Market prices"),
    ("EGamersWorld - Elisa Esports BreakOut Series 2 (bc.game odds module)", "https://egamersworld.com/counterstrike/event/elisa-esports-breakout-series-2-4yn491uUVl", "Market prices"),
    ("Polymarket - CS2 hub", "https://polymarket.com/esports/cs2", "Market prices"),
    ("Polymarket - Elisa BreakOut markets", "https://polymarket.com/esports/cs2/elisa-breakout", "Market prices"),
    ("Polymarket - CCT Europe markets", "https://polymarket.com/esports/cs2/cct-europe", "Market prices"),
    ("Polymarket - ESL Challenger League markets", "https://polymarket.com/esports/cs2/esl-challenger-league", "Market prices"),
    ("Polymarket - Thunderpick World Championship markets", "https://polymarket.com/esports/cs2/thunderpick-world-championship", "Market prices"),
    ("HLTV - Thunderpick World Championship 2026 (event 8932)", "https://www.hltv.org/events/8932/thunderpick-world-championship-2026", "Verification"),
    ("HLTV - Thunderpick World Championship 2026 matches", "https://www.hltv.org/events/8932/matches", "Verification"),
    ("HLTV - Stake Pulse Beat III (event 9223)", "https://www.hltv.org/events/9223/stake-pulse-beat-iii", "Verification"),
    ("HLTV - Stake Pulse Beat III matches", "https://www.hltv.org/events/9223/matches", "Verification"),
    ("HLTV - CCT 2026 Europe Series 11 (event 9442)", "https://www.hltv.org/events/9442/cct-2026-europe-series-11", "Verification"),
    ("HLTV - CCT 2026 Europe Series 11 matches", "https://www.hltv.org/events/9442/matches", "Verification"),
    ("HLTV - Elisa BreakOut Series 2 (event 9332)", "https://www.hltv.org/events/9332/elisa-breakout-series-2", "Verification"),
    ("HLTV - Elisa BreakOut Series 2 matches", "https://www.hltv.org/events/9332/matches", "Verification"),
    ("HLTV - ESL Challenger League Season 52 Cup 3 (event 2635) listings", "https://www.hltv.org/matches?event=2635", "Verification"),
    ("HLTV - betting analytics, Astralis vs Sashi (worked example)", "https://www.hltv.org/betting/analytics/2399134/astralis-vs-sashi-stake-pulse-beat-iii", "Verification"),
    ("bo3.gg - ex-Keyd Stars vs Galorys (fixture + partial book lines)", "https://bo3.gg/matches/ex-keyd-stats-vs-galorys-cs-13-10-2026", "Verification"),
    ("bo3.gg - CS2 match center", "https://bo3.gg/matches/current", "Verification"),
    ("Liquipedia - Elisa BreakOut Series 2 (format, prize pool, map pool)", "https://liquipedia.net/counterstrike/Elisa/BreakOut_Series/2", "Supporting"),
    ("Pallomeri.net (FI) - Elisa BreakOut Series 2 groups, semi-final/final schedule", "https://esports.pallomeri.net/elisa-breakout-series-2-joukkueet-lohkot-havu-ence/", "Supporting"),
    ("freetips.com - Thunderpick World Championship 2026 outright odds (Aurora 6.30, 9z 14.00)", "https://www.freetips.com/esports/thunderpick-world-championship-2026-tournament-betting-preview-20261011-0008/", "Market prices (outright)"),
]


# --------------------------------------------------------------------------
# Derivation
# --------------------------------------------------------------------------
def devig_two_way(o_a, o_b):
    """Normalise 1/odds so the two implied probabilities sum to 1."""
    ra, rb = 1.0 / o_a, 1.0 / o_b
    s = ra + rb
    return ra / s, rb / s, s


def norm_prices(p_a, p_b):
    s = p_a + p_b
    return p_a / s, p_b / s, s


def fmt_pct(x, nd=1):
    return f"{x * 100:.{nd}f}%" if x is not None else ""


def build_rows():
    rows = []
    for m in MATCHES:
        mk = MARKETS.get(m["id"], {})
        r = dict(m)
        r["sources"] = []

        # --- bookmaker (bc.game via EGamersWorld) ---
        egw = mk.get("odds_egw")
        if egw:
            pa, pb, s = devig_two_way(egw["a"], egw["b"])
            r["book_p_a"], r["book_p_b"] = pa, pb
            r["book_margin_sum"] = s
            r["book_odds"] = f'{egw["a"]} / {egw["b"]}'
            r["book_note"] = egw.get("note")
        else:
            r["book_p_a"] = r["book_p_b"] = None
            r["book_margin_sum"] = None
            r["book_odds"] = None
            r["book_note"] = mk.get("odds_egw_note")

        # --- prediction market (Polymarket) ---
        pm = mk.get("pm")
        r["pm_note"] = None
        if pm and pm.get("usable", True) and pm.get("prices"):
            a, b = pm["prices"]
            if pm.get("reversed"):
                a, b = b, a
            pa, pb, s = norm_prices(a, b)
            r["pm_p_a"], r["pm_p_b"] = pa, pb
            r["pm_sum"] = s
            r["pm_prices"] = f"{a}% / {b}%"
            r["pm_note"] = pm.get("note")
        else:
            r["pm_p_a"] = r["pm_p_b"] = None
            r["pm_sum"] = None
            r["pm_prices"] = None
            if pm:
                r["pm_note"] = pm.get("note")

        # --- our own line: equal-weight consensus of available market sources ---
        parts = [p for p in (r["book_p_a"], r["pm_p_a"]) if p is not None]
        if parts:
            p = sum(parts) / len(parts)
            r["line_p_a"] = p
            r["line_p_b"] = 1 - p
            r["line_fair_a"] = 1 / p
            r["line_fair_b"] = 1 / (1 - p)
            r["line_basis"] = " + ".join(
                (["bc.game via EGamersWorld"] if r["book_p_a"] is not None else [])
                + (["Polymarket"] if r["pm_p_a"] is not None else [])
            )
        else:
            r["line_p_a"] = r["line_p_b"] = None
            r["line_fair_a"] = r["line_fair_b"] = None
            r["line_basis"] = None

        # --- quality badge ---
        q, qn = "n/a", []
        if r["book_margin_sum"]:
            qn.append(f'book margin sum {r["book_margin_sum"]:.3f}')
        if r["pm_sum"]:
            qn.append(f'PM price sum {r["pm_sum"]:.0f}')
        if r["book_p_a"] is not None and r["pm_p_a"] is None:
            q = "Medium"
        elif r["book_p_a"] is not None and r["pm_p_a"] is not None:
            spread = abs(r["book_p_a"] - r["pm_p_a"])
            q = "High" if spread <= 0.08 else ("Medium" if spread <= 0.15 else "Low")
        elif r["pm_p_a"] is not None:
            q = "Low" if (r["pm_sum"] or 0) > 1.12 else "Medium"
        r["quality"] = q
        r["quality_note"] = "; ".join(qn)

        # --- source list ---
        src = [("Hotspawn Pick'em entry", m["hotspawn_url"])]
        if m.get("hltv_match_url"):
            src.append(("HLTV match page", m["hltv_match_url"]))
        elif m.get("hltv_event_url"):
            src.append(("HLTV event listing", m["hltv_event_url"]))
        if m.get("hltv_betting_url"):
            src.append(("HLTV betting analytics", m["hltv_betting_url"]))
        if egw:
            src.append((f'EGamersWorld odds ({egw["book"]})', egw["url"]))
        elif mk.get("egw_url"):
            src.append(("EGamersWorld event page", mk["egw_url"]))
        if pm:
            src.append(("Polymarket market", pm["url"]))
        if m.get("other_match_url"):
            src.append(("bo3.gg fixture", m["other_match_url"]))
        r["sources"] = src
        r["verified"] = bool(r["book_p_a"] is not None or r["pm_p_a"] is not None)
        rows.append(r)
    return rows


def to_json(rows):
    pool = dict(
        snapshot=SNAPSHOT,
        hotspawn_lobby=HS_LOBBY,
        hotspawn_cs2_lobby=HS_CS2,
        method="Line = equal-weight average of de-margined market probabilities captured from bc.game (via EGamersWorld) and Polymarket. Hotspawn crowd percentages are displayed for context only and are never part of the calculation.",
        rows=[{k: v for k, v in r.items() if k not in ("sources",)} for r in rows],
        sources=[{"name": n, "url": u, "role": ro} for n, u, ro in SOURCES],
        tournaments=[{"tournament": t, "pool_entries": c, "source": s, "note": n} for t, c, s, n in TOURNAMENTS],
        flags=[{"title": f["title"], "rows": f["rows"], "detail": f["detail"], "action": f["action"]} for f in FLAGS],
    )
    return pool


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------
CSS = """
:root{--bg:#0f1115;--panel:#171a21;--panel2:#1e222b;--line:#2a2f3a;--txt:#e6e9ef;--mut:#98a2b3;
--acc:#6ea8fe;--ok:#31c48d;--warn:#f5a623;--bad:#f4626b;--tierS:#f5a623;--tierB:#6ea8fe;--tierC:#9aa4b2}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
background:var(--bg);color:var(--txt)}
a{color:var(--acc);text-decoration:none}
a:hover{text-decoration:underline}
header{position:sticky;top:0;z-index:20;background:rgba(15,17,21,.95);border-bottom:1px solid var(--line);
backdrop-filter:blur(6px)}
.wrap{max-width:1400px;margin:0 auto;padding:0 18px}
.brand{display:flex;align-items:center;gap:12px;padding:14px 0}
.brand b{font-size:17px}
.brand span{color:var(--mut);font-size:13px}
nav{display:flex;flex-wrap:wrap;gap:6px;padding-bottom:12px}
nav a{padding:6px 12px;border:1px solid var(--line);border-radius:999px;color:var(--txt);font-size:13.5px}
nav a.on{background:var(--acc);border-color:var(--acc);color:#0b0e13;font-weight:600}
main{padding:24px 0 60px}
h1{font-size:26px;margin:6px 0 6px}
h2{font-size:19px;margin:32px 0 10px}
h3{font-size:16px;margin:22px 0 8px}
p,li{color:#d6dae2}
.mut{color:var(--mut)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:14px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}
.card .n{font-size:24px;font-weight:700}
.card .l{color:var(--mut);font-size:12.5px;text-transform:uppercase;letter-spacing:.04em}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{padding:8px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{position:sticky;top:98px;background:var(--panel2);z-index:10;font-size:12.5px;color:#cfd6e4;text-transform:uppercase;letter-spacing:.03em}
tr:hover td{background:#1b1f27}
.tag{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11.5px;border:1px solid var(--line);color:var(--mut)}
.tS{color:var(--tierS);border-color:#5a4415}.tB{color:var(--tierB);border-color:#26456f}.tC{color:var(--tierC)}
.good{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.bar{position:relative;height:18px;background:#242833;border-radius:5px;overflow:hidden;min-width:110px}
.bar i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#3d6fd6,#6ea8fe)}
.bar b{position:absolute;right:6px;top:0;font-size:11.5px;line-height:18px;color:#eef2f8}
.bar.ghost i{background:#39404e}
input[type=search],select{background:var(--panel2);border:1px solid var(--line);color:var(--txt);
border-radius:8px;padding:7px 10px;font-size:13.5px}
.tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:14px 0}
.legend{font-size:12.5px;color:var(--mut)}
footer{border-top:1px solid var(--line);color:var(--mut);font-size:12.5px;padding:18px 0 40px}
table.scroll{display:block;overflow-x:auto;white-space:nowrap}
table.scroll td,table.scroll th{white-space:normal}
.nowrap{white-space:nowrap}
.flag{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:10px;padding:14px;margin:12px 0}
.flag h3{margin:0 0 6px}
.small{font-size:12.5px}
code{background:#20242e;padding:1px 5px;border-radius:5px;font-size:12.5px}
"""

NAV = [
    ("index.html", "Dashboard"),
    ("matches.html", "All matches"),
    ("events.html", "By tournament"),
    ("analysis.html", "Analysis"),
    ("methodology.html", "Methodology"),
    ("flagged.html", "Flagged for review"),
    ("sources.html", "Sources"),
]


def page(title, subtitle, body, active):
    nav = "".join(
        f'<a class="{"on" if f == active else ""}" href="{f}">{n}</a>' for f, n in NAV
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - Hotspawn Pick'em line reconstruction</title>
<link rel="stylesheet" href="assets/style.css">
</head><body>
<header><div class="wrap">
<div class="brand"><b>Hotspawn Pick'em &rarr; independent betting lines</b>
<span>CS2 &middot; snapshot {SNAPSHOT}</span></div>
<nav>{nav}</nav>
</div></header>
<main><div class="wrap">
<h1>{title}</h1>
<p class="mut">{subtitle}</p>
{body}
</div></main>
<footer><div class="wrap">
Data snapshot {SNAPSHOT}. Hotspawn crowd percentages are shown for context only and are never used to
compute a probability. All external prices are point-in-time captures - re-check the linked source before acting.
</div></footer>
</body></html>"""


def bar(p):
    if p is None:
        return '<span class="mut">&mdash;</span>'
    return f'<div class="bar"><i style="width:{p*100:.0f}%"></i><b>{p*100:.1f}%</b></div>'


def quality_tag(q):
    cls = {"High": "good", "Medium": "warn", "Low": "bad"}.get(q, "mut")
    return f'<span class="tag {cls}">{q}</span>' if q != "n/a" else '<span class="tag mut">no line</span>'


def src_links(r):
    return " ".join(f'<a href="{u}" target="_blank" rel="noopener">{n}</a>' for n, u in r["sources"])


def kickoff_label(iso):
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.strftime("%d %b %H:%M UTC")


def render_matches_table(rows, show_event=True, section_class="scroll"):
    head = ["Kickoff", "Match", "Event", "Tier/Pts", "Hotspawn crowd (context only)",
            "bc.game line (via EGW)", "Our line (consensus)", "Quality", "Sources"]
    if not show_event:
        head = [h for h in head if h != "Event"]
    out = [f'<table class="{section_class}"><thead><tr>' + "".join(f"<th>{h}</th>" for h in head) + "</tr></thead><tbody>"]
    for r in rows:
        a, b = r["team_a"], r["team_b"]
        crowd = (f'<div class="small">{a}: {r["pick_pct_a"]}% &middot; {b}: {r["pick_pct_b"]}%</div>'
                 f'<div class="small mut">{r["pick_pct_note"]}</div>')
        book = (f'<div class="small">A {r["book_odds"].split(" / ")[0]} &middot; B {r["book_odds"].split(" / ")[1]}</div>'
                f'<div class="small mut">{fmt_pct(r["book_p_a"])} / {fmt_pct(r["book_p_b"])} (de-margined)</div>'
                if r["book_odds"] else f'<span class="tag">no bc.game line captured</span>')
        line = (f'<div class="small"><b>{fmt_pct(r["line_p_a"])} / {fmt_pct(r["line_p_b"])}</b></div>'
                f'<div class="small mut">fair odds {r["line_fair_a"]:.2f} / {r["line_fair_b"]:.2f}</div>'
                f'<div class="small mut">basis: {r["line_basis"]}</div>'
                if r["line_p_a"] is not None else
                '<span class="tag bad">no line &mdash; flagged</span>')
        cells = [
            f'<td class="nowrap">{kickoff_label(r["kickoff_utc"])}<div class="small mut">{r["fmt"]}</div></td>',
            f'<td class="nowrap"><b>{a}</b> vs <b>{b}</b>'
            + (f'<div class="small mut">{r["alias_note"]}</div>' if r.get("alias_note") else "")
            + (f'<div class="small">{bar(r["line_p_a"])}</div>' if r["line_p_a"] is not None else "")
            + "</td>",
        ]
        if show_event:
            cells.append(f'<td class="small">{r["event"]}<div class="mut">{r["section"]}</div></td>')
        cells += [
            f'<td class="nowrap"><span class="tag t{r["tier"]}">{r["tier"]}</span> {r["points"]} pts'
            f'<div class="small mut">multiplier x1.25</div></td>',
            f"<td>{crowd}</td>",
            f"<td>{book}</td>",
            f"<td>{line}</td>",
            f'<td class="nowrap">{quality_tag(r["quality"])}<div class="small mut">{r["quality_note"]}</div></td>',
            f'<td class="small">{src_links(r)}</td>',
        ]
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def build_site(rows, pool):
    os.makedirs(os.path.join(DOCS, "assets"), exist_ok=True)
    os.makedirs(os.path.join(DOCS, "assets", "data"), exist_ok=True)
    with open(os.path.join(DOCS, "assets", "style.css"), "w") as f:
        f.write(CSS)
    with open(os.path.join(DOCS, ".nojekyll"), "w") as f:
        f.write("")
    with open(os.path.join(DOCS, "assets", "data", "pool.json"), "w") as f:
        json.dump(pool, f, indent=1)

    n_total = len(rows)
    n_book = sum(1 for r in rows if r["book_p_a"] is not None)
    n_pm = sum(1 for r in rows if r["pm_p_a"] is not None)
    n_line = sum(1 for r in rows if r["line_p_a"] is not None)
    n_blank = n_total - n_line
    n_flags = len(FLAGS)

    # ---------------- dashboard ----------------
    soon = sorted(rows, key=lambda r: r["kickoff_utc"])[:6]
    tiers = {t: sum(1 for r in rows if r["tier"] == t) for t in ("S", "B", "C")}
    body = f"""
<div class="cards">
  <div class="card"><div class="n">{n_total}</div><div class="l">Pick'em fixtures covered</div>
    <div class="small mut">open for picks at snapshot</div></div>
  <div class="card"><div class="n">{n_line}</div><div class="l">Rows with our own line</div>
    <div class="small mut">{n_blank} row(s) left blank + flagged</div></div>
  <div class="card"><div class="n">{n_book}</div><div class="l">bc.game lines via EGamersWorld</div>
    <div class="small mut">bookmaker prices used</div></div>
  <div class="card"><div class="n">{n_pm}</div><div class="l">Polymarket markets matched</div>
    <div class="small mut">independent cross-check</div></div>
  <div class="card"><div class="n">{n_flags}</div><div class="l">Flagged items</div>
    <div class="small mut">published for review</div></div>
</div>
<div class="panel">
<h3 style="margin-top:0">What this is</h3>
<p>Every CS2 fixture that was open for picks on the Hotspawn Play Pick'em lobby was captured, matched to an
external betting market, and converted into our own de-margined probability. Nothing on the Hotspawn side is
used as a probability: the crowd "picked" percentage is displayed in its own column and is excluded from every
calculation.</p>
<p class="small mut">Tiers covered: S {tiers['S']} &middot; B {tiers['B']} &middot; C {tiers['C']}. Source snapshot: {SNAPSHOT}.</p>
<p><a href="matches.html">Open the full table &rarr;</a> &nbsp; <a href="flagged.html">Flagged for review &rarr;</a></p>
</div>
<h2>Next up</h2>
{render_matches_table(soon, show_event=True)}
"""
    write(os.path.join(DOCS, "index.html"),
          page("Dashboard", "Independent betting-line reconstruction for the Hotspawn Play CS2 Pick'em lobby.",
               body, "index.html"))

    # ---------------- all matches ----------------
    events = sorted({r["event"] for r in rows})
    opts = "".join(f'<option value="{e}">{e}</option>' for e in events)
    body = f"""
<div class="tools">
  <input type="search" id="q" placeholder="Filter team or tournament...">
  <select id="ev"><option value="">All tournaments</option>{opts}</select>
  <select id="tier"><option value="">All tiers</option><option>S</option><option>B</option><option>C</option></select>
  <span class="legend">Tip: click a column header-free row - every row links its own sources.</span>
</div>
{render_matches_table(rows)}
<p class="small mut">"bc.game line (via EGW)" is the price shown in EGamersWorld's
<code>Bets on &lt;event&gt; by bc.game</code> module, converted to a de-margined probability.
"Our line (consensus)" is the equal-weight average of the available de-margined sources (bc.game via EGamersWorld
and/or Polymarket). Rows without any captured external line are left blank and listed on the
<a href="flagged.html">Flagged for review</a> page.</p>
<script src="assets/table.js"></script>
"""
    write(os.path.join(DOCS, "matches.html"),
          page("All matches", f"{n_total} fixtures captured from the Pick'em lobby, newest first.", body, "matches.html"))

    # ---------------- events ----------------
    blocks = []
    for e in events:
        sub = [r for r in rows if r["event"] == e]
        blocks.append(f"<h2>{e} <span class='mut small'>({len(sub)} open fixture(s))</span></h2>")
        blocks.append(render_matches_table(sub, show_event=False))
    def _tlink(s):
        if not s:
            return '<span class="tag">not resolved</span>'
        return '<a href="' + s + '" target="_blank" rel="noopener">source</a>'

    trows = "".join(
        "<tr><td>" + t + "</td><td>" + str(c) + "</td><td>" + _tlink(s)
        + '</td><td class="small mut">' + n + "</td></tr>"
        for t, c, s, n in TOURNAMENTS)
    body = ("<div class='panel'><h3 style='margin-top:0'>Tournament pool as counted by the Pick'em filter</h3>"
            "<p class='small mut'>The lobby filter counted 85-86 pool entries for the week while 26 fixtures were open "
            "for picks. Counts below are reproduced exactly as displayed.</p>"
            "<table><thead><tr><th>Tournament</th><th>Pool entries</th><th>Verification source</th><th>Note</th></tr></thead>"
            f"<tbody>{trows}</tbody></table></div>") + "".join(blocks)
    write(os.path.join(DOCS, "events.html"),
          page("By tournament", "The same rows grouped by event, plus the full tournament pool counts.", body, "events.html"))

    # ---------------- analysis ----------------
    gaps = []
    for r in rows:
        if r["book_p_a"] is not None and r["pm_p_a"] is not None:
            gaps.append((abs(r["book_p_a"] - r["pm_p_a"]), r))
    gaps.sort(reverse=True, key=lambda x: x[0])
    crowd_gaps = []
    for r in rows:
        if r["line_p_a"] is not None:
            crowd_gaps.append((abs(r["line_p_a"] * 100 - r["pick_pct_a"]), r))
    crowd_gaps.sort(reverse=True, key=lambda x: x[0])
    g_rows = "".join(
        f'<tr><td>{r["team_a"]} vs {r["team_b"]}<div class="small mut">{r["event"]}</div></td>'
        f'<td>{fmt_pct(r["book_p_a"])} / {fmt_pct(r["book_p_b"])}</td>'
        f'<td>{fmt_pct(r["pm_p_a"])} / {fmt_pct(r["pm_p_b"])}</td>'
        f'<td class="{"bad" if d > 0.15 else "warn" if d > 0.08 else "good"}">{(d*100):.1f} pts</td>'
        f'<td class="small">{src_links(r)}</td></tr>'
        for d, r in gaps)
    def _link_list(r):
        parts = []
        for n, u in r["sources"]:
            if n.startswith("Hotspawn"):
                continue
            parts.append('<a href="' + u + '" target="_blank" rel="noopener">' + n + "</a>")
        return " ".join(parts)

    c_rows = "".join(
        f'<tr><td>{r["team_a"]} vs {r["team_b"]}<div class="small mut">{r["event"]}</div></td>'
        f'<td>{r["pick_pct_a"]}% / {r["pick_pct_b"]}%</td>'
        f'<td>{fmt_pct(r["line_p_a"], 0)} / {fmt_pct(r["line_p_b"], 0)}</td>'
        f'<td class="{"bad" if d > 20 else "warn" if d > 10 else "good"}">{d:.0f} pts</td>'
        f'<td class="small"><a href="{r["hotspawn_url"]}" target="_blank" rel="noopener">Hotspawn</a> '
        f'{_link_list(r)}</td></tr>'
        for d, r in crowd_gaps[:10])

    fav_count = {}
    for r in rows:
        if r["line_p_a"] is not None:
            fav = r["team_a"] if r["line_p_a"] >= 0.5 else r["team_b"]
            fav_count[fav] = fav_count.get(fav, 0) + 1
    body = f"""
<div class="panel">
<h3 style="margin-top:0">Method in one line</h3>
<p>Our line = <code>normalise(1/odds)</code> for each source, then an equal-weight average across the sources that
published a two-sided price for that fixture. Hotspawn's crowd percentage is deliberately excluded.</p>
</div>
<h2>Where the two markets disagree</h2>
<p class="small mut">Absolute difference between the bc.game (via EGamersWorld) probability and the Polymarket
probability, both de-margined. Wide gaps on low-volume fixtures usually mean a stale or illiquid market, not a
real edge.</p>
<table class="scroll"><thead><tr><th>Fixture</th><th>bc.game via EGW</th><th>Polymarket</th><th>Gap</th><th>Sources</th></tr></thead>
<tbody>{g_rows or '<tr><td colspan="5" class="mut">No fixture has both a bc.game and a Polymarket price.</td></tr>'}</tbody></table>

<h2>Where the crowd disagrees with the market</h2>
<p class="small mut">Difference between the Hotspawn crowd favourite share and our line for team A. This is the
column that shows why the Pick'em leaderboard and the betting market tell different stories. Crowd numbers are
context only and are not part of the line.</p>
<table class="scroll"><thead><tr><th>Fixture</th><th>Hotspawn crowd</th><th>Our line</th><th>Gap</th><th>Sources</th></tr></thead>
<tbody>{c_rows or '<tr><td colspan="5" class="mut">Not enough data.</td></tr>'}</tbody></table>

<h2>Structural findings</h2>
<ul>
<li><b>Coverage is uneven by tier.</b> All four Tier S Thunderpick fixtures carry a bc.game line (three of the
four also have a Polymarket market). The six Tier C Elisa BreakOut <i>Group B</i> fixtures rely on Polymarket
only, all with $0 volume, and are marked Low quality; Group A has a bc.game line for five of its six fixtures.
15 of 26 rows in total carry a bc.game line and 20 carry a Polymarket market.</li>
<li><b>The 8:00 pm ESL Challenger League final is a live example of crowd-vs-market divergence.</b> The crowd is
86% on ex-Keyd Stars while the prediction market prices Galorys at 68c; the bc.game line for that fixture was not
captured, so the row carries only the prediction-market line and is flagged.</li>
<li><b>Naming differences are systematic, not one-off.</b> Hotspawn uses WROTBERRY/RoundsGG/EAC where HLTV writes
WBT/ROUNDS/EAC and Polymarket writes WBT/RoundsGG/Esport Academy Copenhagen. Fixture slots and kickoff times line
up exactly, but the identity mapping is flagged for human confirmation.</li>
<li><b>Odds drift within a single page.</b> EGamersWorld displayed 3.6/1.27 for 9z vs Aurora in its odds module and
3.8/1.22 in the schedule list of the same page. Both are recorded; only one is used in the derivation.</li>
<li><b>De-margining matters in Tier C.</b> On the most liquid fixtures the book margin is under 5%, so the
difference between raw and de-margined probability is small; on thin markets the raw and de-margined numbers can
move by several points, which is why the raw method is documented on the Methodology page.</li>
</ul>
"""
    write(os.path.join(DOCS, "analysis.html"),
          page("Analysis", "How the two markets compare, where the crowd diverges, and what the data cannot tell us.",
               body, "analysis.html"))

    # ---------------- methodology ----------------
    body = """
<h2>Pipeline</h2>
<ol>
<li><b>Enumerate.</b> The Pick'em lobby (<a href="https://play.hotspawn.com/lobby" target="_blank" rel="noopener">play.hotspawn.com/lobby</a>
and <a href="https://play.hotspawn.com/cs2-pickems" target="_blank" rel="noopener">/cs2-pickems</a>) was read at
three points in time. Every fixture that was open for picks was recorded with its tournament, tier, points,
kickoff (UTC), both team names and the crowd percentages.</li>
<li><b>Verify the fixture.</b> Each fixture was matched to an HLTV match page (kickoff, format, both team names).
Where no HLTV match URL exists yet, the HLTV event listing and a second independent site (bo3.gg) are cited
instead, and the gap is flagged.</li>
<li><b>Capture external prices.</b> Two independent markets are used:
  <ul>
   <li><b>Bookmaker:</b> EGamersWorld's <code>Bets on &lt;event&gt; by bc.game</code> module on each event page
   (every EGamersWorld odds module states the bookmaker it prices).</li>
   <li><b>Prediction market:</b> Polymarket CS2 markets for the same fixture.</li>
  </ul></li>
<li><b>De-margin.</b> For a two-way market with prices <code>o1</code>, <code>o2</code>:
<code>p_i = (1/o_i) / (1/o_1 + 1/o_2)</code>. Prediction-market prices are normalised the same way
<code>p_i = c_i / (c_1 + c_2)</code>, which removes the bid/ask spread.</li>
<li><b>Our line.</b> Equal-weight average of the de-margined probabilities from the sources captured for that
fixture. Fair odds are <code>1/p</code>. Where no external two-sided price was captured the row is left blank and
flagged - no value is guessed.</li>
</ol>

<h2>What is deliberately NOT used</h2>
<ul>
<li><b>Hotspawn crowd percentages.</b> They are displayed in their own column, labelled "context only", and are
excluded from every calculation. They are a measure of what other players did, not of the match.</li>
<li><b>Model/AI win probabilities</b> (for example bo3.gg's "prediction" percentages). They are not market
prices and are not used for the line.</li>
<li><b>Unsourced inference.</b> If a value was not captured with a link, the cell is empty and the item appears on
the <a href="flagged.html">Flagged for review</a> page.</li>
</ul>

<h2>Why the numbers will move</h2>
<p>Prices are point-in-time. Two things were observed inside the capture window: (1) the captured decimals changed
between page components and between fetches, and (2) the market sum (overround) differs by fixture, from roughly
1.02 on liquid Tier S matches to ~1.35 on empty Tier C prediction markets. Every row therefore carries a quality
badge derived from the captured spread, and the capture date is stated in the header of every page.</p>

<h2>Reproducing this build</h2>
<p>The entire site is generated from <code>scripts/build.py</code>, which holds the captured values next to the URL
they came from. <code>python3 scripts/build.py</code> regenerates <code>data/*.json</code> and
<code>docs/**</code>. Data files: <a href="assets/data/pool.json">pool.json</a>.</p>
"""
    write(os.path.join(DOCS, "methodology.html"),
          page("Methodology", "Exactly how each number was produced, and what was excluded.",
               body, "methodology.html"))

    # ---------------- flagged ----------------
    fblocks = []
    for f in FLAGS:
        rows_txt = ""
        if f["rows"]:
            labels = []
            for rid in f["rows"]:
                m = next((r for r in rows if r["id"] == rid), None)
                if m:
                    labels.append(f'<a href="{m["hotspawn_url"]}" target="_blank" rel="noopener">{m["team_a"]} vs {m["team_b"]}</a>')
            rows_txt = f'<div class="small mut">Rows: {" &middot; ".join(labels)}</div>'
        fblocks.append(f'<div class="flag"><h3>{f["title"]}</h3><p>{f["detail"]}</p>{rows_txt}'
                       f'<p class="small"><b>Reviewer action:</b> {f["action"]}</p></div>')
    body = ("<p>Nothing below blocks publication of the dataset; everything here is either a value that was left "
            "blank because it could not be confirmed from a source, or a known disagreement between two official "
            "sources.</p>" + "".join(fblocks))
    write(os.path.join(DOCS, "flagged.html"),
          page("Flagged for review", f"{len(FLAGS)} items, each with the source link needed to resolve it.",
               body, "flagged.html"))

    # ---------------- sources ----------------
    srows = "".join(
        f'<tr><td><a href="{u}" target="_blank" rel="noopener">{n}</a></td><td class="small mut">{ro}</td></tr>'
        for n, u, ro in SOURCES)
    used = "".join(
        f'<tr><td>{r["team_a"]} vs {r["team_b"]}</td><td class="small">{src_links(r)}</td></tr>' for r in rows)
    body = (f"""<h2>Source register</h2>
<table><thead><tr><th>Source</th><th>Role</th></tr></thead><tbody>{srows}</tbody></table>
<h2>Per-row sources</h2>
<p class="small mut">Every fixture row in the dataset with the exact links that back it.</p>
<table class="scroll"><thead><tr><th>Fixture</th><th>Sources</th></tr></thead><tbody>{used}</tbody></table>""")
    write(os.path.join(DOCS, "sources.html"),
          page("Sources", "Every link used by this dataset, plus the per-row citation list.", body, "sources.html"))

    # table.js for the filter tools
    write(os.path.join(DOCS, "assets", "table.js"), """
(function(){
  var q=document.getElementById('q'), ev=document.getElementById('ev'), tier=document.getElementById('tier');
  if(!document.querySelector('table')) return;
  var rows=[].slice.call(document.querySelectorAll('table tbody tr'));
  function apply(){
    var s=(q&&q.value||'').toLowerCase(), e=ev&&ev.value||'', t=tier&&tier.value||'';
    rows.forEach(function(tr){
      var txt=tr.innerText.toLowerCase();
      var okS=!s||txt.indexOf(s)>=0;
      var okE=!e||txt.indexOf(e.toLowerCase())>=0;
      var okT=!t||txt.indexOf(' '+t.toLowerCase()+' ')>=0||txt.indexOf(t.toLowerCase()+' pts')>=0;
      tr.style.display=(okS&&okE&&okT)?'':'none';
    });
  }
  [q,ev,tier].forEach(function(el){ if(el) el.addEventListener('input',apply); });
})();
""")


def write(path, content):
    with open(path, "w") as f:
        f.write(content)


def main():
    rows = build_rows()
    pool = to_json(rows)
    os.makedirs(DATA, exist_ok=True)
    write(os.path.join(DATA, "pickem_pool.json"), json.dumps(pool, indent=1))
    write(os.path.join(DATA, "keys.json"), json.dumps({
        "snapshot": SNAPSHOT,
        "pipeline": "Hotspawn lobby (entries) -> HLTV (fixture verification) -> EGamersWorld bc.game module + Polymarket (prices) -> de-margin -> consensus line",
        "row_fields": {
            "book_odds": "decimal odds as displayed, team A / team B (bc.game via EGamersWorld)",
            "book_p_a/book_p_b": "de-margined probability from the bookmaker line",
            "pm_prices": "Polymarket displayed cents for team A / team B",
            "pm_p_a/pm_p_b": "normalised prediction-market probability",
            "line_p_a/line_p_b": "our line: equal-weight average of available de-margined sources",
            "line_fair_a/line_fair_b": "1 / line_p (fair decimal odds)",
            "quality": "High/Medium/Low from captured spread and liquidity",
            "verified": "true only when at least one external two-sided price was captured",
        },
    }, indent=1))
    build_site(rows, pool)
    n_line = sum(1 for r in rows if r["line_p_a"] is not None)
    print(f"rows={len(rows)} with_line={n_line} without_line={len(rows)-n_line}")


if __name__ == "__main__":
    main()
