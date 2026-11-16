"""#645: "you may pay {X}. If you do, <effect with X>" pays the largest affordable X and the payoff reads it."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, MOUNTAIN, BEAR, card

DRAWER = card("Test Ingenuity", "{1}{U}", "Creature — Wizard",
              "When this creature enters, you may pay {X}. If you do, draw X cards.", 1, 1)
LIFER = card("Test Vigil", "{1}{W}", "Enchantment",
             "Whenever a creature you control dies, you may pay {X}. If you do, you gain X life.")
TOKENS = card("Test Hobgoblins", "{4}{W}", "Enchantment",
              "When this enchantment enters, you may pay {X}. If you do, create X 1/1 white Soldier creature tokens.")
BURN = card("Test Dragon", "{4}{R}", "Creature — Dragon",
            "When this creature enters, you may pay {X}{R}. If you do, this creature deals X damage to any target.", 4, 4)


def game(lands):
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    for _ in range(lands):
        g.enter_battlefield(a, ISLAND)
    return g, a, b


class PayXGate(unittest.TestCase):
    def test_parses_clean(self):
        for c in (DRAWER, LIFER, TOKENS, BURN):
            self.assertEqual(c.unsupported, [], c.name)

    def test_vigil_gains_x(self):
        g, a, b = game(3)
        g.enter_battlefield(a, LIFER)
        bear = g.enter_battlefield(a, BEAR)
        g.settle()
        life = a.life
        g.destroy(bear) if hasattr(g, "destroy") else None
        g.settle()
        self.assertEqual(a.life - life, 3)
        self.assertTrue(all(land.tapped for land in a.battlefield if land.card.is_land))

    def test_draw_x(self):
        g, a, b = game(2)
        before = len(a.hand)
        g.enter_battlefield(a, DRAWER)
        g.settle()
        self.assertEqual(len(a.hand) - before, 2)

    def test_tokens_x(self):
        g, a, b = game(4)
        g.enter_battlefield(a, TOKENS)
        g.settle()
        self.assertEqual(sum(1 for x in a.battlefield if x.card.is_token), 4)

    def test_damage_x(self):
        g, a, b = game(3)
        g.enter_battlefield(a, MOUNTAIN)
        g.enter_battlefield(a, BURN)
        g.settle()
        self.assertEqual(20 - b.life, 3)

    def test_nothing_affordable(self):
        g, a, b = game(0)
        g.enter_battlefield(a, TOKENS)
        g.settle()
        self.assertEqual(sum(1 for x in a.battlefield if x.card.is_token), 0)


if __name__ == "__main__":
    unittest.main()
