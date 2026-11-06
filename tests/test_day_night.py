"""Day and night: real game state, flip by spells cast, daybound/nightbound transform."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND

NAME = "Avabruck Caretaker // Hollowhenge Huntmaster"


class DayNight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = CardDB(offline=True).get(NAME)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_parse_is_full(self):
        self.assertTrue(self.card.daybound and self.card.back.nightbound)
        self.assertFalse(self.card.approximations)
        self.assertFalse(self.card.back.approximations)

    def test_enter_makes_day_and_cycle(self):
        perm = self.game.enter_battlefield(self.a, self.card)
        self.assertEqual(self.game.day_night, "day")
        self.assertEqual(perm.card.name, self.card.name)
        self.game.last_turn_spells = {}
        self.game.take_turn(self.b)               # opponent's turn after a turn with no spells
        self.assertEqual(self.game.day_night, "night")
        self.assertEqual(perm.card.name, self.card.back.name)
        self.game.last_turn_spells = {self.b.name: 2}
        self.game.take_turn(self.a)
        self.assertEqual(self.game.day_night, "day")
        self.assertEqual(perm.card.name, self.card.name)

    def test_enters_transformed_at_night(self):
        self.game.day_night = "night"
        perm = self.game.enter_battlefield(self.a, self.card)
        self.assertEqual(perm.card.name, self.card.back.name)


if __name__ == "__main__":
    unittest.main()
