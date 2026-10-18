"""Evasion restrictions and one-shot upkeep draws use normal combat and stack rules."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI, search_blocks
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player, StackItem, can_block
from tests.test_templates import ISLAND, card


class FearHorsemanshipDelayed(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, 'main1'
        self.a.library = [ISLAND] * 20
        self.b.library = [ISLAND] * 20

    def creature(self, who=None, text='', cost='', types='Creature', power=2, toughness=2):
        c = card('Test creature', cost, types, text, power, toughness)
        self.assertFalse(c.unsupported)
        perm = self.game.enter_battlefield(who or self.a, c)
        perm.sick = False
        return perm

    def spell(self, text="Draw a card at the beginning of the next turn's upkeep.", targets=()):
        c = card('Test delay', types='Instant', text=text)
        self.assertFalse(c.unsupported)
        self.a.hand.append(c)
        self.assertTrue(self.game.cast(self.a, c, list(targets)))
        self.game.settle()
        return c

    def upkeep(self, who):
        self.game.turn += 1
        self.game.active_idx = self.game.players.index(who)
        self.game.step = 'upkeep'
        self.game.begin_upkeep(who)
        self.game.settle()

    def test_fear_allows_black_and_artifact_blockers(self):
        a = self.creature(text='Fear')
        for cost, types, legal in [('', 'Creature', False), ('{G}', 'Creature', False),
                                   ('{B}', 'Creature', True), ('{W}{B}', 'Creature', True),
                                   ('', 'Artifact Creature', True), ('{R}', 'Artifact Creature', True)]:
            with self.subTest(cost=cost, types=types):
                b = self.creature(self.b, cost=cost, types=types)
                self.assertEqual(can_block(b, a), legal)

    def test_devoid_black_mana_is_not_black_for_fear(self):
        a = self.creature(text='Fear')
        b = self.creature(self.b, 'Devoid', '{B}')
        self.assertFalse(can_block(b, a))
        artifact = self.creature(self.b, 'Devoid', '{B}', 'Artifact Creature')
        self.assertTrue(can_block(artifact, a))

    def test_fear_does_not_override_flying_or_tapped(self):
        a = self.creature(text='Flying, fear')
        b = self.creature(self.b, cost='{B}')
        self.assertFalse(can_block(b, a))
        b.temp_kw.add('reach')
        self.assertTrue(can_block(b, a))
        b.tapped = True
        self.assertFalse(can_block(b, a))

    def test_fear_ai_and_combat_pass_ineligible_blocker(self):
        a = self.creature(text='Fear')
        b = self.creature(self.b, power=5, toughness=5)
        self.assertEqual(search_blocks([a], [b], self.a, self.b), {})
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 18)

    def test_horsemanship_requires_horsemanship_not_flying_or_reach(self):
        a = self.creature(text='Horsemanship')
        for text, legal in [('', False), ('Flying', False), ('Reach', False), ('Horsemanship', True)]:
            with self.subTest(text=text):
                b = self.creature(self.b, text)
                self.assertEqual(can_block(b, a), legal)

    def test_horsemanship_blocker_can_block_ground_but_not_flying(self):
        b = self.creature(self.b, 'Horsemanship')
        a = self.creature()
        self.assertTrue(can_block(b, a))
        a.temp_kw.add('flying')
        self.assertFalse(can_block(b, a))

    def test_flying_horsemanship_requires_both_permissions(self):
        a = self.creature(text='Flying, horsemanship')
        b = self.creature(self.b, 'Horsemanship')
        self.assertFalse(can_block(b, a))
        b.temp_kw.add('reach')
        self.assertTrue(can_block(b, a))

    def test_granted_horsemanship_and_fear_update_legality(self):
        a, b = self.creature(), self.creature(self.b)
        a.temp_kw.add('horsemanship')
        self.assertFalse(can_block(b, a))
        b.temp_kw.add('horsemanship')
        self.assertTrue(can_block(b, a))
        a.temp_kw.add('fear')
        self.assertFalse(can_block(b, a))

    def test_horsemanship_ai_and_combat(self):
        a = self.creature(text='Horsemanship')
        b = self.creature(self.b, 'Flying', power=5, toughness=5)
        self.assertEqual(search_blocks([a], [b], self.a, self.b), {})
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 18)

    def test_next_turns_upkeep_draws_for_original_controller_once(self):
        self.spell()
        self.assertEqual(len(self.a.hand), 0)
        self.upkeep(self.b)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 0))
        self.upkeep(self.a)
        self.assertEqual(len(self.a.hand), 1)

    def test_your_next_upkeep_waits_through_opponents_upkeep(self):
        self.spell('Draw two cards at the beginning of your next upkeep.')
        self.upkeep(self.b)
        self.assertEqual(self.a.hand, [])
        self.upkeep(self.a)
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(self.game.delayed_upkeep, [])

    def test_delay_created_during_upkeep_waits_for_following_upkeep(self):
        self.upkeep(self.a)
        self.spell()
        self.game.settle()
        self.assertEqual(self.a.hand, [])
        self.upkeep(self.b)
        self.assertEqual(len(self.a.hand), 1)

    def test_pending_draw_uses_stack_and_can_be_removed(self):
        self.spell()
        self.game.begin_upkeep(self.b)
        self.assertEqual(self.a.hand, [])
        self.assertTrue(self.game.flush_triggers())
        trigger = self.game.stack.pop()  # a countered ability does not return next upkeep
        self.assertEqual((trigger.kind, trigger.controller), ('trigger', self.a))
        self.upkeep(self.a)
        self.assertEqual(self.a.hand, [])

    def test_separate_delayed_draws_stay_separate(self):
        self.spell()
        self.spell('Draw two cards at the beginning of the next turn\'s upkeep.')
        self.game.begin_upkeep(self.b)
        self.game.flush_triggers()
        self.assertEqual(len(self.game.stack), 2)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 3)

    def test_source_can_leave_before_upkeep(self):
        source = self.creature(text="When this creature enters, draw a card at the beginning of the next turn's upkeep.")
        self.game.settle()
        self.game.leave_battlefield(source, 'graveyard')
        self.upkeep(self.b)
        self.assertEqual(len(self.a.hand), 1)

    def test_controller_change_does_not_move_delayed_draw(self):
        source = self.creature()
        item = StackItem(self.a, [], [], source=source)
        self.game.resolve(self.a, Effect('draw_delayed', 1, data={'upkeep': 'any'}), None, item)
        self.a.battlefield.remove(source)
        self.b.battlefield.append(source)
        source.controller = self.b
        self.upkeep(self.b)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 0))

    def test_fizzled_spell_does_not_schedule_draw(self):
        victim = self.creature(self.b)
        with patch.object(self.game, 'settle'):
            self.spell("Destroy target creature. Draw a card at the beginning of the next turn's upkeep.", [victim])
        self.game.leave_battlefield(victim, 'hand')
        self.game.settle()
        self.assertEqual(self.game.delayed_upkeep, [])

    def test_countered_spell_does_not_schedule_draw(self):
        with patch.object(self.game, 'settle'):
            self.spell()
        self.game.stack.pop()
        self.upkeep(self.b)
        self.assertEqual(self.a.hand, [])

    def test_draw_from_empty_library_loses_at_upkeep(self):
        self.spell()
        self.a.library = []
        self.upkeep(self.b)
        self.assertTrue(self.a.lost)

    def test_full_turn_fires_delay_before_normal_draw_step(self):
        self.spell()
        with patch.object(self.game, 'main_phase'), patch.object(self.game, 'combat'):
            self.game.active_idx = 1
            self.game.turn += 1
            self.game.take_turn(self.b)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 1))

    def test_unimplemented_delayed_actions_stay_visible(self):
        c = card('Other delay', types='Instant', text='Draw a card at the beginning of the next end step.')
        self.assertTrue(c.unsupported)
