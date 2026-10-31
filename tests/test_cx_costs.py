"""Activated-ability cost parts paid after the mana (cx_costs)."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

TAPPER = card("Test Tapper", "{2}", "Artifact", "Tap two untapped creatures you control: You gain 3 life.")
DIGGER = card("Test Digger", "{2}", "Artifact", "{1}, Discard two cards: Draw a card.")
BOUNCER = card("Test Bouncer", "{1}{U}", "Creature — Human", "Return ~ to its owner's hand: You gain 1 life.", 1, 1)
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


class CostParts(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parse(self):
        for c in (TAPPER, DIGGER, BOUNCER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_tap_creatures(self):
        tapper = self.game.enter_battlefield(self.a, TAPPER)
        first = self.game.enter_battlefield(self.a, BEAR)
        self.assertFalse(self.game.can_activate(self.a, tapper, 0))
        second = self.game.enter_battlefield(self.a, BEAR)
        self.assertTrue(self.game.activate_ability(self.a, tapper, 0))
        self.game.settle()
        self.assertTrue(first.tapped and second.tapped)
        self.assertEqual(self.a.life, 23)

    def test_discard(self):
        digger = self.game.enter_battlefield(self.a, DIGGER)
        self.game.enter_battlefield(self.a, FOREST).sick = False
        self.a.hand = [ISLAND]
        self.assertFalse(self.game.can_activate(self.a, digger, 0))
        self.a.hand = [ISLAND, ISLAND]
        self.assertTrue(self.game.activate_ability(self.a, digger, 0))
        self.game.settle()
        self.assertEqual(len(self.a.graveyard), 2)
        self.assertEqual(len(self.a.hand), 1)

    def test_return_self(self):
        bouncer = self.game.enter_battlefield(self.a, BOUNCER)
        self.assertTrue(self.game.activate_ability(self.a, bouncer, 0))
        self.game.settle()
        self.assertNotIn(bouncer, self.a.battlefield)
        self.assertEqual(self.a.life, 21)
        self.assertEqual(len(self.a.hand), 1)


if __name__ == "__main__":
    unittest.main()
