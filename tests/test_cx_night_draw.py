"""Howling Mine family: that player draws an additional card."""
import random
import unittest

from mtgsim import cards
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, card

MINE = card("Test Mine", "{2}", "Artifact", "At the beginning of each player's draw step, that player draws an additional card.")


class DrawActive(unittest.TestCase):
    def test_parses(self):
        effects, unmatched = cards._parse_effects("That player draws an additional card.")
        self.assertEqual((unmatched, effects[0].kind), ([], "draw_active"))
        self.assertEqual(MINE.unsupported, [])
        self.assertEqual(MINE.triggers[0].event, "each_draw_step")

    def test_active_player_draws(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        for pl in (a, b):
            pl.library = list(pl.deck)
        game.turn, game.step = 2, "draw"
        game.active_idx = 1
        eff = MINE.triggers[0].effects[0]
        src = Permanent(MINE, a)
        a.battlefield.append(src)
        game.resolve(a, eff, None, StackItem(controller=a, effects=[eff], targets=[None], source=src, context=b))
        self.assertEqual((len(a.hand), len(b.hand)), (0, 1))


if __name__ == "__main__":
    unittest.main()
