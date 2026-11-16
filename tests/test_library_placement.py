"""#632: "third from the top", "its owner shuffles it into their library", "shuffle your hand and graveyard into your library"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, MOUNTAIN, card

THIRD = card("Test Third", "{U}", "Instant", "Put target nonland permanent into its owner's library third from the top.")
SHUF = card("Test Shuffle", "{U}", "Instant", "Target creature's owner shuffles it into their library.")
RESET = card("Test Reset", "{U}", "Sorcery", "Shuffle your hand and graveyard into your library.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    a.library = [ISLAND] * 10
    b.library = [MOUNTAIN] * 10
    return g, a, b


class LibraryPlacement(unittest.TestCase):
    def test_parse(self):
        for c in (THIRD, SHUF, RESET):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(THIRD.spell_effects[0].data["depth"], 2)

    def test_refusal(self):
        c = card("Test Odd", "{U}", "Instant", "Put target nonland permanent into its owner's library third from the top "
                 "and tapped.")
        self.assertTrue(c.unsupported)

    def test_third_from_top(self):
        g, a, b = game()
        ogre = card("Ogre", "{3}", "Creature — Ogre", "", 3, 3)
        perm = g.enter_battlefield(b, ogre)
        g.enter_battlefield(a, ISLAND)
        a.hand = [THIRD]
        self.assertTrue(g.cast(a, THIRD, [perm]))
        g.settle()
        self.assertNotIn(perm, b.battlefield)
        self.assertEqual(b.library[-3].name, "Ogre")        # the top of the library is the end of the list

    def test_shuffle_hand_and_graveyard(self):
        g, a, b = game()
        g.enter_battlefield(a, ISLAND)
        a.hand = [RESET, ISLAND, ISLAND]
        a.graveyard = [MOUNTAIN, MOUNTAIN]
        self.assertTrue(g.cast(a, RESET, []))
        g.settle()
        self.assertEqual(len(a.hand), 0)
        self.assertEqual(len(a.library), 10 + 2 + 2)
        self.assertEqual([c.name for c in a.graveyard], ["Test Reset"])


if __name__ == "__main__":
    unittest.main()
