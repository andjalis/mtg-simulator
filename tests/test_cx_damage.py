"""Divided damage, split on resolution."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, DRAGON3, ISLAND, card

BOLT = card("Test Forked Bolt", "{R}", "Sorcery", "Test Forked Bolt deals 2 damage divided as you choose among one "
            "or two targets.")
VOLLEY = card("Test Volley", "{2}{R}", "Sorcery", "Test Volley deals 3 damage divided as you choose among one, two, or "
              "three target creatures.")


class DividedDamage(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c):
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_parses(self):
        self.assertEqual((BOLT.unsupported, VOLLEY.unsupported), ([], []))

    def test_kills_a_bear_then_face(self):
        bear = self.perm(BEAR, self.b)
        life = self.b.life
        self.cast(BOLT)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.b.life, life)
        self.cast(BOLT)
        self.assertEqual(self.b.life, life - 2)

    def test_creature_only_scope_never_hits_face(self):
        big = self.perm(DRAGON3, self.b)
        life = self.b.life
        self.cast(VOLLEY)
        self.assertEqual(self.b.life, life)
        self.assertEqual(big.damage, 3)


STRIKE = card("Test Strike", "{1}{R}", "Instant", "Test Strike deals 2 damage to target creature and 2 damage to target "
              "player or planeswalker.\nDraw a card.")


class TwoTargets(DividedDamage):
    def test_two_independent_targets(self):
        self.assertEqual(STRIKE.unsupported, [])
        bear = self.perm(BEAR, self.b)
        life = self.b.life
        self.game.stack.append(StackItem(self.a, list(STRIKE.spell_effects), [bear, self.b, None], card=STRIKE,
                                         name=STRIKE.name))
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.b.life, life - 2)


if __name__ == "__main__":
    unittest.main()
