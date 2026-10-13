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
| `cs2.html` | All 87 CS2 pick'em fixtures: odds per source, derived no-vig probability, verification status, review flags |
| `lol.html` | LoL fixtures from the same lobby (external line collection not yet run for LoL) |
| `tournaments.html` + `tournament-*.html` | Coverage per tournament |
| `flagged.html` | Unverified rows, stale fixtures, unused bookmaker lines, rejected matches, source reachability, discrepancies, aliases |
| `methodology.html` | Sources with links, formulas, matching rules, limitations |

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
