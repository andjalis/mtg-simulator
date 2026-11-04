"""Lair lands: sacrifice unless you return a non-Lair land."""
import random
import unittest

from mtgsim import cards
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, card

LAIR = card("Test Lair", "", "Land", "When Test Lair enters, sacrifice it unless you return a non-Lair land you control to its owner's hand.\n{T}: Add {U}.")
OTHER = card("Test Land", "", "Land", "{T}: Add {G}.")


class Lair(unittest.TestCase):
    def test_parses(self):
        effects, unmatched = cards._parse_effects("Sacrifice it unless you return a non-Lair land you control to its owner's hand.")
        self.assertEqual((unmatched, effects[0].kind), ([], "sac_unless_bounce"))
        self.assertEqual(LAIR.unsupported, [])

    def _run(self, with_land):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        lair = Permanent(LAIR, a)
        other = Permanent(OTHER, a)
        a.battlefield.append(lair)
        if with_land:
            a.battlefield.append(other)
        eff = cards._parse_effects("Sacrifice it unless you return a non-Lair land you control to its owner's hand.")[0][0]
        game.resolve(a, eff, None, StackItem(controller=a, effects=[eff], targets=[None], source=lair))
        return a, lair, other

    def test_bounces_other_land(self):
        a, lair, other = self._run(True)
        self.assertIn(lair, a.battlefield)
        self.assertNotIn(other, a.battlefield)

    def test_sacrificed_without_land(self):
        a, lair, _ = self._run(False)
        self.assertNotIn(lair, a.battlefield)


if __name__ == "__main__":
    unittest.main()
