# T5 — Verification pass (2026-10-13)

Scope: every table row on the GitHub Pages site links an official source; unconfirmed values are
blank and flagged "unverified"; nothing was inferred or filled.

## Automated checks (all passed)

1. `python3 tools/build_site.py` — generator asserts per row:
   - `hotspawn_url` present and `https://` (257/257 rows);
   - priced rows have an external odds `source_url` and both derived probabilities (28/28);
   - unpriced rows have **empty** probability cells and `status=unverified` (229/229) — a
     forbidden fill aborts the build;
   - all four pages non-trivial and contain per-row Hotspawn source links.
2. Independent audit script (same criteria, run against the CSVs post-build): 257 rows audited,
   0 failures; derived probabilities sum to 100.0% ± 0.2 on all 28 priced rows.
3. HTML parse check (`html.parser`) on index/cs2/lol/flagged: no unclosed/mismatched tags;
   0 missing local links; 329 external source links total (57 on cs2.html, 243 on lol.html,
   22 on index.html, 7 on flagged.html).
4. Site cross-check: every priced row's odds source URL appears verbatim in its category page.

## Manual spot-checks against live sources (performed during T1–T3 capture)

| Row | Checked against | Result |
|---|---|---|
| 257-row inventory IDs/URLs | play.hotspawn.com SSR pages + www.hotspawn.com wp-json fixtures + www.hotspawn.com/matches | consistent (chunk-boundary card 1071218 reconstructed via REST, flagged) |
| ET→UTC rule (+4h until 2026-10-31, +5h after DST end) | www.hotspawn.com/matches UTC feed (1079009, 1081076); EGW JSON-LD start dates (Zomblers vs Overtake Sector `2026-10-14T01:00:00Z`; Mental Rush vs SK Avarosa `2026-10-19T16:00:00Z`); HLTV TWC page (Falcons-NiP 11:00 UTC) | rule holds on every sample |
| Falcons vs NiP (1080177) | HLTV match page + EGW event page + EGW blog schedule | pairing/time/odds 1.23/3.95 (BC.GAME panel) confirmed |
| ex-Keyd Stars vs Galorys (1081076) | EGW match page widget + EGWxxxBOT aggregate (1.464/2.508) | 2.43/1.46 confirmed; line moved from 2.366/1.53 earlier in the day (noted) |
| KT Rolster vs BNK FearX (1076650) | EGW match/tips pages + Polymarket moneyline (KT 65c/BNK 36c) + kentucky.com bracket report | date 2026-10-14 05:00 ET confirmed by all; format conflict (Bo1 vs Bo5) flagged, not filled |
| Cloud9 vs Karmine Corp (1075808) | EGW widget 2.71/1.41; GG.bet 2.41/1.54 on tips.gg and win.gg | both sources recorded as primary/secondary |
| Elisa BreakOut 12 rows | EGW event page GG.BET panel, team aliases (WBT=WROTBERRY, EA Copenhagen=EAC, Rounds=RoundsGG) | all 12 mapped 1:1 to CSV IDs, build script asserts names |
| Unpriced rows 1079622/1079624/1076025/1076026 | EGW event/match pages (1.8/1.8 placeholder, no "Bets by" panel) | confirmed no market → blank + unverified |

## No-fill rule audit

- 229 rows without external lines: probability cells empty in `data/probabilities.csv`,
  "no market published" + `unverified` badge on the site (2 in cs2.html, 227 in lol.html).
- Community pick percentages never enter `data/probabilities.csv`; they appear only in a
  column explicitly labeled "context only".
- De-vig method documented in `data/analysis.md` and on the dashboard; every probability cell
  on the site shows the exact odds it was derived from.

## Known residual risks (do not block merge; listed on Flagged page)

- Odds snapshots move; `data/odds.csv` holds one capture per match (2026-10-13) with earlier
  same-day captures noted where applicable.
- Minor-league LoL has zero bookmaker coverage anywhere reachable; probabilities remain blank
  by design (irregularities.md item 10).
