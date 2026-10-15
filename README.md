# Pick'ems betting-line dashboard — HotSpawn lobby fixtures

**Live dashboard: https://buffedlizard55-lab.github.io/MaltaProj2/**

**Start with [all CS2 picks](https://buffedlizard55-lab.github.io/MaltaProj2/picks-every-match/).**
Use the [unresolved picks & limitations](https://buffedlizard55-lab.github.io/MaltaProj2/picks-every-match/unresolved.html) page for every unsupported row and its source-attempt ledger.
The landing executive summary links the canonical picks and unresolved list, with a blank probability
and its limitation. Expanded model boards are research with different standards, not verified
coverage. See the [fallback-source audit](https://buffedlizard55-lab.github.io/MaltaProj2/audits/5cd24fb4/)
for disputed identities and the unsupported use of other LFO rosters as a proxy for LFO 10.

An evidence-first table of every CS2 fixture currently offered by the HotSpawn Pick'ems lobby,
with **external betting lines** (never HotSpawn) and **derived no-vig probabilities**, plus an
explicit *Flagged for review* page for everything that could not be confirmed.

Not affiliated with HotSpawn or any bookmaker. HotSpawn is used for fixture discovery only. Its
crowd "picked %" is omitted from the current inventory and never used as a probability input; some
clearly dated archive sections preserve it as reference evidence.

## What the dashboard contains

| Page | Content |
|---|---|
| `index.html` | Every currently open CS2 pick first, coverage summary, lines, probabilities and timestamps |
| `cs2.html` | Exact lobby-embedded CS2 inventory split into open picks and listed-but-closed rows |
| `probabilities.html` | Mobile-first current picks; unpriced rows stay blank; closed rows are collapsed separately |
| `tournaments.html` + `tournament-*.html` | Coverage per tournament |
| `flagged.html` | Open gaps, stale fixtures, unused lines, rejected joins, access failures and discrepancies |
| `verify/7cd2e67a/index.html` | Independent line-by-line re-verification (session `7cd2e67a`): every published probability re-derived from its quoted odds, every estimate rating checked against Valve's official standings, and every external source read again with its URL and UTC read time |
| `methodology.html` | Sources with links, formulas, strict matching rules and limitations |
| `research.html` | Dated audits and alternate session boards, separated from current picks |
| `ourline/` (sub-site) | Session `f7279a54` board: all open CS2 fixtures, with eligible no-vig Pinnacle/Bovada/Melbet/Kalshi consensus first and a market-calibrated Valve VRS model only for unpriced matches with unambiguous ratings; absent evidence remains blank and flagged; the basis is labelled per row, plus a track record graded from HotSpawn final scores, a source link for every quote, and its own Flagged for review page. Refreshed about every 27 min by `.github/workflows/ourline-f7279a54.yml`, which then dispatches Pages |
| `strategy/` (sub-site) | **Start here on your phone (landing button "Open all CS2 picks").** Session `f28afd9e`: every CS2 match listed on the HotSpawn lobby with a **safe pick** (highest win probability from bookmaker/exchange lines, originated model only where no price exists) and a **leaderboard pick** (contrarian-but-not-stupid rules R1–R3 in `scripts/f28afd9e/strategy.py`: coin-flip fades, live-underdog swings, verified-context swings; max 3 swings/day). HotSpawn crowd % is used only as ownership. `strategy/unresolved.html` = unresolved picks & limitations + Flagged for review; `strategy/day1.html` = verified review of TWC day 1 (9z 2-0 Aurora, Aurora's July rebuild) with a backtest. Rebuilt every 4 h and after each lobby/board refresh by `.github/workflows/strategy-f28afd9e.yml` |
| `day3/` (sub-site) | Session `4cf64ea3` **day-2 review → day-3 picks desk.** `day3/index.html` is a mobile executive summary that links every updated picks list on the site; `day3/day1-day2.html` is the verified source-linked review of TWC day 1 (9z 2-0 Aurora upset at 4% crowd ownership; Aurora's July roster rebuild) and day 2 (Falcons 2-1 9z, Aurora 2-0 NIP, BETBOOM 2-1 PARIVISION, FURIA 2-1 Legacy — every map score linked to HLTV); `day3/picks.html` gives the day-3 group deciders (Aurora vs 9z, BETBOOM vs Legacy) both a **safe pick** and a **climb pick** from the contrarian ladder (30% "not stupid" floor, ≥2 verified context flags — roster change/onboarding/H2H/rest — and a quantified crowd differential), plus a pick and win probability for **every** open HotSpawn CS2 match with per-row sources; `day3/unresolved.html` is the separate unresolved-picks + limitations section (incl. the pre-emptive BETBOOM-Legacy originated line, because no book prices it yet and HotSpawn has not listed it); `day3/flagged.html` and `day3/method.html` carry the caveats and formulas. Probabilities are re-derived from retained raw quotes (Melbet / Kalshi / Thunderpick-via-bo3.gg) or the calibrated Valve-VRS curve — HotSpawn crowd % is ownership only. Refreshed every 4 h by `.github/workflows/day3-4cf64ea3.yml` |
| `audits/6c5bb3d6/` (audit) | **Independent line-by-line verification of the picks — read this before trusting any number.** Session `6c5bb3d6` re-verifies the published boards instead of adding another one: official Valve standings re-fetched from Valve's own repository (every `VRS #N (M pts)` citation re-checked), **every published probability re-derived from its retained raw bookmaker quote** (Pinnacle / Bovada / Melbet LineFeed / Kalshi / Thunderpick-via-bo3.gg), the two contested identities re-proven from official rosters (WROTBERRY→WBT 5/5 and RoundsGG→ROUNDS 5/5, with the residual limitation published), the day-1 backtest recomputed from its settled rows, and the **leaderboard differential `points × (probability − crowd ownership)` recomputed independently** for every open fixture. `index.html` = verification summary + the day-1 upset review (9z 2-0 Aurora at 4% ownership) + roster/onboarding intel + executive links to every picks board, `flagged.html` = 13 flagged items with source links incl. the 4 values left blank, `method.html` = formulas and all sources with UTC read times, `report.json` = machine-readable. HotSpawn crowd % is ownership only and never a probability (check C6 proves it). Re-verified every 6 h and after each board refresh by `.github/workflows/verify-6c5bb3d6.yml`; harness `scripts/6c5bb3d6/`, tests `tests/test_6c5bb3d6.py` |
| `picks-every-match/` (sub-site) | **Start here on mobile.** All lobby-listed CS2 fixtures. Market-first picks, a labelled Valve rating-model fallback only for uncovered fixtures, otherwise blank + flagged. Same strict engine as `ourline/`; no sibling/floor ratings, ambiguous-slot joins or forced 50/50s. Four-hour automated collection, provider-response replay gate, search/filter, browser expiry, full inventory and evidence exports. |
| `picks-all/` (sub-site) | Session `b5436cf0` **complete picks** — a pick and win probability for *every* open CS2 match on the HotSpawn pick'em lobby, including low-tier matches no bookmaker prices, in three labelled layers: **M** bookmaker/exchange market line, **R** research-resolved (HLTV first, then esportsbooks, then esports betting lines; each fact dated with its URL), **O** originated model line (Valve VRS / own Elo). `picks-all/unresolved.html` is the dedicated unresolved-picks section with each gap's limitations (also linked from the executive summary); `picks-all/flagged.html` carries irregularities (e.g. name/price order reversals in stored Kalshi quotes, verified live before publishing); `picks-all/method.html` documents the protocol. HotSpawn is fixture discovery + settlement only — its crowd % is never a probability input. Refreshed every 4 hours by `.github/workflows/allpicks-b5436cf0.yml` |
| `board/` (sub-site) | Session `fe803b80` full-coverage picks board, reached from the landing page's executive summary and the header nav (**All picks · every match**). `board/index.html` is the executive summary, `board/picks.html` gives **every** open CS2 fixture a pick, a probability, a confidence label and the basis it uses (`market`, `market+model`, or an explicitly labelled *originated* line), `board/lines.html` shows the raw quotes behind each market row, `board/tournaments.html` groups them by event, `board/results.html` grades published picks against HotSpawn final scores, `board/flagged.html` lists alias joins, originated lines, rejected prices and access failures with links, `board/method.html` documents formulas, weights, tolerances and limits. Prices come from Pinnacle, Bovada, Melbet (and its 1xBet-platform mirrors), Kalshi and the Thunderpick coefficients bo3.gg publishes per fixture; where no reachable bookmaker prices a match the line is originated from the official Valve regional standings (VRS) or, failing that, this project's own Elo over bo3.gg published results and its published world ranking. HotSpawn is discovery and settlement only. Refreshed by `.github/workflows/board-fe803b80.yml` (30-minute cron, self-dispatching chain, contract tests before publish) |
| `exec/` (sub-site) | Session `b1fb1465` mobile-first **executive summary** plus a pick and a win probability for **every** open HotSpawn CS2 fixture. `exec/index.html` is the front door with in-site links, `exec/picks.html` gives one card and one row per open fixture with per-row source links, `exec/unresolved.html` is the required separate **Unresolved picks & limitations** section (what was tried per fixture — HLTV first, then esportsbooks and esports betting lines, then the documented Valve VRS fallback — with the HTTP status every source answered and every refused quote), `exec/sources.html` is the source ledger with UTC read times and the reviewed name decisions, `exec/flagged.html` collects thin books, name decisions, rejected joins and access refusals, and `exec/method.html` documents the join, precedence and formulas. Names are never merged without a reviewed record: each global alias and each per-fixture label call (Kalshi/bo3.gg titles vs HotSpawn/HLTV) carries a note and evidence URLs, and verifier rules R1–R14 fail the build if a row loses its source link, its flag or its evidence. Prices come from Pinnacle, Bovada, the Melbet/1xBet-platform LineFeed, the Kalshi exchange and the Thunderpick coefficients bo3.gg publishes per fixture; HotSpawn is discovery and settlement only and its crowd pick percentage is never read. Refreshed every 4 hours by `.github/workflows/exec-b1fb1465.yml` |
| `fresh/` (sub-site) | Session `dd2b7fee` mobile-first pick board (landing + CS2 board + flagged + method). Probabilities originate exclusively from Bovada / Pinnacle / Kalshi lines captured in-session (see `data/dd2b7fee/lines_snapshot.json`); HotSpawn crowd % is not even displayed there. Re-rendered hourly by `.github/workflows/fresh-dd2b7fee.yml` |
| `summary/` (sub-site) | Session `c0e223d3` **verification companion**. Mobile-first: (1) where to find the picks (links every board, with the every-match board first), (2) an independent cross-check of every pick against the every-match board, (3) the official-source evidence behind the matches with no bookmaker price, (4) sources, method and a line-by-line repository review. Rebuilt hourly by `.github/workflows/summary-c0e223d3.yml` |
| `coverage/` (sub-site) | Session `6ddde224` full-lobby coverage board — every CS2 fixture the HotSpawn lobby lists, each row carrying either a two-sided bookmaker line, a Kalshi exchange quote inside the spread gate, an explicitly labelled originated Bradley-Terry estimate, or a blank row published on the Flagged-for-review page, plus a repo-review/re-reads page and a method page. HotSpawn crowd % is never a probability input. Re-rendered hourly by `.github/workflows/coverage-6ddde224.yml` |
| `unresolved/` (sub-site) | **Session `7177d07f` — picks for every match, with the limitation published.** Every open HotSpawn CS2 fixture in one mobile list: `index.html` is the executive summary (where the picks are + a pick and win probability for all 28 open fixtures, each labelled with its basis), `flagged.html` lists unresolved/contested rows and the team-identity evidence (WROTBERRY→WBT, RoundsGG→ROUNDS, Envy→3DMAX roster, LFO 10's contested rating), `method.html` documents the resolution ladder — featured bookmaker line first, then HLTV research, esportsbook/exchange prices (Melbet, Thunderpick via bo3.gg, Kalshi) and the official Valve regional standings — and `repo-audit.html` is the line-by-line repository review. Rows no route can resolve stay blank and are listed with the reason; nothing is defaulted to 50/50. Refreshed every 4 hours by `.github/workflows/unresolved-7177d07f.yml` |

## Data and evidence

| File | Meaning |
|---|---|
| `data/hotspawn_matches.json` | Exact `/api/v1/fixtures` response embedded in the public lobby render, normalized without crowd percentages |
| `data/odds.json` | Raw quotes per source, with source URLs, ids and retrieval timestamps |
| `data/lines.json` | Fixtures joined to quotes, with derived no-vig probabilities, open/closed state and flags |
| `evidence/hotspawn_probe.json` | Lobby response hash/cache age, counters, exact ids, fields and published-permalink coverage |
| `evidence/*.json` | Source reachability, matching decisions and bounded raw quote payload evidence |
| `audits/1d4de836/**` | Independent audit of the lobby snapshot (session `1d4de836`) |

## Pipeline

`.github/workflows/update-data.yml` runs on every relevant main-branch push and hourly:

1. `scripts/fetch_hotspawn.py` — exact fixture response and published permalink map from the public
   Angular lobby transfer-state at `https://play.hotspawn.com/lobby`. Malformed/ambiguous state fails
   closed and retains the prior inventory; HTTP cache age is preserved.
2. `scripts/collect_odds.py` — external lines: Pinnacle (licensed bookmaker, public guest odds API),
   Bovada (licensed bookmaker, public coupon JSON), Polymarket (public markets; stale CS2 markets are
   filtered out), plus reachability probes for further candidate sources.
3. `scripts/build_lines.py` — strict fixture⇄quote matching and proportional no-vig derivation.
4. `scripts/build_site.py` — renders the static dashboard and refuses to write if an internal link
   would break.

Sources, derivation rules and every rejection are recorded in `evidence/` so the numbers can be
reproduced and audited. Nothing is inferred: a fixture without a confirmed external price renders
blank and is listed on the Flagged for review page.

## LineWatch audited snapshot and shared publication

LineWatch remains available at https://buffedlizard55-lab.github.io/MaltaProj2/docs/ with the independent 86-record source audit, two dated Thunderpick reference markets, original fair-line arithmetic, row-level review flags, CSV/JSON and collection health. Current odds in this stricter snapshot remain blank where current-market joins and freshness are not verified. This does not imply no prices exist in the separate integrated root pipeline.

The Pages workflow now stages all session-owned root HTML/assets/data/evidence/audits **plus** `docs/` and `pickem/`. It waits for the legacy build before deploying the combined artifact. This supersedes the earlier docs-only artifact that hid other sections and the subsequent verification-only workflow. No root or pickem source generator is replaced; their data provenance remains their own. Local navigation is checked across the complete artifact and live LineWatch content is checked after deployment with bounded CDN-propagation retries.

## Current pipeline safety policy (2026-10-14, re-audited by 58cb2600)

The current root **CS2** and **Probabilities** tables supersede the earlier combined
snapshot for current picks. The inventory is the exact fixture response embedded by the
public lobby, not a status-based guess from the much larger direct API response. Current
probabilities use only source-linked Pinnacle/Bovada full-match moneylines with explicit
CS2 identity, confirmed participant/outcome alignment, exact UTC kickoff, a unique
fixture/source join, an open prematch market and an upcoming fixture whose pick lock has
not passed. Quote and cache-adjusted fixture observation age must each be at most
**four hours**. There is no tournament-token fallback.

Hourly GitHub Actions collection requires no user input. It publishes root HTML,
assets, JSON and evidence in one commit; errors in computation or rendering block
publication. Every Pages render also recalculates quote eligibility. Sources can
still be unavailable, and missing evidence leaves probabilities **blank**.
A higher no-vig probability is labeled as the pick; this is a model estimate, not
an official forecast, guarantee, or independently validated predictive accuracy.

- Current reproducible data: `data/current_probabilities.json`, `data/lines.json`.
- Quote/participant/market payloads and failures: `evidence/odds_collection.json`.
- Rejected joins: `evidence/matching_evidence.json`.
- Current audit: [`audits/d4ec32a9/REPORT.md`](audits/d4ec32a9/REPORT.md).
- Tests: `python -m unittest discover -s tests -v`.

All prior third-party and model data, `docs/`, `pickem/` and independent audit
sections are preserved as dated research.

## Independent re-verification (session 7cd2e67a, 2026-10-14)

`scripts/7cd2e67a/verify_published_boards.py` re-checks what the boards already publish, without
trusting it: it re-derives every no-vig probability from the odds stored next to it, re-reads Valve's
official `standings_global_2026_10_05.md` and confirms every originated-estimate rating is a real row
of that file, re-reads the HotSpawn lobby, and re-reads each external source the boards cite. Results
and every irregularity are published on `verify/7cd2e67a/index.html` with the source URL and the UTC
read time for each check. Findings are published as flags, never filled in.

Two defects were found and repaired in the same session:

1. **Per-row HotSpawn links were not per-match links.** The inherited collectors emitted
   `https://www.hotspawn.com/matches/<fixture id>` on every row; fetching that route returns
   HotSpawn's general matches index, not the match page. Rows now use the permalink HotSpawn itself
   publishes on the lobby page, or the official lobby page when HotSpawn publishes no per-match page
   for that fixture. No slug is ever constructed.
2. **The landing page counted locked and past fixtures as coverage.** The KPI cards and the landing
   table now lead with the fixtures that are still open for picks, and the locked/past count is
   published separately.

Regression tests: `python -m unittest tests.test_verify_7cd2e67a -v`. They do **not** enter current picks,
and are not universally re-verified by this session. LoL inventory is retained,
but current primary-bookmaker LoL probabilities remain blank in this CS2-focused
pipeline. Full fixture coverage does not mean every match has a confirmed price.

## 15 October 2026 integration audit

One canonical mobile entry point is published at `picks-every-match/`; alternative boards
remain available under collapsed research navigation, not as competing recommendations.
Source attempts are attached only to rows without an accepted market line. HLTV first,
then esportsbooks/exchange evidence, then an eligible uniquely identified Valve rating pair;
unsupported rows retain blank probabilities and a limitation, never an invented percentage.

[Flagged for Review: source and repository audit](https://buffedlizard55-lab.github.io/MaltaProj2/audits/3faf40e8/)
records the ROUNDS roster gap, WBT/Academy conflict, blocked pages, cached-render limitations,
and restricted GitHub Pages-settings permissions. The four-hour collector preserves source
observations; a rebuild does not make old odds fresh. Unit contracts, primary-response replay
and 320/390/768/1280px browser checks gate the checked Pages artifact. Archived boards are
not certified by the canonical verifier and never override its blank rows.

## Every-match 5/5 HLTV & Valve VRS resolution & line-by-line audit (session 94b3d48a, 2026-10-15)

- **Executive Summary & Every-Match CS2 Picks:** [`audits/94b3d48a/index.html`](audits/94b3d48a/index.html)
- **Unresolved Picks & Limitations Ledger:** [`audits/94b3d48a/unresolved.html`](audits/94b3d48a/unresolved.html)
- **Flagged for Review (Line-by-Line Audit & 36-Team VRS Ledger):** [`audits/94b3d48a/flagged.html`](audits/94b3d48a/flagged.html)
- **Methodology & 4-Hour Refresh Schedule:** [`audits/94b3d48a/methodology.html`](audits/94b3d48a/methodology.html) (`scripts/94b3d48a/build.py`, `.github/workflows/refresh-94b3d48a.yml`, `tests/test_94b3d48a.py`).


## TWC 2026 Day 1–3 review & Day 3 picks (session 869a5375)

- **Executive summary & Day 3 picks:** [`twc/index.html`](twc/index.html) — Day 1 (9z 2–0 Aurora upset, Aurora July 2026 rebuild) and Day 2 results verified line-by-line on HLTV (event 8932), derived group standings, and a safe + contrarian-but-not-stupid leaderboard pick for every Day 3 decider (16 Oct 2026): Aurora vs 9z (HotSpawn card 1080205, market 65/35, leaderboard pick 9z) and BetBoom vs Legacy (research pick Legacy, probability blank — see unresolved).
- **Unresolved picks & limitations:** [`twc/unresolved.html`](twc/unresolved.html) (U-TWC1–U-TWC7: no verified BetBoom–Legacy line, no HotSpawn card for that match in the captured lobby, kick-off-time and ranking-system conflicts, TBD playoff fixtures, roster/rest limits, leaderboard-optimality limits).
- **Method & contrarian rules:** [`twc/method.html`](twc/method.html) (`data/869a5375/twc.json`, `scripts/869a5375/build.py`, `tests/test_869a5375.py`, `.github/workflows/twc-869a5375.yml` — rebuilt every 4 hours; live lines refresh via the strategy/picks-every-match collectors).
