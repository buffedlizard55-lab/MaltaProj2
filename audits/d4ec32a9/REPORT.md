# Current-pipeline safety audit — session d4ec32a9

Audit date: 2026-10-13 UTC. This is a code/evidence audit, **not** a declaration that every inherited factual claim is verified.

## Official sources inspected

- [Hotspawn public lobby](https://play.hotspawn.com/lobby): fetched on this session; rendered extract exposes CS2 fixtures and crowd pick percentages. The extract has three chunks and a 90-fixture filter counter. It is not a complete API snapshot or proof of freshness; displayed times have no confirmed timezone in the extract. Do not copy the crowd percentages into win probabilities.
- [HLTV analytics](https://www.hltv.org/betting/analytics): fetched on this session; primary HLTV analysis content identifies Zomblers–Overtake Sector, ex-Keyd Stars–Galorys, and other fixtures. The extract shows blank numeric best-odds fields; it cannot establish numeric betting quotes. No numeric quote was invented from qualitative favorite/form descriptions.
- [Pinnacle official site](https://www.pinnacle.com/) and [Bovada official site](https://www.bovada.lv/): source links for manual review. This sandbox only permits GitHub/npm/PyPI network hosts for commands. Fresh bookmaker validation is performed by the public-endpoint collectors in GitHub Actions, with the actual outcome/participant/start/market payload recorded in `evidence/odds_collection.json`. A source link alone does not prove a quote.
- [GitHub Pages repository configuration](https://api.github.com/repos/buffedlizard55-lab/MaltaProj2/pages): authenticated API inspected; source `main` `/`, legacy publishing, initially `built`.

## Confirmed code defects and changes

| Finding | Verification performed | Resolution |
|---|---|---|
| Quotes could remain current after kickoff or age indefinitely | Read previous `build_lines.py`: no age, lock, market state or kickoff eligibility checks | Fail closed: timezone-aware timestamps, max four-hour quote and fixture age, upcoming/unlocked fixture, explicit open prematch market |
| Claimed ambiguous-join rejection was absent | Previous loop assigned a quote to first matching fixture, using `used_lines` | Candidate graph rejects multi-fixture joins and multi-quote source groups, independent of input order |
| ISO Pinnacle starts became blank | `ms_iso` previously parsed all inputs as integers | Parse explicit timezone-aware ISO or documented epoch milliseconds; missing/naive time remains blank |
| Bovada ordering depended on array order | Previous code used `competitors[i]` with `outcomes[i]` | Unique `competitorId` join; ambiguous or missing IDs rejected |
| Missing timestamps could join by loose tournament token | Previous matcher accepted one overlapping non-stopword token | Exact UTC kickoff required; no league-name fallback |
| Polymarket end date was treated as kickoff | Previous collector populated `start_time_utc` from `endDate` | End date retained separately; no claimed kickoff. Prediction-market data excluded from primary bookmaker picks |
| Old combined/third-party snapshot presented as current probabilities | Generator read preserved `data/probabilities.json`, not hourly current lines | Current probability page reads eligible primary lines with full automatic fixture inventory; old JSON preserved and labeled research snapshot |
| Data job masked line-builder failure and omitted rendered root HTML | Read original workflow's `|| echo`, `git add data evidence docs` | Builder/test/site failures block commit; root HTML, assets, data and evidence published in one refresh commit |

## Policy and limitations

- Four hours is a **maximum accepted observation age**, not a real-time guarantee. The collection schedule is hourly. Retrieval timestamps do not establish when a bookmaker last updated a price.
- Proportional no-vig normalization and equal-source averaging are explicit modeling assumptions. Neither a probability nor a recommended pick is an official verified outcome.
- Strict matching intentionally leaves more blanks rather than supplying plausible estimates. Missing prices, missing start times, locked matches, old scheduled rows, unavailable sources, third-party odds and unclear identities remain review items.
- Coverage of every available *fixture row* is distinct from coverage of every row with a probability. The latter is not guaranteed. LoL rows are retained but unpriced in this CS2-focused primary pipeline.
- Archived parallel boards/models remain intact and are not re-verified in this audit. Their dated outputs are not inputs to current picks. Existing tests that merely assert a stored `verified` boolean are not independent source verification.
- Official pages can be cached or change. Exact source payloads and observed times, plus source URLs on each current match/rejection row, enable manual review. External link reachability is not universally certified.

## Validation / publication

Regression tests cover fail-closed matching, price arithmetic and source eligibility. Final commands and hosted-runner results, PR and deploy records are appended to `COORDINATION.md`; no deployment is claimed until checked.

### Final observed primary batch

Hosted collector runs [38470098126](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38470098126) and
[38470784435](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38470784435) succeeded.
The latter batch rendered at 2026-10-13T21:29:32Z: 390 non-cancelled/non-ended fixture rows (92 CS2 + 298 LoL),
9 CS2 fixtures with 13 eligible source quotes, 83 CS2 blanks; LoL probabilities all blank.
21 primary quote payloads retained. Tests reconstruct every **eligible** quote's price, ordering, kickoff
and no-vig calculation from the captured official response, rather than trusting a stored verification label.

All 50 combined unit tests passed locally after preserving PR #29's separate board.
Desktop/390px/320px Chromium tests passed for seven current root pages; every root-generator table row has a
source/review link; the complete staged site's local links resolve. Hosted integration push run
[38470784473](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38470784473) and PR run
[38470791052](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38470791052) succeeded.

The parallel `current/` board from PR #29 is preserved, but its unnamed third-party fallback and double-reversal
logic need owner review. It is explicitly linked as a snapshot, not used as current official-source evidence.
The competing older-policy source batch is archived in this audit's `pr29_snapshot/` directory for review.
