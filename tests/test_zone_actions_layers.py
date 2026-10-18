"""Movement traces, atomic costs and scoped continuous-effect interactions."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim.actions import Action, Transaction
from mtgsim import auras
from mtgsim.cards import Activated, Effect, make_token
from mtgsim.continuous import ContinuousEffect, ordered
from mtgsim.engine import Game, Player
from mtgsim.ai import BaselineAI
from tests.test_templates import BEAR, ISLAND, card


class ZoneActionsLayers(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], BaselineAI())
        self.b = Player('b', [], BaselineAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step, self.g._priority_depth = 2, 'main1', 1

    def moves(self):
        return [(e.source_zone, e.destination) for e in self.g.rule_events.history if e.kind == 'zone_change']

    def test_legacy_moves_and_reorder(self):
        self.a.library = [BEAR, ISLAND]
        refs = [self.a.library.reference(c) for c in self.a.library]
        self.a.library.shuffle(self.g.rng)
        self.assertFalse(self.moves())
        self.assertTrue(all(ref.find(self.a.library) is not None for ref in refs))
        physical = self.a.library.pop()
        self.a.graveyard.append(physical)
        self.a.exile.append(self.a.graveyard.pop())
        self.a.hand.append(self.a.exile.pop())
        self.assertEqual(self.moves(), [('library', 'graveyard'), ('graveyard', 'exile'), ('exile', 'hand')])
        self.assertTrue(all(e.before.physical_id == physical.physical_id for e in self.g.rule_events.history))

    def test_spell_stack_trace(self):
        self.a.hand = [card('Draw zero', types='Sorcery', text='Draw a card.')]
        self.a.library = [ISLAND]
        self.assertTrue(self.g.do_action(self.a, Action('cast', self.a.hand[0])))
        self.g.resolve_top()
        self.assertEqual(self.moves(), [('hand', 'stack'), ('library', 'hand'), ('stack', 'graveyard')])

    def test_discover_uses_exile_without_hand_detour(self):
        self.a.library = [card('Discover bear', cost='{1}', types='Creature', power=2, toughness=2), ISLAND]
        found, skipped = self.a.library
        self.g.resolve(self.a, Effect('discover', 2), None)
        self.assertEqual(self.moves(), [('library', 'exile'), ('library', 'exile'),
                                       ('exile', 'stack'), ('exile', 'library')])
        self.assertIs(self.a.library[0], skipped)
        self.assertFalse(self.a.hand)
        self.assertFalse(self.a.exile)
        self.assertIs(self.g.stack[-1].physical_card, found)
        self.g.resolve_top()
        self.assertIs(self.a.creatures[0].front, found)

    def test_manifest_view_preserves_physical_entry_and_death(self):
        self.a.library = [BEAR, ISLAND]
        physicals = {c.physical_id for c in self.a.library}
        self.g.resolve(self.a, Effect('manifest_dread'), None)
        manifest = self.a.creatures[0]
        self.assertIn(manifest.front.physical_id, physicals)
        self.assertIs(manifest.front.zone, manifest)
        entries = [e for e in self.g.rule_events.history if e.destination == 'battlefield']
        self.assertEqual(entries[0].source_zone, 'library')
        self.assertEqual(entries[0].before.physical_id, manifest.front.physical_id)
        self.g.destroy(manifest)
        self.assertEqual({c.physical_id for c in self.a.graveyard}, physicals)

    def test_alternate_face_uses_physical_card_in_entry_event(self):
        self.a.hand = [BEAR]
        physical = self.a.hand.pop()
        view = card('Alternate land face', types='Land')
        permanent = self.g.enter_battlefield(self.a, view, physical_card=physical)
        self.assertIs(permanent.front, physical)
        self.assertIs(physical.zone, permanent)
        event = next(e for e in self.g.rule_events.history if e.kind == 'zone_change')
        self.assertEqual(event.before.physical_id, physical.physical_id)
        self.assertEqual((event.source_zone, event.destination), ('hand', 'battlefield'))

    def test_discover_uncastable_card_moves_from_exile_to_hand(self):
        definition = card('No target', types='Instant')
        definition.spell_effects = [Effect('damage', 1, target='creature')]
        self.a.library = [definition]
        physical = self.a.library[0]
        self.g.resolve(self.a, Effect('discover', 2), None)
        self.assertEqual(self.moves(), [('library', 'exile'), ('exile', 'hand')])
        self.assertIs(self.a.hand[0], physical)
        self.assertFalse(self.g.stack)

    def test_special_zone_and_battlefield_trace(self):
        self.a.hand = [card('Free bear', types='Creature', power=2, toughness=2)]
        physical = self.a.hand[0]
        self.g.move_card(physical, self.a.hand, self.a.foretold, reason='foretell')
        self.g.move_card(physical, self.a.foretold, self.a.hand)
        self.assertTrue(self.g.cast(self.a, physical))
        self.g.resolve_top()
        self.g.destroy(self.a.creatures[0])
        self.assertEqual(self.moves(), [('hand', 'foretold'), ('foretold', 'hand'), ('hand', 'stack'),
                                        ('stack', 'battlefield'), ('battlefield', 'graveyard')])
        self.assertIn('dies', [e.kind for e in self.g.rule_events.history])

    def test_failed_discard_restores_paid_mana_and_observers(self):
        definition = card('Costly choice', cost='{U}', types='Sorcery', text='Draw a card.')
        definition.extra_discard = True
        self.a.hand = [definition, BEAR]
        physical = self.a.hand[0]
        ref = self.a.hand.reference(physical)
        land = self.g.enter_battlefield(self.a, ISLAND)
        history, logs = list(self.g.rule_events.history), list(self.g.events)
        observed = []
        self.g.rule_events.listeners.append(observed.append)
        with patch.object(self.a.ai, 'choose_discard', return_value=None):
            self.assertFalse(self.g.cast(self.a, physical))
        self.assertFalse(land.tapped)
        self.assertIs(ref.find(self.a.hand), physical)
        self.assertEqual(self.g.rule_events.history, history)
        self.assertEqual(self.g.events, logs)
        self.assertFalse(observed)
        self.assertFalse(self.g.stack)

    def test_nested_transaction_and_rng_rollback(self):
        state = self.g.rng.getstate()
        self.a.hand = [BEAR]
        ref = self.a.hand.reference(self.a.hand[0])
        observed = []
        self.g.rule_events.listeners.append(observed.append)
        with Transaction(self.g):
            self.g.rng.random()
            with Transaction(self.g) as inner:
                self.g.move_card(self.a.hand[0], self.a.hand, self.a.exile)
                inner.commit = True
            self.assertFalse(observed)
        self.assertEqual(self.g.rng.getstate(), state)
        self.assertIsNotNone(ref.find(self.a.hand))
        self.assertFalse(observed)

    def test_overlapping_mana_and_sacrifice_costs_roll_back(self):
        definition = card('Consume artifact', cost='{1}', types='Sorcery', text='Draw a card.')
        definition.extra_sacrifice = 'artifact'
        self.a.hand = [definition]
        treasure = self.g.enter_battlefield(self.a, make_token('Treasure', 0, 0, kind='treasure'))
        generation = treasure.front.generation
        history = list(self.g.rule_events.history)
        self.assertFalse(self.g.cast(self.a, self.a.hand[0]))
        self.assertIn(treasure, self.a.battlefield)
        self.assertIs(treasure.front.zone, treasure)
        self.assertEqual(treasure.front.generation, generation)
        self.assertEqual(self.a.sacrificed_turn, 0)
        self.assertFalse(treasure.tapped)
        self.assertEqual(self.g.rule_events.history, history)

    def test_committed_costs_are_visible_before_resolution(self):
        definition = card('Paid draw', cost='{U}', types='Sorcery', text='Draw a card.')
        self.a.hand = [definition]
        self.a.library = [BEAR]
        land = self.g.enter_battlefield(self.a, ISLAND)
        observations = []
        self.g.rule_events.listeners.append(lambda event: observations.append(
            (land.tapped, len(self.g.stack), len(self.a.hand))))
        self.assertTrue(self.g.do_action(self.a, Action('cast', self.a.hand[0])))
        self.assertTrue(land.tapped)
        self.assertTrue(observations)
        self.assertEqual(set(observations), {(True, 1, 0)})
        self.assertEqual(len(self.a.library), 1)

    def test_missing_required_target_cannot_pay_or_cast(self):
        definition = card('Creature damage', cost='{U}', types='Instant')
        definition.spell_effects = [Effect('damage', 1, target='creature')]
        self.a.hand = [definition]
        land = self.g.enter_battlefield(self.a, ISLAND)
        self.assertFalse(self.g.do_action(self.a, Action('cast', self.a.hand[0])))
        self.assertFalse(land.tapped)
        self.assertEqual(len(self.a.hand), 1)

    def test_dependency_cycles_preserve_external_dependencies(self):
        effects = [ContinuousEffect(1, None, 'set_base', 1, depends_on=(2, 3)),
                   ContinuousEffect(2, None, 'set_base', 2, depends_on=(1,)),
                   ContinuousEffect(3, None, 'set_base', 3, depends_on=(4,)),
                   ContinuousEffect(4, None, 'set_base', 4, depends_on=(3,))]
        ids = [e.id for e in ordered(effects)]
        self.assertLess(ids.index(3), ids.index(1))
        self.assertEqual(sorted(ids), [1, 2, 3, 4])

    def test_action_probe_matches_execution_and_preserves_state(self):
        self.a.hand = [card('Free spell', types='Sorcery', text='Draw a card.')]
        action = Action('cast', self.a.hand[0])
        ref = self.a.hand.reference(self.a.hand[0])
        self.assertTrue(self.g.can_perform(self.a, action))
        self.assertIsNotNone(ref.find(self.a.hand))
        self.assertFalse(self.g.stack)
        self.assertFalse(self.moves())
        self.g.step = 'combat'
        self.assertFalse(self.g.can_perform(self.a, action))
        self.assertFalse(self.g.do_action(self.a, action))
        self.g.step = 'main1'
        self.assertTrue(self.g.do_action(self.a, action))
        self.assertFalse(self.g.can_perform(self.a, action))

    def test_invalid_activation_target_and_negative_index(self):
        definition = card('Pinger', types='Artifact')
        definition.activated = [Activated('ability', {'U': 1}, effects=[Effect('damage', 1, target='creature')],
                                          extra_costs={'tap': True})]
        permanent = self.g.enter_battlefield(self.a, definition)
        land = self.g.enter_battlefield(self.a, ISLAND)
        self.assertTrue(self.g.can_activate(self.a, permanent, 0))
        self.assertFalse(self.g.can_activate(self.a, permanent, -1))
        self.assertFalse(self.g.activate_ability(self.a, permanent, 0, [land]))
        self.assertFalse(land.tapped)
        self.assertFalse(permanent.tapped)
        self.assertFalse(self.g.stack)

    def test_target_can_be_sacrificed_as_cost(self):
        definition = card('Sacrificial pump', types='Artifact', text='{0}, Sacrifice a creature: Target creature gets +1/+1 until end of turn.')
        source = self.g.enter_battlefield(self.a, definition)
        target = self.g.enter_battlefield(self.a, BEAR)
        self.assertTrue(self.g.activate_ability(self.a, source, 0, [target]))
        self.assertNotIn(target, self.a.battlefield)
        self.g.resolve_top()  # announced legally, then fizzles rather than undoing the cost
        self.assertEqual(len(self.a.graveyard), 1)

    def test_base_animation_role_timestamps_both_orders(self):
        target = self.g.enter_battlefield(self.a, BEAR)
        curse = dataclasses.replace(card('Curse', types='Enchantment'), aura_flags=frozenset({'base_1_1'}))
        role = self.g.enter_battlefield(self.a, curse)
        target.animated = Activated('animate', {}, 4, 5)
        auras.attach(self.g, role, target)
        self.assertEqual((target.power, target.toughness), (1, 1))
        target.animated = Activated('animate', {}, 4, 5)
        self.assertEqual((target.power, target.toughness), (4, 5))
        auras.detach(role)
        auras.attach(self.g, role, target)
        self.assertEqual((target.power, target.toughness), (1, 1))

    def test_base_modifiers_counters_switch_order(self):
        target = self.g.enter_battlefield(self.a, BEAR)
        self.g.add_continuous_effect(target, 'switch')  # timestamp cannot override layers
        self.g.add_continuous_effect(target, 'modify', power=2, toughness=0)
        self.g.add_continuous_effect(target, 'set_base', power=1, toughness=4)
        target.counters['+1/+1'] = 1
        self.assertEqual((target.power, target.toughness), (5, 4))

    def test_keyword_removal_and_grant_timestamps(self):
        target = self.g.enter_battlefield(self.a, dataclasses.replace(BEAR, keywords=frozenset({'flying'})))
        self.g.add_continuous_effect(target, 'remove', keyword='flying')
        self.assertFalse(target.has('flying'))
        self.g.add_continuous_effect(target, 'grant', keyword='flying')
        self.assertTrue(target.has('flying'))

    def test_explicit_dependencies_override_timestamp_and_cycles_terminate(self):
        a = ContinuousEffect(1, None, 'set_base', 1, depends_on=(2,))
        b = ContinuousEffect(2, None, 'set_base', 2)
        self.assertEqual([e.id for e in ordered([a, b])], [2, 1])
        b = dataclasses.replace(b, depends_on=(1,))
        self.assertEqual([e.id for e in ordered([b, a])], [1, 2])
        target = self.g.enter_battlefield(self.a, BEAR)
        effect = self.g.add_continuous_effect(target, 'set_base', power=3, toughness=4)
        with self.assertRaises(ValueError):
            self.g.add_continuous_effect(target, 'modify', depends_on=(effect.id,))

    def test_source_lifetime_expiry_and_last_known_pt(self):
        target = self.g.enter_battlefield(self.a, BEAR)
        source = self.g.enter_battlefield(self.a, BEAR)
        self.g.add_continuous_effect(target, 'modify', power=1, source=source)
        self.g.add_continuous_effect(target, 'modify', power=2, until_eot=True)
        self.assertEqual(target.power, 5)
        self.g.destroy(source)
        self.assertEqual(target.power, 4)
        self.g.expire_continuous_effects()
        self.assertEqual(target.power, 2)
        self.g.add_continuous_effect(target, 'modify', power=3, toughness=2)
        self.g.destroy(target)
        self.assertEqual((target.power, target.toughness), (5, 4))
        self.assertEqual(next(e for e in reversed(self.g.rule_events.history) if e.kind == 'zone_change').before.power, 5)
        self.a.graveyard.remove(target.front)
        new = self.g.enter_battlefield(self.a, target.front)
        self.assertEqual((new.power, new.toughness), (2, 2))
