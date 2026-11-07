"""A card with no printed mana cost can't be cast from hand normally (CR 118.6); only alternative costs work."""
import random
import unittest

from mtgsim import alt_casts
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND


class NoManaCost(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def names(self):
        return [v.name for v in self.game.spell_options(self.a)]

    def test_flag_distinguishes_no_cost_from_zero_cost(self):
        self.assertTrue(self.db.get("Ancestral Vision").advanced_rules.get("no_mana_cost"))
        self.assertFalse(self.db.get("Ornithopter").advanced_rules.get("no_mana_cost"))
        self.assertFalse(self.db.get("Island").advanced_rules.get("no_mana_cost"))

    def test_evermind_not_castable_alone_but_spliceable(self):
        evermind = self.db.get("Evermind")
        self.a.hand = [evermind]
        self.assertEqual(self.names(), [])
        arcane = self.db.get("Ethereal Haze")
        self.a.hand = [evermind, arcane]
        for land in ("Plains", "Plains"):
            self.game.enter_battlefield(self.a, self.db.get(land))
        self.game.settle()
        names = self.names()
        self.assertTrue(any(n.startswith("Ethereal Haze (splice") for n in names), names)
        self.assertNotIn("Evermind", names)

    def test_ancestral_vision_only_via_suspend(self):
        vision = self.db.get("Ancestral Vision")
        self.a.hand = [vision]
        self.game.enter_battlefield(self.a, self.db.get("Island"))
        self.game.settle()
        self.assertEqual(self.names(), [])
        self.assertTrue(alt_casts.suspend(self.game, self.a, vision))
        self.assertIn(vision, self.a.exile)


if __name__ == "__main__":
    unittest.main()
