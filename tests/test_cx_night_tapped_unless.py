"""Lands that enter tapped unless you control a legendary creature (condition from cx_condlib)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, card

CAMP = card("Test Camp", "", "Land", "~ enters tapped unless you control a legendary creature.\n{T}: Add {R}.")
KING = card("Test King", "{1}{R}", "Legendary Creature — Human", "Haste", 2, 2)


class TappedUnless(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        self.game.turn, self.game.step = 1, "main1"

    def test_parses(self):
        self.assertTrue(CAMP.tapped_condition.startswith("lib:"))
        self.assertEqual(CAMP.unsupported, [])

    def test_tapped_without_legend(self):
        self.assertTrue(self.game.enter_battlefield(self.a, CAMP).tapped)

    def test_untapped_with_legend(self):
        self.a.battlefield.append(Permanent(KING, self.a))
        self.assertFalse(self.game.enter_battlefield(self.a, CAMP).tapped)


if __name__ == "__main__":
    unittest.main()
