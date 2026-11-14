"""Legerdemain: "another target permanent that shares one of those types with it" is checked against the first
target when the pair is chosen; a pair that shares no type is not a legal choice (it used to be accepted and then
did nothing)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

LEGERDEMAIN = card("Test Legerdemain", "{2}{U}{U}", "Sorcery",
                   "Exchange control of target artifact or creature and another target permanent that shares one of "
                   "those types with it.")


def game(ai=None):
    a, b = Player("a", [], ai or HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    for _ in range(4):
        g.enter_battlefield(a, ISLAND).sick = False
    weak = g.enter_battlefield(a, card("Weak", "{1}", "Creature — Human", "", 1, 1))
    rock = g.enter_battlefield(b, card("Rock", "{2}", "Artifact", "{T}: Add {C}."))
    giant = g.enter_battlefield(b, card("Giant", "{5}", "Creature — Giant", "", 6, 6))
    g.settle()
    return g, a, b, weak, rock, giant


class PairCheck(unittest.TestCase):
    def test_pair_sharing_no_type_is_refused(self):
        g, a, b, weak, rock, giant = game()
        a.hand.append(LEGERDEMAIN)
        self.assertFalse(g.valid_action_targets(a, LEGERDEMAIN.spell_effects, [weak, rock], LEGERDEMAIN))
        self.assertFalse(g.cast(a, LEGERDEMAIN, targets=[weak, rock]))
        self.assertIn(LEGERDEMAIN, a.hand)

    def test_sharing_pair_exchanges(self):
        g, a, b, weak, rock, giant = game()
        a.hand.append(LEGERDEMAIN)
        self.assertTrue(g.cast(a, LEGERDEMAIN, targets=[weak, giant]))
        g.settle()
        self.assertIs(giant.controller, a)
        self.assertIs(weak.controller, b)

    def test_ai_takes_the_giant(self):
        g, a, b, weak, rock, giant = game()
        a.hand.append(LEGERDEMAIN)
        g.main_phase(a)
        g.settle()
        self.assertIs(giant.controller, a)


if __name__ == "__main__":
    unittest.main()
