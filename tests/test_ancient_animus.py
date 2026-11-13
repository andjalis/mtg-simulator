"""Ancient Animus (flagged as a suspicious sampled parse on PR #349): the counter only on a legendary creature, then
that creature fights; the AI aims it at its own creature and the opponent's."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
ANIMUS = card("Ancient Animus", "{1}{G}", "Instant",
              "Put a +1/+1 counter on target creature you control if it's legendary. Then it fights target creature "
              "an opponent controls. (Each deals damage equal to its power to the other.)")


def game(ai, legendary):
    a, b = Player("a", [], ai), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 2, "main1"
    a.library = b.library = [FOREST] * 10
    for _ in range(3):
        g.enter_battlefield(a, FOREST).sick = False
    mine = g.enter_battlefield(a, card("Mine", "{1}", ("Legendary " if legendary else "") + "Creature — Elf", "", 3, 3))
    foe = g.enter_battlefield(b, card("Foe", "{1}", "Creature — Ogre", "", 3, 4))
    g.settle()
    a.hand.append(ANIMUS)
    return g, a, b, mine, foe


class AncientAnimus(unittest.TestCase):
    def test_legendary_gets_the_counter_and_wins_the_fight(self):
        g, a, b, mine, foe = game(Scripted(), True)
        self.assertTrue(g.cast(a, ANIMUS, targets=[mine, foe]))
        g.settle()
        self.assertEqual(mine.counters.get("+1/+1"), 1)
        self.assertNotIn(foe, b.battlefield)
        self.assertEqual(mine.damage, 3)

    def test_nonlegendary_just_fights(self):
        g, a, b, mine, foe = game(Scripted(), False)
        self.assertTrue(g.cast(a, ANIMUS, targets=[mine, foe]))
        g.settle()
        self.assertNotIn(mine, a.battlefield)
        self.assertEqual(foe.damage, 3)

    def test_ai_casts_it_on_the_right_sides(self):
        g, a, b, mine, foe = game(HeuristicAI(), True)
        mine.card = card("Mine", "{1}", "Legendary Creature — Elf", "", 4, 4)   # wins the fight without the counter:
        g.main_phase(a)                                                          # the AI's fight check ignores the counter
        g.settle()
        self.assertEqual(mine.counters.get("+1/+1"), 1)
        self.assertNotIn(foe, b.battlefield)


if __name__ == "__main__":
    unittest.main()
