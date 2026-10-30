"""le-chonk-5: the aura/equipment template half of the exact aura combat flags.

The engine consumption landed in le-chonk-4 (tests/test_chonk_le4_aura_flags.py drives the
CardDef fields directly). This file pins the parser side, now that auras.py produces them:

- "Enchanted creature can't attack." — aura_flags {"cant_attack"}, no more defender
  approximation (Cessation)
- "Enchanted creature can block only creatures with flying." — block_only_flying (Stratus
  Walk, Air Bladder)
- "Prevent all damage that would be dealt by enchanted creature." — aura_flags
  {"prevent_source_damage"} (Defang, Muzzle, Temporal Isolation); the "to and dealt by"
  wording (Gaseous Form) keeps an approximation note for the unhandled half
- "protection from creatures" joins the granted keywords (Holy Mantle via equip_keywords)
- "Equipped/Enchanted creature gets +N/+N for each <kind> you control" — pt_per/pt_scale
  (Adaptive Omnitool, Helm of the Gods, Ethereal Armor), counted while the card stays attached
"""
import random
import unittest

from mtgsim import auras
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, can_block

from tests.test_templates import BEAR, DRAGON, DRAGON3, ISLAND, card

CESSATION = card("Test Cessation", "{2}{W}", "Enchantment — Aura",
                 "Enchant creature\nEnchanted creature can't attack.")
STRATUS = card("Test Stratus Walk", "{1}{U}", "Enchantment — Aura",
               "Enchant creature\nEnchanted creature has flying.\n"
               "Enchanted creature can block only creatures with flying.")
DEFANG = card("Test Defang", "{1}{W}", "Enchantment — Aura",
              "Enchant creature\nPrevent all damage that would be dealt by enchanted creature.")
GASEOUS = card("Test Gaseous Form", "{1}{U}", "Enchantment — Aura",
               "Enchant creature\nPrevent all combat damage that would be dealt to and dealt by "
               "enchanted creature.")
MANTLE = card("Test Holy Mantle", "{2}{W}{W}", "Enchantment — Aura",
              "Enchant creature\nEnchanted creature gets +2/+2 and has protection from creatures.")
ARMOR = card("Test Ethereal Armor", "{W}", "Enchantment — Aura",
             "Enchant creature\nEnchanted creature gets +1/+1 for each enchantment you control "
             "and has first strike.")
OMNITOOL = card("Test Omnitool", "{2}", "Artifact — Equipment",
                "Equipped creature gets +1/+1 for each artifact you control.\nEquip {3}")
HELM = card("Test Helm of the Gods", "{2}", "Artifact — Equipment",
            "Equipped creature gets +1/+1 for each enchantment you control.\nEquip {1}")
WELL = card("Test Well", "{2}", "Artifact", "{2}, {T}: Draw a card.")
GLYPH = card("Test Glyph", "{1}{W}", "Enchantment", "")


class AuraParseTests(unittest.TestCase):
    def test_cant_attack_is_exact_not_defender(self):
        self.assertEqual(CESSATION.aura_flags, frozenset({"cant_attack"}))
        self.assertEqual(CESSATION.unsupported, [])
        self.assertEqual(CESSATION.approximations, [])
        self.assertNotIn("defender", CESSATION.equip_keywords)
        self.assertTrue(CESSATION.aura_hostile)       # it goes on the opponent's creature

    def test_block_only_flying(self):
        self.assertEqual(STRATUS.block_only_flying, True)
        self.assertEqual(STRATUS.aura_flags, frozenset())
        self.assertFalse(STRATUS.aura_hostile)        # a pump aura for your own creature

    def test_prevent_source_damage(self):
        self.assertEqual(DEFANG.aura_flags, frozenset({"prevent_source_damage"}))
        self.assertEqual(DEFANG.approximations, [])
        self.assertEqual(GASEOUS.aura_flags, frozenset({"prevent_source_damage"}))
        self.assertIn("only the damage dealt by enchanted creature is prevented",
                      GASEOUS.approximations)

    def test_protection_from_creatures(self):
        self.assertEqual(MANTLE.equip_keywords, frozenset({"protection from creatures"}))
        self.assertEqual(MANTLE.equip_bonus, (2, 2))
        self.assertEqual(MANTLE.unsupported, [])

    def test_pt_per_on_equipment_and_auras(self):
        self.assertEqual(OMNITOOL.pt_per, "artifact")
        self.assertEqual(OMNITOOL.pt_scale, (1, 1))
        self.assertEqual(HELM.pt_per, "enchantment")
        self.assertEqual(ARMOR.pt_per, "enchantment")
        self.assertEqual(ARMOR.equip_keywords, frozenset({"first strike"}))
        for c in (OMNITOOL, HELM, ARMOR):
            self.assertEqual(c.unsupported, [], c.name)


class AuraEngineTests(unittest.TestCase):
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

    def test_parsed_cessation_stops_attacks(self):
        foe = self.perm(BEAR, self.b)
        aura = self.perm(CESSATION, self.a)
        auras.attach(self.game, aura, foe)
        self.assertFalse(foe.can_attack())
        self.assertTrue(can_block(foe, self.perm(BEAR, self.a)))   # blocking still works

    def test_parsed_stratus_walk_limits_blocks(self):
        blocker = self.perm(DRAGON, self.a)
        auras.attach(self.game, self.perm(STRATUS, self.a), blocker)
        self.assertFalse(can_block(blocker, self.perm(BEAR, self.b)))
        self.assertTrue(can_block(blocker, self.perm(DRAGON3, self.b)))

    def test_parsed_defang_prevents_its_damage(self):
        attacker = self.perm(BEAR, self.b)
        auras.attach(self.game, self.perm(DEFANG, self.a), attacker)
        self.game.deal_damage(self.a, 2, by=self.b, cause="test", source=attacker, combat=True)
        self.assertEqual(self.a.life, 20)
        self.assertEqual(attacker.damage, 0)

    def test_parsed_mantle_gives_protection(self):
        bear = self.perm(BEAR, self.a)
        auras.attach(self.game, self.perm(MANTLE, self.a), bear)
        self.assertTrue(bear.has("protection from creatures"))
        self.assertEqual((bear.power, bear.toughness), (4, 4))
        self.assertFalse(can_block(self.perm(BEAR, self.b), bear))

    def test_parsed_armor_counts_enchantments(self):
        self.perm(GLYPH, self.a)                    # the armor itself is the second one
        bear = self.perm(BEAR, self.a)
        auras.attach(self.game, self.perm(ARMOR, self.a), bear)
        self.assertEqual((bear.power, bear.toughness), (4, 4))   # 2/2 + 1/+1 per enchantment
        self.assertTrue(bear.has("first strike"))

    def test_parsed_omnitool_counts_artifacts(self):
        bear = self.perm(BEAR, self.a)
        self.perm(WELL, self.a)                     # a second artifact
        omnitool = self.perm(OMNITOOL, self.a)
        omnitool.attached_to = bear
        self.assertEqual((bear.power, bear.toughness), (4, 4))
