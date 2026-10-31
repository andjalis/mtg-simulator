"""Linked results: "you may X. If you do, Y" with an outcome check, and the top-card "if it's a ... card" sequence."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, card

TAPPER = card("Test Tapper", "{2}{U}", "Creature — Human",
              "When ~ enters, you may tap two untapped creatures you control. If you do, draw two cards.", 1, 1)
SACKER = card("Test Sacker", "{2}{B}", "Creature — Vampire",
              "When ~ enters, you may sacrifice an artifact. If you do, you gain 4 life.", 2, 2)
SCOUT = card("Test Scout", "{1}{G}", "Creature — Elf",
             "When ~ enters, look at the top card of your library. If it's a land card, you may put it onto the "
             "battlefield tapped. Otherwise, put it into your hand.", 1, 1)
TRINKET = card("Test Trinket", "{1}", "Artifact", "")


class LinkParse(unittest.TestCase):
    def test_parse(self):
        for c in (TAPPER, SACKER, SCOUT):
            self.assertEqual(c.unsupported, [], c.name)


class LinkEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_if_you_do_needs_the_action(self):
        hand = len(self.a.hand)
        self.game.enter_battlefield(self.a, TAPPER)          # only itself: can't tap two
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)
        self.game.enter_battlefield(self.a, BEAR).tapped = False
        self.game.enter_battlefield(self.a, TAPPER)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 2)

    def test_sacrifice_filter(self):
        self.game.enter_battlefield(self.a, SACKER)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.game.enter_battlefield(self.a, TRINKET)
        self.game.enter_battlefield(self.a, SACKER)
        self.game.settle()
        self.assertEqual(self.a.life, 24)
        self.assertFalse(any(x.card is TRINKET for x in self.a.battlefield))

    def test_top_card(self):
        self.a.library = [ISLAND, FOREST]
        lands = sum(x.card.is_land for x in self.a.battlefield)
        self.game.enter_battlefield(self.a, SCOUT)
        self.game.settle()
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), lands + 1)
        self.a.library = [ISLAND, BEAR]
        self.game.enter_battlefield(self.a, SCOUT)
        self.game.settle()
        self.assertIn(BEAR, self.a.hand)


if __name__ == "__main__":
    unittest.main()
