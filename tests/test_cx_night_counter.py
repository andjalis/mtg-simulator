"""Counterspell taxes: type filters and "{1} for each ..." scaling."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.kinds.other import counter
from tests.test_templates import BEAR, card

REBUFF = card("Test Rebuff", "{1}{U}", "Instant", "Counter target nonartifact spell unless its controller pays {2}.")
REJECT = card("Test Reject", "{1}{U}", "Instant",
              "Counter target creature or planeswalker spell unless its controller pays {3}.")
WINDS = card("Test Winds", "{U}", "Instant", "Counter target spell unless its controller pays {1} for each card in your graveyard.")
ROCK = card("Test Rock", "{1}", "Artifact", "")


class CounterTaxes(unittest.TestCase):
    def test_filters_parse(self):
        self.assertEqual((REBUFF.unsupported, REBUFF.spell_effects[0].filter, REBUFF.spell_effects[0].amount),
                         ([], "nonartifact", 2))
        self.assertEqual((REJECT.unsupported, REJECT.spell_effects[0].filter),
                         ([], "types:Creature,Planeswalker"))
        self.assertEqual(WINDS.unsupported, [])
        self.assertEqual(WINDS.spell_effects[0].data, {"per": "graveyard"})

    def _game(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        game.turn, game.step = 1, "main1"
        return game, a, b

    def test_can_counter_respects_the_filters(self):
        game, a, b = self._game()
        bear = StackItem(card=BEAR, controller=b, effects=[], targets=[])
        rock = StackItem(card=ROCK, controller=b, effects=[], targets=[])
        game.stack.extend([bear, rock])
        self.assertTrue(game.can_counter(REBUFF.spell_effects[0], bear, by=a))
        self.assertFalse(game.can_counter(REBUFF.spell_effects[0], rock, by=a))
        self.assertTrue(game.can_counter(REJECT.spell_effects[0], bear, by=a))
        self.assertFalse(game.can_counter(REJECT.spell_effects[0], rock, by=a))

    def test_for_each_tax_counts_at_resolution(self):
        game, a, b = self._game()
        spell = StackItem(card=BEAR, controller=b, effects=[], targets=[])
        game.stack.append(spell)
        counter(game, a, WINDS.spell_effects[0], spell, None)        # empty graveyard: nothing to pay, countered
        self.assertNotIn(spell, game.stack)

    def test_count_per(self):
        from mtgsim.cx_night_counter import count_per
        game, a, b = self._game()
        a.graveyard.extend([BEAR, BEAR])
        a.hand.append(BEAR)
        a.battlefield.extend([Permanent(BEAR, a), Permanent(ROCK, a)])
        self.assertEqual([count_per(game, a, k) for k in ("graveyard", "hand", "creatures", "artifacts")],
                         [2, 1, 1, 1])


if __name__ == "__main__":
    unittest.main()
