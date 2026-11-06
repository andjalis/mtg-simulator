"""Global attack-each-combat requirements."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.cx_night_aura import forced_to_attack
from tests.test_templates import BEAR, card

MELEE = card("Test Melee", "{3}{R}", "Enchantment", "All creatures attack each combat if able.")
TURTLE = card("Test Turtle", "{3}{U}", "Creature", "Creatures your opponents control attack each combat if able.",
              power=2, toughness=2)


def _game():
    a = Player("a", [BEAR] * 10, HeuristicAI())
    b = Player("b", [BEAR] * 10, HeuristicAI())
    return Game(a, b, random.Random(0), log=False), a, b


class ForcedAttack(unittest.TestCase):
    def test_parse(self):
        self.assertEqual((MELEE.unsupported, TURTLE.unsupported), ([], []))

    def test_all_creatures(self):
        game, a, b = _game()
        self.assertFalse(forced_to_attack(game, a))
        game.enter_battlefield(a, MELEE)
        self.assertTrue(forced_to_attack(game, a) and forced_to_attack(game, b))

    def test_only_the_opponents_of_the_controller(self):
        game, a, b = _game()
        game.enter_battlefield(a, TURTLE)
        self.assertFalse(forced_to_attack(game, a))
        self.assertTrue(forced_to_attack(game, b))


if __name__ == "__main__":
    unittest.main()
