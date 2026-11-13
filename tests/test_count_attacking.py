"""#420: ("count", "attacking creature") counts the creatures you're attacking with (it was always 0), so Kinscaer
Sentry can put a creature with mana value X or less onto the battlefield attacking."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import PLAINS, card

SENTRY = card("Test Sentry", "{1}{W}", "Creature — Human Soldier",
              "First strike, lifelink\nWhenever this creature attacks, you may put a creature card with mana value X "
              "or less from your hand onto the battlefield tapped and attacking, where X is the number of attacking "
              "creatures you control.", 2, 1)
BEAR = card("Bear", "{1}{W}", "Creature — Bear", "", 2, 2)
TROLL = card("Troll", "{2}{W}", "Creature — Troll", "", 3, 3)


def game(*others):
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [PLAINS] * 10
    attackers = [g.enter_battlefield(a, c) for c in (SENTRY,) + others]
    for x in attackers:
        x.sick = False
    g.settle()
    a.ai.attack = attackers
    return g, a, b


class CountAttacking(unittest.TestCase):
    def test_count(self):
        g, a, b = game(BEAR)
        g.attackers = list(a.battlefield)
        self.assertEqual(g.x_quantity(a, ("count", "attacking creature"), None, None), 2)
        g.attackers = []
        self.assertEqual(g.x_quantity(a, ("count", "attacking creature"), None, None), 0)

    def test_sentry_with_two_attackers_puts_a_two_drop_in(self):
        g, a, b = game(BEAR)
        a.hand += [TROLL, card("Squire", "{1}{W}", "Creature — Human", "", 1, 2)]
        g.combat(a, b)
        g.settle()
        self.assertEqual([c.name for c in a.hand], ["Troll"])         # mana value 3 > X = 2 stays
        self.assertTrue(any(x.card.name == "Squire" for x in a.battlefield))


if __name__ == "__main__":
    unittest.main()
