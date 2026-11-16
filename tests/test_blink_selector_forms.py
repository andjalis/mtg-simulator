"""#645: selector forms behind DELAYEDBLINK leaks: "other than ~", "nonenchantment", "nonland, nontoken"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim import permanent_templates as pt
from tests.test_templates import ISLAND, BEAR


class SelectorForms(unittest.TestCase):
    def test_parse(self):
        self.assertTrue(pt.selector("permanent other than ~")["other"])
        self.assertEqual(pt.selector("nonenchantment permanent")["traits"], ["nonenchantment"])
        self.assertEqual(pt.selector("nonland, nontoken permanent")["traits"], ["nonland", "nontoken"])
        self.assertIsNone(pt.selector("permanent other than Bob"))

    def test_matching(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0))
        g.turn, g.step = 3, "main1"
        bear = g.enter_battlefield(a, BEAR)
        other = g.enter_battlefield(a, BEAR)
        land = g.enter_battlefield(a, ISLAND)
        spec = pt.selector("nonland permanent other than ~")
        self.assertFalse(pt.matches(g, bear, spec, a, bear))
        self.assertTrue(pt.matches(g, other, spec, a, bear))
        self.assertFalse(pt.matches(g, land, spec, a, bear))


if __name__ == "__main__":
    unittest.main()
