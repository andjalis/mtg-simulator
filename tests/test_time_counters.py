"""#345 slice: time counters on "target permanent or suspended card" and on "each permanent and each suspended card"
(Fury Charm, Timebender, Shivan Sand-Mage, Timecrafting, Dust of Moments)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import card

MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
REMOVE = card("Test Hasten", "{R}", "Sorcery", "Remove two time counters from target permanent or suspended card.")
PUT = card("Test Delay", "{R}", "Sorcery",
           "Put two time counters on target permanent with a time counter on it or suspended card.")
REMOVE_X = card("Test Craft", "{X}{R}", "Sorcery", "Remove X time counters from target permanent or suspended card.")
DUST = card("Test Dust", "{R}", "Sorcery", "Remove two time counters from each permanent and each suspended card.")
DUST_PUT = card("Test Dust Put", "{R}", "Sorcery",
                "Put two time counters on each permanent with a time counter on it and each suspended card.")
GIANT = card("Test Giant", "{5}{R}", "Creature — Giant", "Suspend 4—{R}", 6, 6)
FADER = card("Test Fader", "{1}{R}", "Creature — Elemental", "Vanishing 3", 3, 3)


def game(ai=None):
    a, b = Player("a", [], ai or Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [MOUNTAIN] * 10
    for _ in range(4):
        g.enter_battlefield(a, MOUNTAIN).sick = False
    g.settle()
    return g, a, b


def suspend(p, c, n):
    p.exile.append(c)
    entry = [c, n]
    p.suspended.append(entry)
    return entry


class Parse(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual([(e.kind, e.target, e.amount, e.data["op"]) for e in REMOVE.spell_effects],
                         [("time_counters", "perm_or_suspended", 2, "remove")])
        self.assertTrue(PUT.spell_effects[0].data["has_time"])
        self.assertTrue(REMOVE_X.spell_effects[0].data["x"])
        self.assertTrue(DUST.spell_effects[0].data["group"])

    def test_near_misses_stay_unmatched(self):
        for text in ("Remove two time counters from target suspended card you don't own.",
                     "Remove two time counters from target permanent or suspended card. Then it explodes loudly."):
            _, bad = _parse_effects(text)
            self.assertTrue(bad, text)


class Play(unittest.TestCase):
    def test_remove_from_a_suspended_card(self):
        g, a, b = game()
        entry = suspend(a, GIANT, 4)
        a.hand.append(REMOVE)
        self.assertTrue(g.cast(a, REMOVE, targets=[GIANT]))
        g.settle()
        self.assertEqual(entry[1], 2)

    def test_removing_the_last_counter_casts_it(self):
        g, a, b = game()
        suspend(a, GIANT, 2)
        a.hand.append(REMOVE)
        self.assertTrue(g.cast(a, REMOVE, targets=[GIANT]))
        g.settle()
        self.assertTrue(any(x.card.name == "Test Giant" for x in a.battlefield))
        self.assertEqual(a.suspended, [])

    def test_put_on_an_opponents_suspended_card(self):
        g, a, b = game()
        entry = suspend(b, GIANT, 1)
        a.hand.append(PUT)
        self.assertTrue(g.cast(a, PUT, targets=[GIANT]))
        g.settle()
        self.assertEqual(entry[1], 3)

    def test_put_needs_a_permanent_with_a_time_counter(self):
        g, a, b = game()
        bear = g.enter_battlefield(b, card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        fader = g.enter_battlefield(a, FADER)
        g.settle()
        legal = g.legal_targets(a, PUT.spell_effects[0])
        self.assertIn(fader, legal)
        self.assertNotIn(bear, legal)
        self.assertIn(bear, g.legal_targets(a, REMOVE.spell_effects[0]))

    def test_vanishing_permanent_losing_its_last_counter_is_sacrificed(self):
        g, a, b = game()
        fader = g.enter_battlefield(a, FADER)
        g.settle()
        fader.counters["time"] = 2
        a.hand.append(REMOVE)
        g.cast(a, REMOVE, targets=[fader])
        g.settle()
        self.assertNotIn(fader, a.battlefield)

    def test_x(self):
        g, a, b = game()
        entry = suspend(a, GIANT, 4)
        a.hand.append(REMOVE_X)
        from mtgsim.engine.state import StackItem
        item = StackItem(a, list(REMOVE_X.spell_effects), [GIANT], card=REMOVE_X)
        item.x = 3
        g.stack.append(item)
        g.settle()
        self.assertEqual(entry[1], 1)

    def test_dust_hits_every_permanent_and_suspended_card(self):
        g, a, b = game()
        mine, theirs = suspend(a, GIANT, 3), suspend(b, card("Other Giant", "{5}{R}", "Creature — Giant",
                                                              "Suspend 5—{R}", 6, 6), 5)
        fader = g.enter_battlefield(b, FADER)
        g.settle()
        a.hand.append(DUST)
        g.cast(a, DUST)
        g.settle()
        self.assertEqual((mine[1], theirs[1], fader.counters["time"]), (1, 3, 1))

    def test_dust_put_skips_permanents_without_time_counters(self):
        g, a, b = game()
        bear = g.enter_battlefield(b, card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        mine = suspend(a, GIANT, 3)
        a.hand.append(DUST_PUT)
        g.cast(a, DUST_PUT)
        g.settle()
        self.assertEqual((mine[1], bear.counters.get("time", 0)), (5, 0))

    def test_a_card_no_longer_suspended_is_not_a_target(self):
        g, a, b = game()
        suspend(a, GIANT, 3)
        a.exile.remove(GIANT)
        self.assertNotIn(GIANT, g.legal_targets(a, REMOVE.spell_effects[0]))


class AI(unittest.TestCase):
    def test_ai_hastens_its_own_suspended_card(self):
        g, a, b = game(HeuristicAI())
        entry = suspend(a, GIANT, 3)
        suspend(b, card("Other Giant", "{5}{R}", "Creature — Giant", "Suspend 5—{R}", 6, 6), 5)
        a.hand.append(REMOVE)
        g.main_phase(a)
        g.settle()
        self.assertEqual(entry[1], 1)

    def test_ai_delays_the_opponents(self):
        g, a, b = game(HeuristicAI())
        theirs = suspend(b, GIANT, 1)
        a.hand.append(PUT)
        g.main_phase(a)
        g.settle()
        self.assertEqual(theirs[1], 3)


if __name__ == "__main__":
    unittest.main()
