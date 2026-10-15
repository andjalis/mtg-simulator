import json
import tempfile
import unittest
from pathlib import Path

from mtgsim.assess import assess
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck_full, parse_decklist, parse_full
from mtgsim.runner import build_deck
from mtgsim.sideboard import card_value, classify, plan_sideboard, roles, run_bo3

ROOT = Path(__file__).resolve().parent.parent
UB = ROOT / "decks" / "ub_snow_control.txt"
RED = {"Mountain": 24, "Monastery Swiftspear": 4, "Goblin Guide": 4, "Raging Goblin": 4, "Keldon Raider": 4,
       "Lightning Bolt": 4, "Shock": 4, "Lava Spike": 4, "Searing Spear": 4, "Hill Giant": 4}
RED_SB = {"Duress": 2, "Negate": 2, "Pyroclasm": 2}


class ParseTests(unittest.TestCase):
    def test_table_with_bring_in_notes(self):
        _, d = load_deck_full(UB)
        self.assertEqual(sum(d.main.values()), 60)
        self.assertEqual(sum(d.sideboard.values()), 15)
        self.assertEqual(d.bring_in["Duress"], "Control")
        self.assertEqual(d.bring_in["Vampire Nighthawk"], "Aggro")

    def test_arena_mtgo_and_sb_prefix(self):
        main = "\n".join(f"{n} {c}" for c, n in RED.items())
        self.assertEqual(parse_full(main + "\n\nSideboard\n2 Duress\n1 Negate").sideboard, {"Duress": 2, "Negate": 1})
        self.assertEqual(parse_full(main + "\n\n2 Duress").sideboard, {"Duress": 2})       # MTGO blank line
        d = parse_full(main + "\nSB: 2 Duress\nSB: 1 Negate")
        self.assertEqual(d.sideboard, {"Duress": 2, "Negate": 1})
        self.assertEqual(sum(d.main.values()), 60)
        self.assertEqual(parse_decklist(main + "\nSideboard\n2 Duress"), RED)
        self.assertEqual(parse_full(main + "\nMaybeboard\n2 Duress").sideboard, {})


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def test_roles_and_values(self):
        self.assertIn("discard", roles(self.db.get("Duress")))
        self.assertIn("narrow_counter", roles(self.db.get("Negate")))
        self.assertIn("sweeper", roles(self.db.get("Blood on the Snow")))
        duress = self.db.get("Duress")
        self.assertGreater(card_value(duress, "control"), card_value(duress, "aggro"))
        self.assertLess(card_value(duress, "aggro", "Control"), card_value(duress, "aggro"))
        self.assertGreater(card_value(duress, "control", "Control"), card_value(duress, "control", "Aggro"))

    def test_classify(self):
        self.assertEqual(classify(build_deck(self.db, RED)), "aggro")
        self.assertEqual(classify(build_deck(self.db, load_deck_full(UB)[1].main)), "control")

    def test_plan_keeps_size_and_lands(self):
        d = load_deck_full(UB)[1]
        for opp in ("aggro", "midrange", "control"):
            p = plan_sideboard(d.main, d.sideboard, self.db, opp, d.bring_in)
            self.assertEqual(sum(p.deck.values()), 60)
            self.assertLessEqual(sum(p.ins.values()), 6)
            self.assertEqual(sum(p.ins.values()), sum(p.outs.values()))
            self.assertFalse(any("Land" in self.db.get(c).types for c in p.outs))
        vs_aggro = plan_sideboard(d.main, d.sideboard, self.db, "aggro", d.bring_in)
        self.assertIn("Vampire Nighthawk", vs_aggro.ins)
        self.assertNotIn("Duress", vs_aggro.ins)
        vs_control = plan_sideboard(d.main, d.sideboard, self.db, "control", d.bring_in)
        self.assertIn("Duress", vs_control.ins)
        self.assertEqual(plan_sideboard(d.main, {}, self.db, "aggro").ins, {})


class Bo3Tests(unittest.TestCase):
    def test_bo3_match_accounting(self):
        db = CardDB(offline=True)
        d = load_deck_full(UB)[1]
        r = run_bo3("ub", d.main, d.sideboard, "red", RED, RED_SB, db, matches=4, seed=1, bring_in_a=d.bring_in)
        self.assertEqual(r.matches, 4)
        self.assertEqual(r.g1_games, 4)
        self.assertTrue(4 <= r.post_games <= 8)
        self.assertEqual(r.plan_a.opponent_archetype, "aggro")
        self.assertEqual(r.plan_b.opponent_archetype, "control")
        self.assertIn("best-of-three", r.summary())
        self.assertTrue(0 <= r.match_win_rate_a <= 1)
        self.assertTrue(-1 <= r.sideboard_gain_a <= 1)

    def test_assess_adds_sideboard_criterion(self):
        with tempfile.TemporaryDirectory() as tmp:
            gm = Path(tmp) / "decks" / "ranks" / "7-grandmaster"
            gm.mkdir(parents=True)
            (gm / "red.txt").write_text("\n".join(f"{n} {c}" for c, n in RED.items()) + "\n\nSideboard\n2 Pyroclasm")
            meta_file = Path(tmp) / "meta.json"
            meta_file.write_text(json.dumps({
                "format": "Standard", "date": "2026-10-15", "window": "test", "sources": [],
                "archetypes": [{"name": "Red", "file": "red.txt", "share": {"A": 10.0}}]}))
            d = load_deck_full(UB)[1]
            out = assess("ub", d.main, CardDB(offline=True), games=2, goldfish_games=5, samples=200, seed=2,
                         metagame=meta_file, decks_dir=Path(tmp) / "decks", bo3=2, sideboard=d.sideboard,
                         bring_in=d.bring_in)
        json.dumps(out)
        sb = out["criteria"]["sideboard"]
        self.assertIn(sb["grade"], list("SABCDF"))
        self.assertTrue(sb["details"]["has_sideboard"])
        self.assertEqual(sb["details"]["matchups"][0]["matches"], 2)


if __name__ == "__main__":
    unittest.main()
