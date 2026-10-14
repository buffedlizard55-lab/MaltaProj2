# Source and implementation review — 8723ad37

Read on 2026-10-14 UTC. This is a scoped review of the existing every-match board and
root executive-summary generator, not a claim that every historical contribution in this
large repository has been verified. Prior archives and independent boards remain dated research.

## Official sources actually inspected

- [HotSpawn lobby](https://play.hotspawn.com/lobby): platform fetch, chunk 0, at approximately
  03:56 UTC. It reported 88 filter entries and a separate 68-this-week counter. Those counters
  are not interchangeable. Rendered teams include RoundsGG, WROTBERRY and LFO 10. Displayed
  times have no verified zone in the text extract; use the collector's epoch timestamps instead.
  This read is not used to overwrite the automated snapshot or certify its simultaneous freshness.
- [Valve official standings](https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md):
  fetched through GitHub Contents API; entire returned markdown preserved alongside this report.
  Checked ROUNDS 548, EAC 1035, WBT 1201, WBT Academy 911. LFO 7/8/9 exist but LFO 10 does not.
  No other roster's rating proves LFO 10's strength. Every consumed rating in the new board is
  checked against this source in the independent regression test.
- [Valve Glicko implementation](https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/model/glicko.js):
  fetched via GitHub Contents API and preserved. Using that formula on team point differences is
  our modelling choice, not Valve certifying these fixtures' win probabilities.
- [HLTV ROUNDS team](https://www.hltv.org/team/12457/roundsgg): platform fetch redirects to
  `/team/12457/rounds`. Read team identity and FAQ. Current lineup shown: ykis, Monoxx, Kollo,
  Lapa; the historical Valve row also includes Tumppis. Upcoming HAVU, Phantom and Voca matches
  on 16 October are listed. Alias supported, upcoming complete roster not confirmed. Published flag.
- [HLTV Elisa event](https://www.hltv.org/events/9332/elisa-breakout-series-2): platform fetch,
  chunk 0, group A lists WBT / EAC / ENCE / BOJONG. This does NOT establish that HotSpawn's
  WROTBERRY is WBT rather than WBT Academy. Inherited Kalshi naming disagrees. Remains blank.

HLTV is an independent esports publisher, not an official tournament or bookmaker feed.
Its pages support research; the official HotSpawn fixture and Valve rating links remain on rows.
No fresh bookmaker response was obtainable directly through this sandbox's restricted egress.
Committed source snapshots are recomputed, not represented as new live quotes. Hosted collection
and its source-access log are the route for new prices. Source URLs do not themselves certify
all normalized inputs or external-link reachability.

## Line-by-line scoped code findings and remedies

| Scope | Finding | Remedy / verification |
|---|---|---|
| `scripts/c64a5e19/core.py`, joining | 14h window and missing/approximate kickoff accepted | 5-minute explicit UTC gate; regressions for missing/approximate/late kickoff |
| Same file, odds | stored `prob_a` trusted | Recompute from raw decimal/American prices, reject invalid no-vig books |
| `build.py`, inventory | API-only fixtures described as lobby coverage | Only `seen_in=lobby_page`; exact-ID coverage assertion |
| `collect.py`, merge | API response could overwrite lobby participant/status fields | Lobby authoritative; API-only research retained but not counted |
| `build.py`, ratings | most-recent duplicate selected without identity evidence | Duplicate labels rejected; no borrowed calibration from another policy |
| `build.py`, fallback | sibling/floor ratings, one-participant slots, rejected thin books became picks | Removed. Research candidates linked, probabilities blank |
| `build.py`, market | model altered already-priced picks | Market is unchanged by fallback; model only when market absent |
| `build.py`, freshness | no effective age/deadline gate | Cache-adjusted four-hour fixture/quote limit; 14-day rating limit; per-row expiry |
| `collect.py`, failures | repeated failed fetch could reset retained snapshot age | Preserve original observation and cache age across failures |
| `collect.py`, Bovada | closed market/outcome prices could be accepted | Require open event, market, outcome and no live event |
| `build.py`, rendering | flagged A/B rows excluded; tiny navigation; stale picks persisted | All flags published; 44px links, mobile cards/table, search, browser expiry |
| `scripts/build_site.py`, landing prose | hard-coded counts and conflicting “every match has a pick” statements | One prominent board link; dynamic strict counts; explicit coverage vs evidence distinction |

## Remaining irregularities

- Full probability coverage is **not** claimed: blank rows are a necessary result of the user's
  requirement not to infer missing facts. WROTBERRY identities and LFO 10 ratings remain unresolved.
- RoundsGG estimates describe historical team strength, not a verified upcoming roster.
- Model calibration is in-sample and does not establish out-of-sample prediction accuracy.
- Independent archived boards may still contain earlier, conflicting estimates. The root leads to
  the hardened board; the verification companion is dated, not a second authoritative pick source.
- External access, cache staleness and GitHub Actions scheduling can delay updates. The UI expires
  numbers instead of promising uninterrupted live coverage. All future new fixtures are processed
  generically; no particular match IDs or coverage counts are hard-coded into the new safety tests.
