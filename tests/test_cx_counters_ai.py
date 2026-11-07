"""The default AI (HeuristicAI) really uses the cx_counters effects and aims them at the right side."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.engine.state import Permanent
from tests.test_templates import BEAR, ISLAND, card


class AiUse(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [ISLAND] * 20, HeuristicAI()), Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0
        for _ in range(4):
            self.a.battlefield.append(Permanent(ISLAND, self.a))

    def creatures(self, p, n):
        out = [Permanent(BEAR, p) for _ in range(n)]
        p.battlefield.extend(out)
        return out

    def cast(self, c):
        self.a.hand.append(c)
        self.game.main_phase(self.a)

    def test_stun_on_each_of_up_to_two_hits_the_opponent(self):
        mine, theirs = self.creatures(self.a, 2), self.creatures(self.b, 2)
        self.cast(card("Test Freeze", "{1}{U}", "Sorcery", "Put a stun counter on each of up to two target creatures."))
        self.assertEqual([x.counters.get("stun", 0) for x in theirs], [1, 1])
        self.assertEqual([x.counters.get("stun", 0) for x in mine], [0, 0])

    def test_distribute_goes_to_my_creatures(self):
        mine, theirs = self.creatures(self.a, 2), self.creatures(self.b, 2)
        self.cast(card("Test Spread", "{1}{U}", "Sorcery",
                       "Distribute three +1/+1 counters among one, two, or three target creatures you control."))
        self.assertEqual(sum(x.counters.get("+1/+1", 0) for x in mine), 3)
        self.assertEqual(sum(x.counters.get("+1/+1", 0) for x in theirs), 0)

    def test_remove_all_counters_hits_the_opponents_creature(self):
        mine, theirs = self.creatures(self.a, 1), self.creatures(self.b, 1)
        mine[0].counters["+1/+1"], theirs[0].counters["+1/+1"] = 2, 3
        self.cast(card("Test Wither", "{1}{U}", "Sorcery", "Remove all +1/+1 counters from target creature."))
        self.assertEqual((mine[0].counters["+1/+1"], theirs[0].counters["+1/+1"]), (2, 0))

    def test_remove_a_counter_from_my_creature_takes_the_harmful_one(self):
        mine = self.creatures(self.a, 1)[0]
        mine.counters.update({"stun": 1, "+1/+1": 1})
        self.cast(card("Test Mend", "{1}{U}", "Sorcery", "Remove a counter from target creature you control."))
        self.assertEqual((mine.counters["stun"], mine.counters["+1/+1"]), (0, 1))

    def test_move_counter_between_my_creatures(self):
        one, two = self.creatures(self.a, 2)
        one.counters["+1/+1"] = 2
        self.creatures(self.b, 1)[0].counters["+1/+1"] = 5
        self.cast(card("Test Shift", "{1}{U}", "Sorcery",
                       "Move a +1/+1 counter from target creature you control onto another target creature you control."))
        self.assertEqual(one.counters["+1/+1"] + two.counters["+1/+1"], 2)
        self.assertEqual(two.counters["+1/+1"], 1)

    def test_poison_goes_to_the_player_that_was_hit(self):
        hero = card("Test Viper", "{1}", "Creature — Snake",
                    "Whenever ~ deals combat damage to a player, that player gets a poison counter.", 2, 2)
        viper = Permanent(hero, self.a)
        viper.sick = False
        self.a.battlefield.append(viper)
        self.game.step = "main1"
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual((self.b.counters.get("poison", 0), self.a.counters.get("poison", 0)), (1, 0))


if __name__ == "__main__":
    unittest.main()
