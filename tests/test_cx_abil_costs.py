"""Activated-ability cost parts: {Q}, quest-counter sacrifice, counters off a creature, exile the top (cx_abil_costs)."""
import random
import unittest

from mtgsim import cx_abil_costs as C
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

QUEST = card("Test Quest", "{G}", "Enchantment",
             "Remove three quest counters from this enchantment and sacrifice it: Draw two cards.")
HARVEST = card("Test Harvest", "{1}", "Artifact",
               "{1}, Remove a +1/+1 counter from a creature you control: You gain 3 life.")
SLOGGER = card("Test Slogger", "{R}", "Creature — Elemental",
               "{R}, Exile the top two cards of your library: You gain 2 life.", 1, 1)
RAVENER = card("Test Ravener", "{B}", "Creature — Zombie",
               "Exile the top creature card of your graveyard: You gain 2 life.", 1, 1)
UNTAPPER = card("Test Untapper", "{1}", "Creature — Soldier", "{Q}: You gain 1 life.", 1, 1)


class CostParse(unittest.TestCase):
    def parts(self, text):
        extra = {}
        self.assertTrue(C.parse_part(text, extra), text)
        return extra["cx_costs"]

    def test_wordings(self):
        self.assertEqual(self.parts("{Q}")[0][0], "untap_self")
        self.assertEqual(self.parts("Remove three quest counters from ~ and sacrifice it")[0][:2], ("remove_sac", 3))
        self.assertEqual(self.parts("Exile the top ten cards of your library")[0][:2], ("exile_top_library", 10))
        self.assertEqual(self.parts("Exile the top creature card of your graveyard")[0][2], {"type": "creature"})
        self.assertFalse(C.parse_part("Remove zero quest counters from ~ and sacrifice it", {}))


class CostPay(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10
        self.land = self.game.enter_battlefield(self.a, card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)"))
        self.land.sick = False

    def test_parse(self):
        for c in (QUEST, HARVEST, SLOGGER, RAVENER, UNTAPPER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_quest(self):
        q = self.game.enter_battlefield(self.a, QUEST)
        q.counters["quest"] = 2
        self.assertFalse(self.game.can_activate(self.a, q, 0))
        q.counters["quest"] = 3
        hand = len(self.a.hand)
        self.assertTrue(self.game.activate_ability(self.a, q, 0))
        self.game.settle()
        self.assertNotIn(q, self.a.battlefield)
        self.assertEqual(len(self.a.hand), hand + 2)

    def test_counter_off_creature(self):
        h = self.game.enter_battlefield(self.a, HARVEST)
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.assertFalse(self.game.can_activate(self.a, h, 0))
        bear.counters["+1/+1"] = 1
        self.assertTrue(self.game.activate_ability(self.a, h, 0))
        self.game.settle()
        self.assertEqual(bear.counters["+1/+1"], 0)
        self.assertEqual(self.a.life, 23)

    def test_exile_top_library(self):
        s = self.game.enter_battlefield(self.a, SLOGGER)
        self.assertTrue(self.game.activate_ability(self.a, s, 0))
        self.game.settle()
        self.assertEqual((len(self.a.library), len(self.a.exile)), (8, 2))
        self.assertEqual(self.a.life, 22)

    def test_exile_top_graveyard_creature(self):
        r = self.game.enter_battlefield(self.a, RAVENER)
        self.a.graveyard = [ISLAND]
        self.assertFalse(self.game.can_activate(self.a, r, 0))
        self.a.graveyard = [BEAR, ISLAND]
        self.assertTrue(self.game.activate_ability(self.a, r, 0))
        self.game.settle()
        self.assertEqual(self.a.graveyard, [ISLAND])
        self.assertEqual(self.a.exile, [BEAR])

    def test_untap_symbol(self):
        u = self.game.enter_battlefield(self.a, UNTAPPER)
        u.sick = False
        self.assertFalse(self.game.can_activate(self.a, u, 0))
        u.tapped = True
        u.sick = True                       # {Q} is blocked by summoning sickness like {T} (CR 302.6)
        self.assertFalse(self.game.can_activate(self.a, u, 0))
        u.sick = False
        self.assertTrue(self.game.activate_ability(self.a, u, 0))
        self.game.settle()
        self.assertFalse(u.tapped)
        self.assertEqual(self.a.life, 21)


class CostsAI(unittest.TestCase):
    """HeuristicAI activates abilities with the new cost parts, but doesn't pay with its good permanents."""

    def setUp(self):
        from mtgsim.ai import HeuristicAI
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main2"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 30

    def activate_pass(self):
        from mtgsim.engine.policy import choose_ability
        ability = choose_ability(self.game, self.a, instant=False)
        return ability is not None and self.game.do_action(self.a, ability)

    def test_sacrifice_two_elves(self):
        rite = card("Test Rite", "{1}", "Artifact", "Sacrifice two Elves: You gain 3 life.")
        self.game.enter_battlefield(self.a, rite)
        cheap = card("Test Elf", "{0}", "Creature — Elf", "", 1, 1)
        for _ in range(2):
            self.game.enter_battlefield(self.a, cheap)
        self.assertTrue(self.activate_pass())
        self.game.settle()
        self.assertEqual((self.a.life, len(self.a.creatures)), (23, 0))

    def test_ai_keeps_good_elves(self):
        rite = card("Test Rite", "{1}", "Artifact", "Sacrifice two Elves: You gain 3 life.")
        self.game.enter_battlefield(self.a, rite)
        big = card("Test Elf", "{4}", "Creature — Elf", "", 5, 5)
        for _ in range(2):
            self.game.enter_battlefield(self.a, big)
        self.assertFalse(self.activate_pass())
        self.assertEqual(len(self.a.creatures), 2)


if __name__ == "__main__":
    unittest.main()
