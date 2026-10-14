# Independent verification — session 7cd2e67a

Generated 2026-10-14T02:15:51Z. Task INT-1 independent line-by-line verification of the published boards.

Every check below names the official source it was read from and the UTC time it was read.
A value that could not be confirmed is published as a flag, never filled in.

## Checks

| ID | Check | Scope | Rows | Result |
|---|---|---|---|---|
| V1 | Root board: every published no-vig probability re-derived from its quoted odds | data/lines.json | 10 | **pass** |
| V2 | Live board: every market probability re-derived from its quoted odds | data/live/board.json | 16 | **pass_with_note** |
| V3 | Live board: pick side, pick team and edge re-derived | data/live/board.json | 123 | **pass** |
| V4 | Originated-estimate ratings are real rows of Valve's official standings | data/live/board.json vs ValveSoftware/counter-strike_regional_standings | 214 | **pass** |
| V5 | Blank rows for a missing rating are flagged, never estimated | data/live/board.json | 351 | **flag** |
| V6 | Every per-row HotSpawn link is an official URL HotSawn publishes | data/lines.json, data/live/board.json, data/expanded/lines.json | 51 | **repaired** |
| V7 | Committed lobby snapshot cross-checked against an independent re-read | data/hotspawn_matches.json vs play.hotspawn.com/lobby | 89 | **flag** |

## Arithmetic

- Root board: 10 priced rows, 0 mismatches.
- Live board: 16 market rows, 107 originated-estimate rows, 351 blank rows, 1 mismatches.
- Valve ratings: 214 team ratings checked against 349 distinct team names, 0 mismatches, 37 ambiguous duplicate team names.
- Blank rows missing a flag: 1.

## External source observations

| ID | Source | URL | Read (UTC) | Status | Observation |
|---|---|---|---|---|---|
| OBS-01 | HotSpawn Pick'ems lobby | https://play.hotspawn.com/lobby | 2026-10-14T01:47:00Z | ok | Served lobby page. Its own counters read: "This week 68 matches this week", "All tiers (89)", "B (25)", "C (60)", "S (4)", "All tournaments (89)". 28 match cards rendered (13 under Closing Soon, 15 under Upcoming). |
| OBS-02 | HotSpawn numeric match route | https://www.hotspawn.com/matches/1079546 | 2026-10-14T01:50:00Z | fail | Final URL https://www.hotspawn.com/matches, page title "Matches - Hotspawn": the general matches index, not the Zomblers vs Overtake Sector match page. |
| OBS-03 | HotSpawn matches listing | https://www.hotspawn.com/matches | 2026-10-14T01:55:00Z | ok | Official listing page publishes per-match permalinks of the form /matches/<team-a>-vs-<team-b>-<tournament>-<fixture id>, e.g. https://www.hotspawn.com/matches/gothic-vs-lavked-cct-europe-2026-series-11-1079621. |
| OBS-04 | Pinnacle guest API | https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638111785/markets/related/straight | 2026-10-14T01:58:00Z | ok | matchup 1638111785 (9z vs Aurora), cutoff 2026-10-14T08:30Z: full-match moneyline `s;0;m` status open, home +241 / away -307 (decimal 3.41 / 1.3257). Verdict: line moved since the published read; no-vig p(9z) 28.0% / p(Aurora) 72.0% today versus 26.9% / 73.1% published. The pick (Aurora) is unchanged. |
| OBS-05 | Pinnacle guest API | https://guest.api.arcadia.pinnacle.com/0.1/matchups/1637867148/markets/related/straight | 2026-10-14T01:58:00Z | ok | matchup 1637867148 (HOTU vs Fnatic), cutoff 2026-10-14T10:00Z: full-match moneyline `s;0;m` status open, home -101 / away -125 (decimal 1.9901 / 1.8). Verdict: exact match with the published quote; no-vig 47.5% / 52.5% reproduces. |
| OBS-06 | Pinnacle guest API | https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638111674/markets/related/straight | 2026-10-14T02:00:00Z | changed | matchup 1638111674 (Falcons vs Ninjas in Pyjamas), cutoff 2026-10-14T11:00Z: no `period: 0` moneyline is present in the response. The first moneyline is `s;1;m` (map 1, home -243 / away +195); only per-map markets remain. Verdict: the full-match market the published row cites is no longer offered, so that row is stale. Flagged, not silently refreshed. |
| OBS-07 | Pinnacle guest API | https://guest.api.arcadia.pinnacle.com/0.1/matchups/1637936745/markets/related/straight | 2026-10-14T02:00:00Z | changed | matchup 1637936745 (MIBR vs BC.Game), cutoff 2026-10-15T10:00Z: no `period: 0` moneyline is present. First moneyline is `s;1;m` (map 1, home -122 / away -103). Verdict: the cited full-match market is no longer offered; the published row is stale. |
| OBS-08 | Pinnacle guest API | https://guest.api.arcadia.pinnacle.com/0.1/matchups/1637999450/markets/related/straight | 2026-10-14T02:05:00Z | changed | matchup 1637999450 (Heroic vs Envy), cutoff 2026-10-15T10:00Z: no `period: 0` moneyline is present. First moneyline is `s;1;m` (map 1, home -137 / away +109). Verdict: the cited full-match market is no longer offered; the published row is stale. |
| OBS-09 | Bovada quote API | https://www.bovada.lv/services/sports/event/v2/events/A/description/esports | 2026-10-14T02:08:00Z | ok | Served the esports event feed as JSON with live events and two-way moneyline prices (e.g. Cloud9 vs Karmine Corp +170 / -225). |
| OBS-10 | Bovada event page | https://www.bovada.lv/esports/counter-strike-2/pulse-beat-iii/astralis-sashi-esport-202610140600 | 2026-10-14T02:08:00Z | fail | HTTP 200 body is Bovada's "Not Found" page ("PÁGINA NO ENCONTRADA") behind a reCAPTCHA challenge. |
| OBS-11 | Melbet LineFeed (1xBet platform) | https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=4&country=1 | 2026-10-14T02:10:00Z | ok | Served the 1x2 feed as JSON. Its first entry is Gothic vs Lavked (CS 2. CCT Europe Series, start 1791964800 = 2026-10-14T08:00:00Z) with Gothic 1.881 and Lavked 1.782. Verdict: exact match with the published quote. |
| OBS-12 | Valve CS2 Regional Standings (official repository) | https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/2026/standings_global_2026_10_05.md | 2026-10-14T02:15:00Z | ok | File `live/2026/standings_global_2026_10_05.md`, blob sha 2aa2805394fbc68f36a5752a5b16026f2ab2fed5, 77872 bytes, 349 distinct team names (31 of them listed on more than one roster line). Head of the table: 1 Spirit 2046, 2 Legacy 1931, 3 Vitality 1911, 4 MOUZ 1863, 5 G2 1847, 6 Falcons 1843, 7 FURIA 1829, 8 FUT 1799, 9 Aurora 1716, 10 Astralis 1674. |

