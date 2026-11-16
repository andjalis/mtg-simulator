"""#823: a mandatory target the AI's policy declines is still chosen when one is legal (CR 603.3d)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class ForcedTarget(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_decimator_beetle_pays_its_drawback(self):
        wurm = self.game.enter_battlefield(self.a, db("Craw Wurm"))
        beetle = self.game.enter_battlefield(self.a, db("Decimator Beetle"))
        self.game.settle()
        self.assertEqual((wurm.counters.get("-1/-1", 0) + beetle.counters.get("-1/-1", 0)), 1)
        self.assertFalse(any("fizzles" in e for e in self.game.events))

    def test_drawback_on_our_own_goes_to_the_least_valuable(self):
        """Only our own creatures are legal: the -1/-1 lands on the Bear, not the Wurm (same rule as #780)."""
        from tests.test_templates import BEAR
        wurm = self.game.enter_battlefield(self.a, db("Craw Wurm"))
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.enter_battlefield(self.a, db("Decimator Beetle"))
        self.game.settle()
        self.assertEqual(wurm.counters.get("-1/-1", 0), 0)
        self.assertTrue(bear.counters.get("-1/-1", 0) == 1 or bear not in self.a.battlefield)

    def test_shivan_sand_mage_mode_finds_its_target(self):
        clock = self.game.enter_battlefield(self.a, card("T Clock", "{1}", "Artifact", ""))
        clock.counters["time"] = 3
        self.game.enter_battlefield(self.a, db("Shivan Sand-Mage"))
        self.game.settle()
        self.assertIn(clock.counters["time"], (1, 5))

    def test_no_legal_target_still_fizzles(self):
        self.game.enter_battlefield(self.a, db("Shivan Sand-Mage"))      # nothing with a time counter
        self.game.settle()
        self.assertTrue(any("fizzles" in e or "no legal target" in e for e in self.game.events)
                        or not any("trigger resolves" in e for e in self.game.events))


if __name__ == "__main__":
    unittest.main()
