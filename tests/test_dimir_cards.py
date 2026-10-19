"""Dimir Midrange cards: Wan Shi Tong (X counters, half-X draw, search trigger)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import ISLAND, card

WAN = card("Test Librarian", "{X}{X}{U}", "Legendary Creature — Spirit", "Flash\nFlying, vigilance\n"
           "When ~ enters, put X +1/+1 counters on him. Then draw half X cards, rounded down.\n"
           "Whenever an opponent searches their library, put a +1/+1 counter on ~ and draw a card.", 1, 1)
FETCH = card("Test Fetch", "{1}", "Sorcery", "Search your library for a basic land card, reveal it, put it into your hand, then shuffle.")


class Dimir(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 20, HeuristicAI())
        self.b = Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library.extend([ISLAND] * 10)

    def test_templates(self):
        self.assertEqual(WAN.unsupported, [])
        self.assertEqual(FETCH.unsupported, [])

    def test_x_counters_and_half_draw(self):
        perm = self.game.enter_battlefield(self.a, WAN, x=5)
        before = len(self.a.hand)
        self.game.settle()
        self.assertEqual(perm.p1, 5)
        self.assertEqual(len(self.a.hand) - before, 2)

    def test_search_trigger(self):
        perm = self.game.enter_battlefield(self.a, WAN, x=0)
        self.game.stack.clear()
        n = len(self.a.hand)
        self.game.library_searched(self.b)
        self.game.settle()
        self.assertEqual(perm.p1, 1)
        self.assertEqual(len(self.a.hand), n + 1)


TIDE = card("Test Tidebinder", "{2}{U}", "Creature — Merfolk Wizard", "Flash\nWhen ~ enters, counter up to one target activated or triggered "
            "ability. If an ability of an artifact, creature, or planeswalker is countered this way, that permanent loses all "
            "abilities for as long as ~ remains on the battlefield.", 3, 2)
PINGER = card("Test Pinger", "{2}", "Creature — Human", "Flying\n{T}: Draw a card.", 1, 1)


class Tidebinder(Dimir):
    def test_template(self):
        self.assertEqual(TIDE.unsupported, [])

    def test_counters_ability_and_silences_source(self):
        pinger = Permanent(PINGER, self.b)
        pinger.sick = False
        self.b.battlefield.append(pinger)
        self.assertTrue(pinger.has("flying"))
        self.assertTrue(self.game.can_activate(self.b, pinger, 0))
        self.game._priority_depth += 1      # keep the ability on the stack
        self.game.activate(self.b, pinger, "ability:0")
        self.game._priority_depth -= 1
        self.assertTrue(any(i.kind == "ability" for i in self.game.stack))
        tide = self.game.enter_battlefield(self.a, TIDE)
        self.game.flush_triggers()
        self.game.resolve_top()
        self.assertFalse([i for i in self.game.stack if i.kind == "ability"])
        self.assertFalse(pinger.has("flying"))
        self.assertFalse(self.game.can_activate(self.b, pinger, 0))
        self.game.leave_battlefield(tide, "graveyard")
        self.assertTrue(pinger.has("flying"))
