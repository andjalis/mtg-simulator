"""Keyword batches: real combat, triggered abilities and AI predictions agree."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI, LETHAL, combat_score, fight_group, simulate_combat
from mtgsim.cards import Effect, card_from_scryfall
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card


class KeywordBatches(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, 'main1'
        self.a.library = [ISLAND] * 30
        self.b.library = [ISLAND] * 30

    def creature(self, who=None, text='', power=2, toughness=4):
        c = card('Test creature', text=text, power=power, toughness=toughness)
        self.assertEqual(c.unsupported, [])
        p = self.game.enter_battlefield(who or self.a, c)
        p.sick = False
        return p

    def damage(self, a, blockers=()):
        self.game.combat_damage(self.a, self.b, [a], {a: list(blockers)} if blockers else {}, lambda _: True)

    def test_infect_combat_poison_and_lifelink(self):
        a = self.creature(text='Infect, lifelink')
        self.damage(a)
        self.assertEqual((self.b.life, self.b.counters['poison'], self.a.life), (20, 2, 22))

    def test_ten_poison_loses(self):
        self.b.counters['poison'] = 8
        self.damage(self.creature(text='Infect'))
        self.assertTrue(self.game.over)

    def test_infect_kills_indestructible_by_zero_toughness(self):
        a = self.creature(text='Infect')
        b = self.creature(self.b, 'Indestructible', toughness=2)
        self.damage(a, [b])
        self.assertNotIn(b, self.b.battlefield)
        self.assertEqual(b.m1, 2)
        self.assertEqual(b.damage, 0)

    def test_first_strike_infect_reduces_return_damage_and_ai_agrees(self):
        a = self.creature(text='Infect, first strike')
        b = self.creature(self.b, power=3, toughness=4)
        expected = fight_group(a, [b])
        self.game.combat_damage(self.a, self.b, [a], {a: [b]}, lambda c: c.has('first strike'))
        self.game.combat_damage(self.a, self.b, [a], {a: [b]}, lambda c: not c.has('first strike'))
        self.assertEqual(a.damage, 1)
        self.assertEqual(b.m1, 2)
        self.assertEqual(expected[0], set())

    def test_infect_trample_assigns_lethal_then_poison(self):
        a = self.creature(text='Infect, trample', power=5)
        b = self.creature(self.b, toughness=2)
        self.assertEqual(fight_group(a, [b], include_poison=True)[4], 3)
        self.damage(a, [b])
        self.assertEqual(self.b.counters['poison'], 3)

    def test_noncombat_infect_and_zero_damage(self):
        a = self.creature(text='Infect, deathtouch, lifelink')
        b = self.creature(self.b)
        self.game.deal_damage(b, 0, self.a, source=a)
        self.assertFalse(b.deathtouched)
        self.game.deal_damage(b, 1, self.a, source=a)
        self.assertEqual((b.m1, b.damage, self.a.life), (1, 0, 21))
        self.game.deal_damage(self.b, 1, self.a, source=a)
        self.assertEqual((self.b.life, self.b.counters['poison']), (20, 1))

    def test_damage_effect_carries_source_for_each_creature(self):
        a = self.creature(text='Infect')
        b = self.creature(self.b)
        item = StackItem(self.a, [], [], source=a)
        self.game.resolve(self.a, Effect('damage', 1, target='each_creature'), None, item)
        self.assertEqual((a.m1, b.m1), (1, 1))

    def test_infect_planeswalker_damage_removes_loyalty(self):
        a = self.creature(text='Infect')
        pw = self.game.enter_battlefield(self.b, dataclasses.replace(card('Walker', types='Planeswalker'), loyalty=5))
        pw.counters['loyalty'] = 5
        self.game.deal_damage(pw, 2, self.a, source=a)
        self.assertEqual(pw.loyalty, 3)
        self.assertEqual(pw.m1, 0)

    def test_soul_scar_only_replaces_noncombat_damage(self):
        mage = self.creature()
        mage.card = dataclasses.replace(mage.card, wither_noncombat=True)
        a, b = self.creature(), self.creature(self.b)
        self.damage(a, [b])
        self.assertEqual((b.damage, b.m1), (2, 0))
        self.game.deal_damage(b, 1, self.a)
        self.assertEqual(b.m1, 1)

    def test_ai_recognizes_poison_lethal_without_changing_state(self):
        a = self.creature(text='Infect')
        self.b.counters['poison'] = 8
        self.assertEqual(combat_score([a], {}, self.a, self.b)[0], LETHAL)
        self.assertEqual((a.power, self.b.life, self.b.counters['poison']), (2, 20, 8))

    def test_devoid_preserves_cost_and_overrides_explicit_colors(self):
        c = card_from_scryfall(dict(name='Devoid creature', mana_cost='{2}{R}', cmc=3,
                                    type_line='Creature', oracle_text='Devoid', colors=['R']))
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.colors, frozenset())
        self.assertEqual((c.mana_cost['R'], c.cmc), (1, 3))

    def test_colors_include_hybrid_and_explicit_indicator(self):
        self.assertEqual(card('Hybrid', '{W/U}').colors, frozenset('WU'))
        c = card_from_scryfall(dict(name='Indicator', type_line='Creature', colors=['G']))
        self.assertEqual(c.colors, frozenset('G'))

    def test_devoid_does_not_receive_colored_spell_discount(self):
        discount = self.creature()
        discount.card = dataclasses.replace(discount.card, cost_discount=[('red', 1)])
        plain = card('Red creature', '{2}{R}')
        devoid = dataclasses.replace(plain, keywords=frozenset({'devoid'}))
        self.assertEqual(self.game.cost_of(self.a, plain)['generic'], 1)
        self.assertEqual(self.game.cost_of(self.a, devoid)['generic'], 2)

    def test_colored_tokens_keep_colors(self):
        spell = card('Tokens', types='Sorcery', text='Create a 1/1 white Soldier creature token.')
        self.assertEqual(spell.unsupported, [])
        self.game.resolve(self.a, spell.spell_effects[0], None)
        self.assertEqual(self.a.creatures[-1].card.colors, frozenset('W'))

    def test_exalted_instances_stack_from_nonattacking_sources(self):
        a = self.creature(text='Exalted')
        self.creature(text='Exalted\nExalted')
        self.game.fire(self.a, 'attacks_alone', context=a)
        self.game.settle()
        self.assertEqual((a.power, a.toughness), (5, 7))

    def test_exalted_trigger_survives_source_removal(self):
        a = self.creature()
        source = self.creature(text='Exalted')
        self.game.fire(self.a, 'attacks_alone', context=a)
        self.game.leave_battlefield(source, 'graveyard')
        self.game.settle()
        self.assertEqual(a.power, 3)

    def test_exalted_actual_attack_and_multiple_attackers(self):
        a, b = self.creature(text='Exalted'), self.creature()
        with patch.object(self.a.ai, 'choose_attackers', return_value=[a, b]):
            self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 16)
        self.assertEqual(a.power, 2)

    def test_exalted_solo_attack_and_prediction_no_double_count(self):
        a = self.creature(text='Exalted')
        cache = {}
        self.assertEqual(simulate_combat([a], {}, cache)[1], 3)
        self.assertEqual(a.power, 2)
        with patch.object(self.a.ai, 'choose_attackers', return_value=[a]):
            self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 17)
        self.assertEqual(simulate_combat([a], {})[1], 3)

    def test_exalted_cache_distinguishes_solo_and_group(self):
        a, b = self.creature(text='Exalted'), self.creature()
        cache = {}
        self.assertEqual(simulate_combat([a], {}, cache)[1], 3)
        self.assertEqual(simulate_combat([a, b], {}, cache)[1], 4)

    def test_fight_uses_each_creatures_infect_and_original_power(self):
        a = self.creature(text='Infect, lifelink', power=2, toughness=5)
        b = self.creature(self.b, text='Infect', power=3, toughness=5)
        item = StackItem(self.a, [], [a, b], source=None)
        self.game.resolve(self.a, Effect('fight', target='creature'), b, item)
        self.assertEqual((a.m1, b.m1, a.damage, b.damage), (3, 2, 0, 0))
        self.assertEqual(self.a.life, 22)

    def test_double_strike_infect_ai_matches_two_damage_steps(self):
        a = self.creature(text='Infect, double strike', power=2, toughness=4)
        b = self.creature(self.b, power=3, toughness=3)
        self.assertEqual(fight_group(a, [b])[0], {b})
        self.game.combat_damage(self.a, self.b, [a], {a: [b]}, lambda c: c.has('double strike'))
        self.damage(a, [b])
        self.assertEqual(a.damage, 1)
        self.assertNotIn(b, self.b.battlefield)

    def test_infect_still_triggers_combat_damage_player_abilities(self):
        a = self.creature(text='Infect\nWhenever this creature deals combat damage to a player, draw a card.')
        self.damage(a)
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(self.b.life, 20)

    def test_exalted_from_subtype_grants_stacks(self):
        a = self.creature()
        source = self.creature()
        source.card = dataclasses.replace(source.card, keyword_sub=[('Human', 'exalted', False)])
        self.game.fire(self.a, 'attacks_alone', context=a)
        self.game.settle()
        self.assertEqual(a.power, 4)
