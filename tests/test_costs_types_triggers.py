"""Joint payment plans and scoped type/color layer interactions."""
import dataclasses
import random
import unittest

from mtgsim.ai import BaselineAI
from mtgsim.cards import Activated, Effect, make_token
from mtgsim.engine import Game, Player, can_block
from tests.test_templates import BEAR, ISLAND, card


class CostsTypesTriggers(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], BaselineAI()), Player('b', [], BaselineAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step, self.g._priority_depth = 2, 'main1', 1

    def treasure(self):
        return self.g.enter_battlefield(self.a, make_token('Treasure', 0, 0, kind='treasure'))

    def sacrifice_spell(self, cost='{1}', fallback=0):
        definition = card('Sacrifice cost', cost=cost, types='Sorcery')
        definition.extra_sacrifice = 'artifact'
        definition.extra_sac_or_pay = fallback
        self.a.hand = [definition]
        return self.a.hand[0]

    def test_reserve_treasure_and_pay_with_land(self):
        treasure = self.treasure()
        land = self.g.enter_battlefield(self.a, ISLAND)
        spell = self.sacrifice_spell()
        self.assertTrue(self.g.can_cast_now(self.a, spell))
        self.assertTrue(self.g.can_perform(self.a, (spell, [])))
        self.assertFalse(land.tapped)
        self.assertIn(treasure, self.a.battlefield)
        self.assertTrue(self.g.cast(self.a, spell))
        self.assertTrue(land.tapped)
        self.assertNotIn(treasure, self.a.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 1)

    def test_search_other_victim_for_colored_mana(self):
        treasure = self.treasure()
        artifact = self.g.enter_battlefield(self.a, card('Spare artifact', types='Artifact'))
        spell = self.sacrifice_spell('{B}')
        self.assertTrue(self.g.cast(self.a, spell))
        self.assertNotIn(treasure, self.a.battlefield)
        self.assertIn(artifact.front, self.a.graveyard)
        self.assertEqual(self.a.sacrificed_turn, 2)

    def test_tap_for_mana_then_sacrifice_same_permanent(self):
        artifact = self.g.enter_battlefield(self.a, card('Mana rock', types='Artifact', text='{T}: Add {U}.'))
        spell = self.sacrifice_spell('{U}')
        self.assertTrue(self.g.cast(self.a, spell))
        self.assertIn(artifact.front, self.a.graveyard)
        self.assertEqual(self.a.sacrificed_turn, 1)

    def test_optional_tax_when_only_victim_must_pay_mana(self):
        treasure = self.treasure()
        land = self.g.enter_battlefield(self.a, ISLAND)
        spell = self.sacrifice_spell('{U}', fallback=1)
        self.assertTrue(self.g.cast(self.a, spell))  # reserve Treasure, Island pays U; no tax needed
        self.assertTrue(land.tapped)
        self.assertEqual(self.g.stack[-1].mana_spent, 1)
        # The only black source is Treasure, so the next spell must use its tax alternative.
        treasure = self.treasure()
        land.tapped = False
        spell = self.sacrifice_spell('{B}', fallback=1)
        self.assertTrue(self.g.cast(self.a, spell))
        self.assertEqual(self.g.stack[-1].mana_spent, 2)
        self.assertNotIn(treasure, self.a.battlefield)

    def test_x_payment_preserves_reserved_victim(self):
        self.treasure()
        land = self.g.enter_battlefield(self.a, ISLAND)
        spell = self.sacrifice_spell('{X}')
        self.assertTrue(self.g.cast(self.a, spell))
        self.assertEqual(self.g.stack[-1].x, 1)
        self.assertTrue(land.tapped)
        self.assertEqual(self.a.sacrificed_turn, 1)

    def test_ability_and_craft_reserve_mana_consumables(self):
        treasure = self.treasure()
        land = self.g.enter_battlefield(self.a, ISLAND)
        definition = card('Sacrificer', types='Artifact')
        definition.activated = [Activated('ability', {'generic': 1}, extra_costs={'sacrifice': 'treasure'})]
        source = self.g.enter_battlefield(self.a, definition)
        self.assertTrue(self.g.can_activate(self.a, source, 0))
        self.assertTrue(self.g.activate_ability(self.a, source, 0))
        self.assertTrue(land.tapped)
        self.assertNotIn(treasure, self.a.battlefield)
        treasure = self.treasure()
        land.tapped = False
        definition.activated = [Activated('ability', {'generic': 1}, extra_costs={'craft': True})]
        self.assertTrue(self.g.activate_ability(self.a, source, 0))
        self.assertEqual(treasure.last_destination, 'exile')  # the token vanishes after being exiled
        self.assertNotIn(treasure, self.a.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 1)

    def test_type_changes_affect_targets_without_changing_physical_card(self):
        target = self.g.enter_battlefield(self.a, ISLAND)
        effect = Effect('destroy', target='creature')
        self.assertNotIn(target, self.g.legal_targets(self.a, effect))
        self.g.add_continuous_effect(target, 'add_types', types={'Creature', 'Artifact'}, until_eot=True)
        self.g.add_continuous_effect(target, 'set_base', power=3, toughness=4, until_eot=True)
        self.assertIn(target, self.g.legal_targets(self.a, effect))
        self.assertTrue(target.card.is_land)
        self.assertTrue(target.card.is_artifact)
        self.assertFalse(target.front.is_creature)
        self.assertEqual((target.power, target.toughness), (3, 4))
        self.g.expire_continuous_effects()
        self.assertFalse(target.is_creature)
        self.assertIs(target.card, target.copiable_card)

    def test_type_and_subtype_timestamp_order(self):
        target = self.g.enter_battlefield(self.a, BEAR)
        self.g.add_continuous_effect(target, 'set_types', types={'Artifact'}, subtypes=())
        self.assertFalse(target.is_creature)
        self.g.add_continuous_effect(target, 'add_types', types={'Creature'})
        self.g.add_continuous_effect(target, 'set_subtypes', subtypes={'Zombie'})
        self.assertTrue(target.is_creature)
        self.assertEqual(target.card.subtypes, {'Zombie'})
        self.g.add_continuous_effect(target, 'remove_types', types={'Artifact'})
        self.assertFalse(target.card.is_artifact)

    def test_color_layers_override_devoid_without_changing_mana_value(self):
        target = self.g.enter_battlefield(self.a, dataclasses.replace(BEAR, keywords=frozenset({'devoid'})))
        self.assertFalse(target.card.colors)
        self.g.add_continuous_effect(target, 'set_colors', colors={'R'})
        self.g.add_continuous_effect(target, 'add_colors', colors={'U'})
        self.g.add_continuous_effect(target, 'remove_colors', colors={'R'})
        self.assertEqual(target.card.colors, {'U'})
        self.assertEqual(target.card.cmc, BEAR.cmc)
        self.assertFalse(target.front.colors)
        self.assertTrue(target.has('devoid'))
        attacker = self.g.enter_battlefield(self.b, dataclasses.replace(BEAR,
            keywords=frozenset({'intimidate'}), color_override=frozenset({'R'})))
        self.assertFalse(can_block(target, attacker))
        self.g.add_continuous_effect(target, 'add_colors', colors={'R'})
        self.assertTrue(can_block(target, attacker))
        self.g.add_continuous_effect(target, 'set_colors', colors=())
        self.assertFalse(target.card.colors)

    def test_type_timestamp_interacts_with_animation(self):
        target = self.g.enter_battlefield(self.a, ISLAND)
        target.animated = Activated('animate', {}, 2, 3)
        self.g.add_continuous_effect(target, 'remove_types', types={'Creature'})
        self.assertFalse(target.is_creature)
        target.animated = Activated('animate', {}, 4, 5)
        self.assertTrue(target.is_creature)
        self.assertEqual(target.power, 4)

    def test_source_lifetime_and_last_known_type_color(self):
        target = self.g.enter_battlefield(self.a, ISLAND)
        source = self.g.enter_battlefield(self.a, BEAR)
        self.g.add_continuous_effect(target, 'add_types', types={'Creature'}, source=source)
        self.g.add_continuous_effect(target, 'set_base', power=3, toughness=3, source=source)
        self.g.add_continuous_effect(target, 'set_colors', colors={'R'})
        self.g.destroy(target)
        self.assertTrue(target.is_creature)
        self.assertEqual(target.card.colors, {'R'})
        self.assertEqual(target.power, 3)
        self.assertFalse(target.front.is_creature)
        self.a.graveyard.remove(target.front)
        returned = self.g.enter_battlefield(self.a, target.front)
        self.assertFalse(returned.is_creature)
        self.assertFalse(returned.card.colors)
        self.g.add_continuous_effect(returned, 'add_types', types={'Creature'}, source=source)
        self.assertTrue(returned.is_creature)
        self.g.destroy(source)
        self.assertFalse(returned.is_creature)

    def test_copy_uses_copiable_values_not_type_color_effects(self):
        target = self.g.enter_battlefield(self.a, BEAR)
        self.g.add_continuous_effect(target, 'set_colors', colors={'R'})
        self.g.add_continuous_effect(target, 'add_types', types={'Artifact'})
        self.g.resolve(self.a, Effect('copy_perm', data={'what': 'creature', 'n': 1}), None)
        copy = next(x for x in self.a.battlefield if x.front.is_token)
        self.assertFalse(copy.card.is_artifact)
        self.assertEqual(copy.card.colors, BEAR.colors)

    def real(self, name):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        try:
            if db._all is None:
                self.skipTest('offline card database required')
            return db.get(name)
        finally:
            if db._all is not None:
                db._all.close()

    def resolve_pending(self):
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()

    def test_baleful_force_triggers_on_both_upkeeps(self):
        definition = self.real('Baleful Force')
        self.assertFalse(definition.unsupported)
        self.g.enter_battlefield(self.a, definition)
        self.a.library = [ISLAND, ISLAND]
        self.g.begin_upkeep(self.a)
        self.resolve_pending()
        self.g.begin_upkeep(self.b)
        self.resolve_pending()
        self.assertEqual((self.a.life, len(self.a.hand)), (18, 2))
        self.assertEqual((self.b.life, len(self.b.hand)), (20, 0))

    def test_copper_tablet_targets_the_upkeep_player(self):
        definition = self.real('Copper Tablet')
        self.assertFalse(definition.unsupported)
        self.g.enter_battlefield(self.a, definition)
        self.g.begin_upkeep(self.b)
        self.resolve_pending()
        self.assertEqual((self.a.life, self.b.life), (20, 19))
        self.g.begin_upkeep(self.a)
        self.resolve_pending()
        self.assertEqual((self.a.life, self.b.life), (19, 19))

    def test_verdant_force_uses_controller_on_opponents_upkeep(self):
        definition = self.real('Verdant Force')
        self.assertFalse(definition.unsupported)
        self.g.enter_battlefield(self.a, definition)
        self.g.begin_upkeep(self.b)
        self.resolve_pending()
        token = next(x for x in self.a.battlefield if x.front.is_token)
        self.assertEqual((token.power, token.toughness, token.card.colors), (1, 1, {'G'}))
        self.assertFalse(self.b.battlefield)

    def test_end_step_source_actions_on_opponents_turn(self):
        runner, dragon = self.real('Arc Runner'), self.real('Archwing Dragon')
        self.assertFalse(runner.unsupported)
        self.assertFalse(dragon.unsupported)
        a = self.g.enter_battlefield(self.a, runner)
        b = self.g.enter_battlefield(self.a, dragon)
        self.g.fire(self.b, 'end_step')
        self.resolve_pending()
        self.assertIn(a.front, self.a.graveyard)
        self.assertIn(b.front, self.a.hand)
        self.assertEqual(self.a.sacrificed_turn, 1)

    def test_angelic_accord_intervening_if_at_trigger_and_resolution(self):
        definition = self.real('Angelic Accord')
        self.assertFalse(definition.unsupported)
        self.g.enter_battlefield(self.a, definition)
        self.g.fire(self.b, 'end_step')
        self.assertFalse(self.g.pending)  # cannot become eligible later
        self.a.life_gained_turn = 4
        self.g.fire(self.b, 'end_step')
        self.assertEqual(len(self.g.pending), 1)
        self.a.life_gained_turn = 0
        self.resolve_pending()
        self.assertFalse(self.a.creatures)  # condition rechecked at resolution
        self.a.life_gained_turn = 4
        self.g.fire(self.b, 'end_step')
        self.resolve_pending()
        angel = self.a.creatures[0]
        self.assertEqual((angel.power, angel.toughness, angel.card.colors), (4, 4, {'W'}))
        self.assertTrue(angel.has('flying'))

    def test_asylum_visitor_context_condition_and_madness_approximation(self):
        definition = self.real('Asylum Visitor')
        self.assertTrue(any('madness' in text for text in definition.approximations))
        self.g.enter_battlefield(self.a, definition)
        self.a.library = [ISLAND, ISLAND]
        self.b.hand = [BEAR]
        self.g.begin_upkeep(self.b)
        self.assertFalse(self.g.pending)
        self.b.hand.clear()
        self.g.begin_upkeep(self.b)
        self.b.hand.append(BEAR)
        self.resolve_pending()
        self.assertEqual(self.a.life, 20)
        self.b.hand.clear()
        self.g.begin_upkeep(self.b)
        self.resolve_pending()
        self.assertEqual((self.a.life, len(self.a.hand)), (19, 1))

    def test_opponent_only_upkeep_and_apnap_order(self):
        each = card('Each watcher', types='Enchantment', text='At the beginning of each upkeep, you gain 1 life.')
        other = card('Other watcher', types='Enchantment', text="At the beginning of each opponent's upkeep, you gain 2 life.")
        self.assertFalse(each.unsupported + other.unsupported)
        self.g.enter_battlefield(self.a, each)
        self.g.enter_battlefield(self.b, other)
        self.g.active_idx = 1
        self.g.begin_upkeep(self.b)
        self.g.flush_triggers()
        self.assertEqual([i.controller for i in self.g.stack], [self.a])
        self.resolve_pending()
        self.g.active_idx = 0
        self.g.begin_upkeep(self.a)
        self.g.flush_triggers()
        self.assertEqual([i.controller for i in self.g.stack], [self.a, self.b])
        self.resolve_pending()
        self.assertEqual((self.a.life, self.b.life), (22, 22))

    def test_unrecognized_phase_condition_stays_partial(self):
        definition = card('Unsupported condition', types='Enchantment',
                          text='At the beginning of each upkeep, if the moon is blue, you gain 1 life.')
        self.assertTrue(definition.unsupported)
        self.assertFalse(definition.triggers)

    def test_multiple_sacrifices_reserve_all_consumed_sources(self):
        first, second = self.treasure(), self.treasure()
        land = self.g.enter_battlefield(self.a, ISLAND)
        definition = card('Two treasures', types='Artifact')
        definition.activated = [Activated('ability', {'U': 1},
            extra_costs={'sacrifice': 'treasure', 'sac_n': 2})]
        source = self.g.enter_battlefield(self.a, definition)
        self.assertTrue(self.g.can_activate(self.a, source, 0))
        self.assertTrue(self.g.activate_ability(self.a, source, 0))
        self.assertTrue(land.tapped)
        self.assertEqual(self.a.sacrificed_turn, 2)
        self.assertNotIn(first, self.a.battlefield)
        self.assertNotIn(second, self.a.battlefield)

    def test_morbid_intervening_condition_is_checked_before_queuing(self):
        definition = card('Morbid watcher', types='Enchantment',
                          text='At the beginning of each end step, if a creature died this turn, you gain 1 life.')
        self.assertFalse(definition.unsupported)
        self.g.enter_battlefield(self.a, definition)
        self.g.fire(self.b, 'end_step')
        self.assertFalse(self.g.pending)
        self.g.creature_died_turn = True
        self.g.fire(self.b, 'end_step')
        self.assertEqual(len(self.g.pending), 1)
        self.g.creature_died_turn = False
        self.resolve_pending()
        self.assertEqual(self.a.life, 20)

    def test_unknown_token_keywords_and_copy_restrictions_stay_visible(self):
        dragon = self.real('Dragon Broodmother')
        self.assertTrue(any('devour 2' in s.lower() for s in dragon.unsupported))
        token_effect = dragon.triggers[0].effects[0]
        self.assertEqual(token_effect.data['name'], 'Dragon')
        self.assertIn('flying', token_effect.data['keywords'])
        octomancer = self.real('Octomancer')
        self.assertTrue(any('entered' in s.lower() for s in octomancer.unsupported))
