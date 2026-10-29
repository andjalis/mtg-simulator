"""Transmute: discard from hand for a card with the same mana value."""
import random
import unittest

from mtgsim import transmute
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

DIZZY = card("Test Dizzy", "{U}", "Instant", "Target creature gets -3/-0 until end of turn.\nTransmute {1}{U}{U}")
ONE_DROP = card("Test One Drop", "{1}", "Artifact", "")
TWO_DROP = card("Test Two Drop", "{1}{B}", "Creature — Rat", "", 2, 2)
WEST = card("Test West", "", "Land", "Test West enters tapped.\n{T}: Add {U}.\nTransmute {1}{U}{U}")


class Transmute(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main2"
        self.game.active_idx = 0
        self.a.library = [ONE_DROP, TWO_DROP, ISLAND, ONE_DROP]
        self.b.library = [ISLAND] * 10
        for _ in range(3):
            self.game.enter_battlefield(self.a, ISLAND).sick = False
        self.game.settle()

    def test_parses(self):
        self.assertEqual(DIZZY.unsupported, [])
        self.assertEqual(WEST.unsupported, [])
        self.assertEqual(DIZZY.alt_costs[0].kind, "transmute")
        self.assertEqual(DIZZY.alt_costs[0].cost, {"generic": 1, "U": 2})

    def test_fetches_same_mana_value(self):
        self.a.hand = [DIZZY]
        self.assertTrue(transmute.transmute(self.game, self.a, DIZZY))
        self.assertEqual(self.a.hand, [ONE_DROP])
        self.assertIn(DIZZY, self.a.graveyard)
        self.assertEqual(len(self.a.library), 3)

    def test_land_finds_land(self):
        self.a.hand = [WEST]
        self.assertTrue(transmute.transmute(self.game, self.a, WEST))
        self.assertEqual(self.a.hand, [ISLAND])

    def test_needs_mana_and_empty_stack(self):
        self.a.hand = [DIZZY]
        for perm in list(self.a.battlefield)[:2]:
            perm.tapped = True
        self.assertFalse(transmute.transmute(self.game, self.a, DIZZY))
        self.assertIn(DIZZY, self.a.hand)

    def test_ai_transmutes_in_second_main(self):
        self.a.hand = [DIZZY]
        transmute.actions(self.game, self.a)
        self.assertEqual(self.a.hand, [ONE_DROP])


if __name__ == "__main__":
    unittest.main()
