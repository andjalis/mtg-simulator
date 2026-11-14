"""The AI uses leftover mana at the opponent's end step on a modal instant whose mode is card draw / life gain, as it
does for plain ones (Alabaster Potion: "Choose one — Target player gains X life. / Prevent the next X damage ...")."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import PLAINS, card

POTION = card("Test Potion", "{X}{W}{W}", "Instant",
              "Choose one —\n• Target player gains X life.\n"
              "• Prevent the next X damage that would be dealt to any target this turn.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn = 3
    a.library = b.library = [PLAINS] * 10
    for _ in range(5):
        g.enter_battlefield(a, PLAINS).sick = False
    g.settle()
    return g, a, b


class ModalEndStep(unittest.TestCase):
    def test_gains_x_life_at_the_opponents_end_step(self):
        g, a, b = game()
        a.life = 5
        a.hand.append(POTION)
        g.active_idx = 1                 # b's turn
        g.step = "end_step"
        self.assertTrue(g.give_priority(a))          # respond passes, respond_extras takes the modal instant
        g.settle()
        self.assertEqual(a.life, 8)      # X = 3 from five Plains
        self.assertNotIn(POTION, a.hand)


if __name__ == "__main__":
    unittest.main()
