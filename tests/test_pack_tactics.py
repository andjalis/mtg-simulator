"""#419: Pack tactics' condition ("if you attacked with creatures with total power N or greater this combat") is kept;
it used to be dropped, so the ability worked on every attack."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import MOUNTAIN, card

MINION = card("Test Minion", "{R}", "Creature — Kobold",
              "Menace\nPack tactics — Whenever this creature attacks, if you attacked with creatures with total power "
              "6 or greater this combat, you may put a Dragon creature card from your hand onto the battlefield tapped "
              "and attacking.", 0, 1)
DRAGON = card("Test Dragon", "{5}{R}", "Creature — Dragon", "Flying", 5, 5)


def game(*others):
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [MOUNTAIN] * 10
    minion = g.enter_battlefield(a, MINION)
    attackers = [minion] + [g.enter_battlefield(a, c) for c in others]
    for x in attackers:
        x.sick = False
    g.settle()
    a.hand.append(DRAGON)
    a.ai.attack = attackers
    return g, a, b


class PackTactics(unittest.TestCase):
    def test_condition_is_parsed(self):
        trig = MINION.triggers[0]
        self.assertEqual(trig.filter, "packpow:6")

    def test_small_attack_does_nothing(self):
        g, a, b = game(card("Bear", "{1}", "Creature — Bear", "", 2, 2))
        g.combat(a, b)
        g.settle()
        self.assertIn(DRAGON, a.hand)

    def test_total_power_six_puts_the_dragon_in(self):
        g, a, b = game(card("Giant", "{4}", "Creature — Giant", "", 6, 6))
        g.combat(a, b)
        g.settle()
        self.assertNotIn(DRAGON, a.hand)
        self.assertTrue(any(x.card.name == "Test Dragon" for x in a.battlefield))


if __name__ == "__main__":
    unittest.main()
