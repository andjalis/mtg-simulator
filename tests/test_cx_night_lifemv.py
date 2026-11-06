"""You gain life equal to that card's mana value."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem

from tests.test_templates import BEAR, card

TECH = card("Test Technique", "{1}{W}", "Sorcery", "Return target card from your graveyard to your hand. You gain life equal to that card's mana value.")
BIG = card("Test Big", "{3}{G}", "Creature — Beast", "", power="4", toughness="4")


class LifeMV(unittest.TestCase):
    def test_parses(self):
        self.assertEqual(TECH.unsupported, [])
        self.assertEqual([e.kind for e in TECH.spell_effects][-1], "gain_card_mv")

    def test_gains_life_equal_to_returned_card(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        a.graveyard.append(BIG)
        item = StackItem(card=TECH, controller=a, effects=list(TECH.spell_effects), targets=[None] * len(TECH.spell_effects))
        before = a.life
        for eff in item.effects:
            game.resolve(a, eff, None, item)
        self.assertEqual(BIG in a.hand, True)
        self.assertEqual(a.life - before, BIG.cmc)

    def test_nothing_returned_gains_nothing(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        item = StackItem(card=TECH, controller=a, effects=list(TECH.spell_effects), targets=[None] * len(TECH.spell_effects))
        before = a.life
        for eff in item.effects:
            game.resolve(a, eff, None, item)
        self.assertEqual(a.life, before)


if __name__ == "__main__":
    unittest.main()
