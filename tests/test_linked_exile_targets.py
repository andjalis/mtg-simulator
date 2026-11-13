"""#358: O-Ring-style linked exile ("When ~ enters, exile target ... . When ~ leaves the battlefield, return the
exiled card ...", parsed as blink_link_exile/blink_link_return) picks the opponent's best permanent, instead of no
target (the trigger fizzled)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import PLAINS, card

ORING = card("Test Ring", "{2}{W}", "Enchantment",
             "When this enchantment enters, exile another target nonland permanent.\n"
             "When this enchantment leaves the battlefield, return the exiled card to the battlefield under its "
             "owner's control.")
HUNTER = card("Test Hunter", "{2}{W}{W}", "Creature — Human Cleric",
              "When this creature enters, you may exile another target creature.\n"
              "When this creature leaves the battlefield, return the exiled card to the battlefield under its "
              "owner's control.", 1, 3)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [PLAINS] * 10
    for _ in range(4):
        g.enter_battlefield(a, PLAINS).sick = False
    mine = g.enter_battlefield(a, card("Mine", "{1}", "Creature — Human", "", 1, 1))
    small = g.enter_battlefield(b, card("Small", "{1}", "Creature — Ogre", "", 1, 1))
    big = g.enter_battlefield(b, card("Big", "{4}", "Creature — Ogre", "", 5, 5))
    g.settle()
    return g, a, b, mine, small, big


class LinkedExileTargets(unittest.TestCase):
    def test_parse_is_linked_exile(self):
        self.assertEqual(ORING.triggers[0].effects[0].kind, "blink_link_exile")

    def test_ring_exiles_their_best_and_returns_it(self):
        g, a, b, mine, small, big = game()
        a.hand.append(ORING)
        g.main_phase(a)
        g.settle()
        ring = next(x for x in a.battlefield if x.card.name == "Test Ring")
        self.assertNotIn(big, b.battlefield)
        self.assertIn(mine, a.battlefield)
        self.assertIn(small, b.battlefield)
        g.leave_battlefield(ring, "graveyard")
        g.settle()
        self.assertTrue(any(x.card.name == "Big" for x in b.battlefield))

    def test_hunter_exiles_their_creature(self):
        g, a, b, mine, small, big = game()
        a.hand.append(HUNTER)
        g.main_phase(a)
        g.settle()
        self.assertTrue(any(x.card.name == "Test Hunter" for x in a.battlefield))
        self.assertNotIn(big, b.battlefield)
        self.assertIn(mine, a.battlefield)


if __name__ == "__main__":
    unittest.main()
