"""Library-top search behavior through the existing rules and zone machinery."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, ISLAND, SHOCK, card

TOP = 'Search your library for a card, then shuffle and put that card on top.'
CREATURE = ('Search your library for a creature card, reveal it, '
            'then shuffle and put the card on top.')


class LibraryTopSearch(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(42))
        self.g.turn, self.g.step = 3, 'main1'
        for p in self.g.players:
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def effects(self, text):
        effects, ignored = _parse_effects(text)
        self.assertEqual(ignored, [])
        self.assertEqual(len(effects), 1)
        return effects

    def resolve(self, text):
        effects = self.effects(text)
        item = StackItem(self.a, effects, [None])
        self.g.stack.append(item)
        self.g.settle()
        self.assertTrue(item.resolved)

    def test_selected_physical_duplicate_is_the_next_draw(self):
        self.a.library.extend([BEAR, BEAR, SHOCK, ISLAND])
        selected, other = self.a.library[:2]
        with patch('mtgsim.engine.choose_tutor', return_value=selected):
            self.resolve(TOP)
        self.assertIs(self.a.library[-1], selected)
        self.assertIn(other, self.a.library)
        self.assertEqual(len(self.a.library), 4)
        self.g.draw(self.a)
        self.assertIs(self.a.hand[-1], selected)
        self.assertIs(selected.zone, self.a.hand)
        self.assertIs(selected.owner, self.a)

    def test_all_ordinary_types_are_available_to_unrestricted_search(self):
        self.a.library.extend([BEAR, ISLAND, SHOCK,
                               card('Test walker', '{3}', 'Planeswalker'),
                               card('Test battle', '{3}', 'Battle — Siege'),
                               card('Test artifact', '{2}', 'Artifact'),
                               card('Test enchantment', '{2}', 'Enchantment'),
                               card('Test sorcery', '{1}', 'Sorcery')])
        before = list(self.a.library)
        with patch('mtgsim.engine.choose_tutor', return_value=before[0]) as choose:
            self.resolve(TOP)
        self.assertEqual(choose.call_args.args[2], before)

    def test_creature_filter_excludes_noncreatures(self):
        self.a.library.extend([SHOCK, BEAR, ISLAND])
        creature = self.a.library[1]
        with patch('mtgsim.engine.choose_tutor', return_value=creature) as choose:
            self.resolve(CREATURE)
        self.assertEqual(choose.call_args.args[2], [creature])
        self.assertIs(self.a.library[-1], creature)

    def test_union_accepts_either_type(self):
        self.a.library.extend([SHOCK, BEAR, card('Test sorcery', '{1}', 'Sorcery')])
        selected, sorcery = self.a.library[0], self.a.library[2]
        with patch('mtgsim.engine.choose_tutor', return_value=selected) as choose:
            self.resolve('Search your library for an instant or sorcery card, reveal it, '
                         'then shuffle and put the card on top.')
        self.assertEqual(choose.call_args.args[2], [selected, sorcery])
        self.assertTrue(all(c.name != BEAR.name for c in choose.call_args.args[2]))

    def test_basic_land_filter_rejects_nonbasic_land(self):
        self.a.library.extend([ISLAND, card('Test nonbasic', '', 'Land'), BEAR])
        selected = self.a.library[0]
        with patch('mtgsim.engine.choose_tutor', return_value=selected) as choose:
            self.resolve('Search your library for a basic land card, reveal it, '
                         'then shuffle and put the card on top.')
        self.assertEqual(choose.call_args.args[2], [selected])

    def test_shuffle_occurs_once_before_selected_card_is_reinserted(self):
        self.a.library.extend([SHOCK, ISLAND, BEAR])
        chosen = self.a.library[-1]
        calls = []
        library_type = type(self.a.library)
        real_shuffle = library_type.shuffle
        def shuffle(library, rng):
            if library is self.a.library:
                calls.append(list(library))
                self.assertNotIn(chosen, library)
            return real_shuffle(library, rng)
        with patch('mtgsim.engine.choose_tutor', return_value=chosen), \
                patch.object(library_type, 'shuffle', shuffle):
            self.resolve(CREATURE)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 2)
        self.assertIs(self.a.library[-1], chosen)

    def test_failed_search_still_shuffles_and_announces_search(self):
        self.a.library.extend([ISLAND, SHOCK])
        original = list(self.a.library)
        with patch.object(self.g, 'library_searched') as searched, \
                patch.object(type(self.a.library), 'shuffle') as shuffled:
            self.resolve(CREATURE)
        searched.assert_called_once_with(self.a)
        shuffled.assert_called_once_with(self.g.rng)
        self.assertEqual(list(self.a.library), original)

    def test_empty_library_search_does_not_draw_or_lose(self):
        self.resolve(CREATURE)
        self.assertEqual(list(self.a.hand), [])
        self.assertEqual(self.a.life, 20)
        self.assertIsNone(self.g.winner)

    def test_search_does_not_touch_opponents_zones(self):
        self.a.library.extend([ISLAND])
        self.b.library.extend([BEAR, SHOCK])
        theirs = list(self.b.library)
        self.resolve(TOP)
        self.assertEqual(list(self.b.library), theirs)
        self.assertEqual(list(self.b.hand), [])

    def test_unsupported_search_filters_and_multiple_cards_remain_visible(self):
        for text in ('Search your library for a noncreature card, then shuffle and put the card on top.',
                     'Search your library for a colorless card, then shuffle and put the card on top.',
                     'Search your library for two cards with different names, then shuffle and put those cards on top.',
                     "Search target opponent's library for a card, then shuffle and put that card on top."):
            with self.subTest(text=text):
                effects, ignored = _parse_effects(text)
                self.assertTrue(ignored)
                self.assertEqual(effects, [])

    @unittest.skipUnless(ALL_CARDS.exists(), 'offline card database unavailable')
    def test_offline_candidates_are_full_and_both_pilots_cast_them(self):
        db = CardDB(offline=True)
        for name in ('Vampiric Tutor', 'Imperial Seal', 'Cruel Tutor', 'Worldly Tutor'):
            c = db.get(name)
            self.assertEqual(c.unsupported, [])
            for pilot in (HeuristicAI, BaselineAI):
                with self.subTest(name=name, pilot=pilot.__name__):
                    a, b = Player('a', [], pilot()), Player('b', [], pilot())
                    g = Game(a, b, random.Random(9))
                    g.turn, g.step = 3, 'main1'
                    for p in g.players:
                        p.ai.respond = p.ai.respond_extras = lambda *args: None
                    for _ in range(4):
                        g.enter_battlefield(a, card('Test mana', '', 'Land', '{T}: Add {B}{G}.'))
                    a.library.extend([BEAR, SHOCK])
                    a.hand.append(c)
                    self.assertIsNotNone(a.ai.plan_spell(g, a, c))
                    self.assertTrue(g.cast(a, c))
                    self.assertEqual(a.library[-1].name, BEAR.name)
                    self.assertEqual(a.life, 20 if name == 'Worldly Tutor' else 18)
                    self.assertEqual(len(a.library), 2)
