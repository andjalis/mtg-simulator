"""Effects scaled by "equal to <quantity>": damage, life, draw and mill."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

HAND_BOLT = card("Test Hand Bolt", "{R}", "Instant", "Test Hand Bolt deals damage to any target equal to the number of "
                 "cards in your hand.")
HEALER = card("Test Healer", "{W}", "Instant", "You gain life equal to the number of creatures you control.")
READER = card("Test Reader", "{2}{U}", "Sorcery", "Draw cards equal to the greatest power among creatures you control.")
DRAINER = card("Test Drainer", "{1}{B}", "Instant", "Target opponent loses life equal to your life total.")
MILLER = card("Test Miller", "{1}{U}", "Sorcery", "Target player mills cards equal to the number of cards in your hand.")
STRANGE = card("Test Strange", "{1}{U}", "Sorcery", "Draw cards equal to the number of differently named creature "
               "tokens you control.")


class Quantity(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.hand = []

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c):
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [self.b] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_parses(self):
        for c in (HAND_BOLT, HEALER, READER, DRAINER, MILLER):
            with self.subTest(c.name):
                self.assertEqual(c.unsupported, [])

    def test_unknown_quantity_is_not_guessed(self):
        self.assertEqual(len(STRANGE.unsupported), 1)

    def test_damage_equals_hand_size(self):
        self.a.hand = [ISLAND] * 3
        life = self.b.life
        self.cast(HAND_BOLT)
        self.assertEqual(self.b.life, life - 3)

    def test_life_equals_creature_count(self):
        self.perm(BEAR, self.a)
        self.perm(BEAR, self.a)
        life = self.a.life
        self.cast(HEALER)
        self.assertEqual(self.a.life, life + 2)

    def test_draw_equals_greatest_power(self):
        self.perm(BEAR, self.a)
        self.cast(READER)
        self.assertEqual(len(self.a.hand), 2)

    def test_opponent_loses_your_life_total(self):
        self.a.life = 7
        self.b.life = 20
        self.cast(DRAINER)
        self.assertEqual(self.b.life, 13)

    def test_mill_equals_hand_size(self):
        self.a.hand = [ISLAND] * 4
        before = len(self.b.library)
        self.cast(MILLER)
        self.assertEqual(before - len(self.b.library), 4)


if __name__ == "__main__":
    unittest.main()
