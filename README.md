# LineWatch — Hotspawn pick’em source audit

**Dashboard:** https://buffedlizard55-lab.github.io/MaltaProj2/

An evidence-first static directory, external-odds reference analysis, and transparent review queue. Not affiliated with Hotspawn or a bookmaker.

## What is implemented

- Automatic parsing of the public lobby's Angular `ng-state` fixture response; source IDs, explicit UTC timestamps, sport and per-row official links.
- All 86 embedded records and 27 rendered cards in the preserved hosted-runner observation. This is not proof of complete cross-game coverage. Live runs may differ.
- Searchable directory, visibility filter, CSV/JSON downloads, source-health report, methodology and row-level Flagged for Review page.
- Two externally observed Thunderpick Match Winner markets, with our reproducible proportional no-vig reference calculations. **Not current predictions.**
- Hourly GitHub Actions refresh attempts and Pages deployment, with fail-closed collection, retained previous snapshot, automated arithmetic/parser/provenance/link tests.

## Deliberately not claimed

A complete, up-to-date externally priced list has **not** been achieved. Bookmaker direct collection returned a Cloudflare 403. The two reference observations lack provider quote timestamps and validated cross-source event joins. Current odds/probability cells therefore stay blank for every fixture. Hotspawn crowd-pick percentages are never used by the model or imported into normalized data. A successful HTTP probe is not a validated odds adapter.

The public source also contains stale records marked scheduled, cached responses, and a six-minute payload lock offset versus the five-minute help-page rule. These findings are published on the review page, not hidden.

## Reproduce

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r scripts/requirements.txt
python -m unittest discover -s tests -v
python scripts/collect.py     # public network required; failures preserve snapshot
python scripts/build.py
python -m http.server 8000 --bind 0.0.0.0 --directory docs
```

Offline evidence replay: `python scripts/collect.py --fixture docs/evidence/probe/lobby.txt`.

## Provenance

- [Official lobby](https://play.hotspawn.com/lobby): public rendered cards and embedded `/api/v1/fixtures` body. The permalink map is read from the page, not requested from its admin-named URL. No login or private endpoint discovery is required.
- [Official rules](https://play.hotspawn.com/how-it-works).
- [9z Team / Aurora bookmaker market](https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/9z-team-vs-aurora/2796376).
- [Astralis / Sashi bookmaker market](https://thunderpick.io/esports/cs2-betting/pulse-beat-iii/11173/astralis-vs-sashi/2767822).
- [HLTV analytics](https://www.hltv.org/betting/analytics): inspected secondary source, not a verified pricing input.

`docs/evidence` contains public HTML saved as inert `.txt`, selected-field extracts, and sanitized HTTP headers. No session cookies are needed. `docs/data` separates source fixture facts, quote observations and collection health. Reference quotes remain dated and are not overwritten by a new build. Deployed refreshes are artifacts, not automatic commits to main; the repository retains the reviewed baseline. Workflow run artifacts and the live JSON provide the latest generated snapshot.

## Verification scope

Tests verify source parsing, exact fixture values against preserved HTML, odds arithmetic, missing-data behavior, official links on every generated table row, and all local links/anchors. They do not certify every external URL is reachable or that a source is factually correct. No aliases, future years, market identities, live states or missing prices are inferred. See `COORDINATION.md` for integration and release history.

## Parallel publication retained for review

Another session merged PR #7 while this integration was active. Its root-level TWC model and datasets remain in Git, and its [original README is preserved](docs/evidence/parallel-898abb4f-readme.md). Those outputs are **not** source-verified inputs to LineWatch. They describe hypothetical pairings and unsupported claims of absent bookmaker lines that conflict with this session's observed explicit markets. See the LineWatch Flagged for Review page; do not mistake the parallel model for current verified pick’em pricing.
