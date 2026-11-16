"""#609: "Return target permanent to its owner's hand. Then that player discards a card." binds to the owner."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, BEAR, card

SPELL = card("Test Deterrence", "{1}{U}", "Instant", "Return target nonland permanent to its owner's hand. "
             "Then that player discards a card.")


class ThatPlayerAfterBounce(unittest.TestCase):
    def test_owner_discards(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        bear = g.enter_battlefield(b, BEAR)
        a.hand = [SPELL]
        b.hand = [ISLAND, ISLAND]
        g.enter_battlefield(a, ISLAND)
        g.enter_battlefield(a, ISLAND)
        g.settle()
        self.assertTrue(g.cast(a, SPELL, [bear]))
        g.settle()
        self.assertEqual(len(a.hand), 0)
        self.assertEqual(len(b.hand), 2)          # bear returned (+1), one discarded (-1)


if __name__ == "__main__":
    unittest.main()
