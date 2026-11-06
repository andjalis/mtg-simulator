"""Restricted mana in general: "Spend this mana only to cast <spells> or activate abilities of <sources>"."""
import random
import unittest

from mtgsim import cx_abil_mana as M
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

HAWKER = card("Test Hawker", "{2}", "Artifact", "{T}: Add {C}{U}. Spend this mana only to activate abilities.")
ARCH = card("Test Architect", "{2}", "Artifact",
            "{T}: Add {C}{C}. Spend this mana only to cast artifact spells or activate abilities of artifacts.")
BRAIDER = card("Test Braider", "{2}", "Artifact",
               "{T}: Add {R}{R}. Spend this mana only to cast dragon spells.")
DRAGON = card("Test Dragon", "{1}{R}", "Creature — Dragon", "", 2, 2)
MANA_RING = card("Test Ring", "{1}", "Artifact", "{2}, {T}: You gain 3 life.")
PUMP = card("Test Pump", "{1}", "Creature — Human", "{2}: You gain 1 life.", 1, 1)


class Parse(unittest.TestCase):
    def test_wordings(self):
        for text in ("to activate abilities",
                     "to cast artifact spells or activate abilities of artifacts",
                     "to cast creature spells or activate abilities of creature sources",
                     "to cast instant and/or sorcery spells",
                     "to cast dwarf, equipment, and saga spells",
                     "to cast lesson spells", "to cast noncreature spells", "to cast planeswalker spells",
                     "to cast dragon spells or activate abilities of dragons",
                     "to cast mount or vehicle spells"):
            with self.subTest(text=text):
                self.assertTrue(M.parse(text).startswith("pred:"))

    def test_unmodelled_stays_unmodelled(self):
        for text in ("to cast kicked spells", "to cast spells from exile", "to cast your commander",
                     "to cast spells with flashback from a graveyard", "to turn permanents face up"):
            with self.subTest(text=text):
                self.assertIsNone(M.parse(text))

    def test_cards_parse(self):
        for c in (HAWKER, ARCH, BRAIDER):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertTrue(c.mana_restriction.startswith("pred:"))


