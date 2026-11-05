"""Flip cards: you may flip it."""
import random
import unittest

from mtgsim import cards
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR


class Flip(unittest.TestCase):
    def setUp(self):
        self.pupil = CardDB(offline=True).get("Budoka Pupil // Ichiga, Who Topples Oaks")

    def test_parses(self):
        effects, unmatched = cards._parse_effects("You may flip it.")
        self.assertEqual((unmatched, effects[-1].kind), ([], "flip_self"))
        if self.pupil is not None:
            self.assertEqual(self.pupil.unsupported, [])

    def test_flips_to_back_face(self):
        if self.pupil is None:
            self.skipTest("card database missing")
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        perm = Permanent(self.pupil, a)
        a.battlefield.append(perm)
        eff = cards._parse_effects("You may flip it.")[0][-1]
        game.resolve(a, eff, None, StackItem(controller=a, effects=[eff], targets=[None], source=perm))
        self.assertEqual(perm.card.name, "Ichiga, Who Topples Oaks")
        game.resolve(a, eff, None, StackItem(controller=a, effects=[eff], targets=[None], source=perm))
        self.assertEqual(perm.card.name, "Ichiga, Who Topples Oaks")     # flipping never turns it back


if __name__ == "__main__":
    unittest.main()
