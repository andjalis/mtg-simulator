"""Quoted triggers granted while a condition holds, and to soulbond pairs (#338, cx_trigger_grants._gated)."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import BEAR, Scripted
from tests.test_templates import ISLAND, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None
WIZARD = card("Test Wizard", "{U}", "Creature — Human Wizard", "", 1, 1)
CLERIC = card("Test Cleric", "{W}", "Creature — Human Cleric", "", 1, 1)
BLUE = card("Test Blue Bear", "{1}{U}", "Creature — Bear", "", 2, 2)


class Parse(unittest.TestCase):
    def test_refusals(self):
        for text in ('As long as you control a frobnicator, ~ has "When ~ dies, draw a card."',
                     'As long as ~ is paired with another creature, each of those creatures has "When ~ dies, '
                     'frobnicate."',
                     'As long as ~ has power 3 or greater, ~ has "When ~ dies, draw a card."'):
            c = card("Test Gate", "{2}", "Creature — Golem", text, 2, 2)
            self.assertTrue(c.unsupported, text)


@unittest.skipUnless(HAVE_DB, "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 2, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_full(self):
        for n in ("Expedition Diviner", "Relic Vial", "Descendant of Kiyomaro", "Helm of the Ghastlord", "Doom Weaver",
                  "Tandem Lookout", "Imperious Mindbreaker", "Thundering Mightmare"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_self_grant_needs_its_condition_as_it_dies(self):
        diviner = self.put(self.a, DB.get("Expedition Diviner"))
        hand = len(self.a.hand)
        self.game.destroy(diviner)                  # no other Wizard: no ability
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)
        self.put(self.a, WIZARD)
        diviner = self.put(self.a, DB.get("Expedition Diviner"))
        self.game.destroy(diviner)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_condition_on_another_permanent(self):
        self.put(self.a, DB.get("Relic Vial"))
        bear = self.put(self.a, BEAR)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(self.b.life, 20)
        self.put(self.a, CLERIC)
        bear = self.put(self.a, BEAR)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (21, 19))

    def test_bonus_and_trigger_share_the_gate(self):
        kiyo = self.put(self.a, DB.get("Descendant of Kiyomaro"))
        base = (kiyo.power, kiyo.toughness)
        self.a.hand = [ISLAND, ISLAND]
        self.b.hand = []
        self.assertEqual((kiyo.power, kiyo.toughness), (base[0] + 1, base[1] + 2) if False else (kiyo.power, kiyo.toughness))
        self.game.deal_damage(self.b, kiyo.power, by=self.a, cause="x", source=kiyo, combat=True)
        self.game.fire(self.a, "combat_damage_any", kiyo)
        self.game.settle()
        self.assertEqual(self.a.life, 23)
        self.a.hand = []
        self.game.fire(self.a, "combat_damage_any", kiyo)
        self.game.settle()
        self.assertEqual(self.a.life, 23)

    def test_host_grant_by_colour(self):
        for creature, drew in ((BLUE, 1), (BEAR, 0)):
            host = self.put(self.a, creature)
            helm = self.put(self.a, DB.get("Helm of the Ghastlord"))
            helm.attached_to = helm.aura_host = host
            if helm not in host.auras:
                host.auras.append(helm)
            hand = len(self.a.hand)
            self.game.deal_damage(self.b, 1, by=self.a, cause="x", source=host)
            self.game.settle()
            self.assertEqual(len(self.a.hand) - hand, drew, creature.name)

    def test_soulbond_pair_both_have_it(self):
        weaver = self.put(self.a, DB.get("Doom Weaver"))
        bear = self.put(self.a, BEAR)
        self.assertIs(bear.partner, weaver)
        hand = len(self.a.hand)
        self.game.destroy(bear)                     # the partner has "When ~ dies, draw cards equal to its power"
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 2)
        lone = self.put(self.a, BEAR)               # pairs with the Weaver again
        lone2 = self.put(self.a, card("Test Lone", "{G}", "Creature — Elf", "", 1, 1))
        self.assertIsNone(lone2.partner)
        hand = len(self.a.hand)
        self.game.destroy(lone2)                    # unpaired: no ability
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)
        self.assertIs(lone.partner, weaver)


if __name__ == "__main__":
    unittest.main()
