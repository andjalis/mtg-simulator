"""Protection from a color: blocking, targeting, damage, Auras and Equipment, and color-of-your-choice grants."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem, can_block
from tests.test_templates import ISLAND, MOUNTAIN, PLAINS, card

RED_BEAR = card("Test Red Bear", "{1}{R}", "Creature — Bear", "", 2, 2)
WHITE_BEAR = card("Test White Bear", "{1}{W}", "Creature — Bear", "", 2, 2)
PRO_RED = card("Test Pro-Red", "{1}{W}", "Creature — Knight", "First strike, protection from red", 2, 2)
PRO_TWO = card("Test Paladin", "{1}{W}{W}", "Creature — Knight",
               "Flying, protection from black and from red (This creature can't be blocked, targeted, dealt damage, "
               "or enchanted by anything black or red.)", 2, 2)
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
SHOCK_W = card("Test Smite", "{W}", "Instant", "Test Smite deals 3 damage to any target.")
SWORD = card("Test Sword", "{3}", "Artifact — Equipment",
             "Equipped creature gets +2/+2 and has protection from red and from blue.\nEquip {2}")
RED_AURA = card("Test Red Aura", "{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1.")
WARD_AURA = card("Test Ward Aura", "{W}", "Enchantment — Aura",
                 "Enchant creature\nEnchanted creature has protection from red.")
GODS_WILLING = card("Test Willing", "{W}", "Instant",
                    "Target creature you control gains protection from the color of your choice until end of turn.")
FIXED_GRANT = card("Test Blue Ward", "{W}", "Instant", "Target creature gains protection from blue until end of turn.")


class Protection(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        return perm

    def lands(self, who, land, n):
        for _ in range(n):
            self.put(who, land)

    def test_templates(self):
        for c in (PRO_RED, PRO_TWO, SWORD, RED_AURA, WARD_AURA, GODS_WILLING, FIXED_GRANT):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(PRO_TWO.keywords, {"flying", "protection from black", "protection from red"})
        self.assertEqual(SWORD.equip_keywords, {"protection from red", "protection from blue"})

    def test_cant_be_blocked_by_that_color(self):
        knight = self.put(self.a, PRO_RED)
        self.assertFalse(can_block(self.put(self.b, RED_BEAR), knight))
        self.assertTrue(can_block(self.put(self.b, WHITE_BEAR), knight))

    def test_cant_be_targeted_by_that_color(self):
        knight = self.put(self.b, PRO_RED)
        self.lands(self.a, MOUNTAIN, 1)
        self.lands(self.a, PLAINS, 1)
        with self.game.targeting(BOLT):
            self.assertNotIn(knight, self.game.legal_targets(self.a, BOLT.spell_effects[0]))
        with self.game.targeting(SHOCK_W):
            self.assertIn(knight, self.game.legal_targets(self.a, SHOCK_W.spell_effects[0]))
        self.a.hand.append(BOLT)
        self.assertFalse(self.game.cast(self.a, BOLT, [knight]))
        self.a.hand.append(SHOCK_W)
        self.assertTrue(self.game.cast(self.a, SHOCK_W, [knight]))
        self.game.settle()
        self.assertNotIn(knight, self.b.battlefield)

    def test_damage_from_that_color_is_prevented(self):
        knight = self.put(self.b, PRO_RED)
        bear = self.put(self.a, RED_BEAR)
        self.game.deal_damage(knight, 5, by=self.a, source=bear, combat=True)
        self.assertEqual(knight.damage, 0)
        self.game.deal_damage(knight, 1, by=self.a, source=WHITE_BEAR)
        self.assertEqual(knight.damage, 1)

    def test_spell_fizzles_when_target_gains_protection(self):
        bear = self.put(self.b, WHITE_BEAR)
        item = StackItem(self.a, list(BOLT.spell_effects), [bear], card=BOLT)
        self.game.stack.append(item)
        bear.temp_kw.add("protection from red")
        self.game.settle()
        self.assertIn(bear, self.b.battlefield)
        self.assertEqual(bear.damage, 0)

    def test_equipment_grants_protection_and_follows_the_rules(self):
        bear = self.put(self.a, WHITE_BEAR)
        sword = self.put(self.a, SWORD)
        sword.attached_to = bear
        self.assertTrue(bear.has("protection from red") and bear.has("protection from blue"))
        self.assertFalse(can_block(self.put(self.b, RED_BEAR), bear))
        self.assertEqual(bear.power, 4)

    def test_aura_of_that_color_falls_off(self):
        bear = self.put(self.a, WHITE_BEAR)
        aura = self.put(self.a, RED_AURA)
        aura.aura_host = bear
        bear.auras.append(aura)
        self.assertEqual(bear.power, 3)
        bear.temp_kw.add("protection from red")
        self.game.state_based_actions()
        self.assertNotIn(aura, self.a.battlefield)
        self.assertIn(RED_AURA, self.a.graveyard)
        self.assertEqual(bear.power, 2)

    def test_aura_cant_enchant_protected_creature(self):
        from mtgsim import auras
        knight = self.put(self.a, PRO_RED)
        bear = self.put(self.a, WHITE_BEAR)
        hosts = auras.hosts(self.game, self.a, RED_AURA)
        self.assertNotIn(knight, hosts)
        self.assertIn(bear, hosts)

    def test_aura_granting_protection(self):
        bear = self.put(self.a, WHITE_BEAR)
        aura = self.put(self.a, WARD_AURA)
        aura.aura_host = bear
        bear.auras.append(aura)
        self.assertTrue(bear.has("protection from red"))
        self.game.state_based_actions()
        self.assertIn(aura, self.a.battlefield)   # a white Aura stays on

    def test_color_of_your_choice_answers_the_removal_on_the_stack(self):
        bear = self.put(self.a, WHITE_BEAR)
        self.lands(self.a, PLAINS, 1)
        self.lands(self.b, MOUNTAIN, 1)
        self.b.hand.append(BOLT)
        self.a.hand.append(GODS_WILLING)
        self.game.active_idx = 1
        self.assertTrue(self.game.cast(self.b, BOLT, [bear]))
        self.game.settle()
        self.assertIn(bear, self.a.battlefield)
        self.assertTrue(bear.has("protection from red"))
        self.assertIn(GODS_WILLING, self.a.graveyard)

    def test_color_of_your_choice_without_a_threat_uses_opponents_creatures(self):
        bear = self.put(self.a, WHITE_BEAR)
        self.put(self.b, RED_BEAR)
        self.lands(self.a, PLAINS, 1)
        self.a.hand.append(GODS_WILLING)
        self.assertTrue(self.game.cast(self.a, GODS_WILLING, [bear]))
        self.game.settle()
        self.assertTrue(bear.has("protection from red"))

    def test_fixed_color_grant(self):
        bear = self.put(self.a, WHITE_BEAR)
        self.lands(self.a, PLAINS, 1)
        self.a.hand.append(FIXED_GRANT)
        self.assertTrue(self.game.cast(self.a, FIXED_GRANT, [bear]))
        self.game.settle()
        self.assertTrue(bear.has("protection from blue"))


if __name__ == "__main__":
    unittest.main()
