# Independent verification audit — 1d4de836

Audit date: 2026-10-13 UTC. This is an evidence handoff, not a completed match collection or an endorsement of any listed provider.

## Findings

| Item | Finding | Verification status | Source for manual review |
|---|---|---|---|
| Hotspawn lobby | HTTPS access failed from the sandbox. No lobby content, match identifiers, teams, start times, or pick-em rules were read. | Unverified | https://play.hotspawn.com/lobby |
| HLTV matches | HTTPS access failed. No schedule or team statistics were read. HLTV odds must not be presented as directly verified bookmaker quotes without following their bookmaker source. | Unverified | https://www.hltv.org/matches |
| Pinnacle candidate source | HTTPS access failed. No markets or odds were read; availability, region, authentication, and collection permissions are unknown. | Unverified | https://www.pinnacle.com/en/esports |
| Betway candidate source | HTTPS access failed. No markets or odds were read; availability, region, authentication, and collection permissions are unknown. | Unverified | https://betway.com/en/sports/esports |
| The Odds API candidate documentation | HTTPS access failed. No documented coverage, pricing, or API contract was verified. An aggregator is not a bookmaker's official source. | Unverified | https://the-odds-api.com/liveapi/guides/v4/ |
| Existing Pages configuration | GitHub API returned `build_type: legacy`, source `main` at `/`, and `status: built`. This describes the pre-change configuration only, not deployment of the new dashboard. | Verified configuration at audit time | https://api.github.com/repos/buffedlizard55-lab/MaltaProj2/pages |
| Concurrent work | Other live session branches contained overlapping claims. Coordination issue opened. No application, ingestion, or integration files were modified by this session. | Verified repository observation at audit time | https://github.com/buffedlizard55-lab/MaltaProj2/issues/1 |

See `access-evidence.json` for attempt timestamps and exact errors, `pages-api-evidence.json` for the API response, and `branches-evidence.json` for branch observations. A connection failure here is **not** evidence that the website is down. Candidate source links are not verified current market URLs.

## Handoff requirements for final integration

1. Publish these failures on **Flagged for Review**, preserving blank numeric values. An inaccessible lobby means the full list is unknown, not that there are zero matches.
2. Never use Hotspawn pick percentages, rewards, popularity, prices, or scoring as probability inputs. Its role is fixture discovery only.
3. Require evidence for both the Hotspawn fixture and every external price: exact source URL, retrieval time, source event/market identifiers, teams, scheduled UTC start, market type, format, and settlement rules. Evidence must include the quoted decimal prices, not just a homepage link.
4. Do not pair fixtures by fuzzy team name alone. Match tournament, opponents, start time, format, and market. A reverse-order fixture must reverse its outcome prices. Reject map winners paired with match winners and markets with incompatible draw/overtime rules.
5. Keep raw decimal odds separate from computed output. Mathematical derivations are **derived**, never officially verified forecasts. With a complete mutually exclusive market, let `q_i = 1 / decimal_odds_i`; proportional no-vig estimate `p_i = q_i / sum(q)`. This is a chosen normalization assumption, not proof of true probability. Do not fill missing prices, infer a two-outcome market, or treat one price as sufficient evidence.
6. For an independent consensus, normalize each bookmaker's complete, matched market first, then disclose the aggregation rule and participating sources. Do not silently combine prices from different books into a synthetic market. Do not describe this as a trained prediction model unless an actual reproducible model and evaluation exist.
7. Mark stale, suspended, live/in-play, and removed markets. A failed update must not advance the timestamp of older quotes. Show collection attempt time separately from successful data time.
8. Preserve the last successfully verified snapshot on fetch failure, but prominently label it stale. An initial empty snapshot must say **collection unavailable**, not **no upcoming matches**.
9. Do not commit credentials or browser cookies. Do not bypass authentication, bot protection, or source access controls. Unknown API contracts, CSS selectors, or undocumented endpoints must be flagged rather than fabricated.
10. Before merge, test all internal links, JSON schema handling, blank/unverified rendering, escaping of source-derived names, reversed fixtures, missing outcomes, invalid odds, stale quotes, and Pages artifact paths. A successful deploy is not evidence of successful match collection.

## Scope and provenance

The checkout initially contained only `README.md`. This session owns only `audits/1d4de836/**`, plus shared board claim/log updates. The first active integration claim belongs to session `ef111e02`; session `1916f96c` also claimed overlapping integration scopes. See the shared board and issue #1 for the reconciliation request.

No verified matches, betting lines, or current probabilities were obtained in this audit. No live data is invented. No candidate source is asserted to be officially authenticated by this audit.
