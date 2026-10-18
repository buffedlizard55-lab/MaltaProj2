import json, pathlib, unittest
R=pathlib.Path(__file__).resolve().parents[1]
class T(unittest.TestCase):
 def setUp(self): self.d=json.loads((R/"finalday/data/board.json").read_text())
 def test_day5_novig(self):
  for m in self.d["day5"]:
   ia,ib=1/m["odds_a"],1/m["odds_b"]
   self.assertAlmostEqual(m["prob_a"],ia/(ia+ib),places=6); self.assertAlmostEqual(m["prob_a"]+m["prob_b"],1,places=6)
 def test_verdicts(self):
  f=[m for m in self.d["day5"] if m["a"]=="FURIA"][0]; self.assertEqual(f["safe"],"FURIA"); self.assertLess(f["dog_prob"],.35)
  a=[m for m in self.d["day5"] if m["b"]=="Falcons"][0]; self.assertEqual(a["safe"],"Falcons"); self.assertGreaterEqual(a["dog_prob"],.35)
 def test_every_open_row_pick_and_source(self):
  for r in self.d["rows"]:
   self.assertTrue(r.get("pick")); self.assertTrue(r.get("sources")); self.assertAlmostEqual(r["prob_a"]+r["prob_b"],1,delta=.02)
 def test_pages_link_unresolved(self):
  idx=(R/"finalday/index.html").read_text(); self.assertIn("unresolved.html",idx); self.assertIn("picks.html",idx)
  self.assertIn("width=device-width",idx)
 def test_no_crowd_as_probability(self):
  self.assertIn("ownership only",(R/"finalday/index.html").read_text())
if __name__=="__main__": unittest.main()
