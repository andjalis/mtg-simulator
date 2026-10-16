import unittest
from pathlib import Path

from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.runner import build_deck, clear_result, pool_rate, run_match

DB_PATH = Path(__file__).resolve().parent.parent / "mtgsim" / "data" / "cards.sqlite3"
RANKS = Path(__file__).resolve().parent.parent / "decks" / "ranks"


class EarlyStopRuleTests(unittest.TestCase):
    def test_clear_result(self):
        self.assertFalse(clear_result(10, 10))       # too few games, however lopsided
        self.assertTrue(clear_result(17, 20))
        self.assertTrue(clear_result(3, 20))
        self.assertFalse(clear_result(16, 20))
        self.assertFalse(clear_result(55, 100))      # close matchups play in full
        self.assertTrue(clear_result(17.5, 20))      # draws count half

    def test_pool_rate_is_mean_of_matchups(self):
        self.assertAlmostEqual(pool_rate([(19, 20), (30, 100)]), (0.95 + 0.3) / 2)
        self.assertAlmostEqual(pool_rate([(60, 100), (40, 100)]), 0.5)   # same as pooled with equal games
        self.assertEqual(pool_rate([(0, 0)]), 0.0)


@unittest.skipUnless(DB_PATH.exists(), "needs the card database (python3 -m mtgsim.build_carddb)")
class EarlyStopMatchTests(unittest.TestCase):
    def test_stopped_match_is_a_prefix_of_the_full_one(self):
        db = CardDB(offline=True)
        a = build_deck(db, load_deck(RANKS / "4-platinum" / "mono_red_aggro.txt")[1])
        b = build_deck(db, load_deck(RANKS / "1-bronze" / "vanilla_pile.txt")[1])
        seen = []
        short, _ = run_match("a", a, "b", b, games=60, seed=3, stop_early=True)
        full, _ = run_match("a", a, "b", b, games=60, seed=3,
                            on_game=lambda r: seen.append((r.wins_a, r.draws)))
        self.assertLess(short.games, 60)
        self.assertEqual(short.games % 10, 0)
        self.assertEqual((short.wins_a, short.draws), seen[short.games - 1])
        self.assertEqual(short.turns, full.turns[:short.games])


if __name__ == "__main__":
    unittest.main()
