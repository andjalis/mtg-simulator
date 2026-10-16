"""Auras and self-attaching Equipment (mtgsim.auras). Card text is written out so no card DB is needed."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, can_block

from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card

BOOST = card("Test Boost", "{1}{R}", "Enchantment — Aura", (
    "Enchant creature you control\nEnchanted creature gets +2/+1 and has flying."))
CHAINS = card("Test Chains", "{1}{R}", "Enchantment — Aura", (
    "Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its "
    "controller's untap step."))
PACIFY = card("Test Pacify", "{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature can't attack or block.")
WEAKEN = card("Test Weaken", "{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets -3/-3.")
BLADE = card("Test Blade", "{1}", "Artifact — Equipment", (
    "When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +1/+1.\nEquip {2}"))


class AuraTests(unittest.TestCase):
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
        for c in (BOOST, CHAINS, PACIFY, WEAKEN, BLADE):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertTrue(CHAINS.aura_hostile and not BOOST.aura_hostile)

    def test_friendly_aura_buffs_own_best_creature_and_falls_off_with_it(self):
        mine = self.perm(DRAGON3, self.a)
        self.perm(BEAR, self.a)
        self.a.hand = [BOOST]
        self.game.cast(self.a, BOOST)
        self.assertEqual((mine.power, mine.toughness), (5, 4))
        self.assertTrue(mine.has("flying"))
        self.game.destroy(mine)
        self.assertEqual(sorted(c.name for c in self.a.graveyard), ["Big Dragon", "Test Boost"])

    def test_aura_needs_a_host(self):
        self.a.hand = [BOOST, PACIFY]
        self.assertFalse(self.game.can_cast_now(self.a, BOOST))
        self.assertFalse(self.game.can_cast_now(self.a, PACIFY))
        self.perm(BEAR, self.b)
        self.assertTrue(self.game.can_cast_now(self.a, PACIFY))

    def test_hostile_aura_goes_on_the_opponents_creature(self):
        self.perm(BEAR, self.a)
        theirs = self.perm(DRAGON3, self.b)
        self.a.hand = [CHAINS]
        self.game.cast(self.a, CHAINS)
        self.assertTrue(theirs.tapped)
        theirs.tapped = False
        theirs.tapped = True
        self.game.take_turn(self.b)
        self.assertTrue(theirs.tapped)          # didn't untap

    def test_cant_attack_or_block(self):
        theirs = self.perm(DRAGON3, self.b)
        mine = self.perm(BEAR, self.a)
        self.a.hand = [PACIFY]
        self.game.cast(self.a, PACIFY)
        self.assertFalse(theirs.can_attack())
        self.assertFalse(can_block(theirs, mine))

    def test_negative_bonus_kills(self):
        theirs = self.perm(BEAR, self.b)
        self.a.hand = [WEAKEN]
        self.game.cast(self.a, WEAKEN)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_equipment_attaches_on_entering(self):
        mine = self.perm(BEAR, self.a)
        self.a.hand = [BLADE]
        self.game.cast(self.a, BLADE)
        self.assertEqual((mine.power, mine.toughness), (3, 3))


if __name__ == "__main__":
    unittest.main()
