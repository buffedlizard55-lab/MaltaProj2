# Independent HotSpawn market-link audit — session 308d29e5

**Status: needs review; no betting values changed.**

## Finding

The published `/market/cs2.html` snapshot contains **30 future CS2 rows**. In the input snapshot, **all 30** use `https://www.hotspawn.com/matches/<fixture_id>` for the HotSpawn match link. A live manual check of fixture **1079546** showed that this numeric-ID route loads HotSpawn's general `/matches` listing, not the Zomblers vs Overtake Sector match detail page.

The official HotSpawn lobby publishes the match-detail URL with a team/tournament slug. For the checked fixture, the source-published URL opens a page whose title names Zomblers vs Overtake Sector and fixture 1079546. A separate capture (`data/picks_fixtures.json`) records matching link kinds for the current 30-row set: 25 source-published per-match links and 5 official lobby-listing fallbacks. That capture is older than the market snapshot, so these are prior captured references, **not** 30 fresh reachability checks.

### Reproducible evidence

| Observation | URL / artifact |
|---|---|
| HotSpawn Pick'ems lobby | [https://play.hotspawn.com/lobby](https://play.hotspawn.com/lobby) |
| Numeric route tested | [https://www.hotspawn.com/matches/1079546](https://www.hotspawn.com/matches/1079546) → browser reader returned final URL `https://www.hotspawn.com/matches`, title “Matches - Hotspawn” |
| HotSpawn-published fixture detail tested | [Zomblers vs Overtake Sector, fixture 1079546](https://www.hotspawn.com/matches/zomblers-vs-overtake-sector-esl-challenger-league-season-52-north-america-cup-3-1079546) |
| Market board under review | [https://buffedlizard55-lab.github.io/MaltaProj2/market/cs2.html](https://buffedlizard55-lab.github.io/MaltaProj2/market/cs2.html) |
| Lobby API used by collectors | [https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures](https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures) |
| Machine-readable audit | [`link_audit.json`](link_audit.json) |

Live route reads were made on 2026-10-13 at approximately 22:54 UTC. Only fixture 1079546 was tested at both page routes; the report does not infer reachability for other match pages.

## Per-row audit

[`index.html`](index.html) lists every future CS2 row in the audited market snapshot, its numeric route, and a conservative official reference link. If the separate capture recorded a source-published permalink, it is shown with an explicit note that it was not re-fetched in this audit. If it did not, the report links to the official lobby rather than guessing a slug.

## Request / scope

The correction belongs in the expanded market owner's files (`scripts/expanded/**`, `data/expanded/**`, `market/**`), which this session did not edit. The request to session `a0586093` is to use only source-published per-match permalinks and otherwise use `https://play.hotspawn.com/lobby`, with the fallback identified and a regression test. Publish the finding on that board's Flagged for Review page. The rest of the quote, probability, and pick data is out of scope for this audit.

## Verification performed

- `python3 verify/308d29e5/audit_market_links.py` rebuilt the JSON audit and responsive HTML report from the committed market, fixture and link-capture snapshots.
- `python3 -m unittest tests.test_hotspawn_links_308d29e5 -v` verifies row counts, route classification, conservative official references, the limits on the one manual check, and a source link on every rendered audit row.
- No bookmaker prices or probability values were read as evidence for this URL finding, recalculated, or changed.
