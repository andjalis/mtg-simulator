"""Proliferate chooses objects rather than targets and adds every existing counter type."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, ISLAND, card


class Proliferate(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, who=None, counters=None, c=BEAR):
        perm = self.game.enter_battlefield(who or self.a, c)
        perm.counters.update(counters or {})
        return perm

    def cast(self, text="Proliferate."):
        spell = card("Test Proliferation", types="Sorcery", text=text)
        self.assertEqual(spell.unsupported, [])
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()

    def test_every_counter_type_increases_once_without_creating_types(self):
        perm = self.perm(counters={"+1/+1": 3, "charge": 4, "stun": 2, "unknown": 1, "empty": 0})
        self.game.proliferate(self.a, [perm])
        self.assertEqual(perm.counters, {"+1/+1": 4, "charge": 5, "stun": 3, "unknown": 2, "empty": 0})

    def test_no_counters_means_no_new_counters(self):
        perm = self.perm()
        self.game.proliferate(self.a, [perm, self.a])
        self.assertEqual(perm.counters, {})
        self.assertEqual(self.a.counters, {})

    def test_default_policy_chooses_friendly_growth_and_hostile_stun(self):
        mine = self.perm(counters={"+1/+1": 1})
        their_stun = self.perm(self.b, {"stun": 1})
        their_growth = self.perm(self.b, {"+1/+1": 1})
        my_stun = self.perm(counters={"stun": 1})
        self.cast()
        self.assertEqual(mine.p1, 2)
        self.assertEqual(their_stun.counters["stun"], 2)
        self.assertEqual(their_growth.p1, 1)
        self.assertEqual(my_stun.counters["stun"], 1)

    def test_mixed_counters_cannot_be_chosen_individually(self):
        mine = self.perm(counters={"+1/+1": 1, "finality": 1})
        self.cast()
        self.assertEqual(mine.counters, {"+1/+1": 2, "finality": 2})

    def test_manual_selection_handles_any_counter_and_ignores_duplicates_and_stale_objects(self):
        theirs = self.perm(self.b, {"unusual": 3})
        stale = Permanent(BEAR, self.b)
        stale.counters["charge"] = 1
        self.game.proliferate(self.a, [theirs, theirs, stale, object()])
        self.assertEqual(theirs.counters["unusual"], 4)
        self.assertEqual(stale.counters["charge"], 1)

    def test_custom_policy_can_choose_none(self):
        mine = self.perm(counters={"+1/+1": 1})
        with patch.object(self.a.ai, "choose_proliferate", create=True, return_value=[]):
            self.cast()
        self.assertEqual(mine.p1, 1)

    def test_player_counters_include_all_existing_kinds(self):
        self.a.counters = {"energy": 3, "experience": 1, "poison": 2}
        self.game.proliferate(self.a, [self.a])
        self.assertEqual(self.a.counters, {"energy": 4, "experience": 2, "poison": 3})
        self.assertEqual(self.b.counters, {})

    def test_ten_poison_counters_loses_without_life_loss(self):
        self.b.counters["poison"] = 9
        self.cast()
        self.assertEqual(self.b.counters["poison"], 10)
        self.assertTrue(self.b.lost)
        self.assertEqual(self.b.life, 20)

    def test_untargeted_effect_ignores_hexproof_and_ward(self):
        c = card("Test Warded Relic", types="Artifact", text="Hexproof\nWard {5}")
        theirs = self.perm(self.b, {"stun": 1}, c)
        self.cast()
        self.assertEqual(theirs.counters["stun"], 2)
        self.assertFalse(self.game.stack)

    def test_saga_lore_triggers_new_chapters_and_final_sacrifice(self):
        c = card("Test Saga", types="Enchantment — Saga", text="I — You gain 1 life.\nII — You gain 2 life.\nIII — You gain 3 life.")
        saga = self.perm(c=c)
        self.game.settle()
        self.assertEqual(self.a.life, 21)
        self.cast()
        self.assertEqual(self.a.life, 23)
        self.assertEqual(saga.counters["lore"], 2)
        self.cast()
        self.assertEqual(self.a.life, 26)
        self.assertNotIn(saga, self.a.battlefield)

    def test_changes_are_simultaneous_before_lore_triggers_queue(self):
        c = card("Test Saga", types="Enchantment — Saga", text="I — You gain 1 life.\nII — You gain 2 life.")
        saga = self.perm(c=c)
        self.game.settle()
        other = self.perm(counters={"charge": 1})
        original = self.game.lore_triggers
        def observe(perm, old, new):
            self.assertEqual(other.counters["charge"], 2)
            return original(perm, old, new)
        with patch.object(self.game, "lore_triggers", side_effect=observe) as triggered:
            self.game.proliferate(self.a, [saga, other])
            triggered.assert_called_once_with(saga, 1, 2)

    def test_loyalty_and_keyword_counters(self):
        pw = self.perm(c=dataclasses.replace(card("Test Walker", types="Planeswalker — Test"), loyalty=3))
        creature = self.perm()
        self.cast("Put a flying counter on target creature.")
        self.assertTrue(creature.has("flying"))
        self.game.proliferate(self.a, [pw, creature])
        self.assertEqual(pw.loyalty, 4)
        self.assertEqual(creature.counters["flying"], 2)
        creature.counters.pop("flying")
        self.assertFalse(creature.has("flying"))

    def test_twice_and_proliferate_triggers_even_with_no_chosen_objects(self):
        watcher = card("Test Watcher", types="Enchantment", text="Whenever you proliferate, you gain 1 life.")
        self.assertEqual(watcher.unsupported, [])
        self.perm(c=watcher)
        self.cast("Proliferate twice.")
        self.assertEqual(self.a.life, 22)

    def test_opposing_power_counters_cancel_after_proliferation(self):
        perm = self.perm(counters={"+1/+1": 3, "-1/-1": 1})
        self.game.proliferate(self.a, [perm])
        self.assertEqual((perm.p1, perm.m1), (4, 2))
        self.game.state_based_actions()
        self.assertEqual((perm.p1, perm.m1), (2, 0))

    def test_ai_values_and_casts_useful_proliferation(self):
        mine = self.perm(counters={"+1/+1": 1})
        spell = card("Test Growth", types="Sorcery", text="Proliferate.")
        self.a.hand.append(spell)
        plan = self.a.ai.plan_spell(self.game, self.a, spell)
        self.assertIsNotNone(plan)
        self.assertGreater(plan[0], 0)
        self.assertTrue(self.game.cast(self.a, spell, plan[1]))
        self.game.settle()
        self.assertEqual(mine.p1, 2)


if __name__ == "__main__":
    unittest.main()
