"""Event amounts ("that much") and life / damage replacement statics."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

RECKONER = card("Test Reckoner", "{2}{R/W}{R/W}", "Creature — Minotaur", "Whenever ~ is dealt damage, it deals that much "
                "damage to any target.", 3, 3)
CALIPH = card("Test Caliph", "{3}{R}", "Creature — Efreet", "Whenever ~ deals damage, you lose that much life.", 4, 4)
WARRIOR = card("Test Warrior", "{1}{W}", "Creature — Human", "Whenever ~ is dealt combat damage, you gain that much "
               "life.", 2, 4)
CONQUEROR = card("Test Conqueror", "{3}{B}", "Creature — Vampire", "Whenever an opponent loses life, you gain that much "
                 "life.", 3, 3)
BOND = card("Test Bond", "{3}{B}{B}", "Enchantment", "Whenever you gain life, target opponent loses that much life.")
REFLECTION = card("Test Reflection", "{2}{W}", "Enchantment", "If you would gain life, you gain twice that much life "
                  "instead.")
HERON = card("Test Heron", "{2}{W}", "Creature — Bird", "If you would gain life, you gain that much life plus 1 instead.",
             2, 2)
BLOODLETTER = card("Test Bloodletter", "{2}{B}", "Creature — Demon", "If an opponent would lose life during your turn, "
                   "they lose twice that much life instead.", 2, 2)
HELLION = card("Test Hellion", "{2}{R}", "Creature — Hellion", "If another red source you control would deal damage to a "
               "permanent or player, it deals that much damage plus 1 to that permanent or player instead.", 3, 3)
UNICORN = card("Test Unicorn", "{1}{W}", "Creature — Unicorn", "If a spell would deal damage to a permanent or player, it "
               "deals that much damage minus 1 to that permanent or player instead.", 2, 2)
BARRIER = card("Test Barrier", "{1}{W}", "Enchantment", "If a source would deal damage to a creature you control, it "
               "deals that much damage minus 1 to that creature instead.")
TALENT = card("Test Talent", "{2}{R}", "Enchantment", "If a source you control would deal noncombat damage to an "
              "opponent or a permanent an opponent controls, it deals that much damage plus 2 instead.")
RED_BEAR = card("Test Red Bear", "{1}{R}", "Creature — Bear", "", 2, 2)
SWINE = card("Test Swine", "{4}{R}", "Creature — Boar", "Whenever ~ is dealt damage, ~ deals that much damage to each "
             "player.", 4, 4)


class ThatMuch(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, c, who=None):
        perm = self.game.enter_battlefield(who or self.a, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_templates(self):
        for c in (RECKONER, CALIPH, WARRIOR, CONQUEROR, BOND, REFLECTION, HERON, BLOODLETTER, HELLION, UNICORN, BARRIER,
                  TALENT, SWINE):
            self.assertEqual(c.unsupported, [], c.name)

    def test_reckoner_deals_back_what_it_took(self):
        r = self.put(RECKONER)
        self.game.deal_damage(r, 2, by=self.b, source=None)
        self.game.settle()
        self.assertEqual(self.b.life, 18)

    def test_caliph_costs_life_equal_to_damage(self):
        c = self.put(CALIPH)
        self.game.deal_damage(self.b, 3, by=self.a, source=c)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (17, 17))

    def test_warrior_gains_on_combat_damage_only(self):
        w = self.put(WARRIOR)
        self.game.deal_damage(w, 2, by=self.b, source=None)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.game.deal_damage(w, 1, by=self.b, source=None, combat=True)
        self.game.settle()
        self.assertEqual(self.a.life, 21)

    def test_conqueror_gains_when_opponent_loses_life(self):
        self.put(CONQUEROR)
        self.game.change_life(self.b, -4, "test")
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (24, 16))

    def test_bond_drains_for_life_gained(self):
        self.put(BOND)
        self.game.change_life(self.a, 3, "test")
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (23, 17))

    def test_gain_modifiers(self):
        self.put(REFLECTION)
        self.game.change_life(self.a, 3, "test")
        self.assertEqual(self.a.life, 26)
        self.put(HERON)
        self.game.change_life(self.a, 3, "test")      # (3 + 1) * 2
        self.assertEqual(self.a.life, 34)

    def test_bloodletter_doubles_only_on_its_controllers_turn(self):
        self.put(BLOODLETTER)
        self.game.change_life(self.b, -3, "test")
        self.assertEqual(self.b.life, 14)
        self.game.active_idx = 1
        self.game.change_life(self.b, -3, "test")
        self.assertEqual(self.b.life, 11)

    def test_damage_modifiers(self):
        self.put(TALENT)
        self.game.deal_damage(self.b, 3, by=self.a, source=None)
        self.assertEqual(self.b.life, 15)
        self.game.deal_damage(self.a, 3, by=self.b, source=None)       # to its own controller: unchanged
        self.assertEqual(self.a.life, 17)

    def test_another_red_source_adds_one(self):
        h = self.put(HELLION)
        bear = self.put(RED_BEAR)
        self.game.deal_damage(self.b, 2, by=self.a, source=bear)
        self.assertEqual(self.b.life, 17)
        self.game.deal_damage(self.b, 2, by=self.a, source=h)           # "another" source only
        self.assertEqual(self.b.life, 15)

    def test_each_player_takes_that_much(self):
        s = self.put(SWINE)
        self.game.deal_damage(s, 2, by=self.b, source=None)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (18, 18))

    def test_unicorn_and_barrier_reduce_damage(self):
        self.put(UNICORN)
        bear = self.put(card("Test Bear2", "{1}{G}", "Creature — Bear", "", 2, 2))
        self.game.deal_damage(self.b, 3, by=self.a, source=bear.card)    # a spell-like source
        self.assertEqual(self.b.life, 18)
        self.put(BARRIER)
        self.game.deal_damage(bear, 1, by=self.b, source=None)
        self.assertEqual(bear.damage, 0)


if __name__ == "__main__":
    unittest.main()
