"""Platinum Angel: its controller can't lose the game."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, card

ANGEL = card("Test Angel", "{7}", "Artifact Creature", "Flying\nYou can't lose the game and your opponents can't win the game.",
             power=4, toughness=4)


def _game():
    a = Player("a", [BEAR] * 10, HeuristicAI())
    b = Player("b", [BEAR] * 10, HeuristicAI())
    return Game(a, b, random.Random(0), log=False), a, b


class CantLose(unittest.TestCase):
    def test_parses_fully(self):
        self.assertEqual(ANGEL.unsupported, [])

    def test_survives_zero_life_and_empty_library(self):
        game, a, b = _game()
        game.enter_battlefield(a, ANGEL)
        a.life = -3
        a.library = []
        game.draw(a)
        game.state_based_actions()
        self.assertFalse(a.lost)

    def test_loses_once_the_angel_is_gone(self):
        game, a, b = _game()
        game.enter_battlefield(a, ANGEL)
        a.life = 0
        game.state_based_actions()
        self.assertFalse(a.lost)
        game.destroy(a.battlefield[-1])
        game.state_based_actions()
        self.assertTrue(a.lost)

    def test_opponent_without_one_still_loses(self):
        game, a, b = _game()
        game.enter_battlefield(a, ANGEL)
        b.life = 0
        game.state_based_actions()
        self.assertTrue(b.lost)


if __name__ == "__main__":
    unittest.main()
