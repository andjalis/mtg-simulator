"""End the turn."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem

from tests.test_templates import BEAR, card

STOP = card("Test Stop", "{2}{U}{U}", "Instant", "End the turn.")
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")


class EndTurn(unittest.TestCase):
    def test_parses(self):
        self.assertEqual(STOP.unsupported, [])
        self.assertEqual([e.kind for e in STOP.spell_effects], ["end_turn"])

    def _game(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        game.turn, game.step = 1, "main1"
        return game, a, b

    def test_exiles_other_stack_items_and_locks_the_turn(self):
        game, a, b = self._game()
        bolt = StackItem(card=BOLT, controller=b, effects=list(BOLT.spell_effects), targets=[a])
        stop = StackItem(card=STOP, controller=a, effects=list(STOP.spell_effects), targets=[None])
        game.stack.extend([bolt, stop])
        game.resolve(a, stop.effects[0], None, stop)
        self.assertEqual(game.stack, [stop])
        self.assertIn(BOLT, b.exile)
        self.assertTrue(game.turn_ended)
        self.assertTrue(game.nonmana_locked(a) and game.nonmana_locked(b))
        self.assertTrue(stop.exile_self)

    def test_remaining_phases_do_nothing(self):
        game, a, b = self._game()
        game.turn_ended = True
        game.main_phase(a)                      # would otherwise let the AI play
        game.combat(a, b)
        self.assertEqual(b.life, 20)


if __name__ == "__main__":
    unittest.main()
