"""le-chonk-3 batch 4: new "where X is ..." quantities and mana-restriction kinds.

Engine-side support for X-family gap shapes (the cards-side _xq/_mana_restriction strips are
queued for the parser batch; these tests drive the evaluator directly with the spec tuples):
- ("greatest_perm", ...) — "the greatest mana value/power/toughness among permanents you control"
  (Accelerated Mutation, Boon of Boseiju)
- ("tapped_any", (...)) — "the number of tapped artifacts and/or creatures you control",
  an artifact creature counting once (Aang and Katara)
- ("defenders",) — "the number of creatures you control with defender" (Doorkeeper, Coral Colony)
Mana restrictions: "legendary", "x_cost" (spells with {X} in their mana cost) and "c_cost"
(costs that contain {C}), all wired into mana_allowed so restricted mana is spent first when
it may be spent at all.
"""
import dataclasses
import random
import unittest

from mtgsim.cards import CardDef
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

ARTIFACT5 = card("Test Engine", "{5}", "Artifact", "")
DRAGON = card("Test Dragon", "{3}{R}", "Creature — Dragon", "Flying", 4, 4)
WALL = card("Test Wall", "{1}{W}", "Creature — Wall", "Defender", 1, 4)
X_SPELL = card("Test X Blast", "{X}{R}", "Sorcery", "Test X Blast deals nothing.")
PLAIN_SPELL = card("Test Blast", "{2}{R}", "Sorcery", "Test Blast does nothing.")
LEGEND = card("Test Legend", "{2}{W}", "Legendary Creature — Human", "", 2, 2)


def restricted(cdef, restriction):
    return dataclasses.replace(cdef, mana_restriction=restriction, produces=frozenset(),
                               restricted_produces=frozenset({"R"}), restricted_amount=1)


class XQuantity(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], None)
        self.b = Player("b", [], None)
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, "main1"

    def perm(self, c, owner, tapped=False):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, tapped
        owner.battlefield.append(p)
        return p

    def test_greatest_perm(self):
        self.perm(ARTIFACT5, self.a)
        self.perm(DRAGON, self.a)
        self.assertEqual(self.game.x_quantity(self.a, ("greatest_perm", "mana value"), None, None), 5)
        self.assertEqual(self.game.x_quantity(self.a, ("greatest_perm", "power"), None, None), 4)
        self.assertEqual(self.game.x_quantity(self.a, ("greatest_perm", "toughness"), None, None), 4)
        self.a.battlefield.clear()
        self.assertEqual(self.game.x_quantity(self.a, ("greatest_perm", "mana value"), None, None), 0)

    def test_tapped_any_counts_each_permanent_once(self):
        critter = self.perm(BEAR, self.a, tapped=True)
        self.perm(ARTIFACT5, self.a, tapped=True)
        self.perm(DRAGON, self.a, tapped=False)              # untapped: not counted
        spec = ("tapped_any", ("artifact", "creature"))
        self.assertEqual(self.game.x_quantity(self.a, spec, None, None), 2)
        critter.card = dataclasses.replace(critter.card, types=frozenset({"Artifact", "Creature"}))
        self.assertEqual(self.game.x_quantity(self.a, spec, None, None), 2)   # still once

    def test_defenders(self):
        self.perm(WALL, self.a)
        self.perm(WALL, self.a)
        self.perm(BEAR, self.a)
        self.perm(WALL, self.b)                              # only yours
        self.assertEqual(self.game.x_quantity(self.a, ("defenders",), None, None), 2)


class ManaRestrictions(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], None)
        self.b = Player("b", [], None)
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, "main1"

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_mana_allowed_kinds(self):
        land = self.perm(restricted(MOUNTAIN, "x_cost"), self.a)
        self.assertTrue(self.game.mana_allowed(land, X_SPELL))
        self.assertFalse(self.game.mana_allowed(land, PLAIN_SPELL))
        land = self.perm(restricted(MOUNTAIN, "legendary"), self.a)
        self.assertTrue(self.game.mana_allowed(land, LEGEND))
        self.assertFalse(self.game.mana_allowed(land, BEAR))
        land = self.perm(restricted(MOUNTAIN, "c_cost"), self.a)
        self.assertTrue(self.game.mana_allowed(
            land, card("Test colorless", "{1}{C}", "Sorcery", "")))
        self.assertFalse(self.game.mana_allowed(land, PLAIN_SPELL))

    def test_restricted_source_only_counts_for_allowed_spells(self):
        self.perm(restricted(MOUNTAIN, "x_cost"), self.a)
        self.perm(MOUNTAIN, self.a)
        # two {R} available, but only the plain mountain may pay for the non-X spell
        self.assertFalse(self.game.can_pay(self.a, {"R": 2}, spell=PLAIN_SPELL))
        self.assertTrue(self.game.can_pay(self.a, {"R": 2}, spell=X_SPELL))
        self.assertTrue(self.game.can_pay(self.a, {"R": 1}, spell=PLAIN_SPELL))


if __name__ == "__main__":
    unittest.main()
