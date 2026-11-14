"""#345 slice: the Clockwork creatures. "At end of combat, if ~ attacked or blocked this combat, remove a +1/+0 counter
from it" and "{X}, {T}: Put up to X +1/+0 counters on ~. This ability can't cause the total number of +1/+0 counters on ~
to be greater than four. Activate only during your upkeep." """
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import card

WASTE = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
STEED = card("Test Steed", "{4}", "Artifact Creature — Horse",
             "This creature enters with four +1/+0 counters on it.\n"
             "At end of combat, if this creature attacked or blocked this combat, remove a +1/+0 counter from it.\n"
             "{X}, {T}: Put up to X +1/+0 counters on this creature. This ability can't cause the total number of "
             "+1/+0 counters on this creature to be greater than four. Activate only during your upkeep.", 0, 3)
BEAR = card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2)


def game(ai_a=None, ai_b=None):
    a, b = Player("a", [], ai_a or Scripted()), Player("b", [], ai_b or Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [WASTE] * 10
    for _ in range(5):
        g.enter_battlefield(a, WASTE).sick = False
    g.settle()
    return g, a, b


def steed(g, p):
    x = g.enter_battlefield(p, STEED)
    x.sick = False
    g.settle()
    return x


class Parse(unittest.TestCase):
    def test_full(self):
        from mtgsim.coverage import card_coverage
        self.assertEqual(card_coverage(STEED).ignored, [])
        self.assertEqual(STEED.activated[0].effects[0].data["cap"], 4)

    def test_cap_must_name_the_same_counter(self):
        _, bad = _parse_effects("Put up to X +1/+0 counters on ~. This ability can't cause the total number of "
                                "+1/+1 counters on ~ to be greater than four.")
        self.assertTrue(bad)


class EndOfCombat(unittest.TestCase):
    def test_enters_with_four(self):
        g, a, b = game()
        s = steed(g, a)
        self.assertEqual(s.power, 4)

    def test_attacking_costs_a_counter(self):
        g, a, b = game()
        s = steed(g, a)
        a.ai.attack = [s]
        g.combat(a, b)
        g.settle()
        self.assertEqual(s.counters["+1/+0"], 3)

    def test_blocking_costs_a_counter_too(self):
        g, a, b = game()
        s = steed(g, a)
        bear = g.enter_battlefield(b, BEAR)
        bear.sick = False
        g.settle()
        b.ai.attack = [bear]
        a.ai.block = {bear: [s]}
        g.combat(b, a)
        g.settle()
        self.assertEqual(s.counters["+1/+0"], 3)

    def test_staying_home_costs_nothing(self):
        g, a, b = game()
        s = steed(g, a)
        bear = g.enter_battlefield(b, BEAR)
        bear.sick = False
        g.settle()
        b.ai.attack = [bear]
        g.combat(b, a)
        g.settle()
        self.assertEqual(s.counters["+1/+0"], 4)

    def test_same_condition_on_another_card(self):
        guard = card("Test Guard", "{3}{W}", "Creature — Human Soldier",
                     "At end of combat, if this creature attacked or blocked this combat, put a -0/-1 counter on this "
                     "creature and create a 0/1 white Deserter creature token.", 1, 6)       # Kjeldoran Home Guard
        g, a, b = game()
        x = g.enter_battlefield(a, guard)
        x.sick = False
        g.settle()
        a.ai.attack = [x]
        g.combat(a, b)
        g.settle()
        self.assertEqual(x.toughness, 5)
        self.assertTrue(any(y.card.name.startswith("Deserter") for y in a.battlefield))


class Recharge(unittest.TestCase):
    def test_only_in_my_upkeep_and_never_past_four(self):
        g, a, b = game()
        s = steed(g, a)
        s.counters["+1/+0"] = 1
        self.assertFalse(g.can_activate(a, s, 0))           # main phase
        g.step = "upkeep"
        self.assertTrue(g.activate_ability(a, s, 0, x=5))
        g.settle()
        self.assertEqual(s.counters["+1/+0"], 4)
        self.assertTrue(s.tapped)

    def test_ai_recharges_a_spent_one_in_its_upkeep(self):
        g, a, b = game(HeuristicAI())
        s = steed(g, a)
        s.counters["+1/+0"] = 1
        lands = [x for x in a.battlefield if x.card.name == "Mountain"]
        g.step = "upkeep"
        g.begin_upkeep(a)
        g.settle()
        self.assertEqual(s.counters["+1/+0"], 4)
        self.assertEqual(sum(x.tapped for x in lands), 3)     # paid X = 3, not all five lands

    def test_ai_keeps_a_nearly_full_one_ready(self):
        g, a, b = game(HeuristicAI())
        s = steed(g, a)
        s.counters["+1/+0"] = 3
        g.step = "upkeep"
        g.begin_upkeep(a)
        g.settle()
        self.assertFalse(s.tapped)


if __name__ == "__main__":
    unittest.main()
