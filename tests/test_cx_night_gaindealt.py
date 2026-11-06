"""You gain life equal to the damage dealt this way."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, card

SIPHON = card("Test Siphon", "{1}{B}", "Sorcery",
              "~ deals 3 damage to target player. You gain life equal to the damage dealt this way.")
PULSE = card("Test Pulse", "{2}{B}", "Enchantment",
             "At the beginning of your upkeep, ~ deals 1 damage to each opponent. You gain life equal to the damage dealt this way.")


class GainDealt(unittest.TestCase):
    def test_parse(self):
        self.assertEqual((SIPHON.unsupported, PULSE.unsupported), ([], []))

    def test_gains_what_was_dealt(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        a.life = b.life = 10
        for eff in SIPHON.spell_effects:
            game.resolve(a, eff, b, None)
        self.assertEqual((a.life, b.life), (13, 7))

    def test_nothing_dealt_nothing_gained(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        a.life = b.life = 10
        b.prevent_next = 5
        for eff in SIPHON.spell_effects:
            game.resolve(a, eff, b, None)
        self.assertEqual((a.life, b.life), (10, 10))


if __name__ == "__main__":
    unittest.main()
