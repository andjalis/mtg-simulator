"""#512: a generic cost reduction the spell's generic part can't use lowers the {X} part (601.2f: the reduction
applies to the total cost, X included)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import card


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class XReduction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def game(self, lands, permanents):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [self.db.get("Island")] * 10
        tapped = [g.enter_battlefield(a, self.db.get(n)) for n in lands]
        for x in tapped:
            x.sick = False
        for n in permanents:
            g.enter_battlefield(a, self.db.get(n))
        g.settle()
        return g, a, b, tapped

    def cast_blaze(self, permanents):
        g, a, b, lands = self.game(["Mountain"] * 3, permanents)
        blaze = self.db.get("Blaze")
        a.hand.append(blaze)
        self.assertTrue(g.cast(a, blaze, [b]))
        g.settle()
        return b.life, lands

    def test_reduction_lowers_x(self):
        life, lands = self.cast_blaze(["Goblin Electromancer"])      # {1} less: {X}{R} with 3 lands is X=3
        self.assertEqual(life, 17)
        self.assertTrue(all(x.tapped for x in lands))

    def test_two_reductions(self):
        life, _ = self.cast_blaze(["Goblin Electromancer", "Ruby Medallion"])     # {2} less: X=4
        self.assertEqual(life, 16)

    def test_no_reduction(self):
        life, _ = self.cast_blaze([])
        self.assertEqual(life, 18)

    def test_reduction_used_by_generic_part_first(self):
        g, a, b, lands = self.game(["Mountain"] * 3, ["Goblin Electromancer"])
        bolt = card("Test Bolt", "{X}{1}{R}", "Instant", "~ deals X damage to any target.")
        a.hand.append(bolt)
        self.assertTrue(g.cast(a, bolt, [b]))
        g.settle()
        self.assertEqual(b.life, 18)            # {1} goes to the {1}: X=2 from the other two Mountains

    def test_double_x_with_reduction(self):
        g, a, b, lands = self.game(["Mountain"] * 4, ["Goblin Electromancer"])
        drain = card("Test Drain", "{X}{X}{R}", "Sorcery", "Target player loses X life.")
        a.hand.append(drain)
        self.assertTrue(g.cast(a, drain, [b]))
        g.settle()
        self.assertEqual(b.life, 18)            # 3 mana + {1} less = 4 toward {X}{X}: X=2


    def test_ai_expects_the_larger_x(self):
        g, a, b, lands = self.game(["Mountain"] * 3, ["Goblin Electromancer"])
        sized = a.ai._sized(g, a, self.db.get("Blaze"))
        self.assertEqual(sized.spell_effects[0].amount, 3)

if __name__ == "__main__":
    unittest.main()
