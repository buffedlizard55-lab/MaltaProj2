# Independent every-match cross-check — session af573ff1

**Read time:** 2026-10-14 ~02:49 UTC. **Live board verified:**
https://buffedlizard55-lab.github.io/MaltaProj2/picks-every-match/ (fetched and read in full).

## What happened
This session built a complete every-match board independently (claim in COORDINATION.md,
2026-10-14 02:40 UTC; no open claim existed then). While it was being integrated, parallel
session `c64a5e19` merged an equivalent board in PR #81 (same `picks-every-match/` path,
own collector/workflow, ~30-minute self-refresh chain), and session `5a3c1a63` merged the
root executive summary in PR #83. To avoid publishing two competing boards — the exact
confusion the user asked to remove — this session merged `main`, kept the merged board
as the single every-match board, retired its own duplicate workflow, and archived its
board (`data/af573ff1/board.json`, built 2026-10-14T02:49Z from a live 02:43Z collection)
as this cross-check. No merged work was discarded or overwritten.

## Cross-check result (line by line, this session's board vs the merged board)
- Inventory: merged board lists the 28 lobby-open CS2 fixtures; this session's fresh
  HotSpawn lobby/API check at 02:43Z agrees on those 28.
- **Picks agree on 28/28 matches** (same team picked on every match).
- Probabilities are identical or near-identical on 25/28. Three material differences
  are flagged, not hidden:
  1. FORZE Reload vs LFO 10 — merged: FORZE 76.4% (LFO sibling-roster VRS range).
     This session: FORZE 65.0% (single-rating prior, shrunk and clamped; LFO 7/8/9 are
     different rosters). Same pick; this session flags the sibling-range input as the
     weaker evidence and recommends the pick be treated as low-confidence either way.
  2. HAVU vs RoundsGG — merged: HAVU 71.1% (VRS model after RoundsGG=ROUNDS alias).
     This session: HAVU 76.7% (Melbet market HAVU Gaming 1.21 / Rounds 3.99, read
     2026-10-14T02:23:57Z). Same pick; a named-bookmaker price exists for this match.
  3. EAC vs ENCE — merged: EAC 58.8%; this session's snapshot: EAC 50.5% (featured
     VRS model at an earlier refresh). Same pick; probability moved between refreshes.
- Extra API fixture: this session's HotSpawn **API** sweep also returned Wildcard vs
  DENDELE (2026-11-12), which is not in the current lobby pick'em week — so the merged
  board is right to exclude it from the 28. It is recorded here only so a future
  inventory change is noticed.

## Sources checked
- HotSpawn lobby + fixtures API — 200 on the 02:43Z runner collection (88 transfer-state
  fixtures; 11,570 API rows) — https://play.hotspawn.com/lobby
- Melbet LineFeed — 200, 39 CS2 quotes — https://melbet.com/en/line/esports
- Kalshi KXCS2GAME — 200, 27 quotes — https://kalshi.com/markets/kxcs2game
- Valve VRS global/europe/americas/asia — 200, 760 team rows —
  https://github.com/ValveSoftware/counter-strike_regional_standings
- bo3.gg upcoming API — 200. EGamersWorld 403, HLTV 403: recorded, never bypassed,
  no HLTV number used (HLTV team pages were read manually only to verify the
  WROTBERRY=WBT/WhiteBIT and RoundsGG=ROUNDS identities; see the merged board's
  method/flagged pages and this session's claim note in COORDINATION.md).

## Flagged for review
1. FORZE Reload vs LFO 10 rests on no team rating for LFO 10 anywhere (no Valve file,
   only a rejected 1.80/1.80 EGamersWorld placeholder) — lowest-confidence pick.
2. RoundsGG fixtures have a Melbet market price (e.g. HAVU vs Rounds, above) that the
   merged board resolves by VRS model instead; probability differences are published.
3. Pre-existing verification-test failures against the then-current data that were
   also present on this session's base commit (later addressed on `main` by other
   sessions' data refreshes) — no action taken here.

Artifacts: `data/af573ff1/board.json` + `snapshot.json` (the 02:43Z collection and its
access log), `scripts/af573ff1/` (the collector/builder that produced them, kept as
audit tooling; its workflow was retired on integration so only one every-match
workflow runs), `tests/test_picks_every_match_af573ff1.py`.
