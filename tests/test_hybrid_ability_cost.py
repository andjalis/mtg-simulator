"""#418: hybrid mana in an activated ability's cost can be paid with either colour (it collapsed to the first one)."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, MOUNTAIN, card

LIEGE = card("Test Liege", "{3}{U/R}{U/R}{U/R}", "Creature — Horror",
             "{U/R}{U/R}: This creature gets +1/+0 until end of turn.", 2, 2)


def game(lands):
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    for land in lands:
        g.enter_battlefield(a, land).sick = False
    liege = g.enter_battlefield(a, LIEGE)
    liege.sick = False
    g.settle()
    return g, a, liege


class HybridAbilityCost(unittest.TestCase):
    def test_either_colour_or_a_mix(self):
        for lands in ([MOUNTAIN, MOUNTAIN], [ISLAND, ISLAND], [ISLAND, MOUNTAIN]):
            g, a, liege = game(lands)
            self.assertTrue(g.can_activate(a, liege, 0), [x.name for x in lands])
            self.assertTrue(g.activate_ability(a, liege, 0))
            g.settle()
            self.assertEqual(liege.power, 3)

    def test_still_needs_the_colours(self):
        swamp = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
        g2, a2, liege2 = game([swamp, swamp])
        self.assertFalse(g2.can_activate(a2, liege2, 0))


if __name__ == "__main__":
    unittest.main()
