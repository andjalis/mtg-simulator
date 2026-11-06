"""'Target player draws two cards and loses 2 life' targets a player: the draw and the life loss hit the same one."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, StackItem

from tests.test_templates import BEAR, ISLAND


class TargetPlayerDraw(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = CardDB(offline=True).get("Blood Pact")

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def resolve(self, target):
        effects = list(self.card.spell_effects)
        self.game.stack.append(StackItem(self.a, effects, [target, None], card=self.card, name=self.card.name))
        self.game.resolve_top()

    def test_parse_targets_a_player(self):
        self.assertEqual([(e.kind, e.target) for e in self.card.spell_effects], [("draw", "player"), ("lose_life", "prev")])
        self.assertFalse(self.card.unsupported)

    def test_opponent_target(self):
        hand, life = len(self.b.hand), self.b.life
        mine, my_life = len(self.a.hand), self.a.life
        self.resolve(self.b)
        self.assertEqual((len(self.b.hand), self.b.life), (hand + 2, life - 2))
        self.assertEqual((len(self.a.hand), self.a.life), (mine, my_life))

    def test_self_target(self):
        hand, life = len(self.a.hand), self.a.life
        self.resolve(self.a)
        self.assertEqual((len(self.a.hand), self.a.life), (hand + 2, life - 2))

    def test_ai_targets_itself(self):
        from mtgsim.engine.policy import default_choose_target
        self.assertIs(default_choose_target(self.game, self.a, self.card.spell_effects[0]), self.a)


if __name__ == "__main__":
    unittest.main()
