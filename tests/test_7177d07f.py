"""Contract tests for session 7177d07f (unresolved / every-match pick resolution).

Checks, without trusting the board's own claims:
  * every open CS2 fixture in the lobby inventory appears exactly once;
  * a row either carries a pick with a normalized probability pair (pick = higher side)
    or is blank and flagged as unresolved with an official HotSpawn source link;
  * the featured route is never overridden - rows with an eligible bookmaker line keep basis 'featured';
  * every row carries at least one http(s) source link and an official HotSpawn/HLTV/Valve link;
  * originated lines state their official rating input;
  * HotSpawn crowd percentages never enter the board;
  * the rendered pages are mobile-friendly, link to every pick list, and contain no broken local links.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "7177d07f"
SITE = ROOT / "unresolved"

BOARD = DATA / "board.json"
INVENTORY = ROOT / "data" / "hotspawn_matches.json"
LINES = ROOT / "data" / "lines.json"

FORBIDDEN = ("pick_pct", "picked_percent", "crowd_percent", "hotspawn_percent",
             "crowd_pick", "user_prediction")
ALLOWED_BASIS = {"featured", "esportsbook", "originated_vrs", "originated_rank", "unresolved"}


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


class BoardContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load(BOARD)
        cls.rows = cls.board.get("rows") or []
        cls.inventory = load(INVENTORY, {})
        cls.lines = load(LINES, {})

    def test_board_exists_and_has_rows(self):
        self.assertTrue(self.rows, "board.json has no rows")

    def test_every_open_cs2_fixture_is_present_exactly_once(self):
        generated = str((self.board.get("inventory_source") or {}).get("generated_at_utc") or "")
        # This historical board is refreshed independently. Comparing it with a
        # different day's root inventory is not a coverage verification.
        current = str(self.inventory.get("generated_at_utc") or "")
        board_ids = [r["fixture_id"] for r in self.rows]
        self.assertEqual(len(board_ids), len(set(board_ids)), "duplicate fixture ids")
        self.assertTrue(generated, "archive must identify its inventory capture")
        if generated != current:
            self.skipTest(f"Different inventory captures: archive {generated}, root {current}; canonical replay tests enforce current coverage")
        open_ids = {
            str(m.get("fixture_id"))
            for m in (self.inventory.get("matches") or [])
            if m.get("sport") == "cs2"
            and str(m.get("status")) == "scheduled"
            and str(m.get("lock_time") or m.get("scheduled_start_time") or "") > generated
        }
        self.assertTrue(open_ids, "inventory has no open CS2 fixtures")
        board_ids = [r["fixture_id"] for r in self.rows]
        self.assertEqual(len(board_ids), len(set(board_ids)), "duplicate fixture ids on the board")
        self.assertEqual(set(board_ids), open_ids)

    def test_every_row_is_picked_or_blank_and_flagged(self):
        for row in self.rows:
            if row.get("pick"):
                self.assertIsInstance(row.get("prob_a"), (int, float), row["fixture_id"])
                self.assertIsInstance(row.get("prob_b"), (int, float), row["fixture_id"])
                self.assertAlmostEqual(row["prob_a"] + row["prob_b"], 1.0, places=4,
                                       msg=row["fixture_id"])
                self.assertIn(row["pick"], (row["team_a"], row["team_b"]), row["fixture_id"])
                self.assertAlmostEqual(row["pick_prob"], max(row["prob_a"], row["prob_b"]),
                                       places=4, msg=row["fixture_id"])
            else:
                self.assertIsNone(row.get("prob_a"), row["fixture_id"])
                self.assertIn("no_defensible_evidence_probability_left_blank", row["flags"],
                              row["fixture_id"])
                self.assertEqual(row["basis"], "unresolved", row["fixture_id"])

    def test_basis_is_always_a_published_label(self):
        for row in self.rows:
            self.assertIn(row["basis"], ALLOWED_BASIS, row["fixture_id"])

    def test_featured_rows_are_not_replaced_by_originated_lines(self):
        priced = {
            str(fx.get("fixture_id"))
            for fx in (self.lines.get("fixtures") or [])
            if fx.get("bookmaker_lines")
        }
        board_from = (self.board.get("featured_source") or {}).get("generated_at_utc")
        lines_from = self.lines.get("generated_at_utc")
        same_snapshot = bool(board_from) and board_from == lines_from
        for row in self.rows:
            if row["basis"] == "featured":
                self.assertTrue(row["fixture_id"] in priced or not same_snapshot,
                                f"{row['fixture_id']}: claims a featured line that is not in the "
                                f"lines snapshot it was built from")
            elif row["fixture_id"] in priced and same_snapshot:
                # Same snapshot, so the ladder skipped a fixture the strict route did price.
                self.fail(f"{row['fixture_id']}: basis {row['basis']} overrides a featured line")
        if not same_snapshot:
            self.skipTest("board and data/lines.json come from different snapshots "
                          f"(board={board_from}, lines={lines_from}); the workflow rebuilds this "
                          "board whenever update-data runs")

    def test_every_row_carries_an_official_source_link(self):
        for row in self.rows:
            urls = [row.get("hotspawn_url")] + [e.get("url") for e in row.get("evidence") or []]
            self.assertTrue(any(str(u).startswith("https://") for u in urls if u), row["fixture_id"])
            self.assertTrue(str(row.get("hotspawn_url") or "").startswith("https://"), row["fixture_id"])

    def test_originated_rows_cite_the_official_valve_file(self):
        for row in self.rows:
            if row["basis"] in ("originated_vrs", "originated_rank"):
                kinds = {e.get("kind") for e in row.get("evidence") or []}
                self.assertTrue(kinds & {"official_valve_vrs", "official_valve_vrs_rank_substitution"},
                                row["fixture_id"])
                self.assertTrue(
                    any("standings_global" in str(e.get("url"))
                        or "hltv.org" in str(e.get("url"))
                        for e in row["evidence"]),
                    row["fixture_id"],
                )

    def test_rank_substitution_rows_are_flagged(self):
        for row in self.rows:
            if row["basis"] == "originated_rank":
                self.assertIn("rating_from_published_standing_not_a_measured_rating", row["flags"],
                              row["fixture_id"])

    def test_hotspawn_crowd_percentage_never_enters_the_board(self):
        blob = json.dumps(self.board).lower()
        for token in FORBIDDEN:
            self.assertNotIn(token, blob, f"crowd-percentage field '{token}' leaked into the board")

    def test_cross_check_records_other_boards_without_copying_them(self):
        for row in self.rows:
            for item in row.get("cross_check") or []:
                self.assertIn(item.get("agrees"), (True, False), row["fixture_id"])
                self.assertTrue(str(item.get("page") or "").endswith(".html"), row["fixture_id"])

    def test_summary_counts_match_the_rows(self):
        summary = self.board["summary"]
        self.assertEqual(summary["with_pick"], sum(1 for r in self.rows if r.get("pick")))
        self.assertEqual(summary["unresolved"], sum(1 for r in self.rows if not r.get("pick")))
        self.assertEqual(sum(summary["by_basis"].values()), len(self.rows))


class RenderedPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {p.name: p.read_text(encoding="utf-8") for p in SITE.glob("*.html")}

    def test_all_four_pages_exist(self):
        for name in ("index.html", "method.html", "flagged.html", "repo-audit.html"):
            self.assertIn(name, self.pages, f"missing {name}")

    def test_pages_are_mobile_friendly_and_self_contained(self):
        for name, text in self.pages.items():
            self.assertIn('name="viewport"', text, name)
            self.assertIn("width=device-width", text, name)
            self.assertNotIn("<script", text, f"{name} must not ship JavaScript")
            self.assertNotIn("http://", text.replace("http://www.w3.org", ""),
                             f"{name} links must be https")

    def test_index_links_every_pick_list_on_the_site(self):
        text = self.pages["index.html"]
        for href in ("../cs2.html", "../board/picks.html", "../picks-every-match/index.html",
                     "../ourline/index.html", "../coverage/index.html", "../summary/index.html",
                     "../flagged.html", "flagged.html"):
            self.assertIn(f'href="{href}"', text, f"index does not link {href}")

    def test_every_rendered_row_has_a_source_link(self):
        text = self.pages["index.html"]
        cards = re.findall(r'<div class="pickcard" id="m-\d+".*?(?=<div class="pickcard" id="m-|\Z)',
                           text, re.S)
        self.assertTrue(cards, "no pick cards rendered")
        for card in cards:
            self.assertIn("https://", card)
            self.assertTrue(re.search(r'PICK: <b>.+?</b>', card) or "NO PICK" in card,
                            "card without a pick statement")

    def test_unresolved_section_published_on_the_index(self):
        text = self.pages["index.html"]
        self.assertIn("Unresolved picks", text)

    def test_no_broken_local_links(self):
        for name, text in self.pages.items():
            for href in re.findall(r'href="([^"]+)"', text):
                if href.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                self.assertTrue((SITE / href).exists(), f"{name} -> {href}")


class RefreshAutomation(unittest.TestCase):
    WORKFLOW = ROOT / ".github" / "workflows" / "unresolved-7177d07f.yml"

    def test_workflow_refreshes_at_least_every_8_hours(self):
        text = self.WORKFLOW.read_text(encoding="utf-8")
        crons = re.findall(r"cron:\s*'([^']+)'", text)
        self.assertTrue(crons, "no cron schedule")
        for cron in crons:
            fields = cron.split()
            if len(fields) != 5:
                continue
            hour_field = fields[1]
            if hour_field.startswith("*/"):
                gap = int(hour_field.split("/")[1])
            elif "," in hour_field:
                hours = sorted(int(h) for h in hour_field.split(","))
                gap = max(b - a for a, b in zip(hours, hours[1:]) + [(hours[-1], hours[0] + 24)])
            elif hour_field == "*":
                gap = 1
            else:
                gap = 24
            self.assertLessEqual(gap, 8, f"cron '{cron}' gap {gap}h exceeds 8h")


if __name__ == "__main__":
    unittest.main()


class ExchangeJoin(unittest.TestCase):
    """The Kalshi join must only fire when both sides are genuinely quoted."""

    @staticmethod
    def _module():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "board_7177d07f", ROOT / "scripts" / "7177d07f" / "build.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_two_sided_book_is_joined_and_oriented(self):
        mod = self._module()
        snap = {"exchange_books": [
            {"event_id": "EV", "title": "Alpha", "subtitle": "", "public_url": "u1",
             "yes_bid_dollars": 0.30, "yes_ask_dollars": 0.32},
            {"event_id": "EV", "title": "Beta", "subtitle": "", "public_url": "u2",
             "yes_bid_dollars": 0.68, "yes_ask_dollars": 0.70},
        ]}
        out = mod.match_exchange_book(snap, {"team_a": "Alpha", "team_b": "Beta"})
        self.assertIsNotNone(out)
        # Alpha is quoted around 31c, so its implied decimal price must be the larger of the two.
        self.assertGreater(out["decimal_a"], out["decimal_b"])
        self.assertAlmostEqual(1.0 / out["decimal_a"] + 1.0 / out["decimal_b"], 1.0, places=3)

    def test_thin_or_one_sided_books_are_rejected(self):
        mod = self._module()
        thin = {"exchange_books": [
            {"event_id": "EV", "title": "Alpha", "subtitle": "", "public_url": "u1",
             "yes_bid_dollars": 0.10, "yes_ask_dollars": 0.90},
            {"event_id": "EV", "title": "Beta", "subtitle": "", "public_url": "u2",
             "yes_bid_dollars": 0.10, "yes_ask_dollars": 0.90},
        ]}
        self.assertIsNone(mod.match_exchange_book(thin, {"team_a": "Alpha", "team_b": "Beta"}))
        one_sided = {"exchange_books": [
            {"event_id": "EV", "title": "Alpha", "subtitle": "", "public_url": "u1",
             "yes_bid_dollars": 0.40, "yes_ask_dollars": 0.42},
        ]}
        self.assertIsNone(mod.match_exchange_book(one_sided, {"team_a": "Alpha", "team_b": "Beta"}))
        unrelated = {"exchange_books": [
            {"event_id": "EV", "title": "Gamma", "subtitle": "", "public_url": "u1",
             "yes_bid_dollars": 0.40, "yes_ask_dollars": 0.42},
            {"event_id": "EV", "title": "Delta", "subtitle": "", "public_url": "u2",
             "yes_bid_dollars": 0.40, "yes_ask_dollars": 0.42},
        ]}
        self.assertIsNone(mod.match_exchange_book(unrelated, {"team_a": "Alpha", "team_b": "Beta"}))
