"""Swampwalk checks the defending player's Swamp subtype when blocks are declared."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, can_block
from tests.test_templates import BEAR, ISLAND, card


WALKER = card("Test Swampwalker", "{2}", "Creature — Snake", "Swampwalk", 2, 2)
SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")


class Swampwalk(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.attacker = self.game.enter_battlefield(self.a, WALKER)
        self.attacker.sick = False
        self.blocker = self.game.enter_battlefield(self.b, BEAR)

    def test_templates_and_keyword_lists(self):
        self.assertEqual(WALKER.unsupported, [])
        c = card("Test Flying Walker", types="Creature", text="Flying, swampwalk", power=2, toughness=2)
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.keywords, frozenset({"flying", "swampwalk"}))

    def test_no_swamp_and_own_swamp_allow_blocking(self):
        self.assertTrue(can_block(self.blocker, self.attacker))
        self.game.enter_battlefield(self.a, SWAMP)
        self.game.enter_battlefield(self.b, ISLAND)
        self.assertTrue(can_block(self.blocker, self.attacker))

    def test_swamp_dual_and_snow_swamp_prevent_blocking(self):
        for c in (SWAMP, card("Test Dual", types="Land — Island Swamp"),
                  card("Snow-Covered Swamp", types="Basic Snow Land — Swamp")):
            with self.subTest(c=c):
                land = self.game.enter_battlefield(self.b, c)
                land.tapped = True
                self.assertFalse(can_block(self.blocker, self.attacker))
                self.game.leave_battlefield(land, "hand")

    def test_swamp_name_or_black_mana_alone_is_not_enough(self):
        self.game.enter_battlefield(self.b, card("Swamp in Name Only", types="Land", text="{T}: Add {B}."))
        self.assertTrue(can_block(self.blocker, self.attacker))

    def test_losing_defenders_swamp_restores_blockability(self):
        land = self.game.enter_battlefield(self.b, SWAMP)
        self.assertFalse(can_block(self.blocker, self.attacker))
        self.game.destroy(land)
        self.assertTrue(can_block(self.blocker, self.attacker))

    def test_ai_combat_connects_past_a_larger_creature(self):
        self.game.enter_battlefield(self.b, SWAMP)
        self.blocker.pump_p = self.blocker.pump_t = 3
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 18)
        self.assertIn(self.attacker, self.a.battlefield)

    def test_other_landwalk_remains_visible(self):
        c = card("Test Forestwalker", types="Creature", text="Forestwalk", power=2, toughness=2)
        self.assertTrue(c.unsupported)


if __name__ == "__main__":
    unittest.main()
