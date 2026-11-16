"""Static type, colour and base-P/T changes (#406 slice 2): mtgsim.cx_static_chars and cx_grammar_chars."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")
RELIC = card("Test Relic", "{2}", "Artifact", "")
ENSOUL = card("Test Ensoul", "{1}{U}", "Enchantment — Aura",
              "Enchant artifact\nEnchanted artifact is a creature with base power and toughness 5/5 in addition to its "
              "other types.")
WRAP = card("Test Wrappings", "{1}{U}", "Enchantment — Aura",
            "Enchant creature\nEnchanted creature has base power and toughness 0/2.")
ZOMBIFY = card("Test Ghoulflesh", "{B}", "Enchantment — Aura",
               "Enchant creature\nEnchanted creature gets -1/-1 and is a black Zombie in addition to its other colors "
               "and types.")
DRAGONIFY = card("Test Eye", "{B}", "Enchantment — Aura",
                 "Enchant creature\nEnchanted creature is a black Dragon with base power and toughness 4/2 and has "
                 "flying.")
ARMOR = card("Test Armor", "{2}", "Artifact — Equipment",
             "Equipped creature gets +1/+1 and is an artifact in addition to its other types.\nEquip {2}")
KUDO = card("Test Kudo", "{1}{G}{W}", "Legendary Creature — Bear",
            "Other creatures have base power and toughness 2/2 and are Bears in addition to their other types.", 2, 2)
STAG = card("Test Stag", "{3}{W}", "Creature — Elk", "During your turn, ~ has base power and toughness 5/2.", 2, 5)
PACK = card("Test Packbeast", "{2}", "Artifact Creature — Golem", "~ is also a Cleric, Rogue, Warrior, and Wizard.", 2, 2)
GIANT = card("Test Giant", "{4}", "Creature — Giant", "", 5, 5)


class Parsing(unittest.TestCase):
    def rules(self, c):
        self.assertEqual((c.unsupported, c.approximations), ([], []), c.name)
        return c.advanced_rules

    def test_shapes(self):
        self.assertEqual(self.rules(ENSOUL)["cx_chars@host"], ((("add_types", ("Creature",)), ("set_base", 5, 5)),))
        self.assertEqual(self.rules(WRAP)["cx_chars@host"], ((("set_base", 0, 2),),))
        self.assertEqual(self.rules(ZOMBIFY)["cx_chars@host"], ((("add_colors", "B"), ("add_subtypes", ("Zombie",))),))
        self.assertEqual(self.rules(DRAGONIFY)["cx_chars@host"],
                         ((("set_colors", "B"), ("set_subtypes", ("Dragon",)), ("set_base", 4, 2)),))
        self.assertEqual(self.rules(ARMOR)["cx_chars@host"], ((("add_types", ("Artifact",)),),))
        self.assertEqual(ARMOR.equip_bonus, (1, 1))
        self.assertTrue(self.rules(KUDO))
        self.assertTrue(self.rules(STAG)["gated"])
        self.assertEqual(self.rules(PACK) is not None and PACK.subtypes,
                         frozenset({"Golem", "Cleric", "Rogue", "Warrior", "Wizard"}))
        self.assertTrue(WRAP.aura_hostile)
        self.assertFalse(ENSOUL.aura_hostile)

    def test_refusals(self):
        for text, types in (
                ("Enchant creature\nEnchanted creature is a Treefolk with base power and toughness 0/4, loses all "
                 "abilities, card types, and creature types.", "Enchantment — Aura"),       # more than abilities
                ("Creatures you control with +1/+1 counters on them are artifacts in addition to their other types.",
                 "Enchantment"),                                                               # membership changes
                ("Creatures with power 2 or less have base power and toughness 3/3.", "Enchantment"),   # reads itself
                ("As long as you control an Island, ~ is a Fish in addition to its other types.", "Creature — Bear"),
                ("Enchant creature\nEnchanted creature is a Foo with base power and toughness 1/1.",
                 "Enchantment — Aura"),
                ("Enchant creature\nEnchanted creature is goaded.", "Enchantment — Aura"),
                ("~ is also a Foo and Wizard.", "Creature — Bear")):
            with self.subTest(text):
                self.assertTrue(card("Test Refusal", "{1}", types, text, 2, 2).unsupported)


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def enchant(self, aura, host, who=None):
        self.game._aura_host = host
        x = self.game.enter_battlefield(who or self.a, aura)
        self.game.settle()
        return x

    def test_ensoul_artifact(self):
        relic = self.game.enter_battlefield(self.a, RELIC)
        self.assertFalse(relic.is_creature)
        aura = self.enchant(ENSOUL, relic)
        self.assertTrue(relic.is_creature)
        self.assertEqual(set(relic.card.types), {"Artifact", "Creature"})
        self.assertEqual((relic.power, relic.toughness), (5, 5))
        self.game.leave_battlefield(aura, "graveyard")
        self.game.settle()
        self.assertFalse(relic.is_creature)

    def test_base_pt_sits_under_counters_and_pumps(self):
        giant = self.game.enter_battlefield(self.b, GIANT)
        self.enchant(WRAP, giant)
        self.assertEqual((giant.power, giant.toughness), (0, 2))
        giant.counters["+1/+1"] = 2
        giant.pump_p += 1
        self.assertEqual((giant.power, giant.toughness), (3, 4))

    def test_later_animation_wins_over_earlier_static(self):
        giant = self.game.enter_battlefield(self.b, GIANT)
        self.enchant(WRAP, giant)
        self.game.add_continuous_effect(giant, "set_base", power=7, toughness=7, until_eot=True)
        self.assertEqual((giant.power, giant.toughness), (7, 7))
        self.game.expire_continuous_effects()
        self.assertEqual((giant.power, giant.toughness), (0, 2))

    def test_colors_and_types(self):
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.enchant(ZOMBIFY, bear)
        self.assertEqual(set(bear.card.subtypes), {"Bear", "Zombie"})
        self.assertEqual(set(bear.card.colors), {"G", "B"})
        self.assertEqual(bear.power, 1)
        other = self.game.enter_battlefield(self.a, BEAR)
        self.enchant(DRAGONIFY, other)
        self.assertEqual(set(other.card.subtypes), {"Dragon"})
        self.assertEqual(set(other.card.colors), {"B"})
        self.assertEqual((other.power, other.toughness), (4, 2))
        self.assertTrue(other.has("flying"))

    def test_equipment_adds_artifact_and_follows(self):
        x, y = self.game.enter_battlefield(self.a, BEAR), self.game.enter_battlefield(self.a, BEAR)
        armor = self.game.enter_battlefield(self.a, ARMOR)
        armor.attached_to = x
        self.assertIn("Artifact", x.card.types)
        armor.attached_to = y
        self.assertNotIn("Artifact", x.card.types)
        self.assertIn("Artifact", y.card.types)

    def test_group_static(self):
        before = self.game.enter_battlefield(self.b, GIANT)
        kudo = self.game.enter_battlefield(self.a, KUDO)
        after = self.game.enter_battlefield(self.a, GIANT)
        for x in (before, after):
            self.assertEqual((x.power, x.toughness), (2, 2))
            self.assertEqual(set(x.card.subtypes), {"Giant", "Bear"})
        self.assertEqual((kudo.power, kudo.toughness), (2, 2))      # "other": its printed 2/2
        self.game.leave_battlefield(kudo, "graveyard")
        self.assertEqual((before.power, set(before.card.subtypes)), (5, {"Giant"}))

    def test_gated_base_pt(self):
        stag = self.game.enter_battlefield(self.a, STAG)
        self.a.my_turn, self.b.my_turn = True, False
        mine = (stag.power, stag.toughness)
        self.a.my_turn, self.b.my_turn = False, True
        theirs = (stag.power, stag.toughness)
        self.assertEqual((mine, theirs), ((5, 2), (2, 5)))

    def test_cda_subtypes_in_every_zone(self):
        self.assertIn("Wizard", PACK.subtypes)


class AIUse(unittest.TestCase):
    def setUp(self):
        Behaviour.setUp(self)

    def test_shrinking_aura_goes_on_their_creature_and_ensoul_on_my_artifact(self):
        from mtgsim.auras import choose_host
        mine = self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, GIANT)
        self.assertIs(choose_host(self.game, self.a, WRAP), theirs)
        self.assertIsNot(choose_host(self.game, self.a, WRAP), mine)
        relic = self.game.enter_battlefield(self.a, RELIC)
        self.game.enter_battlefield(self.b, RELIC)
        self.assertIs(choose_host(self.game, self.a, ENSOUL), relic)


@unittest.skipUnless(os.path.exists(DB), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Silverskin Armor", "Stonework Packbeast", "Ensoul Artifact", "Illusory Wrappings", "Gigantiform",
                     "Harmonious Archon", "Snowmelt Stag", "Transguild Courier", "Kudo, King Among Bears",
                     "Ghoulflesh", "Godhead of Awe", "Enchanted Evening", "Zoetic Glyph"):
            with self.subTest(name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")


if __name__ == "__main__":
    unittest.main()
