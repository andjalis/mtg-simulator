"""Morph and megamorph, "when ~ is turned face up", afterlife, myriad, bolster, support, and small effects:
each player loses life / discards, top-of-library reordering, "target creature with flying", self shroud, blitz."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, PLAINS, card

ANGEL = card("Test Morph Angel", "{4}{W}{W}", "Creature — Angel", "Flying\nMorph {2}{W}{W}", 4, 5)
BOWMASTER = card("Test Megamorph", "{2}{G}{G}", "Creature — Dog Archer", "Reach\nMegamorph {G}", 3, 3)
FLIPPER = card("Test Flipper", "{3}{U}", "Creature — Human Wizard",
               "Morph {U}\nWhen ~ is turned face up, draw two cards.", 2, 2)
TRANSPORT = card("Test Transport", "{2}{B}", "Creature — Thrull", "Afterlife 2", 2, 1)
HAMMERS = card("Test Myriad", "{4}{W}", "Creature — Dwarf Cleric", "Myriad", 3, 3)
ANAFENZA = card("Test Bolster", "{W}", "Creature — Spirit Soldier",
                "Whenever another nontoken creature you control enters, bolster 1.", 1, 3)
CAVALRY = card("Test Support", "{5}{G}", "Creature — Elf Knight", "When ~ enters, support 2.", 4, 4)
HOUND = card("Test Hound", "{3}{B}", "Creature — Phyrexian Dog", "When ~ dies, each player loses 4 life.", 4, 4)
RAKER = card("Test Raker", "{2}{B}", "Creature — Drake", "Flying\nWhen ~ dies, each player discards a card.", 2, 2)
DEPTHS = card("Test Depths", "", "Land", "~ enters tapped.\nWhen ~ enters, look at the top three cards of your "
                                         "library, then put them back in any order.\n{T}: Add {U}.")
PHEASANT = card("Test Pheasant", "{1}{G}", "Instant", "~ deals 5 damage to target creature with flying.")
GLIMMER = card("Test Glimmer", "{3}{U}", "Creature — Angel", "Flying\n{U}: ~ gains shroud until end of turn.", 2, 2)
BIRD = card("Test Bird", "{U}", "Creature — Bird", "Flying", 1, 1)
DEVOURER = card("Test Blitzer", "{3}{B}{R}{G}", "Creature — Crocodile", "Blitz {B}{R}{G}", 5, 5)


class MorphAndEffects(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def option(self, p, kind):
        return next(o for o in self.game.spell_options(p) if self.game._origin(o)[1] == kind)

    def test_templates(self):
        for c in (ANGEL, BOWMASTER, FLIPPER, TRANSPORT, HAMMERS, ANAFENZA, CAVALRY, HOUND, RAKER, DEPTHS, PHEASANT,
                  GLIMMER, DEVOURER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_morph_face_down_then_up(self):
        self.put(self.a, PLAINS, 3)
        self.a.hand.append(ANGEL)
        self.assertTrue(self.game.cast(self.a, self.option(self.a, "morph")))
        self.game.settle()
        perm = next(x for x in self.a.battlefield if x.hidden is not None and x.hidden.name == ANGEL.name)
        self.assertEqual((perm.power, perm.toughness, perm.ward), (2, 2, 0))
        self.assertFalse(perm.has("flying"))
        for x in self.a.battlefield:
            x.tapped = False
        self.put(self.a, PLAINS, 1)
        self.game.turn_face_up(self.a)
        self.assertEqual(perm.card.name, ANGEL.name)
        self.assertTrue(perm.has("flying"))

    def test_megamorph_counter_and_face_up_trigger(self):
        self.put(self.a, FOREST, 3)
        self.a.hand.append(BOWMASTER)
        self.assertTrue(self.game.cast(self.a, self.option(self.a, "megamorph")))
        self.game.settle()
        perm = next(x for x in self.a.battlefield if x.hidden is not None and x.hidden.name == BOWMASTER.name)
        self.put(self.a, FOREST, 1)
        self.game.turn_face_up(self.a)
        self.assertEqual(perm.p1, 1)
        flipper = self.put(self.a, BEAR)
        flipper.hidden, flipper.card = FLIPPER, flipper.card
        self.put(self.a, ISLAND, 1)
        hand = len(self.a.hand)
        self.game.turn_face_up(self.a)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 2)

    def test_afterlife(self):
        transport = self.put(self.a, TRANSPORT)
        self.game.destroy(transport)
        self.game.settle()
        spirits = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(spirits), 2)
        self.assertTrue(all(x.has("flying") and x.power == 1 for x in spirits))

    def test_bolster_and_support(self):
        anafenza = self.put(self.a, ANAFENZA)
        bear = self.put(self.a, BEAR)
        self.assertEqual(bear.p1, 1)                         # least toughness: the 2/2 bear
        self.assertEqual(anafenza.p1, 0)
        cavalry = self.put(self.a, CAVALRY)
        self.assertEqual((bear.p1, anafenza.p1, cavalry.p1), (3, 1, 0))  # support, then bolster for the Cavalry

    def test_each_player_loses_and_discards(self):
        hound, raker = self.put(self.a, HOUND), self.put(self.a, RAKER)
        self.a.hand.append(ISLAND)
        self.b.hand.append(ISLAND)
        self.game.destroy(hound)
        self.game.destroy(raker)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (16, 16))
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, 0))

    def test_reorder_top_puts_lands_up_when_short(self):
        self.a.library = [ISLAND, BEAR, ISLAND, BEAR, BEAR]
        self.put(self.a, DEPTHS)
        self.assertTrue(self.a.library[-1].is_land)

    def test_flying_only_damage_and_self_shroud(self):
        bird, bear = self.put(self.b, BIRD), self.put(self.b, BEAR)
        legal = self.game.legal_targets(self.a, PHEASANT.spell_effects[0])
        self.assertIn(bird, legal)
        self.assertNotIn(bear, legal)
        glimmer = self.put(self.a, GLIMMER)
        self.put(self.a, ISLAND)
        self.assertTrue(self.game.activate_ability(self.a, glimmer, 0))
        self.game.settle()
        self.assertTrue(glimmer.has("shroud"))

    def test_blitz_without_life(self):
        self.assertTrue(any(a.kind == "blitz" and a.life == 0 for a in DEVOURER.alt_costs))


if __name__ == "__main__":
    unittest.main()
