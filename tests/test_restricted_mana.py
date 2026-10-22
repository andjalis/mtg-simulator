"""Restricted mana that makes more than one mana (Tablet of Discovery, Eldrazi Temple) and restricted storage mana
(Crucible of the Spirit Dragon)."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

TABLET = card("Test Tablet", "{2}{R}", "Artifact", "{T}: Add {R}.\n{T}: Add {R}{R}. Spend this mana only to cast instant "
                                                   "and sorcery spells.")
TEMPLE = card("Test Temple", "", "Land", "{T}: Add {C}.\n{T}: Add {C}{C}. Spend this mana only to cast colorless Eldrazi "
                                         "spells or activate abilities of colorless Eldrazi.")
CRUCIBLE = card("Test Crucible", "", "Land", "{T}: Add {C}.\n{1}, {T}: Put a storage counter on ~.\n{T}, Remove X storage "
                                             "counters from ~: Add X mana in any combination of colors. Spend this mana "
                                             "only to cast Dragon spells or activate abilities of Dragons.")
BLAZE = card("Test Blaze", "{1}{R}", "Sorcery", "~ deals 2 damage to any target.")
GOBLIN = card("Test Goblin", "{1}{R}", "Creature — Goblin", "", 2, 2)
DRAGON = card("Test Dragon", "{2}{R}", "Creature — Dragon", "Flying", 3, 3)
DRONE = card("Test Drone", "{2}", "Creature — Eldrazi Drone", "", 2, 2)


class RestrictedMana(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_templates(self):
        for c in (TABLET, TEMPLE, CRUCIBLE):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual((TABLET.restricted_amount, TABLET.mana_amount), (2, 1))

    def test_two_restricted_mana_only_for_the_allowed_spells(self):
        self.put(self.a, TABLET)
        self.assertTrue(self.game.spell_payable(self.a, BLAZE))
        self.assertFalse(self.game.spell_payable(self.a, GOBLIN))

    def test_tribal_land_pays_two_for_its_type(self):
        self.put(self.a, TEMPLE)
        self.assertTrue(self.game.spell_payable(self.a, DRONE))
        self.assertFalse(self.game.spell_payable(self.a, card("Test Golem", "{2}", "Artifact Creature — Golem", "", 2, 2)))

    def test_restricted_storage_mana(self):
        crucible = self.put(self.a, CRUCIBLE)
        crucible.counters["storage"] = 3
        self.assertTrue(self.game.spell_payable(self.a, DRAGON))
        self.assertFalse(self.game.spell_payable(self.a, GOBLIN))   # only the land's own {C} for anything else
        self.a.hand[:] = [DRAGON]
        self.assertTrue(self.game.cast(self.a, DRAGON))
        self.assertEqual(crucible.counters["storage"], 0)


if __name__ == "__main__":
    unittest.main()
