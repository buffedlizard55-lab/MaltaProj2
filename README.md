# Pick'ems betting-line dashboard — HotSpawn lobby fixtures

**Live dashboard: https://buffedlizard55-lab.github.io/MaltaProj2/**

**Start with [source-linked CS2 picks](https://buffedlizard55-lab.github.io/MaltaProj2/cs2.html).**
The landing executive summary separately lists every unresolved strict row, with a blank probability
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
| `picks-every-match/` (sub-site) | **Start here on mobile.** Every open lobby-listed CS2 fixture: eligible external market first; unique, fresh Valve rating-model fallback only when no market is eligible; otherwise blank and flagged. No sibling/floor ratings or ambiguous slot-price transfers. Row-level expiry hides stale picks. Scheduled twice hourly by `.github/workflows/every-match-c64a5e19.yml`; source/Actions delays are possible. |
| `board/` (sub-site) | Session `fe803b80` full-coverage picks board, reached from the landing page's executive summary and the header nav (**All picks · every match**). `board/index.html` is the executive summary, `board/picks.html` gives **every** open CS2 fixture a pick, a probability, a confidence label and the basis it uses (`market`, `market+model`, or an explicitly labelled *originated* line), `board/lines.html` shows the raw quotes behind each market row, `board/tournaments.html` groups them by event, `board/results.html` grades published picks against HotSpawn final scores, `board/flagged.html` lists alias joins, originated lines, rejected prices and access failures with links, `board/method.html` documents formulas, weights, tolerances and limits. Prices come from Pinnacle, Bovada, Melbet (and its 1xBet-platform mirrors), Kalshi and the Thunderpick coefficients bo3.gg publishes per fixture; where no reachable bookmaker prices a match the line is originated from the official Valve regional standings (VRS) or, failing that, this project's own Elo over bo3.gg published results and its published world ranking. HotSpawn is discovery and settlement only. Refreshed by `.github/workflows/board-fe803b80.yml` (30-minute cron, self-dispatching chain, contract tests before publish) |
| `fresh/` (sub-site) | Session `dd2b7fee` mobile-first pick board (landing + CS2 board + flagged + method). Probabilities originate exclusively from Bovada / Pinnacle / Kalshi lines captured in-session (see `data/dd2b7fee/lines_snapshot.json`); HotSpawn crowd % is not even displayed there. Re-rendered hourly by `.github/workflows/fresh-dd2b7fee.yml` |
| `summary/` (sub-site) | Session `c0e223d3` **verification companion**. Mobile-first: (1) where to find the picks (links every board, with the every-match board first), (2) an independent cross-check of every pick against the every-match board, (3) the official-source evidence behind the matches with no bookmaker price, (4) sources, method and a line-by-line repository review. Rebuilt hourly by `.github/workflows/summary-c0e223d3.yml` |
| `coverage/` (sub-site) | Session `6ddde224` full-lobby coverage board — every CS2 fixture the HotSpawn lobby lists, each row carrying either a two-sided bookmaker line, a Kalshi exchange quote inside the spread gate, an explicitly labelled originated Bradley-Terry estimate, or a blank row published on the Flagged-for-review page, plus a repo-review/re-reads page and a method page. HotSpawn crowd % is never a probability input. Re-rendered hourly by `.github/workflows/coverage-6ddde224.yml` |

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