class Pay(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_ability_only_mana(self):
        hawker = self.game.enter_battlefield(self.a, HAWKER)
        hawker.sick = False
        ring = self.game.enter_battlefield(self.a, PUMP)
        ring.sick = False
        self.assertFalse(self.game.mana_allowed(hawker, BEAR))
        self.assertTrue(self.game.mana_allowed(hawker, M.AbilityPayment(ring)))
        self.assertTrue(self.game.can_activate(self.a, ring, 0))
        self.assertTrue(self.game.activate_ability(self.a, ring, 0))
        self.game.settle()
        self.assertTrue(hawker.tapped)
        self.assertEqual(self.a.life, 21)

    def test_ability_only_mana_cannot_cast(self):
        hawker = self.game.enter_battlefield(self.a, HAWKER)
        hawker.sick = False
        self.a.hand = [DRAGON]
        self.assertFalse(self.game.spell_payable(self.a, DRAGON))

    def test_artifact_source_only(self):
        arch = self.game.enter_battlefield(self.a, ARCH)
        arch.sick = False
        creature = self.game.enter_battlefield(self.a, PUMP)
        creature.sick = False
        ring = self.game.enter_battlefield(self.a, MANA_RING)
        ring.sick = False
        self.assertFalse(self.game.can_activate(self.a, creature, 0))   # an artifact's mana can't pay a creature
        self.assertTrue(self.game.can_activate(self.a, ring, 0))       # ring taps itself; arch pays the {2}
        self.assertTrue(self.game.mana_allowed(arch, ARCH))             # and it can cast artifact spells
        self.assertFalse(self.game.mana_allowed(arch, DRAGON))

    def test_subtype_spells(self):
        braider = self.game.enter_battlefield(self.a, BRAIDER)
        braider.sick = False
        self.assertTrue(self.game.mana_allowed(braider, DRAGON))
        self.assertFalse(self.game.mana_allowed(braider, BEAR))
        self.assertFalse(self.game.mana_allowed(braider, M.AbilityPayment(braider)))


TENDER = card("Test Tender", "{1}{G}", "Creature — Elf", "{T}: For each color among permanents you control, add one "
              "mana of that color.", 1, 1)
GLOBE = card("Test Globe", "{3}", "Artifact", "{1}, {T}: Add two mana of different colors.")
ORB = card("Test Orb", "{2}", "Artifact", "{1}, {T}: Add two mana in any combination of colors. Spend this mana only "
           "to cast Dragon spells or activate abilities of Dragons.")
LOTUS = card("Test Lotus", "{0}", "Artifact", "{T}, Sacrifice ~: Add X mana of any one color, where X is the number "
             "of petal counters on ~.")
RED = card("Test Red", "{R}", "Creature — Goblin", "", 1, 1, )


class ManaEffects(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def pool(self):
        return sorted(next(iter(m.card.produces)) for m in self.a.pool)

    def test_parse(self):
        for c in (TENDER, GLOBE, ORB, LOTUS):
            self.assertEqual(c.unsupported, [], c.name)

    def test_one_per_color_among_permanents(self):
        t = self.game.enter_battlefield(self.a, TENDER)
        t.sick = False
        self.game.enter_battlefield(self.a, BEAR)               # green
        self.game.enter_battlefield(self.a, ISLAND)             # colourless land
        self.assertTrue(self.game.activate_ability(self.a, t, 0))
        self.game.settle()
        self.assertEqual(self.pool(), ["G"])

    def test_two_different_colors(self):
        g = self.game.enter_battlefield(self.a, GLOBE)
        self.game.enter_battlefield(self.a, ISLAND).sick = False
        self.assertTrue(self.game.activate_ability(self.a, g, 0))
        self.game.settle()
        self.assertEqual(len(self.pool()), 2)
        self.assertEqual(len(set(self.pool())), 2)

    def test_restricted_pool_mana(self):
        o = self.game.enter_battlefield(self.a, ORB)
        self.game.enter_battlefield(self.a, ISLAND).sick = False
        self.assertTrue(self.game.activate_ability(self.a, o, 0))
        self.game.settle()
        self.assertEqual(len(self.a.pool), 2)
        sources = self.game.mana_sources(self.a, spell=BEAR)
        self.assertFalse(any(m in sources for m in self.a.pool))        # not a Dragon spell
        self.assertTrue(all(m in self.game.mana_sources(self.a, spell=DRAGON) for m in self.a.pool))

    def test_x_from_counters(self):
        lotus = self.game.enter_battlefield(self.a, LOTUS)
        lotus.sick = False
        lotus.counters["petal"] = 3
        self.assertTrue(self.game.activate_ability(self.a, lotus, 0))
        self.game.settle()
        self.assertEqual(len(self.a.pool), 3)
        self.assertEqual(len(set(self.pool())), 1)              # all one colour


if __name__ == "__main__":
    unittest.main()


class BoostAI(unittest.TestCase):
    """HeuristicAI activates a mana-adding ability when it brings a spell in hand within reach, and not otherwise."""

    def setUp(self):
        from mtgsim.ai import HeuristicAI
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10
        self.island = self.game.enter_battlefield(self.a, ISLAND)
        self.island.sick = False

    def test_casts_a_creature_with_restricted_pool_mana(self):
        fount = card("Test Fount", "{2}", "Artifact", "{1}, {T}: Add three mana in any combination of colors. "
                     "Spend this mana only to cast creature spells.")
        self.assertEqual(fount.unsupported, [])
        self.game.enter_battlefield(self.a, fount).sick = False
        self.game.enter_battlefield(self.a, ISLAND).sick = False
        big = card("Test Titan", "{3}{U}", "Creature — Giant", "", 4, 4)
        self.a.hand = [big]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn(big, [x.card for x in self.a.creatures])

    def test_does_not_waste_restricted_mana_on_the_wrong_spell(self):
        fount = card("Test Fount", "{2}", "Artifact", "{1}, {T}: Add three mana in any combination of colors. "
                     "Spend this mana only to cast creature spells.")
        self.game.enter_battlefield(self.a, fount).sick = False
        self.game.enter_battlefield(self.a, ISLAND).sick = False
        self.a.hand = [card("Test Divination", "{3}{U}", "Sorcery", "Draw two cards.")]
        self.a.ai.main_phase(self.game, self.a)
        self.assertTrue(self.a.hand)
        self.assertFalse(fount.tapped if hasattr(fount, "tapped") else False)
        self.assertEqual(self.a.pool, [])
