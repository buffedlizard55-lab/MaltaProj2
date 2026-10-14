# Pick'ems betting-line dashboard — HotSpawn lobby fixtures

**Live dashboard: https://buffedlizard55-lab.github.io/MaltaProj2/**

An evidence-first table of every CS2 fixture currently offered by the HotSpawn Pick'ems lobby,
with **external betting lines** (never HotSpawn) and **derived no-vig probabilities**, plus an
explicit *Flagged for review* page for everything that could not be confirmed.

Not affiliated with HotSpawn or any bookmaker. HotSpawn is used for fixture discovery only — its
crowd "picked %" is shown for reference and is never used as a probability input.

## What the dashboard contains

| Page | Content |
|---|---|
| `index.html` | Coverage summary, method in short, matches with verified lines, timestamps |
| `cs2.html` | Automatically observed CS2 fixture inventory: odds per source, derived no-vig probability, verification status, review flags |
| `lol.html` | LoL fixtures from the same lobby (external line collection not yet run for LoL) |
| `tournaments.html` + `tournament-*.html` | Coverage per tournament |
| `flagged.html` | Unverified rows, stale fixtures, unused bookmaker lines, rejected matches, source reachability, discrepancies, aliases |
| `verify/7cd2e67a/index.html` | Independent line-by-line re-verification (session `7cd2e67a`): every published probability re-derived from its quoted odds, every estimate rating checked against Valve's official standings, and every external source read again with its URL and UTC read time |
| `methodology.html` | Sources with links, formulas, matching rules, limitations |
| `fresh/` (sub-site) | Session `dd2b7fee` mobile-first pick board (landing + CS2 board + flagged + method). Probabilities originate exclusively from Bovada / Pinnacle / Kalshi lines captured in-session (see `data/dd2b7fee/lines_snapshot.json`); HotSpawn crowd % is not even displayed there. Re-rendered hourly by `.github/workflows/fresh-dd2b7fee.yml` |

## Data and evidence

| File | Meaning |
|---|---|
| `data/hotspawn_matches.json` | Fixture list from the lobby's public API (`/api/v1/fixtures`) |
| `data/odds.json` | Raw quotes per source, with source URLs, ids and retrieval timestamps |
| `data/lines.json` | Fixtures joined to quotes, with derived no-vig probabilities and flags |
| `evidence/*.json` | Probes: API discovery, source reachability, matching decisions, raw payload samples |
| `audits/1d4de836/**` | Independent audit of the lobby snapshot (session `1d4de836`) |

## Pipeline

`.github/workflows/update-data.yml` runs on every relevant push and every 3 hours:

1. `scripts/fetch_hotspawn.py` — lobby fixtures from the reverse-engineered public API
   (`https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures`).
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

## Current pipeline safety policy (2026-10-13, d4ec32a9)

The current root **CS2** and **Probabilities** tables supersede the earlier combined
snapshot for current picks. They use only source-linked Pinnacle/Bovada full-match
moneylines with explicit CS2 identity, confirmed participant/outcome alignment,
exact UTC kickoff, a unique fixture/source join, an open prematch market and an
upcoming fixture whose pick lock has not passed. Quote and fixture observation age
must each be at most **four hours**. There is no tournament-token fallback.

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
