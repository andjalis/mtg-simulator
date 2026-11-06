"""Return that card to the battlefield under your control."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, card

DEMISE = card("Test Demise", "{1}{B}", "Enchantment — Aura", "Enchant creature\nWhen enchanted creature dies, return that card to the battlefield under your control.")
SHIFT = card("Test Shift", "{2}{W}", "Instant", "Exile target creature you control, then return that card to the battlefield under your control.")


class ReturnThat(unittest.TestCase):
    def _game(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        game.turn, game.step = 1, "main1"
        return game, a, b

    def test_parses(self):
        self.assertEqual(DEMISE.unsupported, [])
        self.assertEqual(DEMISE.host_triggers[0].effects[0].kind, "return_dead")
        self.assertEqual(SHIFT.unsupported, [])

    def test_dies_returns_under_auras_controller(self):
        game, a, b = self._game()
        victim = Permanent(BEAR, b)
        b.battlefield.append(victim)
        game.leave_battlefield(victim, "graveyard")
        eff = DEMISE.host_triggers[0].effects[0]
        game.resolve(a, eff, None, StackItem(controller=a, effects=[eff], targets=[None], context=victim), prev=victim)
        self.assertEqual(len(a.battlefield), 1)
        self.assertEqual(len(b.battlefield), 0)
        self.assertEqual(len(b.graveyard), 0)

    def test_blink_returns_exiled_creature(self):
        game, a, b = self._game()
        bear = Permanent(BEAR, a)
        a.battlefield.append(bear)
        item = StackItem(card=SHIFT, controller=a, effects=list(SHIFT.spell_effects), targets=[bear, None])
        game.stack.append(item)
        game.resolve_top()
        self.assertEqual(len(a.battlefield), 1)
        self.assertEqual(len(a.exile), 0)


if __name__ == "__main__":
    unittest.main()
