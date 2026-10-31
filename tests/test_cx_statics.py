"""Conditional Aura / Equipment bonuses and anthems: "... as long as <condition>"."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

FANGS = card("Test Fangs", "{2}{B}", "Enchantment — Aura",
             "Enchant creature\nEnchanted creature gets +2/+2 as long as it's a Vampire. Otherwise, it gets -2/-2.")
CLOAK = card("Test Cloak", "{U}", "Enchantment — Aura",
             "Enchant creature\nEnchanted creature has shroud as long as it's untapped.")
TRAINER = card("Test Trainer", "{R}{W}", "Creature — Human Soldier",
               "Other creatures you control get +1/+0 as long as you control an Equipment.", 3, 2)
VOICES = card("Test Voices", "{2}{W}", "Enchantment",
              "Creatures you control get +1/+1 as long as you control no nonartifact, nonwhite creatures.")
VAMP = card("Test Vampire", "{1}{B}", "Creature — Vampire", "", 2, 2)
GEAR = card("Test Gear", "{1}", "Artifact — Equipment", "Equip {1}")
KNIGHT = card("Test Knight", "{W}", "Creature — Human Knight", "", 2, 2)


class ConditionalStatics(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def enchant(self, aura, host):
        perm = self.game.enter_battlefield(self.a, aura)
        perm.aura_host = host
        host.auras.append(perm)
        return perm

    def test_parse(self):
        for c in (FANGS, CLOAK, TRAINER, VOICES):
            self.assertEqual(c.unsupported, [], c.name)

    def test_aura_otherwise(self):
        vamp = self.game.enter_battlefield(self.a, VAMP)
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.enchant(FANGS, vamp)
        self.enchant(FANGS, bear)
        self.assertEqual((vamp.power, vamp.toughness), (4, 4))
        self.assertEqual((bear.power, bear.toughness), (0, 0))

    def test_aura_keyword(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.enchant(CLOAK, bear)
        self.assertTrue(bear.has("shroud"))
        bear.tapped = True
        self.assertFalse(bear.has("shroud"))

    def test_anthem(self):
        trainer = self.game.enter_battlefield(self.a, TRAINER)
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.assertEqual(bear.power, 2)
        self.game.enter_battlefield(self.a, GEAR)
        self.assertEqual(bear.power, 3)
        self.assertEqual(trainer.power, 3)        # "other"
        opp_bear = self.game.enter_battlefield(self.b, BEAR)
        self.assertEqual(opp_bear.power, 2)       # "you control"

    def test_anthem_filter_condition(self):
        self.game.enter_battlefield(self.a, VOICES)
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.assertEqual(bear.power, 2)           # a green creature: the condition fails
        self.a.battlefield.remove(bear)
        knight = self.game.enter_battlefield(self.a, KNIGHT)
        self.assertEqual(knight.power, 3)


if __name__ == "__main__":
    unittest.main()


RUBINIA = card("Test Rubinia", "{1}{G}{W}{U}", "Legendary Creature — Faerie",
               "{T}: Gain control of target creature for as long as you control ~ and ~ remains tapped.", 2, 3)
SWORD = card("Test Weaponry", "{2}", "Artifact",
             "{2}, {T}: Target creature gets +2/+0 for as long as ~ remains tapped.")


class LinkedDurations(unittest.TestCase):
    def setUp(self):
        from mtgsim.engine.state import StackItem
        self.StackItem = StackItem
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"

    def activate(self, perm, target):
        perm.tapped = True
        eff = perm.card.activated[0].effects[0]
        self.game.resolve(self.a, eff, target, self.StackItem(self.a, [eff], [target], source=perm), None)

    def test_parse(self):
        for c in (RUBINIA, SWORD):
            self.assertEqual(c.unsupported, [], c.name)

    def test_control_while_tapped(self):
        rubinia = self.game.enter_battlefield(self.a, RUBINIA)
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.activate(rubinia, bear)
        self.assertIs(bear.controller, self.a)
        self.game.untap_step(self.a)
        self.assertIs(bear.controller, self.b)

    def test_pump_while_tapped(self):
        sword = self.game.enter_battlefield(self.a, SWORD)
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.activate(sword, bear)
        self.assertEqual(bear.power, 4)
        self.game.untap_step(self.a)
        self.assertEqual(bear.power, 2)
        sword.tapped = True
        self.assertEqual(bear.power, 2)


BLAST = card("Test Blast", "{4}{R}{R}", "Instant",
             "You may sacrifice two Mountains rather than pay ~'s mana cost.\n~ deals 4 damage to any target.")
SNUFF = card("Test Snuff", "{3}{B}", "Instant",
             "If you control a Swamp, you may pay 4 life rather than pay ~'s mana cost.\nYou gain 1 life.")
WILL = card("Test Will", "{3}{U}{U}", "Instant",
            "You may pay 1 life and exile a blue card from your hand rather than pay ~'s mana cost.\nDraw a card.")
MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")


class AlternativeCosts(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def alt(self, c):
        return [v for v in self.game.spell_options(self.a) if getattr(v, "origin", (None, ""))[1].startswith("cond_alt")
                and v.origin[0].name == c.name]

    def test_parse(self):
        for c in (BLAST, SNUFF, WILL):
            self.assertEqual(c.unsupported, [], c.name)

    def test_sacrifice_mountains(self):
        self.a.hand = [BLAST]
        self.game.enter_battlefield(self.a, MOUNTAIN)
        self.assertFalse(self.alt(BLAST))
        self.game.enter_battlefield(self.a, MOUNTAIN)
        variants = self.alt(BLAST)
        self.assertTrue(variants)
        self.assertTrue(self.game.cast(self.a, variants[0], [self.b]))
        self.game.settle()
        self.assertEqual(self.b.life, 16)
        self.assertFalse(self.a.battlefield)

    def test_condition_and_life(self):
        self.a.hand = [SNUFF]
        self.assertFalse(self.alt(SNUFF))
        self.game.enter_battlefield(self.a, SWAMP).tapped = True
        variants = self.alt(SNUFF)
        self.assertTrue(variants)
        self.assertTrue(self.game.cast(self.a, variants[0], []))
        self.game.settle()
        self.assertEqual(self.a.life, 17)

    def test_pitch(self):
        self.a.hand = [WILL]
        self.assertFalse(self.alt(WILL))
        self.a.hand = [WILL, WILL]
        self.assertTrue(self.game.cast(self.a, self.alt(WILL)[0], []))
        self.game.settle()
        self.assertEqual(len(self.a.exile), 1)
        self.assertEqual(self.a.life, 19)
