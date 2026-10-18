"""Mana abilities with costs: filter lands, once-per-turn converters, tap-another costs, sacrifice, conditions."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, find_payment, payable

from tests.test_templates import BEAR, MOUNTAIN, card

FILTER = card("Capital City", types="Land", text="{T}: Add {C}.\n{1}, {T}: Add one mana of any color.".replace("{T}: Add {C}.\n", ""))
DEVOTEE = card("Abzan Devotee", "{1}{W}", "Creature — Human", "{1}: Add {W}, {B}, or {G}. Activate only once each turn.", 1, 1)
RELIC = card("Springleaf Drum", "{1}", "Artifact", "{T}, Tap an untapped creature you control: Add one mana of any color.")
TREASURE = card("Buried Treasure", "{1}", "Artifact", "{T}, Sacrifice ~: Add one mana of any color.")
MOX = card("Mox Jasper", "{0}", "Artifact", "{T}: Add one mana of any color. Activate only if you control a Dragon.")


class ManaFilters(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def perm(self, c):
        p = Permanent(c, self.a)
        p.sick = False
        self.a.battlefield.append(p)
        return p

    def test_templates(self):
        for c in (FILTER, DEVOTEE, RELIC, TREASURE, MOX):
            self.assertEqual(c.unsupported, [], c.name)

    def test_filter_recolours_one_mana_and_adds_none(self):
        self.perm(FILTER)
        self.perm(MOUNTAIN)
        src = self.game.mana_sources(self.a)
        self.assertTrue(payable(src, {"W": 1}))             # Mountain's mana becomes white
        self.assertFalse(payable(src, {"W": 1, "generic": 1}))   # but it is still only one mana
        got = find_payment(src, {"W": 1})
        self.assertEqual({x.card.name for x in got}, {"Capital City", "Mountain"})

    def test_filter_alone_makes_nothing(self):
        self.perm(FILTER)
        self.assertFalse(payable(self.game.mana_sources(self.a), {"generic": 1}))

    def test_once_per_turn_converter(self):
        dev = self.perm(DEVOTEE)
        dev.sick = True                                    # no {T} in the cost
        self.perm(MOUNTAIN)
        self.assertIsNotNone(self.game.pay(self.a, {"W": 1}))
        self.assertTrue(self.a.battlefield[1].tapped)
        self.assertFalse(dev.tapped)
        self.perm(MOUNTAIN)
        self.assertIsNone(self.game.pay(self.a, {"W": 1}))  # used up this turn
        self.game.turn += 1
        self.assertIsNotNone(self.game.pay(self.a, {"W": 1}))

    def test_tap_another_creature_cost(self):
        self.perm(RELIC)
        self.assertIsNone(self.game.pay(self.a, {"generic": 1}))
        bear = self.perm(BEAR)
        self.assertIsNotNone(self.game.pay(self.a, {"W": 1}))
        self.assertTrue(bear.tapped)

    def test_sacrifice_mana_and_condition(self):
        tr = self.perm(TREASURE)
        self.game.pay(self.a, {"G": 1})
        self.assertNotIn(tr, self.a.battlefield)
        self.perm(MOX)
        self.assertEqual(self.game.mana_sources(self.a), [])
        self.perm(card("Drake", "{2}", "Creature — Dragon", "", 1, 1))
        self.assertEqual(len(self.game.mana_sources(self.a)), 1)


if __name__ == "__main__":
    unittest.main()
