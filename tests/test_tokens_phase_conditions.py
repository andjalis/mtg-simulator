"""Decayed timing and bounded phase-trigger conditions, including changed state."""
import random
import unittest

from mtgsim.ai import BaselineAI
from mtgsim.cards import make_token
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, can_block
from tests.test_templates import BEAR, ISLAND, card


class TokensPhaseConditions(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], BaselineAI()), Player('b', [], BaselineAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g._priority_depth = 2, 1

    def real(self, name):
        db = CardDB(offline=True)
        if db._all is None:
            self.skipTest('local card database unavailable')
        try:
            return db.get(name)
        finally:
            db._all.close()

    def drain_stack(self):
        while self.g.pending or self.g.stack:
            self.g.flush_triggers()
            self.g.resolve_top()

    def zombie(self, owner=None):
        source = self.g.enter_battlefield(owner or self.a, make_token('Zombie', 2, 2, {'decayed'}))
        source.sick = False
        return source

    def watcher(self, condition, effects='you gain 1 life', phase='each upkeep'):
        definition = card('Condition watcher', types='Enchantment',
                          text=f'At the beginning of {phase}, if {condition}, {effects}.')
        self.assertFalse(definition.unsupported)
        return self.g.enter_battlefield(self.a, definition)

    def test_falcon_abomination_token_cannot_block(self):
        falcon = self.real('Falcon Abomination')
        self.assertFalse(falcon.unsupported)
        self.g.enter_battlefield(self.a, falcon)
        self.drain_stack()
        zombie = next(x for x in self.a.creatures if x.card.is_token)
        attacker = self.g.enter_battlefield(self.b, BEAR)
        self.assertEqual((zombie.power, zombie.toughness, zombie.card.colors), (2, 2, {'B'}))
        self.assertTrue(zombie.has('decayed'))
        self.assertFalse(can_block(zombie, attacker))
        self.g.add_continuous_effect(zombie, 'remove', keyword='decayed')
        self.assertTrue(can_block(zombie, attacker))

    def test_decayed_attacker_deals_damage_then_is_sacrificed(self):
        zombie = self.zombie()
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 18)
        self.assertEqual(self.g.step, 'end_combat')
        self.assertNotIn(zombie, self.a.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 1)
        self.assertFalse(self.g.delayed_end_combat)

    def test_removing_keyword_after_attack_keeps_delayed_sacrifice(self):
        zombie = self.zombie()
        self.g.fire(self.a, 'attacks', zombie)
        self.g.add_continuous_effect(zombie, 'remove', keyword='decayed')
        self.drain_stack()
        self.assertEqual(len(self.g.delayed_end_combat), 1)
        self.g.end_combat(self.a)
        self.assertNotIn(zombie, self.a.battlefield)

    def test_countered_attack_trigger_creates_no_delayed_trigger(self):
        zombie = self.zombie()
        self.g.fire(self.a, 'attacks', zombie)
        self.g.flush_triggers()
        self.g.stack.pop()  # counter the attack-triggered ability
        self.g.end_combat(self.a)
        self.assertIn(zombie, self.a.battlefield)

    def test_delayed_sacrifice_can_be_countered(self):
        zombie = self.zombie()
        self.g.fire(self.a, 'attacks', zombie)
        self.drain_stack()
        # End-combat queuing uses the normal priority loop and stack.
        original = self.g.run_priority
        self.g.run_priority = lambda **kw: self.g.flush_triggers()
        self.g.end_combat(self.a)
        self.g.run_priority = original
        self.assertEqual(self.g.stack[-1].source, zombie)
        self.g.stack.pop()
        self.g.end_combat(self.a)
        self.assertIn(zombie, self.a.battlefield)

    def test_delayed_sacrifice_does_not_follow_blink_or_control_change(self):
        zombie = self.zombie()
        self.g.fire(self.a, 'attacks', zombie)
        self.drain_stack()
        definition = zombie.card
        self.g.leave_battlefield(zombie, 'exile')
        replacement = self.g.enter_battlefield(self.a, definition)
        self.g.end_combat(self.a)
        self.assertIn(replacement, self.a.battlefield)
        self.g.fire(self.a, 'attacks', replacement)
        self.drain_stack()
        self.a.battlefield.remove(replacement)
        replacement.controller = self.b
        self.b.battlefield.append(replacement)
        self.g.end_combat(self.a)
        self.assertIn(replacement, self.b.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 0)

    def test_entering_attacking_does_not_trigger_decayed(self):
        self.g.step = 'declare_attackers'
        zombie = self.g.enter_battlefield(self.a, make_token('Zombie', 2, 2, {'decayed'}), tapped_attacking=True)
        self.drain_stack()
        self.g.end_combat(self.a)
        self.assertIn(zombie, self.a.battlefield)

    def test_summoning_sick_decayed_creature_survives_combat(self):
        zombie = self.zombie()
        zombie.sick = True
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20)
        self.assertIn(zombie, self.a.battlefield)
        self.assertEqual(self.g.step, 'end_combat')

    def test_oxford_comma_keywords_and_unknown_keywords(self):
        definition = card('Keyword tokens', types='Sorcery', text='Create a 2/2 white Bird creature token with flying, vigilance, and haste.')
        self.assertFalse(definition.unsupported)
        self.g.resolve(self.a, definition.spell_effects[0], None)
        token = self.a.creatures[0]
        self.assertTrue(all(token.has(k) for k in ('flying', 'vigilance', 'haste')))
        self.assertEqual(token.card.subtypes, {'Bird'})
        unknown = card('Unknown token', types='Sorcery', text='Create a 2/2 green Dragon creature token with flying, vigilance, and devour 2.')
        self.assertTrue(any('devour 2' in text for text in unknown.unsupported))

    def test_empty_hand_gates_all_effects_at_resolution(self):
        self.watcher('you have no cards in hand', 'draw a card. You gain 3 life')
        self.a.library = [ISLAND]
        self.g.begin_upkeep(self.b)
        self.a.hand = [BEAR]
        self.drain_stack()
        self.assertEqual((self.a.life, len(self.a.library)), (20, 1))
        self.a.hand.clear()
        self.g.begin_upkeep(self.b)
        self.drain_stack()
        self.assertEqual((self.a.life, len(self.a.hand)), (23, 1))

    def test_intervening_condition_is_not_rechecked_between_effects(self):
        self.watcher('you have exactly one card in hand', 'draw a card and draw a card')
        self.a.hand, self.a.library = [BEAR], [ISLAND, ISLAND]
        self.g.begin_upkeep(self.b)
        self.drain_stack()
        self.assertEqual(len(self.a.hand), 3)
        self.g.begin_upkeep(self.b)
        self.assertFalse(self.g.pending)

    def test_convalescent_care_life_threshold_is_checked_once(self):
        definition = self.real('Convalescent Care')
        self.assertFalse(definition.unsupported)
        self.g.enter_battlefield(self.a, definition)
        self.a.library = [ISLAND, ISLAND]
        self.a.life = 6
        self.g.begin_upkeep(self.a)
        self.assertFalse(self.g.pending)
        self.a.life = 5
        self.g.begin_upkeep(self.a)
        self.a.life = 6
        self.drain_stack()
        self.assertEqual(len(self.a.hand), 0)
        self.a.life = 5
        self.g.begin_upkeep(self.a)
        self.drain_stack()
        self.assertEqual((self.a.life, len(self.a.hand)), (8, 1))

    def test_hollowborn_barghest_checks_the_correct_players_hand(self):
        definition = self.real('Hollowborn Barghest')
        self.assertFalse(definition.unsupported)
        self.g.enter_battlefield(self.a, definition)
        self.b.hand = [BEAR]
        self.g.begin_upkeep(self.a)
        self.drain_stack()
        self.assertEqual((self.a.life, self.b.life), (20, 18))
        self.g.begin_upkeep(self.b)
        self.assertFalse(self.g.pending)
        self.a.hand, self.b.hand = [BEAR], []
        self.g.begin_upkeep(self.b)
        self.drain_stack()
        self.assertEqual((self.a.life, self.b.life), (20, 16))

    def test_imaginary_pet_a_card_means_at_least_one(self):
        definition = self.real('Imaginary Pet')
        self.assertFalse(definition.unsupported)
        for size in (0, 1, 2):
            with self.subTest(hand_size=size):
                self.a.hand = [BEAR] * size
                source = self.g.enter_battlefield(self.a, definition)
                self.g.begin_upkeep(self.a)
                self.drain_stack()
                self.assertEqual(source in self.a.battlefield, size == 0)
                if size:
                    self.assertIn(source.front, self.a.hand)
                else:
                    self.g.sacrifice(source)

    def test_life_and_hand_comparison_boundaries(self):
        for condition, accepted, rejected in [('you have 30 or more life', 30, 29),
                                               ('you have exactly 13 life', 13, 14),
                                               ('you have two or fewer cards in hand', 2, 3)]:
            with self.subTest(condition=condition):
                source = self.watcher(condition)
                is_hand = 'hand' in condition
                if is_hand:
                    self.a.hand = [BEAR] * rejected
                else:
                    self.a.life = rejected
                self.g.begin_upkeep(self.b)
                self.assertFalse(self.g.pending)
                if is_hand:
                    self.a.hand = [BEAR] * accepted
                else:
                    self.a.life = accepted
                self.g.begin_upkeep(self.b)
                self.assertEqual(len(self.g.pending), 1)
                self.g.pending.clear()
                self.g.leave_battlefield(source, 'graveyard')

    def test_source_tapped_and_untapped_recheck(self):
        for state in ('tapped', 'untapped'):
            with self.subTest(state=state):
                source = self.watcher('~ is ' + state, phase='each end step')
                source.tapped = state == 'tapped'
                self.g.fire(self.b, 'end_step')
                self.assertEqual(len(self.g.pending), 1)
                source.tapped = not source.tapped
                self.drain_stack()
                self.assertEqual(self.a.life, 20)
                self.g.leave_battlefield(source, 'graveyard')

    def test_jadar_requires_no_decayed_creatures_at_both_checks(self):
        definition = self.real('Jadar, Ghoulcaller of Nephalia')
        self.assertFalse(definition.unsupported)
        self.g.enter_battlefield(self.a, definition)
        self.g.fire(self.a, 'end_step')
        zombie = self.zombie()
        self.drain_stack()
        self.assertEqual(len([x for x in self.a.creatures if x.card.is_token]), 1)
        self.g.fire(self.a, 'end_step')
        self.assertFalse(self.g.pending)
        self.g.sacrifice(zombie)
        self.g.fire(self.a, 'end_step')
        self.drain_stack()
        tokens = [x for x in self.a.creatures if x.card.is_token]
        self.assertEqual(len(tokens), 1)
        self.assertTrue(tokens[0].has('decayed'))

    def test_nonintervening_effect_condition_does_not_suppress_other_effects(self):
        definition = card('Later condition', types='Enchantment',
                          text='At the beginning of each upkeep, you gain 1 life. If you have no cards in hand, draw a card.')
        self.assertFalse(definition.unsupported)
        self.assertFalse(definition.triggers[0].intervening_if)
        self.g.enter_battlefield(self.a, definition)
        self.a.hand = [BEAR]
        self.g.begin_upkeep(self.b)
        self.drain_stack()
        self.assertEqual((self.a.life, len(self.a.hand)), (21, 1))

    def test_unknown_keyword_and_compound_condition_remain_gaps(self):
        for condition in ('you control no creatures with banding',
                          'you have no cards in hand and control an artifact', 'the moon is blue'):
            with self.subTest(condition=condition):
                definition = card('Unknown condition', types='Enchantment',
                                  text=f'At the beginning of each upkeep, if {condition}, you gain 1 life.')
                self.assertTrue(definition.unsupported)
                self.assertFalse(definition.triggers)
        self.assertFalse(self.real('Test of Endurance').unsupported)  # the life gate and "you win the game" (cx_effects)


if __name__ == '__main__':
    unittest.main()
