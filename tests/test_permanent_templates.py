"""Composed selectors, generic counter operations and temporary grants."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.cards import _parse_effects, make_token
from mtgsim.engine import Game, Player, StackItem, TARGETED
from mtgsim.permanent_templates import selector, parse_effect, split_sentences
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card
from tests.test_storage_lands import POOLS


class PermanentTemplates(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 2, 'main1'
        for player in self.g.players:
            player.library = [ISLAND] * 30
            player.ai.choose_graft = lambda *args: False
            player.ai.attack, player.ai.block = (), {}

    def put(self, definition=BEAR, who=None, counters=None):
        result = self.g.enter_battlefield(who or self.a, definition, counters=counters)
        result.sick = False
        self.g.settle()
        return result

    def parse(self, text):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        self.assertTrue(effects)
        return effects

    def apply(self, text, target=None, source=None, settle=True):
        effects = self.parse(text)
        targets = [target if e.target in TARGETED else None for e in effects]
        item = StackItem(self.a, effects, targets, source=source, kind='ability')
        self.g.stack.append(item)
        if settle:
            self.g.settle()
        return item

    def cleanup(self):
        with patch.object(self.g, 'main_phase'), patch.object(self.g, 'combat'):
            self.g.take_turn(self.b)

    def test_selector_combines_controller_subtype_color_and_counter(self):
        goblin = card('Goblin fixture', '{R}', 'Creature — Goblin', '', 2, 2)
        yes = self.put(goblin, counters={'+1/+1': 1})
        enemy = self.put(goblin, self.b, counters={'+1/+1': 1})
        plain = self.put(goblin)
        wrong_type = self.put(counters={'+1/+1': 1})
        eff = self.parse('Target red Goblin creature you control with a +1/+1 counter on it gains haste until end of turn.')[0]
        legal = self.g.legal_targets(self.a, eff)
        self.assertEqual(legal, [yes])
        self.assertNotIn(enemy, legal)
        self.assertNotIn(plain, legal)
        self.assertNotIn(wrong_type, legal)

    def test_target_controller_and_counter_filter_rechecked_on_resolution(self):
        obj = self.put(counters={'+1/+1': 1})
        self.apply('Target creature you control with a +1/+1 counter on it gains shroud until end of turn.', obj, settle=False)
        obj.counters['+1/+1'] = 0
        self.g.settle()
        self.assertFalse(obj.has('shroud'))

    def test_stat_filter_uses_current_power_not_printed_power(self):
        obj = self.put(counters={'+1/+1': 1})
        eff = self.parse('Target creature with power 2 or less gains shroud until end of turn.')[0]
        self.assertNotIn(obj, self.g.legal_targets(self.a, eff))
        obj.counters['+1/+1'] = 0
        self.assertIn(obj, self.g.legal_targets(self.a, eff))

    def test_mana_value_filter_and_type_union(self):
        artifact = self.put(card('Tool', '{1}', 'Artifact', ''))
        bear = self.put()
        land = self.put(ISLAND)
        eff = self.parse('Tap target artifact or creature with mana value 1 or less.')[0]
        self.assertEqual(self.g.legal_targets(self.a, eff), [artifact])
        self.assertNotIn(bear, self.g.legal_targets(self.a, eff))
        self.assertNotIn(land, self.g.legal_targets(self.a, eff))

    def test_changeling_satisfies_subtype_selectors(self):
        obj = self.put(dataclasses.replace(BEAR, changeling=True))
        eff = self.parse('Target Elf creature gains shroud until end of turn.')[0]
        self.assertIn(obj, self.g.legal_targets(self.a, eff))

    def test_negative_subtype_excludes_changelings(self):
        changeling = self.put(dataclasses.replace(BEAR, changeling=True))
        bear = self.put()
        eff = self.parse('Target non-Elf creature gains shroud until end of turn.')[0]
        self.assertNotIn(changeling, self.g.legal_targets(self.a, eff))
        self.assertIn(bear, self.g.legal_targets(self.a, eff))

    def test_player_and_host_phrases_are_not_permanent_subtypes(self):
        for text in ('You', 'Enchanted creature', 'Equipped creature', 'Those creatures'):
            self.assertIsNone(selector(text, plural=True))
        definition = card('Law', '', 'Enchantment', 'You have hexproof.')
        # This feature does not implement player keyword statics.
        self.assertTrue(definition.unsupported)

    def test_changeling_does_not_grant_land_subtypes(self):
        obj = self.put(dataclasses.replace(BEAR, changeling=True))
        eff = self.parse('Target Island creature gains shroud until end of turn.')[0]
        self.assertNotIn(obj, self.g.legal_targets(self.a, eff))

    def test_unknown_predicate_never_disappears(self):
        for text in ('Tap target creature with a strange quality.',
                     'Target creature controlled by the chosen player gains shroud until end of turn.',
                     'Put two mystery counters on target creature unless its controller pays {1}.',
                     'All creatures with a name chosen this way gain flying until end of turn.'):
            with self.subTest(text=text):
                self.assertIsNone(parse_effect(text.rstrip('.')))

    def test_tapped_attacking_token_and_colorless_traits(self):
        obj = self.put(make_token('Soldier', 2, 2))
        obj.tapped = True
        self.g.attackers = [obj]
        eff = self.parse('Target tapped attacking colorless creature token gains shroud until end of turn.')[0]
        self.assertEqual(self.g.legal_targets(self.a, eff), [obj])
        self.g.attackers = []
        self.assertEqual(self.g.legal_targets(self.a, eff), [])

    def test_optional_target_can_be_omitted(self):
        self.apply('Put four charge counters on up to one target artifact.')
        self.assertFalse(self.g.stack)

    def test_other_target_excludes_source(self):
        source, other = self.put(), self.put()
        eff = self.parse('Another target creature gains shroud until end of turn.')[0]
        with self.g.targeting(source):
            self.assertEqual(self.g.legal_targets(self.a, eff), [other])

    def test_protection_hexproof_and_shroud_still_apply(self):
        obj = self.put(who=self.b)
        eff = self.parse('Put five -1/-1 counters on target creature.')[0]
        obj.temp_kw.add('hexproof')
        self.assertNotIn(obj, self.g.legal_targets(self.a, eff))
        obj.temp_kw = {'shroud'}
        self.assertNotIn(obj, self.g.legal_targets(self.b, eff))

    def test_named_counters_can_be_added_to_land_artifact_or_creature(self):
        for definition in (ISLAND, card('Tool', '', 'Artifact', ''), BEAR):
            with self.subTest(kind=definition.types):
                obj = self.put(definition)
                self.apply('Put seven charge counters on target permanent.', obj)
                self.assertEqual(obj.counters['charge'], 7)

    def test_counter_removal_clamps_at_zero_and_preserves_other_types(self):
        obj = self.put(counters={'charge': 2, '+1/+1': 1})
        self.apply('Remove five charge counters from target creature.', obj)
        self.assertEqual((obj.counters['charge'], obj.p1), (0, 1))

    def test_double_one_counter_kind(self):
        obj = self.put(counters={'+1/+1': 2, 'vigilance': 1})
        self.apply('Double the number of +1/+1 counters on target creature.', obj)
        self.assertEqual((obj.p1, obj.counters['vigilance']), (4, 1))

    def test_double_all_counter_kinds(self):
        obj = self.put(counters={'+1/+1': 2, 'vigilance': 1})
        self.apply('Double each kind of counters on target creature.', obj)
        self.assertEqual((obj.p1, obj.counters['vigilance']), (4, 2))

    def test_group_counter_doubling_excludes_opponents(self):
        ally = self.put(counters={'+1/+1': 2})
        enemy = self.put(who=self.b, counters={'+1/+1': 2})
        self.apply('Double the number of +1/+1 counters on each creature you control.')
        self.assertEqual((ally.p1, enemy.p1), (4, 2))

    def test_group_all_counter_types_are_applied_before_state_based_actions(self):
        # Both creatures become zero toughness in the same effect.
        first, second = self.put(), self.put()
        seen = []
        original = self.g.state_based_actions
        def inspect():
            seen.append((first.counters.get('-1/-1', 0), second.counters.get('-1/-1', 0)))
            original()
        with patch.object(self.g, 'state_based_actions', side_effect=inspect):
            self.apply('Put four -1/-1 counters on each creature.')
        self.assertIn((4, 4), seen)
        self.assertNotIn((4, 0), seen)
        self.assertNotIn(first, self.a.battlefield)
        self.assertNotIn(second, self.a.battlefield)

    def test_pump_and_keyword_share_one_group_snapshot(self):
        obj = self.put()
        self.apply('All creatures you control with power 2 or less get +4/+4 and gain haste until end of turn.')
        self.assertEqual(obj.power, 6)
        self.assertTrue(obj.has('haste'))
        self.cleanup()
        self.assertEqual(obj.power, 2)
        self.assertFalse(obj.has('haste'))

    def test_self_pump_and_keyword_use_same_source(self):
        obj = self.put()
        self.apply('~ gets +5/+0 and gains shroud until end of turn.', source=obj)
        self.assertEqual(obj.power, 7)
        self.assertTrue(obj.has('shroud'))

    def test_arbitrary_keyword_list_keeps_all_keywords(self):
        obj = self.put()
        self.apply('Target creature gains flying, vigilance, and shroud until end of turn.', obj)
        self.assertTrue(all(obj.has(k) for k in ('flying', 'vigilance', 'shroud')))

    def test_unknown_keyword_list_is_not_partially_accepted(self):
        self.assertIsNone(parse_effect('target creature gains flying and an unknown ability until end of turn'))

    def test_negative_stat_change_can_kill_target(self):
        obj = self.put(who=self.b)
        self.apply('Target creature gets -7/-3 until end of turn.', obj)
        self.assertNotIn(obj, self.b.battlefield)

    def test_exile_uses_exile_and_ignores_indestructible(self):
        obj = self.put(who=self.b)
        obj.temp_kw.add('indestructible')
        self.apply('Exile target creature with toughness 2 or less.', obj)
        self.assertIn(obj.front, self.b.exile)
        self.assertNotIn(obj.front, self.b.graveyard)

    def test_pilots_automatically_exile_indestructible_artifacts(self):
        for pilot in (HeuristicAI, BaselineAI):
            with self.subTest(pilot=pilot.__name__):
                self.setUp()
                self.a.ai = pilot()
                target = self.put(card('Rock', '{2}', 'Artifact', 'Indestructible'), self.b)
                spell = card('Removal', '', 'Sorcery', 'Exile target artifact with mana value 3 or less.')
                self.assertFalse(spell.unsupported)
                self.a.hand.append(spell)
                self.g.main_phase(self.a)
                self.assertIn(target.front, self.b.exile)

    def test_optional_payment_gate_is_preserved_for_exact_exile(self):
        obj = self.put(who=self.b)
        self.apply('You may pay {U}. If you do, exile target creature with toughness 2 or less.', obj)
        self.assertIn(obj, self.b.battlefield)
        self.put(ISLAND)
        self.apply('You may pay {U}. If you do, exile target creature with toughness 2 or less.', obj)
        self.assertIn(obj.front, self.b.exile)

    def test_tap_group_then_untap_group(self):
        objs = [self.put(), self.put(who=self.b)]
        self.apply('Tap all creatures with power 3 or less.')
        self.assertTrue(all(x.tapped for x in objs))
        self.apply('Untap all creatures with power 3 or less.')
        self.assertTrue(all(not x.tapped for x in objs))

    def test_named_entry_counters_are_present_before_entry_trigger(self):
        obj = self.put(card('Bank', '', 'Artifact', '~ enters with seven storage counters on it.'))
        self.assertEqual(obj.counters['storage'], 7)

    def test_named_entry_counter_text_with_unknown_clause_stays_unsupported(self):
        definition = card('Bank', '', 'Artifact', '~ enters with seven storage counters on it if you paid {U}.')
        self.assertTrue(definition.unsupported)

    def test_static_keyword_list_on_subtype_obeys_other_and_controller(self):
        elf = card('Elf fixture', '{G}', 'Creature — Elf', '', 2, 2)
        lord = self.put(card('Lord', '', 'Creature — Elf', 'Other Elves you control have haste and shroud.', 2, 2))
        ally, enemy = self.put(elf), self.put(elf, self.b)
        self.assertTrue(ally.has('haste') and ally.has('shroud'))
        self.assertFalse(lord.has('shroud'))
        self.assertFalse(enemy.has('haste'))
        self.g.destroy(lord)
        self.assertFalse(ally.has('haste'))

    def test_static_grant_can_affect_both_players(self):
        source = self.put(card('Law', '', 'Enchantment', 'Creatures have haste and shroud.'))
        ally, enemy = self.put(), self.put(who=self.b)
        self.assertTrue(ally.has('shroud') and enemy.has('shroud'))
        source.silenced_by = ally
        self.assertFalse(enemy.has('shroud'))

    def test_static_counter_selector_updates_as_counters_change(self):
        self.put(card('Law', '', 'Enchantment', 'Creatures you control with +1/+1 counters on them have shroud.'))
        obj = self.put()
        self.assertFalse(obj.has('shroud'))
        obj.counters['+1/+1'] = 1
        self.assertTrue(obj.has('shroud'))
        obj.counters['+1/+1'] = 0
        self.assertFalse(obj.has('shroud'))

    def test_static_keyword_dependency_is_rejected(self):
        definition = card('Law', '', 'Enchantment', 'Creatures with flying have shroud.')
        self.assertTrue(definition.unsupported)

    def test_fixed_multiple_self_counter_cost_pays_exact_quantity(self):
        obj = self.put(card('Bank', '', 'Artifact', 'Remove three charge counters from ~: Draw a card.'))
        obj.counters['charge'] = 5
        self.assertTrue(self.g.activate_ability(self.a, obj, 0))
        self.assertEqual(obj.counters['charge'], 2)
        self.assertEqual(len(self.a.hand), 1)
        self.assertFalse(self.g.activate_ability(self.a, obj, 0))
        self.assertEqual(obj.counters['charge'], 2)

    def test_self_counter_cost_can_kill_source_after_ability_stacked(self):
        obj = self.put(card('Automaton', '', 'Creature', 'Remove two +1/+1 counters from ~: Draw a card.', 0, 0), counters={'+1/+1': 2})
        self.assertTrue(self.g.activate_ability(self.a, obj, 0))
        self.assertNotIn(obj, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 1)

    def test_repeated_counter_costs_are_not_silently_overwritten(self):
        definition = card('Bank', '', 'Artifact', 'Remove a charge counter from ~, Remove a storage counter from ~: Draw a card.')
        self.assertTrue(definition.unsupported)

    def test_counter_cost_cannot_double_spend_storage_mana(self):
        definition = dataclasses.replace(POOLS, activated=card('Bank', '', 'Artifact', '{1}, Remove two storage counters from ~: Draw a card.').activated)
        obj = self.put(definition)
        obj.counters['storage'] = 2
        obj.tapped = True
        self.assertFalse(self.g.activate_ability(self.a, obj, 0))
        self.assertEqual(obj.counters['storage'], 2)
        self.put(ISLAND)
        self.assertTrue(self.g.activate_ability(self.a, obj, 0))
        self.assertEqual(obj.counters['storage'], 0)

    def test_quoted_ability_sentences_remain_intact(self):
        text = 'Target creature gains "Whenever this creature attacks, draw a card. Then you gain 2 life." until end of turn. Draw a card.'
        parts = list(split_sentences(text))
        self.assertEqual(len(parts), 2)
        self.assertIn('Then you gain 2 life.', parts[0])

    def test_granted_attack_trigger_fires_and_expires(self):
        obj = self.put()
        self.apply('Target creature gains "Whenever this creature attacks, draw a card." until end of turn.', obj)
        self.g.fire(self.a, 'attacks', obj)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.cleanup()
        self.g.fire(self.a, 'attacks', obj)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_granted_multi_sentence_trigger_resolves_all_effects(self):
        obj = self.put()
        self.apply('Target creature gains "Whenever this creature attacks, draw a card. Then you gain 2 life." until end of turn.', obj)
        self.g.fire(self.a, 'attacks', obj)
        self.g.settle()
        self.assertEqual((len(self.a.hand), self.a.life), (1, 22))

    def test_granted_death_trigger_survives_source_departure(self):
        obj = self.put()
        self.apply('Until end of turn, target creature gains "When this creature dies, draw two cards."', obj)
        self.g.destroy(obj)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 2)

    def test_group_trigger_grant_applies_to_each_recipient(self):
        first, second = self.put(), self.put()
        self.apply('All creatures you control gain "Whenever this creature attacks, you gain 1 life." until end of turn.')
        for obj in (first, second):
            self.g.fire(self.a, 'attacks', obj)
        self.g.settle()
        self.assertEqual(self.a.life, 22)

    def test_unsupported_quoted_ability_remains_a_gap(self):
        definition = card('Spell', '', 'Instant', 'Target creature gains "Whenever this creature attacks, do something unknown." until end of turn.')
        self.assertTrue(definition.unsupported)

    def test_new_permanent_target_selects_land_and_preserves_ownership_on_bounce(self):
        obj = self.put(ISLAND, self.b)
        self.apply("Return target land with mana value 0 or less to its owner's hand.", obj)
        self.assertIn(obj.front, self.b.hand)
        self.assertNotIn(obj.front, self.a.hand)


if __name__ == '__main__':
    unittest.main()
