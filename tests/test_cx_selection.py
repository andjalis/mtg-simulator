"""Behavior for library-top hand selections and their preserved paid-X amounts."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI, BaselineAI
from mtgsim.cards import _parse_effects
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, ISLAND, SHOCK, FOREST, card

ALL_CREATURES = ('Reveal the top four cards of your library. Put all creature cards revealed this way '
                 'into your hand and the rest on the bottom of your library in any order.')


class LibrarySelection(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], HeuristicAI()), Player('b', [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(18))
        self.g.turn, self.g.step = 4, 'main1'
        for p in self.g.players:
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def resolve(self, text, x=0):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        self.assertEqual(len(effects), 1)
        item = StackItem(self.a, effects, [None])
        item.x = x
        self.g.stack.append(item)
        self.g.settle()
        self.assertTrue(item.resolved)
        return item

    def test_all_matching_cards_in_window_are_selected_and_only_remainder_bottomed(self):
        self.a.library.extend([BEAR, SHOCK, ISLAND, BEAR, BEAR, SHOCK])
        before = list(self.a.library)
        selected = before[3:5]
        remainder = [before[2], before[5]]
        untouched = before[:2]
        self.resolve(ALL_CREATURES)
        self.assertEqual(set(self.a.hand), set(selected))
        self.assertEqual(set(self.a.library[:2]), set(remainder))
        self.assertEqual(list(self.a.library[2:]), untouched)
        self.assertFalse(self.a.graveyard)
        self.assertFalse(self.a.exile)

    def test_type_union_is_inclusive(self):
        self.a.library.extend([BEAR, ISLAND, SHOCK])
        selected = set(self.a.library[:2])
        self.resolve('Reveal the top three cards of your library. Put all creature and land cards '
                     'revealed this way into your hand and the rest on the bottom of your library in any order.')
        self.assertEqual(set(self.a.hand), selected)
        self.assertEqual([c.name for c in self.a.library], [SHOCK.name])

    def test_subtype_filter_uses_physical_duplicates(self):
        goblin = card('Test goblin', '{R}', 'Creature — Goblin', '', 1, 1)
        self.a.library.extend([goblin, goblin, BEAR, SHOCK])
        selected = set(self.a.library[:2])
        self.resolve('Reveal the top four cards of your library. Put all Goblin cards revealed this way '
                     'into your hand and the rest on the bottom of your library in any order.')
        self.assertEqual(set(self.a.hand), selected)
        self.assertEqual(len({id(c) for c in self.a.hand}), 2)
        self.assertTrue(all(c.zone is self.a.hand and c.owner is self.a for c in self.a.hand))

    def test_land_subtype_filter_includes_nonbasic_islands(self):
        dual = card('Test dual', '', 'Land — Island Forest')
        self.a.library.extend([ISLAND, FOREST, dual])
        selected = {self.a.library[0], self.a.library[2]}
        self.resolve('Reveal the top three cards of your library. Put all Island cards revealed this way '
                     'into your hand and the rest on the bottom of your library in any order.')
        self.assertEqual(set(self.a.hand), selected)

    def test_comma_then_selection_and_optional_the_in_remainder(self):
        self.a.library.extend([ISLAND, BEAR, SHOCK])
        selected = self.a.library[1]
        self.a.ai.choose_dig = lambda game, me, candidates, keep: [selected]
        self.resolve('Look at the top three cards of your library, then put one of them into your hand '
                     'and rest on the bottom of your library in any order.')
        self.assertIs(self.a.hand[-1], selected)
        self.assertEqual(len(self.a.library), 2)

    def test_selection_is_not_a_draw_scry_search_or_mill(self):
        self.a.library.extend([BEAR, SHOCK, ISLAND, BEAR])
        with patch.object(self.g, 'draw') as draw, patch.object(self.g, 'scry') as scry, \
                patch.object(self.g, 'library_searched') as searched:
            self.resolve(ALL_CREATURES)
        draw.assert_not_called()
        scry.assert_not_called()
        searched.assert_not_called()
        self.assertEqual(self.a.milled_last, [])
        self.assertEqual(len(self.a.hand), 2)

    def test_empty_library_and_no_match_do_not_cause_draw_loss(self):
        self.resolve(ALL_CREATURES)
        self.assertFalse(self.a.lost)
        self.a.library.extend([ISLAND, SHOCK])
        original = set(self.a.library)
        self.resolve(ALL_CREATURES)
        self.assertEqual(set(self.a.library), original)
        self.assertFalse(self.a.hand)
        self.assertFalse(self.a.lost)

    def test_opponent_zones_are_untouched(self):
        self.b.library.extend([BEAR, SHOCK, ISLAND])
        original = list(self.b.library)
        self.resolve(ALL_CREATURES)
        self.assertEqual(list(self.b.library), original)
        self.assertFalse(self.b.hand)

    def test_optional_you_prefix_is_consumed_and_unsupported_cost_has_no_marker(self):
        self.a.library.extend([BEAR, ISLAND, SHOCK])
        self.resolve('You look at the top three cards of your library, then put one of those cards '
                     'into your hand and the rest on the bottom of your library in a random order.')
        self.assertEqual(len(self.a.hand), 1)
        unsupported = card('Test unsupported X cost', '{1}', 'Artifact',
                           '{3}{U}, {T}, Tap X untapped artifacts you control: '
                           'Look at the top X cards of your library. Put one of them into your hand '
                           'and the rest on the bottom of your library in any order.')
        self.assertTrue(unsupported.unsupported)
        self.assertFalse(any('CXSELECTION' in line for line in unsupported.unsupported))

    def test_paid_x_is_preserved_in_card_parser_and_execution_for_both_pilots(self):
        text = ALL_CREATURES.replace('four', 'X')
        for pilot in (HeuristicAI, BaselineAI):
            for printed_mv in (1, 9):
                with self.subTest(pilot=pilot.__name__, printed_mv=printed_mv):
                    spell = card('Test X selection', '{X}{G}', 'Sorcery', text, cmc=printed_mv)
                    self.assertFalse(spell.unsupported)
                    a, b = Player('a', [], pilot()), Player('b', [], pilot())
                    g = Game(a, b, random.Random(23))
                    g.turn, g.step = 3, 'main1'
                    for p in g.players:
                        p.ai.respond = p.ai.respond_extras = lambda *args: None
                    for _ in range(5):
                        g.enter_battlefield(a, FOREST)
                    a.library.extend([BEAR] * 7)
                    chosen = set(a.library[-4:])
                    a.hand.append(spell)
                    self.assertIsNotNone(a.ai.plan_spell(g, a, spell))
                    self.assertTrue(g.cast(a, spell))
                    self.assertEqual(set(a.hand), chosen)
                    self.assertEqual(len(a.library), 3)

    def test_x_zero_and_x_larger_than_library(self):
        text = ALL_CREATURES.replace('four', 'X')
        self.a.library.extend([BEAR, ISLAND])
        original = list(self.a.library)
        self.resolve(text, x=0)
        self.assertEqual(list(self.a.library), original)
        self.assertFalse(self.a.hand)
        self.resolve(text, x=9)
        self.assertEqual([c.name for c in self.a.hand], [BEAR.name])
        self.assertEqual([c.name for c in self.a.library], [ISLAND.name])

    def test_unknown_filters_and_destinations_stay_ignored_without_internal_markers(self):
        cases = [ALL_CREATURES.replace('creature cards', 'colorless cards'),
                 ALL_CREATURES.replace('creature cards', 'nonland cards'),
                 ALL_CREATURES.replace('creature cards', 'artifact creature cards'),
                 ALL_CREATURES.replace('on the bottom of your library in any order', 'into your graveyard')]
        for text in cases:
            with self.subTest(text=text):
                _, ignored = _parse_effects(text)
                self.assertTrue(ignored)
                self.assertFalse(any('CXSELECTION' in line for line in ignored))

    @unittest.skipUnless(ALL_CARDS.exists(), 'offline database unavailable')
    def test_actual_goblin_ringleader_etb_and_enshrined_memories_paid_x(self):
        db = CardDB(offline=True)
        goblin = card('Test goblin', '{R}', 'Creature — Goblin', '', 1, 1)
        self.a.library.extend([goblin, BEAR, goblin, SHOCK])
        expected = {self.a.library[0], self.a.library[2]}
        creature = db.get('Goblin Ringleader')
        self.assertFalse(creature.unsupported)
        self.g.enter_battlefield(self.a, creature)
        self.g.settle()
        self.assertEqual(set(self.a.hand), expected)
        self.a.hand.clear()
        spell = db.get('Enshrined Memories')
        self.assertFalse(spell.unsupported)
        self.a.library = [BEAR] * 7
        expected = set(self.a.library[-4:])
        for _ in range(5):
            self.g.enter_battlefield(self.a, FOREST)
        self.a.hand.append(spell)
        self.assertTrue(self.g.cast(self.a, spell))
        self.assertEqual(set(self.a.hand), expected)
