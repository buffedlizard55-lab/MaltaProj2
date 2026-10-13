# Data irregularities & capture notes (T1)

Captured: 2026-10-13 (session `arena-1da4b0ef-maltaproj2`)

## Sources for the match inventory (official)
- https://play.hotspawn.com/lobby — pick'em lobby (combined)
- https://play.hotspawn.com/cs2-pickems — CS2 pick'em lobby (all 26 pickable cards harvested)
- https://play.hotspawn.com/lol-pickems — LoL pick'em lobby (all 231 pickable cards harvested, 16 content chunks)
- https://www.hotspawn.com/matches — Hotspawn official match schedule (used to cross-check pairings and times)
- https://www.hotspawn.com/wp-json/wp/v2/fixtures — Hotspawn WordPress REST API (fixture records; used to validate match IDs/permalinks)
- https://www.hotspawn.com/wp-json/fixtures/v1/get?external_id=1081076 — official fixture endpoint (spot-checked: returns matching participants + status "scheduled")

Every row in `data/matches.csv` links its official Hotspawn match page (`hotspawn_url`), which is the source of
record for pairing, tournament, and match ID.

## Timezone note (verified)
- The pick'em lobby renders times in US Eastern (UTC-4 while EDT in effect). Verified against
  https://www.hotspawn.com/matches which labels times in UTC:
  - Match 1079009 (No Need Orga vs Reveal Multigaming): lobby "Oct 13, 14:30" = matches page "18:30 UTC" → lobby = UTC-4. ✔
  - Match 1081076 (ex-Keyd Stars vs Galorys): lobby "Oct 13, 17:00" = matches page "21:00 UTC". ✔
- `start_utc` in data/matches.csv = displayed time + 4h for dates through 2026-10-31, and + 5h from
  2026-11-01 (US DST ends 2026-11-01 02:00 ET; times after that are EST = UTC-5).

## Irregularities found (flagged for review)

1. **Lobby banner vs rendered list.** The CS2 lobby banner says "60 matches this week" and filter widgets
   count 85 tracked CS2 matches (294 for LoL), but only 26 CS2 + 231 LoL match cards are publicly rendered
   as pickable ("Closing Soon" + "Upcoming"). The remainder are presumably locked/graded/TBD-stage and are
   not publicly enumerable without signing in. Inventory = the matches actually listed as pickable at
   capture time (2026-10-13). Source: https://play.hotspawn.com/cs2-pickems and https://play.hotspawn.com/lol-pickems

2. **Community-pick percentages do not always sum to 100.** Example: Gothic vs Lavked (1079621) displayed
   10% + 90% at one fetch and 13% + 88% (=101%) at another — Hotspawn's live pick percentages drift with
   new votes and are rounded. These are recorded as captured context only and are NEVER used to derive our
   probabilities. Source: https://play.hotspawn.com/lobby

3. **Chunk-boundary gap (resolved, documented).** One match card (1071218, Volda E-Sport vs CNG Royal,
   Komplettligaen 2026 Autumn) was split across extraction chunks; its permalink was reconstructed from the
   Hotspawn fixtures REST API and its pairing confirmed on https://www.hotspawn.com/matches
   (see verification log). Its team order follows the fixture slug. Flagged for manual review of team order.
   Match 1071217 (Phenti vs VES Japan) had its community-pick % cut at a chunk boundary → left blank (unverified).

4. **Duplicate fixture IDs for same pairings.** Several LoL pairings appear twice with two Hotspawn fixture IDs
   (e.g. Neko Elite Kittens vs Second Time Alive Revival = 1075724 (Oct 13) and 1080901 (Oct 13) — two
   different BO1s of the same league round, or a re-scheduled fixture). Recorded as listed, both rows kept.

5. **"WAITING FOR INFORMATION" tier.** Many LoL cards show tier "WAITING FOR INFORMATION" and stage
   "Waiting For Information" (Hotspawn has not yet classified them). Recorded verbatim; NOT inferred.

