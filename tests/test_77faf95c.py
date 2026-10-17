"""Contract tests for session 77faf95c (HQ board)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "77faf95c"


def _load(rel, default=None):
    p = DATA / rel
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


class TestCollectorContract(unittest.TestCase):
    def test_collect_script_exists(self):
        self.assertTrue((ROOT / "scripts" / "77faf95c" / "collect.py").exists())

    def test_access_log_records_every_source(self):
        acc = _load("access.json")
        if acc is None:
            self.skipTest("no capture yet")
        for key in ("hotspawn_lobby_page", "pinnacle", "bovada", "melbet", "kalshi"):
            self.assertIn(key, acc["sources"])


if __name__ == "__main__":
    unittest.main()
