# COORDINATION.md — shared task board

This file is the coordination board for every agent session working on this repo.
Read it before starting work, claim a task by writing your session ID here, and
push the claim before you start.

## Session registry

| Session ID | Branch | Status | Notes |
|---|---|---|---|
| `a0fcf175` | `arena/a0fcf175-maltaproj2` | active (sole session) | This environment is fixed to the `arena/a0fcf175-maltaproj2` branch and cannot create or push other branches/worktrees. To keep scopes non-overlapping anyway, every task below records an explicit **file scope**, and this session only writes inside its claimed scopes. |

> Note for other sessions: because this environment requires all work on
> `arena/a0fcf175-maltaproj2`, the branch-per-task rule in the project
> instructions is implemented as **file-scope locking inside one branch** plus a
> single integration step. If you are a different session, do not edit files in a
> scope claimed here; log a request instead.

## Task board

| # | Task | Status | Owner | File scope | Evidence |
|---|---|---|---|---|---|
| 1 | Enumerate every CS2 fixture open for picks on the Hotspawn Play Pick'em lobby, with tier/points/kickoff/crowd % and the per-fixture Hotspawn URL | done | `a0fcf175` | `data/pickem_pool.json`, `scripts/build.py` (MATCHES) | three reads of `play.hotspawn.com/lobby` + `/cs2-pickems`; 26 open fixtures; pool counts (85–86) reproduced on the Tournaments page |
| 2 | Verify each fixture against an independent esports data source (HLTV match page / event listing, plus bo3.gg where no HLTV page exists) | done (2 gaps flagged) | `a0fcf175` | same as #1 | HLTV match URLs for 24/26 fixtures; HLTV event 2635 listing + bo3.gg for the 2 ESL Challenger League finals |
| 3 | Capture external betting lines (never Hotspawn): bookmaker module `Bets on <event> by bc.game` on EGamersWorld event pages + Polymarket CS2 markets | done | `a0fcf175` | same as #1 | EGamersWorld event pages (Elisa, CCT Europe #11, Stake Pulse Beat III, Thunderpick WC) and Polymarket tournament pages |
| 4 | Derive our own line (de-margin + equal-weight consensus), keep blanks blank, record source links per row | done | `a0fcf175` | `scripts/build.py`, `data/pickem_pool.json` | 25/26 rows carry a line (15 bc.game + 20 Polymarket captures); 1 row blank + flagged; formula on the Methodology page |
| 5 | Publish a static GitHub Pages dashboard with subpages by category, analysis and a Flagged for review page | done | `a0fcf175` | `docs/**`, `data/**`, `scripts/**` | `python3 scripts/build.py` regenerates 7 pages from the captured data; `python3 scripts/check_links.py` reports 0 broken local links (130 external source links, all hosts: hltv/hotspawn/egamersworld/polymarket/bo3.gg/liquipedia/pallomeri/freetips) |
| 6 | Final integration: re-verify combined data, check for broken links, open PR to `main`, merge, confirm the Pages deploy | unclaimed | — | `main` | to be recorded below |

## Verification log

* 2026-10-13 — Session `a0fcf175` claimed tasks 1–5 and pushed this file before
  starting work outside its scope.
* 2026-10-13 — Hotspawn lobby read three times (13:56, 14:15, 14:36 UTC). The
  open-for-picks list was stable across reads; crowd percentages ticked
  (e.g. ex-Keyd Stars 83% → 86%), which is recorded per row.
* 2026-10-13 — Fixture verification: HLTV match pages fetched for all
  Thunderpick WC, Stake Pulse Beat III, CCT Europe #11 and Elisa BreakOut
  fixtures (IDs 2399134–2399137, 2399298–2399301, 2399384–2399387,
  2399418–2399429). Kickoff times on HLTV match the Hotspawn UTC times exactly.
* 2026-10-13 — Price capture: EGamersWorld event modules state the pricing
  bookmaker (`bc.game`). Polymarket prices captured per tournament page.
  Discrepancies between page components (3.6/1.27 vs 3.8/1.22 for 9z vs Aurora)
  are recorded in the flagged list rather than silently resolved.
* 2026-10-13 — Values that could not be confirmed from a source were left empty:
  the two ESL Challenger League rows have no two-sided book line (only a
  prediction-market line), several Elisa Group B rows have no book line at all,
  and the FORZE Reload row has no usable market line because the prediction
  market lists a different opponent.

## Irregularities (mirrored on the site's "Flagged for review" page)

1. Per-match HLTV page missing for `ex-Keyd Stars vs Galorys` and
   `Zomblers vs Overtake Sector` (event-level listing used instead).
2. Crowd-vs-market divergence on `ex-Keyd Stars vs Galorys` (crowd 86% vs market
   33c/68c for Galorys), `HOTU vs Fnatic`, `MIBR vs BC.Game`, `Gothic vs Lavked`.
3. Team-name aliases: `WROTBERRY` ↔ `WBT`, `RoundsGG` ↔ `ROUNDS`,
   `EAC` ↔ `EA Copenhagen` / `Esport Academy Copenhagen`.
4. `FORZE Reload` opponent listed as `Sökerorg` on the prediction market but
   `LFO 10` on Hotspawn and HLTV.
5. Team order differs between sources for `RoundsGG vs Voca`.
6. EGamersWorld match pages showing identical `1.8 / 1.8` lines (placeholder-like)
   were excluded from the derivation.
7. Odds drift between page components and between captures — all values are
   timestamped snapshots.
8. Wide prediction-market spreads on near-zero-volume Tier C fixtures (price sums
   up to 1.39); normalised before use and marked Low quality.
9. Coverage boundary: matches that had already locked/completed are not in the
   table (they cannot be picked); the weekly pool count of 85–86 is reproduced on
   the Tournaments page.
10. HLTV betting-analytics pages render analytics but not machine-readable
    numeric odds in this pipeline → used for verification only.
11. LoL Pick'em tab not covered (CS2 only).
12. Pool counts differ between renders (86/27/55/4 vs 85/26/55/4).

## Pull request / deploy record

* PR: _pending_
* Merge: _pending_
* Pages deploy: _pending_
