"""Damage prevention and redirection rules."""
import random
import unittest

from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

FOG = card("Test Fog", "{G}", "Instant", "Prevent all damage that would be dealt to creatures this turn.")
RESTRAIN = card("Test Restrain", "{2}{W}", "Instant",
                "Prevent all combat damage that would be dealt by target attacking creature this turn.")
COP = card("Test Circle", "{1}{W}", "Enchantment",
           "{1}: The next time a red source of your choice would deal damage to you this turn, prevent that damage.")
LANCERS = card("Test Lancers", "{3}{W}{W}", "Creature — Kor Soldier",
               "{0}: The next 1 damage that would be dealt to ~ this turn is dealt to target creature you control instead.",
               3, 3)
SERAPH = card("Test Seraph", "{2}{W}{W}", "Creature — Angel",
              "Flying\nIf a source an opponent controls would deal damage to you, prevent 1 of that damage.", 3, 4)
ARCHANGEL = card("Test Archangel", "{4}{G}{W}{W}{U}", "Creature — Angel",
                 "Flying\nAll damage that would be dealt to you is dealt to ~ instead.", 5, 8)
SANCTUM = card("Test Sanctum", "{1}{W}{W}", "Enchantment", "Prevent all damage that would be dealt to creatures you control.")
TORMENT = card("Test Torment", "{2}{B}", "Enchantment", "Damage can't be prevented.")
RED = card("Test Goblin", "{R}", "Creature — Goblin", "", 2, 1)


class Shields(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def run_ability(self, perm, target=None):
        eff = perm.card.activated[0].effects[0]
        self.game.resolve(self.a, eff, target, item=StackItem(self.a, [eff], [target], source=perm))

    def test_parse(self):
        for c in (FOG, RESTRAIN, COP, LANCERS, SERAPH, ARCHANGEL, SANCTUM, TORMENT):
            self.assertEqual(c.unsupported, [], c.name)

    def test_fog_creatures(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.resolve(self.a, FOG.spell_effects[0], None)
        self.game.deal_damage(bear, 3, self.b)
        self.game.deal_damage(self.a, 3, self.b)
        self.assertEqual(bear.damage, 0)
        self.assertEqual(self.a.life, 17)
        self.game.turn += 1
        self.game.deal_damage(bear, 1, self.b)
        self.assertEqual(bear.damage, 1)

    def test_by_target_combat_only(self):
        goblin = self.game.enter_battlefield(self.b, RED)
        self.game.resolve(self.a, RESTRAIN.spell_effects[0], goblin)
        self.game.deal_damage(self.a, 2, self.b, source=goblin, combat=True)
        self.assertEqual(self.a.life, 20)
        self.game.deal_damage(self.a, 2, self.b, source=goblin)
        self.assertEqual(self.a.life, 18)

    def test_circle_once_and_colour(self):
        circle = self.game.enter_battlefield(self.a, COP)
        goblin = self.game.enter_battlefield(self.b, RED)
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.run_ability(circle)
        self.game.deal_damage(self.a, 2, self.b, source=bear)
        self.assertEqual(self.a.life, 18)
        self.game.deal_damage(self.a, 2, self.b, source=goblin)
        self.assertEqual(self.a.life, 18)
        self.game.deal_damage(self.a, 2, self.b, source=goblin)
        self.assertEqual(self.a.life, 16)

    def test_redirect(self):
        lancers = self.game.enter_battlefield(self.a, LANCERS)
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.run_ability(lancers, bear)
        self.game.deal_damage(lancers, 3, self.b)
        self.assertEqual((lancers.damage, bear.damage), (2, 1))

    def test_static_reduce_and_redirect(self):
        self.game.enter_battlefield(self.a, SERAPH)
        self.game.deal_damage(self.a, 3, self.b)
        self.assertEqual(self.a.life, 18)
        angel = self.game.enter_battlefield(self.a, ARCHANGEL)
        self.game.deal_damage(self.a, 3, self.b)
        self.assertEqual(self.a.life, 18)
        self.assertEqual(angel.damage, 2)       # the Seraph prevents 1 first, the rest goes to the angel

    def test_static_prevent_and_unpreventable(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, BEAR)
        self.game.enter_battlefield(self.a, SANCTUM)
        self.game.deal_damage(bear, 1, self.b)
        self.game.deal_damage(theirs, 1, self.a)
        self.assertEqual((bear.damage, theirs.damage), (0, 1))
        self.game.enter_battlefield(self.b, TORMENT)
        self.game.deal_damage(bear, 1, self.b)
        self.assertEqual(bear.damage, 1)


if __name__ == "__main__":
    unittest.main()
