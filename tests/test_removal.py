"""Restricted removal and fights (mtgsim.removal). Card text is written out so no card DB is needed."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card

FIGHT = card("Test Fight", "{1}{R}", "Sorcery", "Target creature you control fights target creature an opponent controls.")
BITE = card("Test Bite", "{R}", "Sorcery", "Target creature you control deals damage equal to its power to target creature an opponent controls.")
SMASH = card("Test Smash", "{1}{R}", "Instant", "Destroy target creature with power 4 or greater.")
NAIL = card("Test Nail", "{1}{W}", "Instant", "Exile target enchantment.")
SKY = card("Test Sky", "{1}{G}", "Instant", "Destroy target creature with flying.")
OATH = card("Test Oath", "{1}", "Enchantment", "")
ARTI = card("Test Rock", "{1}", "Artifact", "")
BIG = card("Big Guy", "{4}", "Creature — Giant", "", 5, 5)


class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        for _ in range(4):
            self.perm(MOUNTAIN, self.a)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (FIGHT, BITE, SMASH, NAIL, SKY):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_fight_kills_a_smaller_creature_and_marks_damage_back(self):
        mine, theirs = self.perm(DRAGON3, self.a), self.perm(BEAR, self.b)
        self.a.hand = [FIGHT]
        self.game.cast(self.a, FIGHT, [mine, theirs])
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertEqual(mine.damage, 2)

    def test_bite_is_one_way(self):
        mine, theirs = self.perm(DRAGON3, self.a), self.perm(BEAR, self.b)
        self.a.hand = [BITE]
        self.game.cast(self.a, BITE, [mine, theirs])
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertEqual(mine.damage, 0)

    def test_power_restriction(self):
        small, big = self.perm(BEAR, self.b), self.perm(BIG, self.b)
        self.assertFalse(self.game.legal_target(self.a, SMASH.spell_effects[0], small))
        self.assertTrue(self.game.legal_target(self.a, SMASH.spell_effects[0], big))

    def test_enchantment_and_flying_restrictions(self):
        oath, rock = self.perm(OATH, self.b), self.perm(ARTI, self.b)
        flyer, bear = self.perm(DRAGON3, self.b), self.perm(BEAR, self.b)
        self.assertEqual(self.game.legal_targets(self.a, NAIL.spell_effects[0]), [oath])
        self.assertEqual(self.game.legal_targets(self.a, SKY.spell_effects[0]), [flyer])
        self.assertNotIn(rock, self.game.legal_targets(self.a, NAIL.spell_effects[0]))
        self.assertNotIn(bear, self.game.legal_targets(self.a, SKY.spell_effects[0]))


if __name__ == "__main__":
    unittest.main()
