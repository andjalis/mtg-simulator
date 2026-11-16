""""When you sacrifice ~" (#538): its own sacrifice, not another one, and not destruction."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card


class SacrificeSelf(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 5, HeuristicAI())
        self.b = Player("b", [BEAR] * 5, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_own_sacrifice_only(self):
        text = "When you sacrifice ~, you gain 2 life."
        mine = self.game.enter_battlefield(self.a, card("Test Snack", "{1}", "Artifact — Food", text))
        other = self.game.enter_battlefield(self.a, card("Rock", "{1}", "Artifact"))
        self.game.sacrifice(other)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.game.sacrifice(mine)
        self.game.settle()
        self.assertEqual(self.a.life, 22)
        again = self.game.enter_battlefield(self.a, card("Test Snack", "{1}", "Artifact — Food", text))
        self.game.destroy(again)                    # destroyed, not sacrificed
        self.game.settle()
        self.assertEqual(self.a.life, 22)

    @unittest.skipUnless(os.path.exists(os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data",
                                                     "cards.sqlite3")), "card database not built")
    def test_carrot_cake_both_heads(self):
        from mtgsim.carddb import CardDB
        cake = self.game.enter_battlefield(self.a, CardDB(offline=True).get("Carrot Cake"))
        self.game.settle()
        rabbits = lambda: sum("Rabbit" in x.card.subtypes for x in self.a.battlefield)
        self.assertEqual(rabbits(), 1)
        self.game.sacrifice(cake)
        self.game.settle()
        self.assertEqual(rabbits(), 2)


if __name__ == "__main__":
    unittest.main()