6. **List extends beyond the stated week.** Although the lobby is labelled "This week" (weekly reset in
   ~5 days), the Upcoming list continues to 2026-11-13. All listed pickable matches are included in the
   inventory regardless of date.

## T2/T3 additions (2026-10-13, external odds sweep)

7. **Demacia Cup format conflict (match 1076650, KT Rolster vs BNK FearX).** EGamersWorld labels the match "Bo1"; Polymarket and esportbet.com describe the same semifinal as "Bo5". Time agrees across sources (2026-10-14 05:00 ET / 09:00 UTC). Format left blank; flagged for review. Sources: https://egamersworld.com/lol/match/FqxSssBfV/fearx-vs-kt-rolster-tW-gg6CEW, https://polymarket.com/esports/league-of-legends/demacia-cup-global-invitational/lol-fox1-kt-2026-10-14, https://esportbet.com/2026-demacia-cup-global-invitational-playoffs-betting-tips-monday-october-12/

8. **Thunderpick WC day-1 slot-order disagreement.** esports.gg lists the day-1 order as 9z-Aurora, Legacy-PARIVISION, Falcons-NiP, FURIA-BetBoom; HLTV, EGamersWorld and the Hotspawn lobby all order it 9z-Aurora (08:30 UTC), Falcons-NiP (11:00 UTC), Legacy-PARIVISION (13:30 UTC), FURIA-BetBoom (16:00 UTC). Inventory uses the Hotspawn lobby times (majority of sources). Sources: https://esports.gg/news/counter-strike-2/cs2-thunderpick-world-championship-2026-results/, https://egamersworld.com/blog/thunderpick-world-championship-2026-schedule-teams-3y5NuMb4pp, https://www.hltv.org/matches/2399385/falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026

9. **No external market published for 4 pick'em matches (blank, unverified).** ex-RUSTEC vs mellren (1079622) and FORZE Reload vs LFO 10 (1079624) show only the EGW 1.8/1.8 placeholder (opponent "LFO 10" is absent from the EGW team database); Mental Rush vs SK Gaming Avarosa (1076025) and Vitality Rising Bees vs G2 Hel (1076026) likewise show 1.8/1.8 with no "Bets by" panel for LGC 2026 Rising. No prices on any checked source. Probabilities left blank.

10. **225 minor-league LoL matches have no bookmaker market on any checked source** (PRM 2nd/3rd Div, Tunisian Super League, RIVALS LEAGUE, Arabian League 2nd Div, Komplettligaen, LigaGG CELOL A, Superstrike League, MängudeÖÖ, Benelux Ascend). EGamersWorld, Polymarket and general odds aggregators cover none of these leagues. All probabilities blank + "unverified". No values inferred.

11. **Odds snapshot volatility.** Several lines moved during the 2026-10-13 capture session (e.g. ex-Keyd Stars/Galorys 2.366/1.53 -> 2.43/1.46; KT/FearX 2.79/1.38 -> 3.27/1.31). `data/odds.csv` records one snapshot per match (the later capture) with earlier captures noted in the row notes.

## Team-name alias mappings used for odds sources (not irregularities; recorded for verification)

- Hotspawn "WROTBERRY" = EGW "WBT"; "EAC" = EGW "EA Copenhagen"; "RoundsGG" = EGW "Rounds"; "Phantom" = EGW "Phantom Esports"; "Sashi" = EGW "Sashi Esport"; "Envy" = EGW "Team Envy"; "BC.Game" = EGW "BC.Game Esports"; "BetBoom" = EGW "BetBoom Team"; "Ninjas in Pyjamas" = EGW "NiP"; "Fnatic" = EGW "fnatic"; Hotspawn "BNK FearX" = EGW "FearX" = Polymarket "BNK FEARX"; Hotspawn "The Last Resort" = EGW "The Last Resort" (tag TLR).
