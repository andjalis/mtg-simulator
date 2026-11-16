"""#638: "Return an artifact you control to its owner's hand" / "Each player returns a creature they control ..."."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

CURFEW = card("Test Curfew", "{U}", "Instant", "Each player returns a creature they control to its owner's hand.")
SELF = card("Test Whirl", "{U}", "Instant", "Return another permanent you control to its owner's hand. Draw a card.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class BounceChoice(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(CURFEW.unsupported, [])
        self.assertEqual(CURFEW.spell_effects[0].kind, "bounce_choice")
        self.assertEqual(CURFEW.spell_effects[0].data["who"], "each")
        self.assertEqual(SELF.unsupported, [])

    def test_refuses_unreadable_phrase(self):
        c = card("Test Odd", "{U}", "Instant", "Return a creature that attacked this turn you control to its owner's hand.")
        self.assertTrue(c.unsupported)

    def test_each_player_returns_one(self):
        g, a, b = game()
        small = g.enter_battlefield(a, card("Elf", "{1}", "Creature — Elf", "", 1, 1))
        big = g.enter_battlefield(a, card("Ogre", "{3}", "Creature — Ogre", "", 3, 3))
        theirs = g.enter_battlefield(b, card("Imp", "{1}", "Creature — Imp", "", 1, 1))
        g.enter_battlefield(a, ISLAND)
        a.hand = [CURFEW]
        self.assertTrue(g.cast(a, CURFEW, [None]))
        g.settle()
        self.assertNotIn(small, a.battlefield)         # the cheapest creature went back
        self.assertIn(big, a.battlefield)
        self.assertNotIn(theirs, b.battlefield)
        self.assertEqual(len(b.hand), 1)


if __name__ == "__main__":
    unittest.main()
