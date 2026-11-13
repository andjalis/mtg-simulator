"""#377: a mandatory targeted -N/-N trigger targets a legal creature even when the debuff kills nothing (as #295/#301
did for damage)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
LEECH = card("Test Leech", "{2}{B}", "Creature — Leech",
             "When this creature enters, target creature an opponent controls gets -2/-2 until end of turn. "
             "Remove all counters from that creature.", 1, 1)
SHADE = card("Test Shade", "{2}{B}", "Creature — Shade",
             "When this creature enters, target creature gets -2/-2 until end of turn.", 2, 2)
MAYBE = card("Test Maybe", "{2}{B}", "Creature — Shade",
             "When this creature enters, you may have target creature get -2/-2 until end of turn.", 2, 2)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [SWAMP] * 10
    for _ in range(4):
        g.enter_battlefield(a, SWAMP).sick = False
    g.settle()
    return g, a, b


class MandatoryDebuff(unittest.TestCase):
    def test_hits_a_survivor(self):
        g, a, b = game()
        foe = g.enter_battlefield(b, card("Foe", "{3}", "Creature — Ogre", "", 2, 2))
        foe.counters["+1/+1"] = 3
        g.settle()
        a.hand.append(LEECH)
        g.cast(a, LEECH)
        g.settle()
        self.assertNotIn(foe, b.battlefield)       # counters gone, then a 2/2 with -2/-2

    def test_only_my_creatures_means_mine(self):
        g, a, b = game()
        mine = g.enter_battlefield(a, card("Mine", "{3}", "Creature — Ogre", "", 5, 5))
        g.settle()
        a.hand.append(SHADE)
        g.cast(a, SHADE)
        g.settle()
        shade = next(x for x in a.battlefield if x.card.name == "Test Shade")
        hit = [x for x in (mine, shade) if x.toughness < x.card.toughness]
        self.assertEqual(len(hit), 1)                 # one of my creatures took it: the trigger is mandatory

    def test_prefers_the_opponents_creature(self):
        g, a, b = game()
        mine = g.enter_battlefield(a, card("Mine", "{3}", "Creature — Ogre", "", 5, 5))
        foe = g.enter_battlefield(b, card("Foe", "{3}", "Creature — Ogre", "", 5, 5))
        g.settle()
        a.hand.append(SHADE)
        g.cast(a, SHADE)
        g.settle()
        self.assertEqual((foe.power, mine.power), (3, 5))

    def test_you_may_is_still_a_choice(self):
        g, a, b = game()
        mine = g.enter_battlefield(a, card("Mine", "{3}", "Creature — Ogre", "", 5, 5))
        g.settle()
        a.hand.append(MAYBE)
        g.cast(a, MAYBE)
        g.settle()
        self.assertEqual(mine.power, 5)


if __name__ == "__main__":
    unittest.main()
