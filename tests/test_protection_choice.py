"""#296: 'protection from the color of your choice' with an empty opposing board reads other visible information."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from mtgsim.protection import choose_color

from tests.test_templates import BEAR, ISLAND


class ProtectionChoice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"

    def test_empty_board_uses_opponents_lands(self):
        self.game.enter_battlefield(self.b, self.db.get("Swamp"))
        self.game.enter_battlefield(self.b, self.db.get("Swamp"))
        self.game.enter_battlefield(self.b, self.db.get("Mountain"))
        self.assertEqual(choose_color(self.game, self.a, None), "protection from black")

    def test_creatures_still_win_over_lands(self):
        self.game.enter_battlefield(self.b, self.db.get("Swamp"))
        self.game.enter_battlefield(self.b, self.db.get("Hill Giant"))
        self.assertEqual(choose_color(self.game, self.a, None), "protection from red")

    def test_no_information_is_deterministic(self):
        self.assertEqual(choose_color(self.game, self.a, None), "protection from white")


if __name__ == "__main__":
    unittest.main()
