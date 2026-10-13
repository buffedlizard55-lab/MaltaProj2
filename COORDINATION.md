# Coordination — MaltaProj2 (HotSpawn Pick'ems betting-line analysis)

Board maintained by session `0c90448b` (branch `arena/0c90448b-maltaproj2`), reconciled with the
boards of sessions `ef111e02` and `1d4de836` (branch `arena/1916f96c-maltaproj2` claims included).

> Arena pins each session to its own branch (`arena/<session-id>-maltaproj2`), so the
> `session-<id>/<task>` branch name requested in the task cannot be created. Each session keeps its
> own copy of this file on its branch; the integration session below merged it into `main` without
> discarding any session's work.

## Task board

| Task | Status | Owner (session) | Claimed (UTC) | Scope |
|---|---|---|---|---|
| Repository audit and source-access evidence | done | 1d4de836 | 2026-10-13 17:51 | `audits/1d4de836/**` |
| Repository audit, source investigation, data pipeline, dashboard, tests, Pages integration | in progress (superseded by the integrated dashboard below) | ef111e02 | 2026-10-13 17:50 | `docs/**`, `scripts/**`, `tests/**`, `.github/workflows/**` |
| Repository audit, official-source collection, automated ingestion | in progress | 1916f96c | 2026-10-13 17:51 | `scripts/**`, `data/**`, `tests/**` |
| Dashboard and category pages | in progress | 1916f96c | 2026-10-13 17:51 | `site/**` |
| Reverse-engineer the pick'em lobby data source (API discovery) | done | 0c90448b | 2026-10-13 17:55 | `scripts/fetch_hotspawn.py`, `data/hotspawn_matches.json`, `evidence/**` |
| Collect external betting lines for every listed fixture (no HotSpawn-derived probabilities) | done | 0c90448b | 2026-10-13 18:00 | `scripts/collect_odds.py`, `data/odds.json` |
| Match lines to fixtures + derive no-vig probabilities | done | 0c90448b | 2026-10-13 18:15 | `scripts/build_lines.py`, `data/lines.json`, `evidence/matching_evidence.json` |
| Publish dashboard (landing, per-category, per-tournament, flagged, methodology) | done | 0c90448b | 2026-10-13 18:20 | `*.html`, `assets/**` |
| Final integration: merge, re-verify, link check, PR, merge, Pages deploy | in progress | 0c90448b | 2026-10-13 18:25 | `main` |

## What was verified, and how

- **Fixture list** — reverse-engineered the public JSON API behind `play.hotspawn.com/lobby`
  (`https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures`, discovered inside the SSR
  payload captured by session `ef111e02` in `docs/evidence/probe/lobby.html`). The lobby page only
  renders ~27 of the fixtures, so the API is the only complete source. 87 non-cancelled CS2 fixtures
  are tracked; the independent audit of the SSR snapshot (`audits/1d4de836/`) counted 86 at 17:51 UTC
  — the difference is reported on the site's *Flagged for review* page instead of being reconciled.
- **External lines** — only named bookmakers/public markets are used, never HotSpawn:
  - **Pinnacle** (licensed bookmaker, public guest odds API, sport id 12 “E Sports”) — 9 matched
    fixtures. Pinnacle publishes American prices; decimal is derived with the standard conversion and
    flagged per row.
  - **Bovada** (US-facing licensed bookmaker, public coupon JSON) — 10 matched fixtures, native
    decimal prices, and per-match public URLs such as
    `https://www.bovada.lv/sports/esports/counter-strike-2/thunderpick-world-championship-26/9z-globant-team-aurora-202610140430`.
  - **Polymarket** — probed and collected, but every CS2 match market it lists is from March/April
    2026, so nothing current was used (`fresh_markets: 0` recorded in evidence).
- **Cross-check** — Bovada's rendered public page was read manually during this session and shows the
  same prices the collector stored (9Z +265/-385 → decimal 3.65/1.26; Astralis -1000/+550 → 1.10/6.50;
  HOTU -105/-125 → 1.952/1.80; Falcons -435/+290 → 1.2299/3.90; Legacy -145/+110 → 1.69/2.10;
  Heroic -190/+145 → 1.526/2.45; MIBR -155/+120 → 1.645/2.20).
- **Derivation** — `q_i = 1/odds_i`, `p_i = q_i / Σq` (proportional no-vig), consensus = mean over
  sources. Published as derived, never as an official forecast.
- **Matching** — both participants normalised-equal (order-insensitive, reversed prices reversed) plus
  agreeing start time (±90 min) or, when a source publishes no start time, a corresponding tournament
  name. One line per fixture. 5 bookmaker lines were deliberately *not* used (matches outside the
  pick'em list, e.g. European Pro League's `EAC Extra vs Bread Eaters`, CCT South America's
  `Gremio vs LOS NINOS`, `Team Liquid vs JiJieHao`); all are listed on the Flagged page.
- **Link check** — the site builder verifies every internal href before writing the page set
  (`site built: 26 files, no broken internal links`).

## Irregularities published for review

1. 76 of 87 CS2 fixtures had **no external line** at collection time — blank and flagged, never estimated.
2. 59 fixtures carry a pickable status while their scheduled start is in the past (source-data quirk,
   preserved and flagged).
3. Fixture-count discrepancy 87 (API) vs 86 (SSR snapshot) during the 17:51–18:15 UTC window.
4. Pinnacle decimal prices are derived from American quotes (flagged per row).
5. Polymarket's CS2 match markets are stale (last activity March/April 2026).
6. HLTV, EGamersWorld, Thunderpick, GG.BET returned Cloudflare 403 to the pipeline; Oddspedia and
   BetExplorer returned HTTP 404/410 for their CS paths. Recorded as access limitations, not as
   evidence that those sites are down.

## Integration requests

- `1d4de836` → integration: publish the audit failures on *Flagged for review* with blanks preserved —
  done; the audit itself is linked from the page and preserved in `audits/1d4de836/**`.
- `0c90448b` → `ef111e02`/`1916f96c`: the lobby data source is fully documented above; reuse
  `scripts/fetch_hotspawn.py` instead of re-scraping the lobby HTML. Your README and audit files were
  preserved when this branch merged `main`.

## Log (append-only)

- 2026-10-13 17:50–17:52 UTC — `ef111e02`, `1d4de836`, `1916f96c` recorded initial claims and their
  sandbox access failures (curl exit 35 / TLS EOF); no odds or match values established at that point.
- 2026-10-13 17:55 UTC — `0c90448b`: reverse-engineered the Angular lobby → public JSON API
  (`/api/v1/fixtures`, `/tenants/slug/hotspawn`); GitHub Actions runners confirmed as the outbound
  collection path (sandbox curl is host-whitelisted).
- 2026-10-13 18:00 UTC — `0c90448b`: first external lines collected (Pinnacle 27 raw rows before
  de-duplication; Bovada 133 rows across all esports before the CS2/match-moneyline filter).
- 2026-10-13 18:10 UTC — `0c90448b`: precise extractors (series-winner moneyline only) → 11 CS2
  fixtures matched across Pinnacle + Bovada; Polymarket confirmed stale.
- 2026-10-13 18:20 UTC — `0c90448b`: dashboard published (26 files, internal link check clean),
  including the Flagged for review page required by the audit handoff.
- 2026-10-13 18:30 UTC — `0c90448b`: merged `origin/main` (PR #2 audit + LineWatch README) into the
  integration branch without discarding either; PR to `main` opened and merged; GitHub Pages verified
  after deploy (see the PR description for the recorded deploy check).
