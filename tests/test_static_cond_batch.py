"""Static-condition batch: capitalised 'Protection from X and from Y' lines."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import ISLAND, card


class ProtectionAndFrom(unittest.TestCase):
    def test_capitalised_double_protection(self):
        c = card("Test Crusader", "{3}", "Creature — Human", "Protection from black and from red", 2, 2)
        self.assertEqual(c.unsupported, [])
        self.assertEqual(set(c.keywords), {"protection from black", "protection from red"})


WHISKER = card("Test Whisker", "{1}{U}", "Creature — Human",
               "Threshold — As long as there are seven or more cards in your graveyard, creatures your opponents control get -1/-0.", 1, 1)
BEAR = card("Test Bear", "{2}", "Creature — Bear", "", 2, 2)


class OpponentThresholdDebuff(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 10, HeuristicAI())
        self.b = Player("b", [ISLAND] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.whisker = self._put(self.a, WHISKER)
        self.mine = self._put(self.a, BEAR)
        self.theirs = self._put(self.b, BEAR)

    def _put(self, player, c):
        p = Permanent(c, player)
        player.battlefield.append(p)
        return p

    def test_parses(self):
        self.assertEqual(WHISKER.unsupported, [])

    def test_threshold_gates_and_scope(self):
        self.a.graveyard[:] = [ISLAND] * 6
        self.assertEqual(self.theirs.power, 2)
        self.a.graveyard.append(ISLAND)
        self.assertEqual(self.theirs.power, 1)
        self.assertEqual(self.theirs.toughness, 2)
        self.assertEqual(self.mine.power, 2)       # own creatures are untouched
        self.assertEqual(self.whisker.power, 1)


if __name__ == "__main__":
    unittest.main()
