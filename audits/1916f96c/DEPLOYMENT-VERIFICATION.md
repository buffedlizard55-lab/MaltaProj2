# Publication verification — independent audit session

Verified 2026-10-13 after final integration; this records publication status, **not complete current odds coverage**.

- Final integration [PR #8](https://github.com/buffedlizard55-lab/MaltaProj2/pull/8) API reports `state=closed`, `merged=true`, `merged_at=2026-10-13T18:03:43Z`.
- Main publication [Actions run 38443703250](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38443703250) reports `status=completed`, `conclusion=success`, head `3d2dafad730f5ab87d2f0cc502ac71dcb8b417b8`.
- Watched this run to completion. Build passed preserved-source tests, independent audit handoff checks, public refresh attempt, generated-site/link checks and browser smoke tests. The `Deploy to GitHub Pages` step completed successfully. A successful refresh *attempt* does not establish successful bookmaker odds ingestion.
- Cache-busted public root read through `fetch_page` returned title `A clearer view of the lines. · LineWatch`, **86 embedded fixtures, 27 visible cards, 0 current probabilities, 2 reference markets**. [Observed public root](https://buffedlizard55-lab.github.io/MaltaProj2/?audit=38443703250).
- Public reference table returned title `External lines · LineWatch`, correct source-linked +280/-455 and -1250/+530 pairs, derived probabilities 24.30%/75.70% and 85.37%/14.63%, original observed date 2026-10-13, and prominent freshness/identity/phase limitations. [Observed reference page](https://buffedlizard55-lab.github.io/MaltaProj2/odds.html?audit=38443703250).
- Public review page returned title `Flagged for Review · LineWatch`, findings F01–F14 plus source-linked per-fixture verification gaps. It explicitly documents no current probabilities, incomplete coverage, stale/source-time concerns, LoL uncertainty, sportsbook access limits and the excluded hypothetical concurrent model. [Observed review page](https://buffedlizard55-lab.github.io/MaltaProj2/flags.html?audit=38443703250).
- Original independent report was accepted into the integration branch without overwriting shared files. Redundant contribution [PR #5](https://github.com/buffedlizard55-lab/MaltaProj2/pull/5) was closed, not merged. The integration owner's board records copying only `audits/1916f96c/**` and six passing independent tests.

## User-facing links

- [Dashboard](https://buffedlizard55-lab.github.io/MaltaProj2/)
- [Match directory](https://buffedlizard55-lab.github.io/MaltaProj2/matches.html)
- [External reference lines](https://buffedlizard55-lab.github.io/MaltaProj2/odds.html)
- [Flagged for Review](https://buffedlizard55-lab.github.io/MaltaProj2/flags.html)

## Remaining scope limits

This establishes a deployed evidence-first dashboard, not a fully priced live feed. Current match probabilities remain blank. Only two dated sportsbook reference pairs have been independently read. Automatic current sportsbook adapters, verified complete cross-game inventory, and fully timestamped event/market joins are still unverified and published as review findings. No unsupported prices were supplied to make the table appear complete.
