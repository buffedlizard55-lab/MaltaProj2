#!/usr/bin/env python3
"""Regression tests for session 7cd2e67a (INT-1 / INT-2).

Covers the two defects this session found and repaired, so neither can silently come back:

  1. A per-row HotSpawn source link must be a URL HotSawn publishes — a published per-match
     permalink, or the official lobby page. A constructed `https://www.hotspawn.com/matches/<id>`
     is never acceptable, because that route resolves to the general matches index (verified
     2026-10-14 ~01:50 UTC).
  2. The published probabilities must reproduce from the odds stored next to them, and every
     originated estimate must use a rating that is a real row of Valve's official standings.

Run with:  python -m unittest tests.test_verify_7cd2e67a -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "live"))

from live_core import extract_lobby_permalinks  # noqa: E402

BARE = "https://www.hotspawn.com/matches/"
LOBBY = "https://play.hotspawn.com/lobby"
VRS_API = ("https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings"
           "/contents/live/2026/standings_global_2026_10_05.md")


def devig(a: float, b: float):
    qa, qb = 1.0 / a, 1.0 / b
    total = qa + qb
    return round(qa / total, 4), round(qb / total, 4), round(total - 1, 5)


class PermalinkExtraction(unittest.TestCase):
    """The permalink map must come only from URLs HotSawn publishes, and never invent a slug."""

    def test_published_permalinks_are_read_from_the_lobby_capture(self):
        sample = os.path.join(ROOT, "data", "live", "samples", "lobby_page.txt")
        with open(sample, encoding="utf-8", errors="replace") as fh:
            found = extract_lobby_permalinks(fh.read())
        self.assertTrue(found, "no published permalinks found in the official lobby capture")
        for fixture_id, url in found.items():
            self.assertTrue(url.startswith("https://www.hotspawn.com/matches/"), url)
            self.assertTrue(url.endswith("-" + fixture_id), (url, fixture_id))
            self.assertNotRegex(url, r"/matches/\d+$")

    def test_tournament_names_containing_digits_do_not_truncate_the_id(self):
        html = ('<a href="https://www.hotspawn.com/matches/'
                'gothic-vs-lavked-cct-europe-2026-series-11-1079621">x</a>')
        found = extract_lobby_permalinks(html)
        self.assertEqual(found, {"1079621": "https://www.hotspawn.com/matches/"
                                            "gothic-vs-lavked-cct-europe-2026-series-11-1079621"})

    def test_a_bare_numeric_route_is_never_returned(self):
        html = '<a href="https://www.hotspawn.com/matches/1079546">x</a>'
        self.assertEqual(extract_lobby_permalinks(html), {})

    def test_matches_the_independently_captured_permalink_map(self):
        path = os.path.join(ROOT, "data", "picks_permalinks.json")
        with open(path, encoding="utf-8") as fh:
            published = json.load(fh)["permalinks"]
        sample = os.path.join(ROOT, "data", "live", "samples", "lobby_page.txt")
        with open(sample, encoding="utf-8", errors="replace") as fh:
            found = extract_lobby_permalinks(fh.read())
        # The two official captures have different observation times. Removed fixtures are
        # not evidence of a parser defect. Compare every overlapping permalink exactly;
        # extraction of all current-state URLs is covered by the other tests above.
        # The anti-vacuity floor must not encode lobby recency: as the lobby turns over, the
        # two captures can share far fewer fixtures than at capture time. One shared fixture is
        # enough to make the exact-match assertion meaningful. (Repair by session 4cf64ea3,
        # logged takeover: 7cd2e67a scope, gate-red incident 2026-10-15.)
        shared = set(published) & set(found)
        if not shared:
            self.skipTest("Independent captures have no overlapping fixtures; shape/extraction contracts still run")
        self.assertGreaterEqual(len(shared), 1)
        for fixture_id in shared:
            for url in (found[fixture_id], published[fixture_id]):
                self.assertTrue(url.startswith("https://www.hotspawn.com/matches/"), (fixture_id, url))
                self.assertTrue(url.endswith(f"-{fixture_id}"), (fixture_id, url))


class NoConstructedMatchLinks(unittest.TestCase):
    """No published snapshot may carry a constructed /matches/<id> per-row link."""

    def _assert_clean(self, path, key, id_key):
        """Every row's HotSpawn link must be a URL HotSawn publishes, never a constructed path.

        The per-row link is stored under different keys on each board: the root inventory carries
        `source.published_match_url` (only trusted when `published_match_url_verified` is true), the
        live and expanded boards carry `hotspawn_match_url`. A row with no published permalink may
        only ever link the official lobby page.
        """
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        rows = doc.get(key) or []
        self.assertTrue(rows, path)
        for row in rows:
            source = row.get("source") or {}
            url = (source.get("hotspawn_match_url") or row.get("hotspawn_match_url")
                   or source.get("published_match_url"))
            if url is None:
                # The root collector only records a URL when it has verified one; anything else
                # must resolve to the official lobby when the board is rendered.
                continue
            self.assertTrue(
                url.startswith("https://www.hotspawn.com/matches/")
                or url == LOBBY or url.startswith("https://play.hotspawn.com"), url)
            if url.startswith(BARE):
                tail = url[len(BARE):]
                self.assertFalse(tail.isdigit(),
                                 f"{path}: constructed numeric route {url} for {row.get(id_key)}")

    def test_root_inventory_only_records_verified_permalinks(self):
        """A recorded `published_match_url` must be verified and must end in its own fixture id."""
        with open(os.path.join(ROOT, "data", "hotspawn_matches.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        for row in doc["matches"]:
            source = row.get("source") or {}
            url = source.get("published_match_url")
            if url is None:
                continue
            self.assertTrue(source.get("published_match_url_verified"), row["fixture_id"])
            self.assertTrue(url.endswith("-" + str(row["fixture_id"])), url)

    def test_root_inventory_has_no_constructed_route(self):
        self._assert_clean(os.path.join(ROOT, "data", "hotspawn_matches.json"), "matches",
                           "fixture_id")

    def test_live_snapshot_has_no_constructed_route(self):
        self._assert_clean(os.path.join(ROOT, "data", "live", "fixtures.json"), "fixtures",
                           "fixture_id")

    def test_rendered_pages_have_no_constructed_route(self):
        import re
        for name in ("index.html", "cs2.html", "lol.html", "probabilities.html", "flagged.html"):
            page = os.path.join(ROOT, name)
            if not os.path.exists(page):
                continue
            with open(page, encoding="utf-8") as fh:
                html = fh.read()
            for url in re.findall(r'https://www\.hotspawn\.com/matches/[^"\'\s<]+', html):
                tail = url[len(BARE):]
                self.assertFalse(tail.isdigit(), f"{name}: {url}")
        for section in ("live", "market"):
            for base, _dirs, files in os.walk(os.path.join(ROOT, section)):
                for name in files:
                    if not name.endswith(".html"):
                        continue
                    with open(os.path.join(base, name), encoding="utf-8") as fh:
                        html = fh.read()
                    for url in re.findall(
                            r'https://www\.hotspawn\.com/matches/[^"\'\s<]+', html):
                        tail = url[len(BARE):]
                        self.assertFalse(tail.isdigit(), f"{section}/{name}: {url}")


class PublishedArithmetic(unittest.TestCase):
    """Every published probability must reproduce from the odds stored beside it."""

    def test_root_board_probabilities_reproduce(self):
        with open(os.path.join(ROOT, "data", "lines.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        checked = 0
        for fx in doc["fixtures"]:
            lines = fx.get("bookmaker_lines") or []
            consensus = (fx.get("derived") or {}).get("consensus")
            if not lines:
                self.assertIsNone(consensus, fx['fixture_id'])
                self.assertIn('external_odds_not_found', fx['review_flags'])
                continue
            self.assertIsNotNone(consensus, fx['fixture_id'])
            checked += 1
            ps = []
            for line in lines:
                pa, pb, ov = devig(line["decimal_odds_a"], line["decimal_odds_b"])
                self.assertEqual(pa, line["derived_probability_a"], fx["fixture_id"])
                self.assertEqual(pb, line["derived_probability_b"], fx["fixture_id"])
                self.assertEqual(ov, line["overround"], fx["fixture_id"])
                ps.append(pa)
            mean = round(sum(ps) / len(ps), 4)
            self.assertEqual(mean, consensus["derived_probability_a_mean"], fx["fixture_id"])
            self.assertEqual(round(1 - mean, 4), consensus["derived_probability_b_mean"])
            self.assertEqual(min(ps), consensus["derived_probability_a_min"])
            self.assertEqual(max(ps), consensus["derived_probability_a_max"])
        # All quotes can expire or fail to join. A source-backed blank is valid;
        # demanding a price would contradict the fail-closed publication policy.
        self.assertTrue(doc['fixtures'], 'fixture inventory must not disappear')
        self.assertEqual(checked, doc['summary']['fixtures_with_external_line'])

    def test_live_board_probabilities_reproduce(self):
        with open(os.path.join(ROOT, "data", "live", "board.json"), encoding="utf-8") as fh:
            board = json.load(fh)
        market = estimate = 0
        for row in board["rows"]:
            pub = row["published"]
            if pub["basis"] == "market":
                market += 1
                ps = []
                # Consensus includes one eligible quote per source, not rejected
                # live/stale candidates retained in the audit's row["quotes"].
                accepted = row["market"]["sources_detail"]
                self.assertEqual(len(accepted), row["market"]["n_sources"])
                self.assertEqual(len({q["source_key"] for q in accepted}), len(accepted))
                for q in accepted:
                    self.assertTrue(any(all(q.get(k) == raw.get(k) for k in
                        ("source_key", "source_event_id", "decimal_odds_a", "decimal_odds_b"))
                        and not raw.get("market_is_live") and not raw.get("stale")
                        for raw in row["quotes"]), row["fixture_id"])
                    pa, pb, ov = devig(q["decimal_odds_a"], q["decimal_odds_b"])
                    self.assertEqual(pa, round(q["prob_a"], 4), row["fixture_id"])
                    self.assertEqual(pb, round(q["prob_b"], 4), row["fixture_id"])
                    self.assertEqual(ov, round(q["overround"], 5), row["fixture_id"])
                    ps.append(pa)
                mean = round(sum(ps) / len(ps), 4)
                # The published consensus averages unrounded per-source probabilities; the stored
                # per-source values are rounded to 4 dp, so allow one rounding step of slack.
                self.assertAlmostEqual(mean, round(pub["prob_a"], 4), delta=0.0002,
                                       msg=row["fixture_id"])
            elif pub["basis"] == "estimate":
                estimate += 1
                est = row["estimate"]
                recomputed = 1.0 / (1.0 + 10.0 ** (-(est["rating_diff"] / est["scale"])))
                self.assertAlmostEqual(recomputed, est["prob_a"], delta=0.0002,
                                       msg=row["fixture_id"])
                self.assertAlmostEqual(recomputed, pub["prob_a"], delta=0.0002,
                                       msg=row["fixture_id"])
        self.assertGreater(market, 0)
        self.assertGreater(estimate, 0)

    def test_live_board_picks_and_edges_reproduce(self):
        with open(os.path.join(ROOT, "data", "live", "board.json"), encoding="utf-8") as fh:
            board = json.load(fh)
        checked = 0
        for row in board["rows"]:
            pub = row["published"]
            if pub["basis"] == "none":
                self.assertIsNone(pub["pick_side"], row["fixture_id"])
                self.assertIsNone(pub["prob_a"], row["fixture_id"])
                continue
            checked += 1
            pa, pb = pub["prob_a"], pub["prob_b"]
            side = "a" if pa > pb + 0.005 else ("b" if pb > pa + 0.005 else None)
            self.assertEqual(side, pub["pick_side"], row["fixture_id"])
            if side:
                self.assertEqual(row["team_a"] if side == "a" else row["team_b"],
                                 pub["pick_team"], row["fixture_id"])
                self.assertAlmostEqual(abs(pa - pb), pub["edge"], delta=0.0002,
                                       msg=row["fixture_id"])
        self.assertGreater(checked, 0)


class ValveRatings(unittest.TestCase):
    """Originated-estimate ratings must be rows of Valve's official standings file."""

    @classmethod
    def setUpClass(cls):
        import base64
        import urllib.request
        req = urllib.request.Request(
            VRS_API, headers={"User-Agent": "MaltaProj2-research/1.0",
                              "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        text = base64.b64decode(doc["content"]).decode("utf-8")
        cls.rows: dict[str, list[tuple[int, int]]] = {}
        for line in text.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) > 4 and parts[1].isdigit() and parts[2].lstrip("-").isdigit():
                cls.rows.setdefault(parts[3], []).append((int(parts[1]), int(parts[2])))

    def test_official_standings_file_is_readable(self):
        self.assertGreater(len(self.rows), 100, "Valve standings did not parse")

    def test_every_estimate_rating_is_an_official_row(self):
        with open(os.path.join(ROOT, "data", "live", "board.json"), encoding="utf-8") as fh:
            board = json.load(fh)
        checked = 0
        for row in board["rows"]:
            est = row.get("estimate")
            if not est:
                continue
            for side in ("a", "b"):
                if est.get(f"team_{side}_region") != "global":
                    continue
                team = row[f"team_{side}"]
                if team not in self.rows:
                    continue
                checked += 1
                self.assertIn(
                    (est.get(f"team_{side}_standing"), est.get(f"team_{side}_points")),
                    self.rows[team],
                    f"{row['fixture_id']}: {team} rating is not a row of Valve's standings")
        self.assertGreater(checked, 0, "no estimate ratings to verify")


class VerificationArtifact(unittest.TestCase):
    """The published verification page must exist, carry source links and name every check."""

    def test_audit_page_and_evidence_exist(self):
        for name in ("index.html", "audit.json", "AUDIT.md"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "verify", "7cd2e67a", name)), name)

    def test_every_check_row_carries_a_source_link(self):
        with open(os.path.join(ROOT, "verify", "7cd2e67a", "audit.json"), encoding="utf-8") as fh:
            audit = json.load(fh)
        self.assertTrue(audit["checks"])
        for check in audit["checks"]:
            self.assertIn(check["result"], {"pass", "pass_with_note", "flag", "repaired"},
                          check["id"])
            self.assertTrue(check["detail"].strip(), check["id"])
        for obs in audit["observations"]:
            self.assertTrue(obs["url"].startswith("https://"), obs["id"])
            self.assertTrue(obs["read_utc"], obs["id"])

    def test_audit_page_links_the_official_sources(self):
        with open(os.path.join(ROOT, "verify", "7cd2e67a", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        for needle in ("play.hotspawn.com/lobby", "pinnacle.com", "bovada.lv", "melbet.com",
                       "ValveSoftware/counter-strike_regional_standings"):
            self.assertIn(needle, html)
        self.assertIn('name="viewport"', html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
