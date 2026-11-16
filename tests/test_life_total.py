"""#629: double / set / exchange a life total and "target player loses the game"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card


def spell(text):
    return card("Zork Spell", "{1}", "Sorcery", text)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


def cast(text, targets=None, setup=None):
    g, a, b = game()
    s = spell(text)
    if setup:
        setup(a, b)
    a.hand.append(s)
    g.enter_battlefield(a, ISLAND)
    assert g.cast(a, s, targets) if targets is not None else g.cast(a, s)
    g.settle()
    return g, a, b


class LifeTotals(unittest.TestCase):
    def test_parse(self):
        for text in ("Double target player's life total.", "Your life total becomes 1.",
                     "Exchange life totals with target player.", "Target player loses the game."):
            self.assertEqual(spell(text).unsupported, [], text)

    def test_refusals(self):
        for text in ("Each player's life total becomes 3.", "Double target creature's power.",
                     "Target player's life total becomes half your life total."):
            self.assertTrue(spell(text).unsupported, text)

    def test_double_your_life(self):
        g, a, b = cast("Double your life total.", [None], lambda a, b: setattr(a, "life", 7))
        self.assertEqual(a.life, 14)

    def test_set_your_life(self):
        g, a, b = cast("Your life total becomes 1.", [None])
        self.assertEqual(a.life, 1)

    def test_exchange_with_opponent(self):
        def setup(a, b):
            a.life, b.life = 3, 17
        g, a, b = cast("Exchange life totals with target player.", [None], setup)
        self.assertEqual((a.life, b.life), (17, 3))

    def test_target_player_loses(self):
        g, a, b = cast("Target player loses the game.", [None])
        self.assertTrue(b.lost)
        self.assertFalse(a.lost)

    def test_ai_aims_exchange_and_loss(self):
        g, a, b = game()
        a.life, b.life = 4, 20
        s = spell("Exchange life totals with target player.")
        g.enter_battlefield(a, ISLAND)
        a.hand = [s]
        g.active_idx = 0
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual((a.life, b.life), (20, 4))
        g2, a2, b2 = game()
        a2.life, b2.life = 20, 4
        s2 = spell("Exchange life totals with target player.")
        g2.enter_battlefield(a2, ISLAND)
        a2.hand = [s2]
        g2.active_idx = 0
        a2.ai.main_phase(g2, a2)
        g2.settle()
        self.assertEqual((a2.life, b2.life), (20, 4))     # a swap that costs us life is never cast


if __name__ == "__main__":
    unittest.main()
