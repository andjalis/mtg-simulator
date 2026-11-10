"""cx_mech: Station "N+ | ..." tiers (keywords and triggers gated on the source's charge counters)."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND


class StationTiers(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, name, charge):
        perm = self.game.enter_battlefield(self.a, self.db.get(name))
        self.game.settle()
        perm.counters["charge"] = charge
        return perm

    def test_keyword_tier_parses_without_ignored_text(self):
        card = self.db.get("Class-4 Tactical Cube")
        self.assertEqual(card.unsupported, [])
        self.assertEqual(card.cond_keywords, (("flying", "cx:charge>=7"),))

    def test_keyword_needs_the_charge_counters(self):
        cube = self.put("Class-4 Tactical Cube", 6)
        self.assertFalse(cube.has("flying"))
        cube.counters["charge"] = 7
        self.assertTrue(cube.has("flying"))

    def test_trigger_tier_is_gated(self):
        card = self.db.get("D-7 Battle Cruiser")
        self.assertEqual(card.unsupported, [])
        self.assertEqual([t.data.get("trigger_gate") for t in card.triggers], ["charge>=3"])
        self.assertFalse([a for a in card.approximations if "trigger" in a])

    def test_trigger_fires_only_with_enough_counters(self):
        for charge, tokens in ((2, 0), (3, 1)):
            self.setUp()
            self.put("D-7 Battle Cruiser", charge)
            self.game.fire(self.a, "begin_combat")
            self.game.settle()
            made = [x for x in self.a.battlefield if x.card.is_token]
            self.assertEqual(len(made), tokens, charge)

    def test_tier_is_checked_when_it_triggers_not_only_on_resolution(self):
        """Fixes #252: charge counters removed in response don't matter once the tier was met; below the tier it never triggers."""
        perm = self.put("D-7 Battle Cruiser", 3)
        self.game.fire(self.a, "begin_combat")
        self.assertEqual(len(self.game.pending), 1)        # triggered
        perm.counters["charge"] = 0                          # removed in response
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 1)
        self.setUp()
        self.put("D-7 Battle Cruiser", 2)
        self.game.fire(self.a, "begin_combat")
        self.assertEqual(len(self.game.pending), 0)        # never triggers


if __name__ == "__main__":
    unittest.main()
