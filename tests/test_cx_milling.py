"""Behavior evidence for additional mill counts and current-resolution selections."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI, BaselineAI
from mtgsim.cards import _parse_effects
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, ISLAND, SHOCK, card


class MillingQuantities(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], HeuristicAI()), Player('b', [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(15))
        self.g.turn, self.g.step = 3, 'main1'
        for p in self.g.players:
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def effects(self, text):
        effects, ignored = _parse_effects(text)
        self.assertEqual(ignored, [])
        return effects

    def resolve(self, text, target=None, x=0):
        effects = self.effects(text)
        item = StackItem(self.a, effects, [target if e.target == 'player' else None for e in effects])
        item.x = x
        self.g.check_ward(item)
        self.g.stack.append(item)
        self.g.settle()
        self.assertTrue(item.resolved)
        return item

    def test_large_number_word_moves_exact_physical_cards(self):
        self.b.library.extend([ISLAND] * 20)
        top = list(reversed(self.b.library[-13:]))
        self.resolve('Target opponent mills thirteen cards.', self.b)
        self.assertEqual(list(self.b.graveyard), top)
        self.assertEqual(len(self.b.library), 7)
        self.assertTrue(all(c.zone is self.b.graveyard and c.owner is self.b for c in top))

    def test_compound_english_count_and_numeric_existing_count(self):
        for text, amount in [('Mill twenty-one cards.', 21), ('Mill ninety-nine cards.', 99),
                             ('Mill 14 cards.', 14), ('Mill eleven cards.', 11)]:
            with self.subTest(text=text):
                self.a.library = [ISLAND] * 105
                before = len(self.a.graveyard)
                self.resolve(text)
                self.assertEqual(len(self.a.library), 105-amount)
                self.assertEqual(len(self.a.graveyard)-before, amount)

    def test_each_opponent_only(self):
        for p in self.g.players:
            p.library.extend([ISLAND] * 20)
        self.resolve('Each opponent mills fourteen cards.')
        self.assertEqual((len(self.a.library), len(self.b.library)), (20, 6))

    def test_each_player(self):
        for p in self.g.players:
            p.library.extend([ISLAND] * 20)
        self.resolve('Each player mills twelve cards.')
        self.assertEqual((len(self.a.library), len(self.b.library)), (8, 8))

    def test_milling_short_library_does_not_lose_until_draw(self):
        self.b.library.extend([ISLAND] * 3)
        self.resolve('Target player mills thirteen cards.', self.b)
        self.assertEqual(len(self.b.graveyard), 3)
        self.assertFalse(self.b.lost)
        self.g.draw(self.b)
        self.assertTrue(self.b.lost)

    def test_x_mill_tracks_only_this_resolution(self):
        self.b.library.extend([ISLAND] * 12)
        first = self.resolve('Target player mills X cards.', self.b, x=4)
        second = self.resolve('Target player mills X cards.', self.b, x=2)
        self.assertEqual(len(self.b.library), 6)
        self.assertEqual(len(first.milled[self.b]), 4)
        self.assertEqual(len(second.milled[self.b]), 2)
        self.assertFalse(set(first.milled[self.b]) & set(second.milled[self.b]))

    def test_x_zero_preserves_library_and_clears_current_mill(self):
        self.b.library.extend([ISLAND] * 3)
        self.resolve('Target player mills X cards.', self.b, x=1)
        item = self.resolve('Target player mills X cards.', self.b, x=0)
        self.assertEqual(len(self.b.library), 2)
        self.assertEqual(item.milled[self.b], [])

    def test_opponent_only_x_target_cannot_be_caster(self):
        effect = self.effects('Target opponent mills X cards.')[0]
        self.assertFalse(self.g.legal_target(self.a, effect, self.a))
        self.assertTrue(self.g.legal_target(self.a, effect, self.b))

    def test_x_life_gain_uses_paid_x_even_if_library_is_short(self):
        self.b.library.append(ISLAND)
        self.resolve('Target player mills X cards and you gain X life.', self.b, x=4)
        self.assertEqual(self.a.life, 24)
        self.assertEqual(len(self.b.graveyard), 1)
        self.assertEqual(self.b.life, 20)

    @unittest.skipUnless(ALL_CARDS.exists(), 'offline card database unavailable')
    def test_paid_x_cast_and_baseline_target_planning_limit(self):
        spell = CardDB(offline=True).get('Psychic Drain')
        self.assertFalse(spell.unsupported)
        for pilot in (HeuristicAI, BaselineAI):
            with self.subTest(pilot=pilot.__name__):
                a,b = Player('a', [], pilot()), Player('b', [], pilot())
                g = Game(a,b,random.Random(9))
                g.turn,g.step=3,'main1'
                for p in g.players:
                    p.ai.respond = p.ai.respond_extras = lambda *args: None
                for _ in range(5):
                    g.enter_battlefield(a, ISLAND)
                g.enter_battlefield(a, card('Test black land', '', 'Land', '{T}: Add {B}.'))
                b.library.extend([ISLAND] * 20)
                a.hand.append(spell)
                plan = a.ai.plan_spell(g,a,spell)
                if pilot is BaselineAI:
                    # Baseline has no mill target policy; explicit legal casting
                    # must still use the paid X and normal resolution.
                    self.assertIsNone(plan)
                    targets = [b, None]
                else:
                    self.assertIsNotNone(plan)
                    targets = plan[1]
                self.assertTrue(g.cast(a,spell,targets))
                self.assertEqual(len(b.graveyard), 4)
                self.assertEqual(a.life, 24)

    def test_selecting_explicitly_milled_type_union_to_battlefield(self):
        ench = card('Test enchantment', '{2}', 'Enchantment')
        self.a.library.extend([SHOCK, BEAR, ench])
        physical = self.a.library[-1]
        with patch('mtgsim.engine.choose_tutor', return_value=physical):
            self.resolve('Mill three cards, then put a creature, enchantment, or land card '
                         'from among cards milled this way onto the battlefield.')
        self.assertTrue(any(p.front is physical for p in self.a.battlefield))
        self.assertEqual(len(self.a.graveyard), 2)
        self.assertEqual(len(self.a.library), 0)

    def test_selection_cannot_reuse_cards_from_prior_resolution(self):
        self.a.library.extend([BEAR])
        self.resolve('Mill one card.')
        old = self.a.graveyard[-1]
        self.a.library.extend([SHOCK])
        self.resolve('Mill one card, then put a creature card from among cards milled this way into your hand.')
        self.assertIn(old, self.a.graveyard)
        self.assertEqual(len(self.a.hand), 0)

    def test_select_any_number_returns_only_matching_current_cards(self):
        self.a.library.extend([BEAR, SHOCK, BEAR, ISLAND])
        physical = [self.a.library[i] for i in (0, 2)]
        self.resolve('Mill four cards, then put any number of creature cards milled this way into your hand.')
        self.assertEqual(set(self.a.hand), set(physical))
        self.assertEqual(len(self.a.graveyard), 2)

    def test_type_filter_and_up_to_bound(self):
        self.a.library.extend([BEAR, SHOCK, BEAR, ISLAND])
        self.resolve('Mill four cards, then put up to one creature card from among cards milled this way into your hand.')
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(self.a.hand[0].name, BEAR.name)
        self.assertEqual(len(self.a.graveyard), 3)

    def test_empty_selection_is_legal(self):
        self.a.library.extend([SHOCK])
        self.resolve('Mill one card, then put a creature card from among cards milled this way onto the battlefield.')
        self.assertEqual(len(self.a.battlefield), 0)
        self.assertEqual(len(self.a.graveyard), 1)

    def test_unknown_filters_stay_ignored(self):
        for text in ('Put a noncreature card from among cards milled this way into your hand.',
                     'Put a creature card with an even mana value from among cards milled this way onto the battlefield.',
                     'Target player mills twice X cards.',
                     'Target player mills half their library, rounded up.'):
            with self.subTest(text=text):
                effects, ignored = _parse_effects(text)
                self.assertTrue(ignored)
                self.assertEqual(effects, [])

    @unittest.skipUnless(ALL_CARDS.exists(), 'offline card database unavailable')
    def test_residual_clauses_stay_visible_and_x_activation_cost_is_not_invented(self):
        db=CardDB(offline=True)
        for name, residual in [('Archive Trap','rather than'),('Increasing Confusion','twice'),
                               ('Sands of Delirium','{X}'),('Vivien on the Hunt','sacrificed')]:
            with self.subTest(name=name):
                c=db.get(name)
                self.assertTrue(any(residual in line for line in c.unsupported))
