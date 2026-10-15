import json
import tempfile
import unittest
from pathlib import Path

from mtgsim.assess import (assess, assess_consistency, assess_mana, color_pips, grade, load_metagame,
                           meta_weighted_rows, p_on_curve, sources_needed, text_report)
from mtgsim.carddb import CardDB
from mtgsim.rating import RANKS, performance_rating
from mtgsim.runner import build_deck

RED = {"Mountain": 24, "Monastery Swiftspear": 4, "Goblin Guide": 4, "Raging Goblin": 4, "Keldon Raider": 4,
       "Lightning Bolt": 4, "Shock": 4, "Lava Spike": 4, "Searing Spear": 4, "Hill Giant": 4}
GREEN = {"Forest": 24, "Llanowar Elves": 4, "Grizzly Bears": 4, "Elvish Visionary": 4, "Kalonian Tusker": 4,
         "Garruk's Companion": 4, "Centaur Courser": 4, "Giant Growth": 4, "Rumbling Baloth": 4,
         "Colossal Dreadmaw": 4}


def as_text(counts):
    return "\n".join(f"{n} {c}" for c, n in counts.items())


class KarstenTests(unittest.TestCase):
    def test_close_to_karstens_table(self):
        # Karsten's 60-card table (with mulligans) says 14 for C on turn 1, 21 for CC on turn 2,
        # 16 for 2CC on turn 4; the exact calculation without mulligans is within a source or two.
        self.assertIn(sources_needed(60, 24, 1, 1), (14, 15, 16))
        self.assertIn(sources_needed(60, 24, 2, 2), (20, 21, 22))
        self.assertIn(sources_needed(60, 24, 2, 4), (15, 16, 17))
        self.assertAlmostEqual(p_on_curve(60, 24, 24, 1, 1), 1.0)
        self.assertLess(p_on_curve(60, 24, 8, 1, 1), p_on_curve(60, 24, 16, 1, 1))

    def test_pips(self):
        self.assertEqual(color_pips("{1}{U}{U}"), {"U": 2})
        self.assertEqual(color_pips("{W/U}{B/P}{2}{R}"), {"R": 1})  # hybrid and Phyrexian can be paid otherwise

    def test_grades(self):
        self.assertEqual([grade(s) for s in (95, 80, 60, 50, 30, 0)], ["S", "A", "B", "C", "D", "F"])


class CriteriaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def test_mana_punishes_splashing_on_basics(self):
        mono = assess_mana(RED, self.db)
        self.assertEqual(mono["score"], 100)
        mess = {"Mountain": 12, "Forest": 12, "Lightning Bolt": 12, "Grizzly Bears": 12, "Kalonian Tusker": 12}
        bad = assess_mana(mess, self.db)
        self.assertLess(bad["score"], 60)
        self.assertEqual(bad["details"]["sources"], {"R": 12, "G": 12})
        self.assertEqual(bad["details"]["spells"][0]["name"], "Kalonian Tusker")  # GG on turn 2 is the worst

    def test_consistency_sees_flood(self):
        normal = assess_consistency(build_deck(self.db, RED), samples=3000, seed=1)
        glut = dict(RED, Mountain=36, **{"Hill Giant": 0})
        glut = assess_consistency(build_deck(self.db, {k: v for k, v in glut.items() if v}), samples=3000, seed=1)
        self.assertGreater(glut["details"]["flood_rate"], normal["details"]["flood_rate"] + 0.2)
        self.assertGreater(normal["score"], glut["score"])
        keys = {k["name"] for k in normal["details"]["key_cards"]}
        self.assertIn("Lightning Bolt", keys)
        self.assertGreater(normal["details"]["curve"]["1"], 0.5)


class MetaTests(unittest.TestCase):
    def test_reweighting(self):
        r = RANKS[-1].anchor
        res = [("a", r, 9, 10), ("b", r, 1, 10), ("silver/x", 1100, 5, 10)]
        even = performance_rating(meta_weighted_rows(res, {"a": 0.5, "b": 0.5}))
        self.assertAlmostEqual(even, performance_rating([(r, 9, 10), (r, 1, 10), (1100, 5, 10)]), delta=0.5)
        heavy_a = performance_rating(meta_weighted_rows(res, {"a": 0.9, "b": 0.1}))
        self.assertGreater(heavy_a, even + 100)
        # ladder names carry the pool: "grandmaster/a" matches archetype "a"
        rows = meta_weighted_rows([("grandmaster/a", r, 9, 10), ("grandmaster/b", r, 1, 10)], {"a": 0.9, "b": 0.1})
        self.assertAlmostEqual(sum(p for _, p, _ in rows), 0.9 * 20 * 0.9 + 0.1 * 20 * 0.1)

    def test_assess_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            pro = Path(tmp) / "decks" / "tiers" / "5-pro"
            pro.mkdir(parents=True)
            (pro / "green.txt").write_text(as_text(GREEN))
            meta_file = Path(tmp) / "meta.json"
            meta_file.write_text(json.dumps({
                "format": "Standard", "date": "2026-10-15", "window": "test",
                "sources": [{"name": "Test", "url": "https://example.com", "read": "2026-10-15"}],
                "archetypes": [{"name": "Green", "file": "green.txt", "share": {"A": 10.0, "B": 20.0}},
                               {"name": "Absent", "file": "absent.txt", "share": {"A": 5.0}}]}))
            meta, archetypes = load_metagame(meta_file, Path(tmp) / "decks")
            self.assertEqual([a.name for a in archetypes], ["Green"])
            self.assertEqual(meta["missing"], ["Absent"])
            self.assertAlmostEqual(archetypes[0].weight, 1.0)
            out = assess("red", RED, CardDB(offline=True), games=6, goldfish_games=10, samples=500, seed=3,
                         metagame=meta_file, decks_dir=Path(tmp) / "decks")
        json.dumps(out)  # plain JSON
        self.assertEqual(set(out["criteria"]), {"meta", "mana", "speed", "consistency"})
        self.assertIn(out["rating"]["rank"], [r.name for r in RANKS])
        m = out["criteria"]["meta"]["details"]
        self.assertEqual(m["games"], 6)
        self.assertEqual(m["matchups"][0]["name"], "Green")
        self.assertEqual(m["metagame"]["missing_decklists"], ["Absent"])
        for c in out["criteria"].values():
            self.assertTrue(0 <= c["score"] <= 100 and c["grade"] and c["summary"])
        self.assertIn("Rank", text_report(out))

    def test_reuses_given_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            pro = Path(tmp) / "decks" / "tiers" / "5-pro"
            pro.mkdir(parents=True)
            (pro / "green.txt").write_text(as_text(GREEN))
            meta_file = Path(tmp) / "meta.json"
            meta_file.write_text(json.dumps({"archetypes": [{"name": "Green", "file": "green.txt",
                                                             "share": {"A": 10.0}}]}))
            out = assess("red", RED, CardDB(offline=True), goldfish_games=5, samples=200, metagame=meta_file,
                         decks_dir=Path(tmp) / "decks", meta_results={"green": (50.0, 100)})
        self.assertAlmostEqual(out["criteria"]["meta"]["details"]["weighted_win_rate"], 0.5)
        self.assertEqual(out["criteria"]["meta"]["details"]["engine"], "given")


if __name__ == "__main__":
    unittest.main()
