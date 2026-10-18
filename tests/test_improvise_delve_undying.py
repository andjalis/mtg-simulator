"""Generic payment assistance and undying must commit real costs and respect zone changes."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect, make_token
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card


class ImproviseDelveUndying(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, 'main1'
        self.a.library = [ISLAND] * 30
        self.b.library = [ISLAND] * 30

    def perm(self, c=BEAR, who=None):
        return self.game.enter_battlefield(who or self.a, c)

    def artifact(self, text='', types='Artifact'):
        c = card('Test artifact', types=types, text=text, power=1, toughness=1)
        self.assertFalse(c.unsupported)
        return self.perm(c)

    def spell(self, keyword, cost='{3}{U}', text='Draw a card.', types='Sorcery'):
        c = card('Test spell', cost, types, keyword + '\n' + text)
        self.assertFalse(c.unsupported)
        self.a.hand.append(c)
        return c

    def undying(self, who=None, text='Undying', power=2, toughness=2):
        c = card('Test undying', text=text, power=power, toughness=toughness)
        self.assertFalse(c.unsupported)
        return self.perm(c, who)

    def test_improvise_taps_artifacts_without_sacrificing_treasure(self):
        self.perm(ISLAND)
        rocks = [self.artifact() for _ in range(2)]
        treasure = self.perm(make_token('', 0, 0, kind='treasure', artifact=True))
        c = self.spell('Improvise')
        self.assertTrue(self.game.can_cast_now(self.a, c))
        self.assertTrue(self.game.cast(self.a, c))
        self.assertTrue(all(x.tapped for x in rocks + [treasure]))
        self.assertIn(treasure, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 1)

    def test_improvise_does_not_pay_colored_or_colorless_requirements(self):
        for cost in ('{U}', '{C}'):
            with self.subTest(cost=cost):
                self.artifact()
                c = self.spell('Improvise', cost)
                self.assertFalse(self.game.can_cast_now(self.a, c))
                self.assertFalse(self.game.cast(self.a, c))

    def test_improvise_artifact_creatures_can_be_summoning_sick(self):
        self.perm(ISLAND)
        a = self.artifact(types='Artifact Creature')
        self.assertTrue(a.sick)
        c = self.spell('Improvise', '{1}{U}')
        self.assertTrue(self.game.cast(self.a, c))
        self.assertTrue(a.tapped)

    def test_improvise_rejects_tapped_and_opponents_artifacts(self):
        self.perm(ISLAND)
        self.artifact().tapped = True
        other = self.artifact()
        self.a.battlefield.remove(other)
        other.controller = self.b
        self.b.battlefield.append(other)
        c = self.spell('Improvise', '{1}{U}')
        self.assertFalse(self.game.cast(self.a, c))
        self.assertFalse(other.tapped)

    def test_artifact_mana_cannot_also_improvise_same_spell(self):
        mana = self.artifact('{T}: Add {U}.')
        c = self.spell('Improvise', '{1}{U}')
        self.assertFalse(self.game.can_cast_now(self.a, c))
        self.assertFalse(self.game.cast(self.a, c))
        self.assertFalse(mana.tapped)
        helper = self.artifact()
        self.assertTrue(self.game.can_cast_now(self.a, c))
        self.assertTrue(self.game.cast(self.a, c))
        self.assertTrue(mana.tapped and helper.tapped)

    def test_multi_mana_artifact_uses_mana_instead_of_improvising(self):
        ring = self.artifact('{T}: Add {C}{C}.')
        c = self.spell('Improvise', '{2}')
        self.assertTrue(self.game.cast(self.a, c))
        self.assertTrue(ring.tapped)

    def test_mana_ability_helper_cannot_also_improvise(self):
        mana = self.artifact('{T}: Add {C}.')
        mana.card = dataclasses.replace(mana.card, mana_tap_other='permanent')
        helper = self.artifact()
        c = self.spell('Improvise', '{1}{C}')
        self.assertFalse(self.game.can_cast_now(self.a, c))
        self.assertFalse(self.game.cast(self.a, c))
        self.assertFalse(mana.tapped or helper.tapped)

    def test_improvise_can_pay_through_activation_stopping_effect(self):
        lock = self.perm()
        lock.card = dataclasses.replace(lock.card, stops_activations=True)
        a = self.artifact()
        c = self.spell('Improvise', '{1}')
        self.assertTrue(self.game.cast(self.a, c))
        self.assertTrue(a.tapped)

    def test_planning_improvise_is_repeatable_and_does_not_spend(self):
        self.perm(ISLAND)
        a = self.artifact()
        c = self.spell('Improvise', '{1}{U}')
        for _ in range(3):
            self.assertEqual(self.game.cost_of(self.a, c), {'generic': 0, 'U': 1})
            self.assertTrue(self.game.can_cast_now(self.a, c))
        self.assertFalse(a.tapped)
        self.assertIn(c, self.a.hand)

    def test_delve_exiles_only_needed_cards_and_keeps_colored_cost(self):
        self.perm(ISLAND)
        self.a.graveyard.extend([ISLAND] * 5)
        c = self.spell('Delve')
        self.assertTrue(self.game.cast(self.a, c))
        self.assertEqual(len(self.a.exile), 3)
        self.assertEqual(len(self.a.graveyard), 3)  # two remaining cards and the spell
        self.assertEqual(c.cmc, 4)

    def test_delve_cannot_replace_colored_mana(self):
        self.a.graveyard.extend([ISLAND] * 10)
        c = self.spell('Delve', '{2}{U}')
        self.assertFalse(self.game.cast(self.a, c))
        self.assertEqual(len(self.a.graveyard), 10)
        self.assertEqual(self.a.exile, [])

    def test_delve_can_combine_graveyard_and_mana(self):
        for _ in range(3):
            self.perm(ISLAND)
        self.a.graveyard.append(BEAR)
        c = self.spell('Delve', '{3}{U}')
        self.assertTrue(self.game.cast(self.a, c))
        self.assertEqual(self.a.exile, [BEAR])

    def test_delve_cost_reductions_apply_before_exiling(self):
        self.perm(ISLAND)
        discount = self.perm()
        discount.card = dataclasses.replace(discount.card, cost_discount=[('instant and sorcery', 2)])
        self.a.graveyard.extend([BEAR] * 5)
        c = self.spell('Delve')
        self.assertTrue(self.game.cast(self.a, c))
        self.assertEqual(len(self.a.exile), 1)

    def test_delve_planning_does_not_move_cards(self):
        self.perm(ISLAND)
        self.a.graveyard.extend([BEAR] * 3)
        c = self.spell('Delve')
        for _ in range(3):
            self.assertTrue(self.game.can_cast_now(self.a, c))
        self.assertEqual(len(self.a.graveyard), 3)
        self.assertEqual(self.a.exile, [])

    def test_delve_cannot_exile_spell_being_cast_from_graveyard(self):
        c = self.spell('Delve', '{1}')
        self.a.hand.remove(c)
        self.a.graveyard.append(c)
        variant = dataclasses.replace(c)
        variant.origin = (c, 'flashback', None)
        self.assertFalse(self.game.cast(self.a, variant))
        self.assertEqual(self.a.graveyard, [c])

    def test_countered_spell_keeps_assistance_costs_paid(self):
        self.perm(ISLAND)
        self.a.graveyard.extend([BEAR] * 3)
        c = self.spell('Delve')
        with patch.object(self.game, 'settle'):
            self.assertTrue(self.game.cast(self.a, c))
        self.game.counter(self.b, Effect('counter', target='spell'), self.game.stack[-1])
        self.assertEqual(len(self.a.exile), 3)

    def test_delve_can_pay_x_and_preserves_stack_x(self):
        self.perm(ISLAND)
        self.a.graveyard.extend([BEAR] * 4)
        c = self.spell('Delve', '{X}{U}')
        with patch.object(self.game, 'settle'):
            self.assertTrue(self.game.cast(self.a, c))
        self.assertEqual(self.game.stack[-1].x, 4)
        self.assertEqual(self.game.stack[-1].mana_spent, 1)

    def test_improvise_can_pay_x(self):
        self.perm(ISLAND)
        rocks = [self.artifact() for _ in range(3)]
        c = self.spell('Improvise', '{X}{U}')
        with patch.object(self.game, 'settle'):
            self.assertTrue(self.game.cast(self.a, c))
        self.assertEqual(self.game.stack[-1].x, 3)
        self.assertTrue(all(x.tapped for x in rocks))

    def test_undying_returns_as_new_permanent_with_counter(self):
        a = self.undying()
        self.game.destroy(a)
        self.assertNotIn(a, self.a.battlefield)
        self.assertTrue(self.game.pending)
        self.game.settle()
        b = self.a.creatures[0]
        self.assertIsNot(a, b)
        self.assertEqual((b.power, b.toughness, b.p1, b.damage), (3, 3, 1, 0))
        self.game.destroy(b)
        self.game.settle()
        self.assertEqual(self.a.creatures, [])

    def test_undying_counter_removed_allows_another_return(self):
        a = self.undying()
        a.counters['+1/+1'] = 1
        a.counters['-1/-1'] = 1
        self.game.state_based_actions()
        self.game.destroy(a)
        self.game.settle()
        self.assertEqual(len(self.a.creatures), 1)
        self.assertEqual(self.a.creatures[0].p1, 1)

    def test_counter_cancellation_at_lethal_does_not_trigger_undying(self):
        a = self.undying()
        a.counters.update({'+1/+1': 1, '-1/-1': 3})
        self.game.state_based_actions()
        self.game.settle()
        self.assertEqual(self.a.creatures, [])

    def test_undying_sacrifice_and_tokens(self):
        a = self.undying()
        self.game.sacrifice(a)
        self.game.settle()
        self.assertEqual(self.a.creatures[0].p1, 1)
        token = self.perm(make_token('Undying', 1, 1, {'undying'}))
        self.game.sacrifice(token)
        self.game.settle()
        self.assertEqual(len(self.a.creatures), 1)

    def test_undying_does_not_replace_exile_or_finality(self):
        a = self.undying()
        a.counters['finality'] = 1
        self.game.destroy(a)
        self.game.settle()
        self.assertEqual(self.a.creatures, [])
        self.assertEqual(len(self.a.exile), 1)

    def test_undying_fails_if_card_exiled_in_response(self):
        a = self.undying()
        self.game.destroy(a)
        self.a.exile.append(self.a.graveyard.pop())
        self.game.settle()
        self.assertEqual(self.a.creatures, [])

    def test_stale_undying_does_not_return_same_card_reentering_graveyard(self):
        a = self.undying()
        self.game.destroy(a)
        c = self.a.graveyard.pop()
        self.a.graveyard.append(c)
        self.game.settle()
        self.assertEqual(self.a.creatures, [])

    def test_simultaneous_identical_cards_return_independently(self):
        a = self.undying()
        b = self.perm(a.card)
        self.game.destroy(a)
        self.game.destroy(b)
        self.a.graveyard.pop(0)  # remove the first physical copy
        self.game.settle()
        self.assertEqual(len(self.a.creatures), 1)
        self.assertEqual(self.a.creatures[0].p1, 1)

    def test_undying_returns_stolen_creature_to_owner(self):
        a = self.undying()
        self.a.battlefield.remove(a)
        self.b.battlefield.append(a)
        a.controller = self.b
        self.game.destroy(a)
        self.assertEqual(len(self.a.graveyard), 1)
        self.assertIs(self.game.pending[0][0], self.b)
        self.game.settle()
        self.assertEqual((len(self.a.creatures), len(self.b.creatures)), (1, 0))

    def test_undying_counter_is_present_for_etb_trigger(self):
        a = self.undying(text='Undying\nWhen this creature enters, draw a card.')
        self.game.settle()
        self.game.destroy(a)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(self.a.creatures[0].p1, 1)

    def test_granted_undying_uses_keyword_at_death(self):
        a = self.perm()
        a.temp_kw.add('undying')
        self.game.destroy(a)
        self.game.settle()
        b = self.a.creatures[0]
        self.assertEqual(b.p1, 1)
        self.assertFalse(b.has('undying'))
