# TASK-06 — independent TWC model and Pages audit

**Audit snapshot:** 2026-10-13 18:21 UTC · repository `main` at `d530651` · report authored on `arena/ca621beb-maltaproj2`. A separate live-site follow-up was performed through 18:36 UTC after PR #13/#15/#17/#18/#19/#20/#22 integration and refresh changes.

**Scope:** independently check the merged TWC 2026 field/openers, the PARIVISION roster correction, source coverage and arithmetic in the preserved root-level model, and what GitHub Pages actually serves. This is an audit, not an adoption of another session's model or prices. No Hotspawn crowd-pick percentage was used as a probability. **Model/data links for the baseline audit are pinned to `d530651`; the later public dashboard is reported separately.**

## Executive conclusion

- **The current eight-team field and four Oct. 14 openers are represented correctly in the audited fixture data.** Virtus.pro is withdrawn and Ninjas in Pyjamas is in. The group assignments and BO3 opener pairings below match HLTV's Oct. 9/12 event coverage and match records. The historical `fixtures_verified.json` records cautiously leave timezone-unclear kickoff times and their dedicated bookmaker fields blank; the later integrated dashboard adds separately timestamped Bovada/Pinnacle quotes (see follow-up).
- **PARIVISION's current roster entry with HObbit is correct.** PARIVISION's official account announced on Sept. 17 that HObbit joined permanently; HLTV's current team page also lists him. Valve's Oct. 5 standings are a dated VRS snapshot and still list `slaxejezzz`; that historical roster line does not make the current HObbit entry wrong. The model's use of dated team-level VRS points is a separate, unadjusted assumption.
- **The probabilities are model outputs, not verified or empirically calibrated forecasts.** The code uses two VRS point snapshots, fixed hand-set bonuses, and chosen formula constants. It does not use the HLTV ranking, head-to-head records, or prediction-market history claimed in the generator docstring. Some page copy and compliance booleans still overstate what the code establishes.
- **The generated odds and interactive simulator are not internally consistent.** Decimal odds are generated from a vigged probability while American odds are generated from the fair probability; the page does not label that distinction. The JavaScript simulator also omits the Python model's probability cap and 15% Over 2.5 floor.
- **The publication state changed during the audit.** At the 18:21 pre-integration check on `d530651`, the live root showed LineWatch (86 embedded fixtures, 27 visible cards, 0 current probabilities, 2 reference markets), and `/pickem/` file routes returned 404. After PR #15/#17 and subsequent refreshes, the integrated odds dashboard replaced it; the direct `/pickem/` paths now serve the 26-row reconstruction. At an 18:36 cache-busted recheck, the root showed 93 tracked fixtures, 12 with external lines and 81 left blank after PR #19. All four TWC openers show direct Bovada and Pinnacle links with quote-read times from 18:30 UTC. The root also exposes a Flagged-for-review page with the 81 unpriced rows, and the Pick'em sub-board has its 14-item flag page. Generated root HTML includes a Pick'em navigation anchor; the post-PR #20/#22 Pages runs passed, and public fetches confirmed the root and direct board/flag pages, although the fetcher does not expose the nav header itself. This resolves route availability for the paths tested, but this audit did not certify all 93 fixtures or all 12 quoted markets. The root now serves the integrated odds dashboard, not the historical d530 VRS-probability model.

## Evidence checked

### Valve VRS snapshot values

The following rank/point values are copied correctly from Valve's **Oct. 5, 2026** global standings. Each row links directly to that official snapshot. These are snapshot values, not current live ratings.

| Finalist | Oct. 5 VRS | Source |
|---|---:|---|
| Legacy | #2 · 1,931 | [Valve VRS, Oct. 5](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_10_05.md) |
| Team Falcons | #6 · 1,843 | [Valve VRS, Oct. 5](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_10_05.md) |
| FURIA | #7 · 1,829 | [Valve VRS, Oct. 5](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_10_05.md) |
| Aurora | #9 · 1,716 | [Valve VRS, Oct. 5](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_10_05.md) |
| BETBOOM | #11 · 1,596 | [Valve VRS, Oct. 5](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_10_05.md) |
| 9z | #17 · 1,543 | [Valve VRS, Oct. 5](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_10_05.md) |
| Ninjas in Pyjamas | #18 · 1,534 | [Valve VRS, Oct. 5](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_10_05.md) |
| PARIVISION | #36 · 1,411 | [Valve VRS, Oct. 5](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_10_05.md) |

