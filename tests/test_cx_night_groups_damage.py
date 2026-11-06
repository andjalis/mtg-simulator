"""Damage to a group written with "and each", and "it deals N damage to each ..."."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

STORM = card("Test Storm", "{3}{R}", "Sorcery", "Test Storm deals 3 damage to each creature and each planeswalker.")
FIRE = card("Test Fire", "{2}{R}", "Sorcery", "Test Fire deals 1 damage to each opponent and each creature they control.")
HELLION = card("Test Hellion", "{3}{R}", "Creature — Hellion", "When Test Hellion enters, it deals 3 damage to each "
               "other creature.", 4, 4)


class GroupDamage(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        self.mine, self.theirs = (self._perm(p) for p in (self.a, self.b))

    def _perm(self, owner):
        x = Permanent(BEAR, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c):
        targets = [self.b if e.target == "player" else None for e in c.spell_effects]
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), targets, card=c, name=c.name))
        self.game.resolve_top()

    def test_parses(self):
        for c in (STORM, FIRE, HELLION):
            with self.subTest(c.name):
                self.assertEqual(c.unsupported, [])

    def test_storm_hits_everyone(self):
        self.cast(STORM)
        self.assertNotIn(self.mine, self.a.battlefield)
        self.assertNotIn(self.theirs, self.b.battlefield)

    def test_fire_hits_only_the_opponent_side(self):
        life = self.b.life
        self.cast(FIRE)
        self.assertEqual(self.b.life, life - 1)
        self.assertEqual(self.theirs.damage, 1)
        self.assertEqual(self.mine.damage, 0)


if __name__ == "__main__":
    unittest.main()
