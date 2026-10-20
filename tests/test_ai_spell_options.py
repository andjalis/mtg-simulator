"""Casting-cost alternatives survive AI deduplication without becoming extra spells."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import BaselineAI, HeuristicAI, _spell_options
from mtgsim.cards import AltCost
from mtgsim.engine import Game, GraveyardTarget, Permanent, Player, respond, respond_extras
from tests.invariants import assert_clean
from tests.test_templates import ISLAND, MOUNTAIN, card


class AISpellOptionsTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], BaselineAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, "main2"
        self.a.library = [ISLAND] * 20
        self.b.library = [ISLAND] * 20

    def lands(self, n):
        self.a.battlefield = [Permanent(MOUNTAIN, self.a) for _ in range(n)]

    def flashback(self, native_cheaper=False, copies=1, modal=False, damage=False, sorcery=False):
        cost, native = ("{3}{R}", "{R}") if native_cheaper else ("{R}", "{3}{R}")
        text = ("Test Recall deals 2 damage to any target." if damage else
                "Choose one —\n• Draw a card.\n• You gain 2 life." if modal else "Draw a card.")
        spell = card("Test Recall", cost, "Sorcery" if sorcery else "Instant", text + "\nFlashback " + native)
        self.a.graveyard.extend([spell] * copies)
        for entry in self.a.graveyard.entries:
            self.a.granted_fb.append(GraveyardTarget(self.a, spell, entry))
        return spell

    def test_both_costs_survive_in_both_directions(self):
        for native_cheaper in (False, True):
            with self.subTest(native_cheaper=native_cheaper):
                self.setUp()
                self.flashback(native_cheaper)
                options = _spell_options(self.game, self.a)
                self.assertEqual([sum(c.mana_cost.values()) for c in options], [1, 4])
                self.assertEqual([c.granted_flashback for c in options],
                                 [not native_cheaper, native_cheaper])

    def test_main_phase_and_responses_use_the_only_affordable_cost(self):
        for native_cheaper in (False, True):
            for policy in ("main", "heuristic", "default", "extras"):
                with self.subTest(native_cheaper=native_cheaper, policy=policy):
                    self.setUp()
                    spell = self.flashback(native_cheaper, sorcery=policy == "main")
                    self.lands(1)
                    if policy == "main":
                        action = self.a.ai.choose_spell(self.game, self.a, False)
                    else:
                        self.game.active_idx, self.game.step = 1, "end_step"
                        action = {"heuristic": self.a.ai.respond, "default": respond,
                                  "extras": respond_extras}[policy](self.game, self.a)
                    self.assertIsNotNone(action)
                    self.assertEqual(sum(action[0].mana_cost.values()), 1)
                    self.assertEqual(action[0].granted_flashback, not native_cheaper)
                    self.assertTrue(self.game.do_action(self.a, action))
                    self.assertEqual(list(self.a.exile), [spell])
                    self.assertEqual(list(self.a.graveyard), [])
                    self.assertEqual(len(self.a.hand), 1)

    def test_cheapest_equivalent_cast_when_both_are_affordable(self):
        for native_cheaper in (False, True):
            for policy in ("main", "heuristic", "default", "extras"):
                with self.subTest(native_cheaper=native_cheaper, policy=policy):
                    self.setUp()
                    self.flashback(native_cheaper, sorcery=policy == "main")
                    self.lands(4)
                    if policy == "main":
                        action = self.a.ai.choose_spell(self.game, self.a, False)
                    else:
                        self.game.active_idx, self.game.step = 1, "end_step"
                        action = {"heuristic": self.a.ai.respond, "default": respond,
                                  "extras": respond_extras}[policy](self.game, self.a)
                    self.assertIsNotNone(action)
                    self.assertEqual(sum(action[0].mana_cost.values()), 1)
                    self.assertTrue(self.game.do_action(self.a, action))
                    self.assertEqual(sum(p.tapped for p in self.a.battlefield), 1)

    def test_modal_fallback_uses_cheapest_cost(self):
        for native_cheaper in (False, True):
            with self.subTest(native_cheaper=native_cheaper):
                self.setUp()
                self.flashback(native_cheaper, modal=True)
                self.a.ai.choose_modes = lambda game, me, modes, n, up_to: [0]
                self.lands(4)
                self.game.active_idx, self.game.step = 1, "end_step"
                self.assertIsNone(self.a.ai.respond(self.game, self.a))
                self.assertTrue(self.game.give_priority(self.a))
                self.assertEqual(sum(p.tapped for p in self.a.battlefield), 1)
                self.assertEqual(len(self.a.hand), 1)

    def test_duplicate_copies_refresh_after_cast_and_stale_choices_are_unpaid(self):
        spell = self.flashback(copies=2)
        self.lands(4)
        options = _spell_options(self.game, self.a)
        self.assertEqual(len(options), 2)  # one per cost, rather than one per physical copy
        self.assertTrue(self.game.do_action(self.a, (options[0], None)))
        tapped = sum(p.tapped for p in self.a.battlefield)
        for stale in options:
            self.assertFalse(self.game.can_cast_now(self.a, stale))
            self.assertFalse(self.game.do_action(self.a, (stale, None)))
        self.assertEqual(sum(p.tapped for p in self.a.battlefield), tapped)
        fresh = _spell_options(self.game, self.a)
        self.assertEqual(len(fresh), 2)
        self.assertIsNot(fresh[0].graveyard_target.entry, options[0].graveyard_target.entry)
        self.assertTrue(self.game.do_action(self.a, (fresh[0], None)))
        self.assertEqual(list(self.a.exile), [spell, spell])
        self.assertEqual(_spell_options(self.game, self.a), [])

    def test_leave_and_reenter_invalidates_both_cost_options(self):
        spell = self.flashback()
        stale = _spell_options(self.game, self.a)
        self.a.graveyard.pop()
        self.a.graveyard.append(spell)
        self.lands(4)
        for c in stale:
            self.assertFalse(self.game.do_action(self.a, (c, None)))
        fresh = _spell_options(self.game, self.a)
        self.assertEqual(len(fresh), 1)
        self.assertFalse(fresh[0].granted_flashback)
        self.assertFalse(any(p.tapped for p in self.a.battlefield))

    def test_expired_grant_does_not_hide_native_cast(self):
        self.flashback(native_cheaper=True)
        stale_grant = next(c for c in _spell_options(self.game, self.a) if c.granted_flashback)
        self.a.granted_fb.clear()
        self.lands(4)
        self.assertFalse(self.game.do_action(self.a, (stale_grant, None)))
        fresh = _spell_options(self.game, self.a)
        self.assertEqual(len(fresh), 1)
        self.assertFalse(fresh[0].granted_flashback)
        self.assertTrue(self.game.do_action(self.a, (fresh[0], None)))

    def test_equal_cost_permissions_remain_distinct(self):
        spell = self.flashback()
        spell.alt_costs[0].cost = dict(spell.mana_cost)
        options = _spell_options(self.game, self.a)
        self.assertEqual(len(options), 2)
        self.a.granted_fb.clear()
        self.lands(1)
        native = next(c for c in options if not c.granted_flashback)
        granted = next(c for c in options if c.granted_flashback)
        self.assertFalse(self.game.do_action(self.a, (granted, None)))
        self.assertTrue(self.game.do_action(self.a, (native, None)))

    def test_different_colored_and_life_costs_are_preserved(self):
        spell = card("Test Choices", "{2}{R}", "Sorcery", "Draw a card.")
        spell.alt_costs = [AltCost("flashback", {"R": 1}), AltCost("flashback", {"U": 1}),
                           AltCost("flashback", {"R": 1}, life=2)]
        self.a.graveyard.extend([spell, spell])
        self.assertEqual(len(_spell_options(self.game, self.a)), 3)
        self.a.battlefield = [Permanent(ISLAND, self.a)]
        choice = self.a.ai.choose_spell(self.game, self.a, False)
        self.assertEqual(choice[0].mana_cost, {"U": 1})
        self.assertTrue(self.game.do_action(self.a, choice))
        self.assertEqual(self.a.life, 20)

    def test_planner_does_not_count_two_costs_as_two_spells(self):
        spell = self.flashback()
        other = card("Test Other", "{4}{R}", "Sorcery", "Draw a card.")
        self.a.hand = [other]
        self.lands(5)
        with patch.object(self.a.ai, "plan_spell", side_effect=lambda game, me, c, pre: (
                15 if c is other else 10, None)):
            action = self.a.ai.choose_spell(self.game, self.a, False)
        self.assertIs(action[0], other)  # imaginary double-flashback would score 20
        self.assertIn(spell, self.a.graveyard)

    def test_lethal_setup_uses_the_affordable_flashback_cost(self):
        for native_cheaper in (False, True):
            with self.subTest(native_cheaper=native_cheaper):
                self.setUp()
                spell = self.flashback(native_cheaper, damage=True)
                self.lands(1)
                bear = card("Test Attacker", "{1}{R}", "Creature", "", 2, 2)
                attacker = Permanent(bear, self.a)
                attacker.sick = False
                self.a.battlefield.append(attacker)
                self.b.life = 4
                self.game.step = "main1"
                self.assertTrue(self.a.ai.lethal_setup(self.game, self.a))
                self.assertEqual(self.b.life, 2)
                self.assertEqual(list(self.a.exile), [spell])

    def test_lethal_setup_does_not_double_cast_one_graveyard_entry(self):
        self.flashback(damage=True)
        self.lands(5)
        bear = card("Test Attacker", "{1}{R}", "Creature", "", 2, 2)
        attacker = Permanent(bear, self.a)
        attacker.sick = False
        self.a.battlefield.append(attacker)
        self.b.life = 6
        self.game.step = "main1"
        self.assertFalse(self.a.ai.lethal_setup(self.game, self.a))
        self.assertEqual(self.b.life, 6)
        self.assertEqual(len(self.a.graveyard), 1)
        self.assertFalse(any(p.tapped for p in self.a.battlefield))

    def test_cost_alternatives_share_a_lethal_setup_candidate_slot(self):
        self.flashback(damage=True)
        burst = card("Test Burst", "{1}{R}", "Sorcery", "Test Burst deals 4 damage to any target.")
        self.a.hand = [burst]
        self.lands(5)
        bear = card("Test Attacker", "{1}{R}", "Creature", "", 2, 2)
        attacker = Permanent(bear, self.a)
        attacker.sick = False
        self.a.battlefield.append(attacker)
        self.b.life = 8
        self.game.step = "main1"
        with patch("mtgsim.ai.MAX_SETUP_SPELLS", 2):
            self.assertTrue(self.a.ai.lethal_setup(self.game, self.a))
        self.assertEqual(self.b.life, 2)
        self.assertEqual(self.a.hand, [])
        self.assertEqual(list(self.a.graveyard), [burst])

    def test_bounded_flashback_games_end_in_a_clean_state(self):
        recall = card("Test Recall", "{R}", "Instant", "Test Recall deals 2 damage to any target.\nFlashback {3}{R}")
        deck = [MOUNTAIN] * 16 + [recall] * 12
        for seed in (1, 2):
            a, b = Player("a", list(deck), HeuristicAI()), Player("b", list(deck), BaselineAI())
            g = Game(a, b, random.Random(seed), max_turns=10)
            g.play()
            assert_clean(self, g, f"seed {seed}")


if __name__ == "__main__":
    unittest.main()
