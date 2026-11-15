"""Equipment attachment heads: "Whenever ~ becomes attached to a creature / unattached from a permanent" (#538)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_trigger
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")
MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")


def events(line):
    out = _parse_trigger(line)
    return None if out is None or out[1] else [(t.event, [(e.kind, e.target) for e in t.effects]) for t in out[0]]


class Parsing(unittest.TestCase):
    def test_heads(self):
        self.assertEqual(events("Whenever ~ becomes attached to a creature, tap that creature."),
                         [("equip_attached", [("tap", "prev")])])
        self.assertEqual(events("Whenever ~ becomes unattached from a permanent, sacrifice that permanent."),
                         [("equip_unattached", [("cx_sac_that", "prev")])])

    def test_refusals(self):
        self.assertIsNone(events("When ~ becomes attached to an instant or sorcery, put that card onto the "
                                 "battlefield under its owner's control."))


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 5, HeuristicAI())
        self.b = Player("b", [BEAR] * 5, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for _ in range(6):
            self.game.enter_battlefield(self.a, MOUNTAIN).sick = False

    def equipment(self, text):
        return self.game.enter_battlefield(self.a, card("Test Gear", "{1}", "Artifact — Equipment",
                                                        text + "\nEquip {0}"))

    def test_attached_taps_the_creature(self):
        gear = self.equipment("Whenever ~ becomes attached to a creature, tap that creature.")
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.assertTrue(self.game.equip(self.a, gear, bear))
        self.game.settle()
        self.assertTrue(bear.tapped)

    def test_unattached_sacrifices_the_old_creature_also_when_the_equipment_leaves(self):
        gear = self.equipment("Whenever ~ becomes unattached from a permanent, sacrifice that permanent.")
        first, second = self.game.enter_battlefield(self.a, BEAR), self.game.enter_battlefield(self.a, BEAR)
        self.assertTrue(self.game.equip(self.a, gear, first))
        self.game.settle()
        self.assertIn(first, self.a.battlefield)                   # attaching alone does nothing
        self.assertTrue(self.game.equip(self.a, gear, second))     # moved: the old one is sacrificed
        self.game.settle()
        self.assertNotIn(first, self.a.battlefield)
        self.assertIn(second, self.a.battlefield)
        self.game.destroy(gear)                                     # leaves while attached: still triggers
        self.game.settle()
        self.assertNotIn(second, self.a.battlefield)

    def test_sacrifice_only_what_you_control(self):
        gear = self.equipment("Whenever ~ becomes unattached from a permanent, sacrifice that permanent.")
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.equip(self.a, gear, bear)
        self.game.settle()
        self.a.battlefield.remove(bear)                             # an opponent gained control of it
        bear.controller = self.b
        self.b.battlefield.append(bear)
        gear.attached_to = None
        self.game.settle()
        self.assertIn(bear, self.b.battlefield)

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Enormous Energy Blade", "Grafted Wargear", "Grafted Exoskeleton", "Stitcher's Graft",
                     "Captain's Hook"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)
        hook = self.game.enter_battlefield(self.a, db.get("Captain's Hook"))
        bear = self.game.enter_battlefield(self.a, BEAR)
        for _ in range(2):
            self.game.enter_battlefield(self.a, MOUNTAIN).sick = False
        self.assertTrue(self.game.equip(self.a, hook, bear))
        self.game.settle()
        self.game.destroy(hook)                                     # "destroy that permanent"
        self.game.settle()
        self.assertNotIn(bear, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()
