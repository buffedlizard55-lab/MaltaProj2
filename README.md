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

---

# Pick'em line reconstruction — priced board at `/pickem/` (session `a0fcf175`)

Complementary deliverable to the audit dashboard above: the **26 fixtures that were open for picks** at
snapshot time, each priced from **external markets only** and converted into our own de-margined line.

* **Board:** https://buffedlizard55-lab.github.io/MaltaProj2/pickem/ (7 pages: dashboard, all matches,
  by tournament, analysis, methodology, flagged for review, sources)
* **Dataset:** `data/pickem_pool.json` (26 rows, per-row source links, captured prices, derived lines,
  tournament pool counts, 14 flagged items) and `data/keys.json`
* **Pipeline:** `scripts/build_pickem_lines.py` (captured values sit next to the URL they came from;
  regenerates `data/**` and `pickem/**`), `scripts/check_links.py` (0 broken local links, 138 external
  source links)

## Method

`p_i = (1/o_i) / Σ_j(1/o_j)` for bookmaker decimals, `p_i = c_i / Σ c_j` for prediction-market cents;
our line = equal-weight average of the available de-margined sources; fair odds = `1/p`. Hotspawn's
crowd percentage is displayed for context and is **never** part of any probability.

## Coverage (2026-10-13 UTC snapshot)

* 25/26 rows carry a line; `FORZE Reload vs LFO 10` is deliberately blank and flagged (no market pairs
  those two teams).
* 22 rows priced from EGamersWorld's `Bets on <event> by bc.game` modules, 20 from Polymarket CS2
  markets, 17 from both.
* Kickoffs are true UTC from the lobby payload's `scheduled_start` epoch (evidence:
  `audits/1d4de836/lobby-snapshot-audit.json`, already in this repository), cross-checked against all
  26 HLTV match pages. Hotspawn's rendered clock reads 4 h earlier (US Eastern); Polymarket's Elisa
  clocks read 4 h earlier again — both are published on the Flagged page, not silently corrected.
* Corrections logged on the Flagged page: the `RoundsGG vs Voca` price mapping was double-flipped in a
  first build and is corrected; the two ESL Challenger League fixtures now carry their HLTV match pages
  (2399204, 2399232); Elisa bc.game lines were completed on re-check (WBT–EAC refined to the page's own
  1.989/1.722); the WROTBERRY/WBT alias gained direct evidence (EGamersWorld team URL slug `wrotberry`).

## Build

```sh
python3 scripts/build_pickem_lines.py   # regenerates data/** and pickem/**
python3 scripts/check_links.py          # verifies pickem/ has no broken local links
```


---

## Parallel root dashboard (session 898abb4f, corrected by arena/8c3d79a6 on 2026-10-13)

The repository root (`index.html`, `lines.html`, `teams.html`, `methodology.html`, `hotspawn.html`, `flagged.html`) contains a separate originated-lines dashboard for the Thunderpick World Championship 2026 Malta Finals. It is **derived model output, not verified bookmaker pricing**. Re-verified 2026-10-13: groups/Oct 14 openers published (HLTV Oct 9/12), **Virtus.pro withdrew → Ninjas in Pyjamas replaced them** (previous VP lines superseded), all 28 pairwise + 8 outright lines regenerated from Valve VRS Oct 5. Current finalists (VRS Oct 5): Legacy #2 1931 (34.0% / 2.67), Falcons #6 1843 (31.1% / 2.92), FURIA #7 1829 (17.4% / 5.22), Aurora #9 1716 (7.5% / 12.16), BetBoom #11 1596 (3.8% / 23.74), 9z #17 1543 (3.5% / 26.34), NiP #18 1534 (1.5% / 60.22), PARIVISION #36 1411 (1.2% / 77.02). Bookmaker match odds in the root dashboard remain blank/unverified except the flagged Thunderpick reference observation in `docs/data/quotes.json` (reference only) and a secondary FreeTips outright table in `data/external_outrights_snapshot.json` (no attribution). IRREG-007…012 on the root Flagged page do not block merge. The `/pickem/` board (PR #11) and LineWatch `docs/` site are preserved untouched.