### Current group and opener facts

HLTV's Oct. 12 overview and Oct. 9 matchup report list these groups and Oct. 14 BO3 openers. The table links to the **slugged** HLTV match page, which loaded during this audit.

| Group | Fixture | Format/date | Match source |
|---|---|---|---|
| A | 9z vs. Aurora | BO3 · Oct. 14, 2026 | [HLTV match 2399384](https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026) · [Oct. 12 event overview](https://www.hltv.org/news/45706/thunderpick-world-championship-teams-format-schedule-prizes-talent-fantasy) |
| A | Falcons vs. Ninjas in Pyjamas | BO3 · Oct. 14, 2026 | [HLTV match 2399385](https://www.hltv.org/matches/2399385/falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026) · [Oct. 9 matchup report](https://www.hltv.org/news/45688/thunderpick-world-championship-matchups-announced-with-virtuspro-replaced-by-nip) |
| B | Legacy vs. PARIVISION | BO3 · Oct. 14, 2026 | [HLTV match 2399386](https://www.hltv.org/matches/2399386/legacy-vs-parivision-thunderpick-world-championship-2026) · [Oct. 12 event overview](https://www.hltv.org/news/45706/thunderpick-world-championship-teams-format-schedule-prizes-talent-fantasy) |
| B | FURIA vs. BETBOOM | BO3 · Oct. 14, 2026 | [HLTV match 2399387](https://www.hltv.org/matches/2399387/furia-vs-betboom-thunderpick-world-championship-2026) · [Oct. 9 matchup report](https://www.hltv.org/news/45688/thunderpick-world-championship-matchups-announced-with-virtuspro-replaced-by-nip) |

The Oct. 9 report explains that NiP replaced Virtus.pro and gives the GSL-group/playoff format; the Oct. 12 overview confirms the eight teams and groups. The extracted HLTV clock times do not include a confirmed timezone. Accordingly, `start_time_utc: null` in [`data/fixtures_verified.json`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/data/fixtures_verified.json) is the cautious choice. Do not replace it with a guessed timezone.

### PARIVISION / HObbit

**No HObbit roster error was found.** The official [@parivisiongg post of Sept. 17](https://x.com/parivisiongg/status/2100555617832149185) says Abay “HObbit” Khassenov joined PARIVISION's main roster permanently. HLTV's [current PARIVISION team page](https://www.hltv.org/team/12467/parivision) lists HObbit and says slaxejezzz was benched after the Sept. 17 change.

The two Valve snapshots show why the dates must be distinguished: the [Aug. 3 VRS snapshot](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_08_03.md) lists PARIVISION at #12 / 1,685 with HObbit; the [Oct. 5 snapshot](https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/invitation/2026/standings_global_2026_10_05.md) lists #36 / 1,411 with slaxejezzz. The `teams_verified.json` active roster using HObbit is supported; the Oct. 5 point value remains a dated team rating, not a lineup-adjusted strength estimate.

## Findings requiring review

### CA-01 — Field and schedule corrections are substantively sound

The merged replacement of Virtus.pro with NiP, publication of the groups, and addition of the four real openers resolve the stale-field/schedule defects in the original PR #7 edition. The 28 entries in [`data/originated_matches.json`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/data/originated_matches.json) are pairwise model scenarios, **not 28 scheduled fixtures**; only four Oct. 14 openers are verified in [`data/fixtures_verified.json`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/data/fixtures_verified.json). Keep that distinction visible. The dedicated bookmaker fields in the historical fixture-verification file remain null; the later integrated dashboard's dated Bovada/Pinnacle quote layer is separate and documented in the follow-up table.

### CA-02 — Model provenance is disclosed in part, but calibration claims remain inconsistent

[`scripts/originate_lines.py`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/scripts/originate_lines.py) calculates an effective rating as:

```text
R = 0.75 × Oct. 5 VRS points + 0.25 × Aug. 3 VRS points + fixed team bonus
P(A) = 1 / (1 + 10^(-rating_difference / 400)), capped to [0.08, 0.92]
```

It then applies fixed bonuses of +35 Falcons, +25 Legacy, +15 FURIA, and +10 Aurora. The data's `origination_method` and [`methodology.html`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/methodology.html) disclose the bonuses as assumptions; that disclosure is good. But the current implementation does **not** read `hltv_rank_sept`, H2H match records, or historical prediction-market data. The generator docstring still claims those are model inputs. The dashboard subtitle still says the outputs are “calibrated against” VRS and HLTV; `methodology.html` retains “Calibration” in its title/meta and “Calibration Matrix” heading; and [`data/origination_summary.json`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/data/origination_summary.json) asserts `verified_against_official_sources: true` and `no_hallucinations: true`. Those statements go beyond the code and evidence. IRREG-012 correctly records that the model is derived, not a verified forecast, but the remaining copy/status fields should be brought into line with it.

The 25% invite-point input is the Aug. 3 VRS snapshot, but **none** of the eight `teams_verified.json` source lists link to that snapshot, and none of the 28 `verification_sources` arrays in `originated_matches.json` link to it. The match rows link Oct. 5 VRS, an HLTV event page, and Liquipedia. A reviewer therefore cannot follow every rating input from the row even though the Aug. 3 source exists. `hltv_rank_sept` is stored in team data but is not used by the calculation.

**Request:** keep the model marked as derived/unvalidated; either remove calibration/H2H/HLTV-input claims that are not implemented or add the actual reproducible data and backtest; attach the Aug. 3 VRS source to each row whose rating uses it; and avoid a blanket “no hallucinations” boolean for derived probabilities.

### CA-03 — Odds formats and the interactive simulator do not match generated rows

The Python generator calculates decimal prices from `fair_probability × 1.045` (vig included) but calculates American prices directly from `fair_probability` (vig excluded). Unless those columns are explicitly labeled “market decimal” and “fair American,” they are not two formats for the same probability. This was reproduced for all 28 pairwise records: every row has at least one side whose decimal- and American-implied probabilities differ by more than 1.5 percentage points.

Example, Legacy vs. PARIVISION in [`data/originated_matches.json`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/data/originated_matches.json):

- fair probability: Legacy 92.0%;
- decimal price 1.04 implies 96.15%;
- American price −1150 implies 92.00%.

There is also a generated-data/UI mismatch. For the same pair, Python caps the series probability at 92.0% and floors the Over 2.5 probability at 15.0%. The embedded simulator in [`index.html`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/index.html) omits both operations; using the same ratings it displays about 92.5% and 9.6% Over 2.5. The JavaScript does use the same static effective ratings, but it does not reproduce the Python generator's exact limits. Five of the 28 generated total-map rows hit the 15% floor, so the UI difference is not isolated to an unused parameter.

The current tests pass probability-normalization/count assertions but do not test cross-format odds consistency, source coverage for each model input, or equality between the JS simulator and generated JSON. Do not present the displayed prices as a quoted sportsbook line; resolve or clearly label the fair-vs-vig distinction before promoting them as interchangeable odds formats.

### CA-04 — The four specific HLTV links stored in the TWC opener table return 404

The merged root `index.html` and [`data/fixtures_verified.json`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/data/fixtures_verified.json) use `https://www.hltv.org/matches/2399384/` through `.../2399387/` without slugs. I fetched the bare paths for all four IDs; HLTV returned its 404 page. The slugged links in the verified-fixture table above load correctly. The row also has a valid HLTV article and Hotspawn link, so the fixture facts are supported, but the cell labeled “HLTV match” is a broken source link. Replace the bare paths with the slugged URLs and add an outbound-link check for those exact rows.

### CA-05 — External prices are observations, not validated model inputs

The official [Thunderpick 9z–Aurora market page](https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/9z-team-vs-aurora/2796376) showed 9z +280 / Aurora −455 and a “Live” label during this audit, while the same page listed an Oct. 14 future fixture and exposed no provider quote timestamp or timezone in the extracted text. The existing [`docs/data/quotes.json`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/docs/data/quotes.json) and Flagged page correctly retain this only as a reference observation. Do not convert it into a current verified price without resolving the `Live`/future-time, timestamp, and market-identity issues.

A merged but separate Pick'em dataset also stores market-derived consensus figures for the four TWC openers. At the repository snapshot, its `line_p_a` values were 25.9% (9z), 76.2% (Falcons), 57.7% (Legacy), and 68.4% (FURIA), versus the root model's 35.9%, 90.6%, 92.0%, and 75.7% respectively. These are **discrepancy signals, not independently validated fair probabilities**: this audit did not verify all 26 Pick'em joins, and the source page is time-varying.

For the sample 9z–Aurora row, the [EGamersWorld event page](https://egamersworld.com/counterstrike/event/thunderpick-world-championship-2026-5X5sFiL7H) labels its odds module “Bets on … by bc.game” and displayed 3.6 / 1.27; the same page's schedule module displayed 3.8 / 1.22. It carries no per-quote timestamp. The [Polymarket 9z–Aurora market](https://polymarket.com/esports/cs2/thunderpick-world-championship/cs2-9z-aur1-2026-10-14) showed 26¢ / 75¢ at fetch time. These pages are useful independent references, but they do not make the root model calibrated or establish a durable quote.

### CA-06 — Row-level Polymarket URLs were missing in the baseline; quote timestamps remain thin

In the d530 baseline [`data/pickem_pool.json`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/data/pickem_pool.json), the Falcons–NiP and Legacy–PARIVISION records contain `pm_prices`, `pm_p_a`, `pm_p_b`, and a consensus basis that includes Polymarket, but no per-row `pm_url`; the registered Polymarket source is only a generic TWC hub. That baseline provenance gap is **resolved in the later public table**: a cache-busted re-fetch of [`/pickem/matches.html`](https://buffedlizard55-lab.github.io/MaltaProj2/pickem/matches.html?audit=ca621beb-1831) showed exact Polymarket market links on the 9z–Aurora, Falcons–NiP, and Legacy–PARIVISION rows. The FURIA–BetBoom row has the event/bookmaker source and no Polymarket component. The visible rows do not show an individual Polymarket quote-read timestamp, however; they give only the board-level snapshot date. Preserve an exact URL **and** per-market capture time in the raw data for each Polymarket input, or do not present the price as a current quote. The displayed EGamersWorld event page supports the bookmaker component only. This audit did not validate the other 22 Pick'em rows.

### CA-07 — A publication mismatch was observed, then resolved for the tested routes

**Initial observation (18:21 UTC; baseline `d530651`):** GitHub Pages still served LineWatch at the root (86 embedded fixtures, 27 visible cards, 0 current probabilities, 2 reference markets). Cache-busted `/pickem/index.html` and `/pickem/matches.html` requests returned 404, despite the earlier PR #14 coordination note reporting 200. At that baseline, the [Pages workflow](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/.github/workflows/pages.yml) uploaded `docs/` and its [deployment checker](https://github.com/buffedlizard55-lab/MaltaProj2/blob/d530651/scripts/check_deployment.py) did not probe the Pick'em routes. This explains the discrepancy as a deployment/cache transition; the 404 was not a stable current result.

**Follow-up (18:23–18:36 UTC):** after PR #15/#17 integrated the new odds dashboard and PR #18 merged the Pick'em navigation-generator change, cache-busted requests found:

- The public [root dashboard](https://buffedlizard55-lab.github.io/MaltaProj2/?audit=ca621beb-1836) served the integrated market-based site. At the 18:36 recheck it displayed 93 fixtures, 12 priced, and 81 left blank/unverified, after PR #19's name-normalisation change.
- The root [Flagged for review page](https://buffedlizard55-lab.github.io/MaltaProj2/flagged.html?audit=ca621beb-1836) showed 81 unpriced fixtures; the separate [`/pickem/`](https://buffedlizard55-lab.github.io/MaltaProj2/pickem/?audit=ca621beb-1836), [`/pickem/index.html`](https://buffedlizard55-lab.github.io/MaltaProj2/pickem/index.html?audit=ca621beb-1836), and [`/pickem/matches.html`](https://buffedlizard55-lab.github.io/MaltaProj2/pickem/matches.html?audit=ca621beb-1831) served the 26-match reconstruction, with [`/pickem/flagged.html`](https://buffedlizard55-lab.github.io/MaltaProj2/pickem/flagged.html?audit=ca621beb-1836) showing 14 items. This confirms the direct routes and review pages are published at the follow-up check.
- PR #13's merged main run [38446661064](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38446661064) passed build/deploy/public verification; PR #20's [38447169101](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38447169101) and PR #22's [38447860601](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38447860601) main checks passed, and the PR #22 Pages deploy [38447860252](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38447860252) succeeded.

This resolves the earlier direct-route 404 finding. It does **not** validate every row in the integrated 93-fixture dataset or every price; this audit rechecked the four TWC opener rows only. PR #18 added the `/pickem/` navigation entry, and the regenerated root source at [`5dd243e`](https://github.com/buffedlizard55-lab/MaltaProj2/blob/5dd243e/index.html) includes it. The post-PR #20/#22 Pages builds and deployments succeeded; cache-busted public fetches of the root, root Flagged page, and direct Pick'em/review routes returned expected content. The fetcher does not expose the header itself, so this is source-plus-deploy confirmation, not a browser click test. The new root is the odds-derived integrated dashboard, not the historical d530 VRS-probability simulator. The older PR #12 and PR #14 failed post-deploy probes remain historical failures; they are superseded by successful main deployment/verification runs.

**Remaining request:** keep explicit post-deploy checks for the direct Pick'em routes. Keep the four old bare HLTV URLs fixed if the archived TWC fixture/model pages are reused. Do not promote the archived VRS model as a market quote or calibrated forecast.

### Post-integration TWC market snapshot (public root fetched 18:36 UTC; quote batch read 18:30 UTC)

After PR #15's integration, the live root displayed direct Bovada/Pinnacle source links and per-source read times for all four TWC openers. The table below transcribes the **18:30 UTC quote batch**, rendered by the dashboard at 18:31:13Z and fetched publicly at about 18:36Z. The percentages are odds-derived outputs from that page, not independently established match probabilities and not current prices; they are shown only to compare with the older d530 model. All quote rows below link to the provider's match/API page.

| TWC opener | Bovada price (read UTC) | Pinnacle price (read UTC) | Integrated board no-vig consensus, team A | d530 VRS model, team A |
|---|---|---|---:|---:|
| 9z vs. Aurora | [3.65 / 1.26](https://www.bovada.lv/esports/counter-strike-2/thunderpick-world-championship-26/9z-globant-team-aurora-202610140430) · 18:30:49 | [3.65 / 1.2933](https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638111785/markets/related/straight) · 18:30:37 | 9z 25.9% / 74.1% | 9z 35.9% |
| Falcons vs. Ninjas in Pyjamas | [1.229885 / 3.9](https://www.bovada.lv/esports/counter-strike-2/thunderpick-world-championship-26/team-falcons-ninjas-in-pyjamas-202610140700) · 18:30:49 | [1.2494 / 4.06](https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638111674/markets/related/straight) · 18:30:48 | Falcons 76.2% / 23.8% | Falcons 90.6% |
| Legacy vs. PARIVISION | [1.69 / 2.1](https://www.bovada.lv/esports/counter-strike-2/thunderpick-world-championship-26/legacy-parivision-202610140930) · 18:30:49 | [1.6667 / 2.23](https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638111786/markets/related/straight) · 18:30:46 | Legacy 56.3% / 43.7% | Legacy 92.0% |
| FURIA vs. BetBoom | [1.350877 / 3.1](https://www.bovada.lv/esports/counter-strike-2/thunderpick-world-championship-26/furia-esports-bb-team-202610141200) · 18:30:49 | [1.3745 / 3.12](https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638111787/markets/related/straight) · 18:30:39 | FURIA 69.5% / 30.5% | FURIA 75.7% |

The direct-bookmaker table is materially better provenance than the older EGamersWorld/Polymarket-only **Pick'em** source chain. It still needs normal time-decay treatment: the quotes were read at 18:30Z and can move. This follow-up confirms what the public root rendered at fetch time, but does not independently reopen every linked API, certify bookmaker availability by jurisdiction, validate the rest of the 93 fixtures, or bless the old VRS model. The root count advanced from 11/82 to 12/81 after PR #19 merged at 18:27:44; the new accented fixture is outside this audit's TWC scope. The separate `/pickem/` PR #11 board remains the 26-fixture snapshot described in CA-06; its per-row Polymarket provenance is distinct from this newer root dashboard.

## Verification performed

- Read the merged main files at the `d530651` baseline for team, fixture, originated-line, quote, and Pages records; inspected `scripts/originate_lines.py`, `index.html`, `methodology.html`, `tests/test_site.py`, `scripts/check_deployment.py`, and `.github/workflows/pages.yml`. The findings about that historical simulator are scoped to that exact snapshot.
- Fetched Valve's Oct. 5 and Aug. 3 VRS files; HLTV's Oct. 9/12 TWC articles, the current PARIVISION team page, slugged and bare TWC match URLs; PARIVISION's official X post; the Thunderpick 9z–Aurora market; EGamersWorld's TWC odds page; and the 9z–Aurora Polymarket page. After integration, re-fetched the public root and `/flagged.html`, plus `/pickem/`, `/pickem/index.html`, `/pickem/matches.html`, and `/pickem/flagged.html`; recorded the current integrated dashboard's four TWC source URLs, per-book read timestamps, and rendered de-vig outputs in the follow-up table.
- `python -m unittest discover tests/` initially could not import `bs4` because the base interpreter lacked the pinned project dependency. Installed `scripts/requirements.txt` in ignored `.venv/` and reran with bytecode writes disabled: **18 tests passed** against the audited checkout. After rebasing through main commit `5dd243e`, reran the current suite on this task branch: **27 tests, all passing**; two existing test cases emit non-failing `ResourceWarning`s for unclosed HTML reads. The earlier PR #12 post-deploy probe failed; PR #13 main run [38446661064](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38446661064), PR #20 Pages run [38447169101](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38447169101), PR #22 main run [38447860601](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38447860601), and PR #22 Pages deployment [38447860252](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38447860252) passed.
- This audit does not certify the other 22 Pick'em market joins or every legal name/role field in the team file. Existing IRREG-011 already notes that not every other roster detail was re-fetched in PR #12. It also does not certify the other 89 rows in the integrated 93-fixture dashboard or the eight non-TWC market joins among its 12 priced rows.

## Handoff requests (no shared site/data files changed)

The audit output is restricted to `audits/ca621beb/**` plus coordination. Follow-up items are logged in [`COORDINATION.md`](../../COORDINATION.md):

1. The tested `/pickem/`, `/pickem/index.html`, and `/pickem/matches.html` routes return the expected board; both the root and Pick'em Flagged pages also loaded with the expected unresolved counts. The regenerated `5dd243e` root HTML includes the Pick'em nav anchor, and the post-PR #22 Pages deploy passed; keep the route smoke tests in place. The fetcher did not expose the nav header, so no browser click test was performed.
2. Replace the four bare HLTV match URLs in the archived d530 TWC fixture/model pages with slugged links and test them before those pages are reused.
3. Keep the archived VRS model clearly labeled as a derived hypothetical; correct its calibration/provenance language, link the Aug. 3 VRS input, align American/decimal odds treatment, and make its JS simulator match Python.
4. The separate 26-row `/pickem/` board now displays exact Polymarket links for its TWC rows, but does not display a per-market quote-read time. Persist the exact URL and capture timestamp in the raw source record, or leave that input blank/flagged. Do not confuse this older board with the new root dashboard's direct Bovada/Pinnacle snapshot.
5. Do not treat the remaining 81 blank rows, the other rows in the 93-fixture site, or the eight non-TWC quoted markets as independently audited by this report.

**Audit status:** complete. The corrected field/openers and HObbit entry are supported; the tested public routes and post-PR #13/#20/#22 deployment checks pass, and regenerated main HTML includes the Pick'em nav anchor. Remaining review items concern the archived d530 model, per-market quote-time provenance on legacy Polymarket rows, and unreviewed rows in the new integrated dashboard. No root model, table data, or shared dashboard files were edited by this audit.
