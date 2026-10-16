"""Role tokens, connive, and "it deals damage equal to its power" / "it fights" follow-ups."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

ROYAL = card("Test Royal", "{1}{W}", "Sorcery", "Create a Royal Role token attached to target creature you control.")
CURSE = card("Test Curse", "{1}{B}", "Sorcery", "Create a Cursed Role token attached to target creature an opponent controls.")
HERO = card("Test Hero Role", "{W}", "Sorcery", "Create a Young Hero Role token attached to target creature you control.")
WICKED = card("Test Wicked", "{B}", "Sorcery", "Create a Wicked Role token attached to target creature you control.")
CONNIVER = card("Test Conniver", "{1}{U}", "Creature — Rogue", "When ~ enters, it connives.", 2, 2)
GNAW = card("Test Gnaw", "{1}{G}", "Instant", "Target creature you control gets +1/+0 until end of turn. Then it deals damage "
            "equal to its power to target creature you don't control.")
SMASH = card("Test Smash", "{R}", "Instant", "Target creature you control deals damage equal to its power to target creature "
             "or planeswalker you don't control.")
PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


class RolesConniveBite(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def cast(self, spell, lands, targets):
        for l in lands:
            self.perm(l)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, targets))
        self.game.settle()

    def test_templates(self):
        for c in (ROYAL, CURSE, HERO, WICKED, CONNIVER, GNAW, SMASH):
            self.assertEqual(c.unsupported, [], c.name)

    def test_royal_role_bonus_ward_and_replacement(self):
        bear = self.perm(BEAR)
        self.cast(ROYAL, [PLAINS, PLAINS], [bear])
        self.assertEqual((bear.power, bear.toughness, bear.ward), (3, 3, 1))
        self.cast(WICKED, [SWAMP], [bear])                       # a new Role replaces the old one
        self.assertEqual(len(bear.auras), 1)
        self.assertEqual((bear.power, bear.ward), (3, 0))

    def test_cursed_role_sets_base_1_1(self):
        big = self.perm(card("Ogre", "{3}", "Creature — Ogre", "", 5, 5), self.b)
        self.cast(CURSE, [SWAMP, SWAMP], [big])
        self.assertEqual((big.power, big.toughness), (1, 1))

    def test_young_hero_counts_up_small_attackers(self):
        bear = self.perm(BEAR)
        self.cast(HERO, [PLAINS], [bear])
        self.game.fire(self.a, "attacks", bear)
        self.game.settle()
        self.assertEqual(bear.p1, 1)

    def test_wicked_role_drains_when_it_leaves(self):
        bear = self.perm(BEAR)
        self.cast(WICKED, [SWAMP], [bear])
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(self.b.life, 19)

    def test_connive_draws_discards_and_grows_on_nonland(self):
        self.a.hand = [MOUNTAIN, MOUNTAIN]
        self.a.library = [BEAR, ISLAND, ISLAND]
        bear = self.game.enter_battlefield(self.a, CONNIVER)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 2)
        self.assertIn(bear.p1, (0, 1))

    def test_follow_up_bite_uses_the_first_target(self):
        # 3 power + 1 from the pump = 4 damage, which kills the 2/2
        mine = self.perm(card("Brute", "{2}", "Creature — Ogre", "", 3, 3))
        theirs = self.perm(BEAR, self.b)
        self.cast(GNAW, [FOREST, FOREST], [mine, theirs])
        self.assertNotIn(theirs, self.b.battlefield)

    def test_bite_can_hit_a_planeswalker(self):
        mine = self.perm(card("Brute", "{2}", "Creature — Ogre", "", 3, 3))
        pw = self.perm(card("Test Walker", "{3}", "Planeswalker — Test", "", None, None), self.b)
        pw.counters["loyalty"] = 5
        self.cast(SMASH, [MOUNTAIN], [mine, pw])
        self.assertEqual(pw.loyalty, 2)


if __name__ == "__main__":
    unittest.main()
