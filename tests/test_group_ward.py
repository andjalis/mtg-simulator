"""#633: "Other creatures you control have ward {1}" (a keyword grant with a parameter)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

WHALE = card("Test Whale", "{3}{U}", "Creature — Whale", "Other creatures you control have ward {1}.", 3, 3)
BEAR = card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2)


class GroupWard(unittest.TestCase):
    def setUp(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(a, b, random.Random(0), log=True)
        self.g.turn, self.g.step = 1, "main1"
        a.library = b.library = [ISLAND] * 10
        self.a, self.b = a, b

    def test_parse(self):
        self.assertEqual(WHALE.unsupported, [])
        odd = card("Odd", "{1}", "Creature — Elf", "Creatures you control with a counter on them have ward {1}.", 1, 1)
        self.assertTrue(odd.unsupported)         # "a counter" names no counter kind: left ignored, not guessed

    def test_grants_ward_to_others_only(self):
        whale = self.g.enter_battlefield(self.a, WHALE)
        bear = self.g.enter_battlefield(self.a, BEAR)
        theirs = self.g.enter_battlefield(self.b, BEAR)
        self.assertEqual(bear.ward, 1)
        self.assertEqual(whale.ward, 0)
        self.assertEqual(theirs.ward, 0)

    def test_goes_away_with_the_source(self):
        whale = self.g.enter_battlefield(self.a, WHALE)
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.g.leave_battlefield(whale, "graveyard")
        self.assertEqual(bear.ward, 0)


if __name__ == "__main__":
    unittest.main()
