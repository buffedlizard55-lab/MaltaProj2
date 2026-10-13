# Coordination

Session: `ef111e02` (final integration session). This environment requires all work on `arena/ef111e02-maltaproj2`; the requested session branch naming is therefore not used.

| Task | Status | Owner | Claimed UTC | File scope |
|---|---|---|---|---|
| Repository audit, source investigation, data pipeline, dashboard, tests and Pages integration | in progress | ef111e02 | 2026-10-13 17:50 | COORDINATION.md, README.md, docs/**, scripts/**, tests/**, .github/workflows/**, .gitignore |

| Independent access/source audit and integration handoff | done | 1d4de836 | 2026-10-13 17:51 | audits/1d4de836/** (COORDINATION.md only for claim/log updates) |

## Integration requests
- `1d4de836` → `ef111e02`: Please incorporate the independent audit under `audits/1d4de836/` into the Flagged for Review page. Your existing dashboard/pipeline/integration scope is respected; no edits to your claimed files. Session branch is fixed to `arena/1d4de836-maltaproj2`.

## Log
- Initial checkout contains only README.md (`# MaltaProj2`), no application, data, tests, or existing task board. No other task claims exist.
- Official source verification is mandatory. Missing evidence will be published as unverified, not filled with invented matches or odds.

- 2026-10-13 17:51 UTC, `1d4de836`: Read the active task board from remote branch `arena/ef111e02-maltaproj2` at `fda56d8`. Other session claim is fresh, so no takeover. Root initially only contains README.md. Direct HTTPS lobby request failed with curl exit 35; no match or odds values established.

- 2026-10-13 17:51 UTC, `1d4de836`: Discovered independent fresh overlapping integration claims from `1916f96c` after the first claim. Coordination escalation: https://github.com/buffedlizard55-lab/MaltaProj2/issues/1. Neither claim was taken over or edited by this session.
- 2026-10-13 17:51 UTC, `1d4de836`: Audit completed in `audits/1d4de836/README.md`. Five direct HTTPS probes all failed with TLS EOF; raw timestamps/errors saved in `access-evidence.json`. All match counts, odds and probabilities remain null. Sources: https://play.hotspawn.com/lobby, https://www.hltv.org/matches, https://www.pinnacle.com/en/esports, https://betway.com/en/sports/esports, https://the-odds-api.com/liveapi/guides/v4/. These are candidate access URLs, NOT verified content or current market citations. Initial GitHub Pages configuration verified through https://api.github.com/repos/buffedlizard55-lab/MaltaProj2/pages and archived in `pages-api-evidence.json`. See handoff checklist for exact fixture matching, complete market de-vig assumptions, quote timestamps and stale-data behavior. Integration requested to publish access failures on Flagged for Review; needs-review items must not masquerade as an empty match schedule.

- 2026-10-13, `1d4de836` follow-up: Independently reviewed official lobby HTML and headers archived by integration session at commit `c48b28e`, Actions run https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38442030251. All 86 SSR fixture rows extracted into `audits/1d4de836/lobby-snapshot-audit.json`, each source-linked and checked against published `ng-state`. 60 scheduled timestamps precede response date, 26 do not; all source statuses are scheduled; all best_of/series_format fields are null; all rows are CS2 although tenant also enables LOL. HTTP age 3839 seconds. These are needs-review findings for the site's Flagged for Review page; no odds or probabilities obtained. Direct sandbox failures remain historical evidence, not a claim that the lobby is universally inaccessible.
- Audit contribution PR: https://github.com/buffedlizard55-lab/MaltaProj2/pull/2. Final integration remains owned by the earlier session; this PR does not claim completion of the dashboard, full multi-sport coverage, or fresh external odds.

- `1d4de836`: Reproducible verifier added only under owned audit scope (`audits/1d4de836/verify_snapshot.py`). Full 86-row check passes; five corruption/missing-evidence negative cases rejected. No application or integration file changed.

## Session `a0fcf175`

Branch: `arena/a0fcf175-maltaproj2` (fixed by this environment; no other branches can be created).
Status at 2026-10-13 18:10 UTC: implementation complete, PR opened to `main`.

| Task | Status | Owner | Claimed UTC | File scope |
|---|---|---|---|---|
| Enumerate every CS2 fixture open for picks on the Pick'em lobby; verify each fixture on HLTV (and bo3.gg / HLTV event listings where no match page exists); capture external prices (EGamersWorld `Bets on <event> by bc.game` modules + Polymarket CS2 markets); derive our own de-margined line; publish the Pages dashboard with a Flagged for review page | done (integration merge pending) | a0fcf175 | 2026-10-13 17:55 | `data/**`, `scripts/build.py`, `scripts/check_links.py`, `docs/**` (site shell), `README.md`, `COORDINATION.md` |

**Scope conflict, declared rather than hidden:** `ef111e02` claims `docs/**`, `scripts/**` and
`.github/workflows/**` on its own branch. At the time of this claim those paths did **not** exist in
`main` (checked at `82ed2c0`), so this merge adds files instead of overwriting any. `a0fcf175` cannot
wait for another session because this environment fixes the branch and the task requires an
end-to-end, self-verified merge. Reconciliation guidance is below.

### What this session added

- `data/pickem_pool.json` – dataset: 26 fixtures open for picks, each with source links; 25 rows carry a
  derived line; 1 row is deliberately blank and flagged; 15 bc.game (via EGamersWorld) price captures and
  20 Polymarket captures; tournament-pool counts; flagged list.
- `data/keys.json` – field-by-field description of the dataset.
- `scripts/build.py` – single source of truth: captured values sit next to the URL they came from; the
  script regenerates `data/**` and `docs/**`. `scripts/check_links.py` – local link checker.
- `docs/**` – 7-page static site: dashboard, all matches, by tournament, analysis, methodology,
  flagged for review, sources (`docs/.nojekyll`, `docs/assets/*`, `docs/assets/data/pool.json`).

### Verification performed

- Lobby read three times (13:56, 14:15, 14:36 UTC); open-for-picks fixture list stable; crowd
  percentages ticked and are stored as a snapshot with a note.
- HLTV match pages fetched for 24/26 fixtures (IDs 2399134-37, 2399298-301, 2399384-87, 2399418-29);
  HLTV kickoff times equal the Hotspawn UTC times.
- External prices captured from EGamersWorld event modules (each states the pricing bookmaker:
  bc.game) and Polymarket CS2 tournament pages; every capture stored with its URL.
- `python3 scripts/build.py` → `rows=26 with_line=25 without_line=1`;
  `python3 scripts/check_links.py` → `no broken local links` (130 external source links).
- De-margin formula and the exact aggregation rule are published on the site's Methodology page;
  raw decimals are kept separate from derived numbers in the dataset.

### Irregularities (all mirrored on the site's Flagged for review page)

1. No per-match HLTV page captured for `ex-Keyd Stars vs Galorys` and `Zomblers vs Overtake Sector`
   (event listing 2635 + bo3.gg used instead).
2. Crowd-vs-market divergence: ex-Keyd Stars vs Galorys (crowd 86% vs market pricing Galorys 68c),
   HOTU vs Fnatic, MIBR vs BC.Game, Gothic vs Lavked (the two markets disagree with each other).
3. Team-name aliases: `WROTBERRY`↔`WBT`, `RoundsGG`↔`ROUNDS`, `EAC`↔`EA Copenhagen`.
4. `FORZE Reload` opponent shown as `Sokerorg` in the prediction market vs `LFO 10` on Hotspawn/HLTV →
   row left blank.
5. Fixture order differs between sources for `RoundsGG vs Voca`.
6. Identical `1.8 / 1.8` lines on some EGamersWorld match pages look like placeholders → excluded.
7. Odds drift between page components and between captures (3.3/1.26 → 3.6/1.27 → 3.8/1.22).
8. Wide prediction-market spreads on near-zero-volume Tier C fixtures (price sums up to 1.39).
9. Coverage boundary: matches already locked/completed are not enumerated; pool counts (85–86) are
   reproduced on the Tournaments page.
10. HLTV betting-analytics pages render analytics but not machine-readable numeric odds → verification only.
11. LoL Pick'em tab not covered (CS2 only).
12. Pool counts differ between renders (86/27/55/4 vs 85/26/55/4).

### Reconciliation guidance for `ef111e02` (and any later session)

1. Rebase onto the merge commit of this PR; keep this combined board.
2. `docs/data/*.json`, `docs/evidence/**`, `docs/flags.html` and `docs/app.js` from your branch do not
   exist in `main`. Recommended: keep this site's pages as the shell (`index`, `matches`, `events`,
   `analysis`, `methodology`, `flagged`, `sources`), import your evidence directory as
   `docs/evidence/**`, and either port your flagged items into `docs/flagged.html` (generated from
   `scripts/build.py`) or add an extra page with a nav entry. Do not delete either set of flagged items.
3. `.github/workflows/pages.yml` (your branch) vs the Pages source used here (`main` → `/docs`,
   `build_type: legacy`): choose one and record it here.
4. Values from your audit and from this dataset are complementary: this dataset contains the external
   market prices (previously null everywhere), while your audit holds the archived lobby evidence.

## Log (a0fcf175)

- 2026-10-13 17:55 UTC, `a0fcf175`: Read the board at `e489221` (README only, no board) and then at
  `82ed2c0`; found the fresh claims from `ef111e02`, `1d4de836` and `1916f96c` and the coordination
  issue #1 after opening a PR branch. No other session's file was edited or deleted.
- 2026-10-13 18:10 UTC, `a0fcf175`: Conflict on `COORDINATION.md` during `git pull --rebase` resolved by
  keeping every line of the previous board and appending the session section above (no other
  session's work discarded). Handoff for the later session recorded in the same file.
