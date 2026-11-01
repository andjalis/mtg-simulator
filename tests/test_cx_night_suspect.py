"""Suspect: menace and can't block."""
import random
import unittest

from mtgsim import cards
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.state import can_block

from tests.test_templates import BEAR, card

SUSPECTER = card("Test Suspecter", "{1}{B}", "Sorcery", "Suspect target creature an opponent controls.")


class Suspect(unittest.TestCase):
    def test_parses(self):
        for text in ("Suspect it.", "Suspect enchanted creature.", "Suspect up to one target creature."):
            effects, unmatched = cards._parse_effects(text)
            self.assertEqual((unmatched, effects[0].kind), ([], "suspect"))
        self.assertEqual(SUSPECTER.unsupported, [])

    def test_suspected_creature_cannot_block_and_has_menace(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        game.turn, game.step = 1, "main1"
        victim, attacker = Permanent(BEAR, b), Permanent(BEAR, a)
        b.battlefield.append(victim)
        a.battlefield.append(attacker)
        self.assertTrue(can_block(victim, attacker))
        eff = SUSPECTER.spell_effects[0]
        game.resolve(a, eff, victim, StackItem(card=SUSPECTER, controller=a, effects=[eff], targets=[victim]))
        self.assertTrue(victim.has("suspected"))
        self.assertTrue(victim.has("menace"))
        self.assertFalse(can_block(victim, attacker))


if __name__ == "__main__":
    unittest.main()
