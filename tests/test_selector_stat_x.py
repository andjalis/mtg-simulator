"""#421: "target ... creature ... with power X or less, where X is the number of lands you control" (Invasion of Lorwyn)
compares the power with X at targeting (it compared with 1)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_templates import card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
LORWYN = card("Test Siege", "{4}{B}{G}", "Sorcery",
              "Destroy target non-Elf creature an opponent controls with power X or less, where X is the number of "
              "lands you control.")


def game(lands):
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [FOREST] * 10
    for i in range(lands):
        g.enter_battlefield(a, SWAMP if i == 0 else FOREST).sick = False
    three = g.enter_battlefield(b, card("Three", "{3}", "Creature — Ogre", "", 3, 3))
    five = g.enter_battlefield(b, card("Five", "{5}", "Creature — Giant", "", 5, 5))
    elf = g.enter_battlefield(b, card("Elfy", "{1}", "Creature — Elf", "", 1, 1))
    g.settle()
    return g, a, b, three, five, elf


class SelectorStatX(unittest.TestCase):
    def legal(self, g, a):
        eff = LORWYN.spell_effects[0]
        with g.targeting(StackItem(a, [eff], [None], card=LORWYN)):
            return g.legal_targets(a, eff)

    def test_power_up_to_the_land_count(self):
        g, a, b, three, five, elf = game(4)
        self.assertEqual(self.legal(g, a), [three])
        g, a, b, three, five, elf = game(6)
        self.assertEqual(set(self.legal(g, a)), {three, five})

    def test_ai_kills_the_biggest_legal_one(self):
        g, a, b, three, five, elf = game(6)
        a.hand.append(LORWYN)
        g.main_phase(a)
        g.settle()
        self.assertNotIn(five, b.battlefield)


if __name__ == "__main__":
    unittest.main()
