"""le-chonk-4 foundation: turn-scoped "can't gain life" and gain-life rules events.

Skullcrack-family riders ("players can't gain life this turn", "damage can't be prevented
this turn") need a turn-scoped flag consulted by ``Game.change_life`` / ``Game.deal_damage``,
distinct from the existing permanent statics (batch1_templates.no_lifegain). This file pins
the flag, its cleanup expiry, and the two gain-life events: "gain_life" for the gaining
player's own triggers and "opp_gain_life" (context: the gaining player) for the other
player's "whenever an opponent gains life" cluster (Punishing Fire, mega-chonk-2's
template). The rules events carry the amount for evidence and listeners.
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect, Trigger
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, card


class NoLifegainTurnTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_flag_blocks_only_the_named_players(self):
        self.game.no_lifegain_turn = {self.a}
        self.game.change_life(self.a, 3, "test")
        self.game.change_life(self.b, 2, "test")
        self.assertEqual(self.a.life, 20)
        self.assertEqual(self.b.life, 22)

    def test_flag_beats_lifelink_path(self):
        self.game.no_lifegain_turn = {self.a, self.b}
        bear = Permanent(BEAR, self.a)
        bear.sick = bear.tapped = False
        self.a.battlefield.append(bear)
        bear.temp_kw.add("lifelink")
        self.game.deal_damage(self.b, 2, by=self.a, cause="combat damage", source=bear, combat=True)
        self.assertEqual(self.b.life, 18)
        self.assertEqual(self.a.life, 20)     # the lifelink gain is suppressed this turn

    def test_gain_life_rules_events_carry_the_amount(self):
        self.game.change_life(self.b, 3, "test")
        gains = [e for e in self.game.rule_events.history if e.kind == "gain_life"]
        opps = [e for e in self.game.rule_events.history if e.kind == "opp_gain_life"]
        self.assertEqual([(e.player, e.amount) for e in gains], [(self.b, 3)])
        self.assertEqual([(e.player, e.context, e.amount) for e in opps], [(self.a, self.b, 3)])

    def test_blocked_gain_fires_no_events(self):
        self.game.no_lifegain_turn = {self.b}
        self.game.change_life(self.b, 3, "test")
        self.assertFalse([e for e in self.game.rule_events.history if e.kind in ("gain_life", "opp_gain_life")])

    def test_opp_gain_life_triggers_on_the_other_player(self):
        watcher = card("Test Watcher", "{1}{W}", "Creature — Human",
                       "Whenever an opponent gains life, you gain 2 life.", 1, 1)
        from dataclasses import replace
        watcher = replace(watcher, triggers=(Trigger("opp_gain_life", [Effect("gain_life", 2)]),))
        perm = Permanent(watcher, self.a)
        perm.sick = perm.tapped = False
        self.a.battlefield.append(perm)
        self.game.change_life(self.b, 1, "test")
        self.game.settle()
        self.assertEqual(self.a.life, 22)

    def test_flag_expires_in_cleanup(self):
        self.game.no_lifegain_turn = {self.a, self.b}
        self.game.take_turn(self.game.active)
        self.assertEqual(self.game.no_lifegain_turn, set())
        self.assertFalse(self.game.no_prevention_turn)
        self.game.change_life(self.a, 1, "test")
        self.assertEqual(self.a.life, 21)