## Sources

| Name | URL |
|---|---|
| hotspawn_lobby | https://play.hotspawn.com/lobby |
| hotspawn_matches_listing | https://www.hotspawn.com/matches |
| pinnacle_guest_api | https://guest.api.arcadia.pinnacle.com/0.1/matchups/{matchupId}/markets/related/straight |
| bovada_quote_api | https://www.bovada.lv/services/sports/event/v2/events/A/description/esports |
| melbet_linefeed | https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=4&country=1 |
| valve_vrs_repo | https://github.com/ValveSoftware/counter-strike_regional_standings |
| valve_vrs_file | https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/2026/standings_global_2026_10_05.md |
| valve_vrs_file_html | https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md |

## Irregularities flagged for review

- **F-7cd2e67a-01** HotSpawn per-row links were not per-match links: the inherited collectors used `https://www.hotspawn.com/matches/<fixture id>`, which resolves to the general matches index. Repaired to published permalinks or the official lobby page.
- **F-7cd2e67a-02** Three Pinnacle full-match markets (1638111674 Falcons vs NiP, 1637936745 MIBR vs BC.Game, 1637999450 Heroic vs Envy) no longer offer a `period: 0` moneyline; the published rows still cite the withdrawn quotes.
- **F-7cd2e67a-03** Bovada per-event page URLs return a Not Found page behind a reCAPTCHA challenge, while the quote API endpoint answers normally.
- **F-7cd2e67a-04** The lobby inventory moved between the committed snapshot (2026-10-14T01:15:53Z, 90 fixtures, s4/b26/c60) and the independent re-read (2026-10-14T01:47Z, 89 fixtures, s4/b25/c60).
- **F-7cd2e67a-05** 31 team names appear on more than one roster line in Valve's `standings_global_2026_10_05.md`, so the roster line behind an estimate is ambiguous.
- **F-7cd2e67a-06** One blank CS2 row (1052184, Atreides vs Donstu) names only one of its two missing ratings; `Donstu` is absent from every Valve regional standings file.
- **F-7cd2e67a-07** The live board's published consensus averages unrounded per-source probabilities while the per-source values are stored rounded to 4 dp, so a recomputation from the rounded values can differ by 0.01 percentage point.

