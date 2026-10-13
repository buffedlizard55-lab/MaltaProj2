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
