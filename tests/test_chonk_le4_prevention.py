"""le-chonk-4 foundation: source-side damage prevention and the prevention event amount.

"Prevent all damage that would be dealt by enchanted creature" (Defang) is an ``aura_flags``
entry on the *source*; deal_damage consults it before the target's shields. The turn-scoped
"damage can't be prevented this turn" flag (Skullcrack) disables every prevention path.
Whenever prevention actually reduces damage, deal_damage sets ``event_amount`` to the
prevented total and fires "damage_prevented" (context: the source) to whoever held the
shield, so "If damage is prevented this way, ... that much ..." riders (Acolyte's Reward)
can be written as trigger templates on that event.
"""
import random
import unittest

from mtgsim import auras
from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect, Trigger
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, card


DEFANG = card("Test Defang", "{1}{W}", "Enchantment — Aura",
              "Enchant creature\nPrevent all damage that would be dealt by enchanted creature.")


class PreventionTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def prevented_events(self):
        return [e for e in self.game.rule_events.history if e.kind == "damage_prevented"]

    def test_aura_prevents_all_damage_from_the_source(self):
        from dataclasses import replace
        defang = replace(DEFANG, aura_flags=frozenset({"prevent_source_damage"}))
        attacker = self.perm(BEAR, self.b)
        aura = self.perm(defang, self.a)
        auras.attach(self.game, aura, attacker)
        self.game.deal_damage(self.a, 2, by=self.b, cause="test", source=attacker, combat=True)
        self.assertEqual(self.a.life, 20)
        self.assertEqual([(e.player, e.context, e.amount) for e in self.prevented_events()],
                         [(self.a, attacker, 2)])

    def test_partial_shield_prevents_then_damage_continues(self):
        blocker = self.perm(BEAR, self.a)
        blocker.prevent_next = 1
        attacker = self.perm(BEAR, self.b)
        self.game.deal_damage(blocker, 3, by=self.b, cause="test", source=attacker, combat=True)
        self.assertEqual(blocker.damage, 2)
        self.assertEqual(blocker.prevent_next, 0)
        self.assertEqual([(e.player, e.context, e.amount) for e in self.prevented_events()],
                         [(self.a, attacker, 1)])

    def test_no_prevention_turn_disables_shields(self):
        self.a.prevent_next = 5
        self.game.no_prevention_turn = True
        attacker = self.perm(BEAR, self.b)
        self.game.deal_damage(self.a, 2, by=self.b, cause="test", source=attacker, combat=True)
        self.assertEqual(self.a.life, 18)
        self.assertEqual(self.a.prevent_next, 5)      # the shield never applied
        self.assertEqual(self.prevented_events(), [])

    def test_no_prevention_turn_disables_source_side_prevention(self):
        from dataclasses import replace
        defang = replace(DEFANG, aura_flags=frozenset({"prevent_source_damage"}))
        attacker = self.perm(BEAR, self.b)
        aura = self.perm(defang, self.a)
        auras.attach(self.game, aura, attacker)
        self.game.no_prevention_turn = True
        self.game.deal_damage(self.a, 2, by=self.b, cause="test", source=attacker, combat=True)
        self.assertEqual(self.a.life, 18)

    def test_prevented_amount_feeds_a_that_much_rider(self):
        watcher = card("Test Reward", "{1}{W}", "Creature — Human",
                       "Whenever damage is prevented, you gain that much life.", 1, 1)
        from dataclasses import replace
        watcher = replace(watcher, triggers=(Trigger(
            "damage_prevented", [Effect("gain_life", 0, data={"that_much": True})]),))
        perm = Permanent(watcher, self.a)
        perm.sick = perm.tapped = False
        self.a.battlefield.append(perm)
        self.a.prevent_next = 5
        attacker = self.perm(BEAR, self.b)
        self.game.deal_damage(self.a, 3, by=self.b, cause="test", source=attacker, combat=True)
        self.game.settle()
        self.assertEqual(self.a.life, 20 + 3)
