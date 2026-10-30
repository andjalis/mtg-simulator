"""le-chonk-4 foundation: exact aura combat flags, protection from creatures, dynamic attach bonuses.

The engine side of the next aura batch: an exact per-aura "can't attack"
(aura_flags, instead of the defender approximation), per-aura "can block only creatures
with flying" (Stratus Walk), "protection from creatures" (Holy Mantle) in the shared
protected_from, and attached-card "for each" bonuses in the power calculation
("Equipped/enchanted creature gets +1/+1 for each artifact you control", Adaptive Omnitool).
Each test sets the CardDef fields the parser template will produce.
"""
import random
import unittest
from dataclasses import replace

from mtgsim import auras
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, can_block

from tests.test_templates import BEAR, DRAGON, DRAGON3, ISLAND, card


CESSATION = card("Test Cessation", "{2}{W}", "Enchantment — Aura",
                 "Enchant creature\nEnchanted creature can't attack.")
STRATUS = card("Test Stratus", "{1}{U}", "Enchantment — Aura",
               "Enchant creature\nEnchanted creature can block only creatures with flying.")
MANTLE = card("Test Mantle", "{2}{W}", "Enchantment — Aura",
              "Enchant creature\nEnchanted creature has protection from creatures.")
OMNITOOL = card("Test Omnitool", "{2}", "Artifact — Equipment",
                "Equipped creature gets +1/+1 for each artifact you control.\nEquip {2}")
WELL = card("Test Well", "{2}", "Artifact", "{2}, {T}: Draw a card.")


class AuraCombatFlagTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def enchant(self, aura_card, host):
        aura = self.perm(aura_card, host.controller)
        auras.attach(self.game, aura, host)
        return aura

    def test_cant_attack_flag_is_exact(self):
        bear = self.perm(BEAR, self.a)
        self.assertTrue(bear.can_attack())
        self.enchant(replace(CESSATION, aura_flags=frozenset({"cant_attack"})), bear)
        self.assertFalse(bear.can_attack())
        self.assertTrue(can_block(bear, self.perm(BEAR, self.b)))   # it can still block
        bear.auras.clear()
        self.assertTrue(bear.can_attack())

    def test_block_only_flying_aura(self):
        blocker = self.perm(DRAGON, self.a)                  # flying, so only the rider can stop it
        self.enchant(replace(STRATUS, block_only_flying=True), blocker)
        ground = self.perm(BEAR, self.b)
        flyer = self.perm(DRAGON3, self.b)
        self.assertFalse(can_block(blocker, ground))
        self.assertTrue(can_block(blocker, flyer))

    def test_protection_from_creatures_blocks_and_damage(self):
        bear = self.perm(BEAR, self.a)
        aura = self.perm(replace(MANTLE, equip_keywords=frozenset({"protection from creatures"})), self.a)
        auras.attach(self.game, aura, bear)
        self.assertTrue(bear.has("protection from creatures"))
        foe = self.perm(BEAR, self.b)
        self.assertFalse(can_block(foe, bear))               # a creature can't block it
        self.assertFalse(self.game.targetable(bear, self.b, source=foe))
        self.game.deal_damage(bear, 2, by=self.b, cause="test", source=foe, combat=True)
        self.assertEqual(bear.damage, 0)
        self.game.deal_damage(bear, 2, by=self.b, cause="test", source=None, combat=True)
        self.assertEqual(bear.damage, 2)                      # a sourceless effect still hurts

    def test_dynamic_equipment_bonus(self):
        bear = self.perm(BEAR, self.a)
        self.perm(WELL, self.a)                               # a second artifact
        omnitool = self.perm(replace(OMNITOOL, pt_per="artifact"), self.a)
        omnitool.attached_to = bear
        self.assertEqual((bear.power, bear.toughness), (4, 4))   # +1/+1 for 2 artifacts

    def test_dynamic_aura_bonus(self):
        bear = self.perm(BEAR, self.a)
        self.perm(WELL, self.a)
        self.perm(WELL, self.a)                               # the aura is no artifact: two wells
        aura = self.perm(replace(MANTLE, equip_bonus=(0, 0), pt_per="artifact"), self.a)
        auras.attach(self.game, aura, bear)
        self.assertEqual((bear.power, bear.toughness), (4, 4))
