"""Wheel-for-seven wording and the Ali from Cairo life floor."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, card

TECHNIQUE = card("Test Technique", "{2}{R}", "Sorcery", "Each player may discard their hand and draw seven cards.")
ALI = card("Test Ali", "{4}", "Artifact Creature", "Damage that would reduce your life total to less than 1 reduces it to 1 instead.",
           power=0, toughness=4)


def _game():
    a = Player("a", [BEAR] * 20, HeuristicAI())
    b = Player("b", [BEAR] * 20, HeuristicAI())
    game = Game(a, b, random.Random(0), log=False)
    a.library = list(a.deck)
    b.library = list(b.deck)
    return game, a, b


class Misc(unittest.TestCase):
    def test_parse(self):
        self.assertEqual((TECHNIQUE.unsupported, ALI.unsupported), ([], []))

    def test_wheel(self):
        game, a, b = _game()
        a.hand, b.hand = [BEAR] * 2, [BEAR] * 5
        game.resolve(a, TECHNIQUE.spell_effects[0], None, None)
        self.assertEqual((len(a.hand), len(b.hand), len(a.graveyard), len(b.graveyard)), (7, 7, 2, 5))

    def test_life_floor(self):
        game, a, b = _game()
        game.enter_battlefield(a, ALI)
        a.life = 3
        game.deal_damage(a, 10, by=b)
        game.state_based_actions()
        self.assertEqual((a.life, a.lost), (1, False))
        game.deal_damage(a, 5, by=b)
        game.state_based_actions()
        self.assertEqual((a.life, a.lost), (1, False))

    def test_other_life_loss_and_the_opponent_are_unaffected(self):
        game, a, b = _game()
        game.enter_battlefield(a, ALI)
        b.life = 3
        game.deal_damage(b, 10, by=a)
        game.state_based_actions()
        self.assertTrue(b.lost)


if __name__ == "__main__":
    unittest.main()
