"""Death triggers that deal damage equal to the dying creature's power to each opponent."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import card

HERO = card("Test Hero", "{R}", "Creature — Mouse", "When Test Hero dies, it deals damage equal to its power to each opponent.",
            power="1", toughness="1")


class DamageEqualToPower(unittest.TestCase):
    def test_parses(self):
        self.assertEqual((HERO.unsupported, HERO.triggers[0].event, HERO.triggers[0].effects[0].kind),
                         ([], "dies", "damage_power_opp"))

    def test_the_opponent_takes_the_dead_creatures_power(self):
        a = Player("a", [HERO] * 10, HeuristicAI())
        b = Player("b", [HERO] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        hero = Permanent(HERO, a)
        hero.counters["+1/+1"] = 2
        a.battlefield.append(hero)
        before = b.life
        game.destroy(hero)
        game.settle()
        self.assertEqual(before - b.life, 3)

    def test_a_watcher_uses_the_creature_that_entered(self):
        from mtgsim.engine import StackItem
        from mtgsim.engine.kinds.cx_night_combat import damage_power_opp
        a = Player("a", [HERO] * 10, HeuristicAI())
        b = Player("b", [HERO] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        watcher, entered = Permanent(HERO, a), Permanent(HERO, a)
        entered.counters["+1/+1"] = 4                           # a 5/5
        a.battlefield.extend([watcher, entered])
        before = b.life
        damage_power_opp(game, a, item=StackItem(card=HERO, controller=a, effects=[], targets=[], source=watcher,
                                                 context=entered), opp=b, cause="test")
        self.assertEqual(before - b.life, 5)


if __name__ == "__main__":
    unittest.main()
