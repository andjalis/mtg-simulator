"""Bounded and multiple-card library searches reuse the engine's search effect."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI, BaselineAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, SHOCK, card

LOW = card('Test low creature','{G}','Creature — Elf','',1,1)
HIGH = card('Test high creature','{3}{G}','Creature — Elf','',4,4)
SCOUT = card('Test scout','{1}{W}','Creature — Rebel',
             '{4}, {T}: Search your library for a Rebel permanent card with mana value 3 or less, '
             'put it onto the battlefield, then shuffle.',1,1)


class BoundedTutors(unittest.TestCase):
    def setUp(self):
        self.a,self.b=Player('a',[],HeuristicAI()),Player('b',[],HeuristicAI())
        self.g=Game(self.a,self.b,random.Random(23))
        self.g.turn,self.g.step=3,'main1'
        for p in self.g.players:
            p.ai.respond=p.ai.respond_extras=lambda *args: None

    def resolve(self,text):
        effects,ignored=_parse_effects(text)
        self.assertFalse(ignored,ignored)
        self.assertEqual(len(effects),1)
        item=StackItem(self.a,effects,[None])
        self.g.stack.append(item)
        self.g.settle()
        self.assertTrue(item.resolved)

    def test_multiple_top_search_selects_distinct_physical_duplicates_and_shuffles_once(self):
        self.a.library.extend([LOW,LOW,LOW,SHOCK,ISLAND])
        expected=list(self.a.library[:3])
        with patch.object(type(self.a.library),'shuffle') as shuffled:
            self.resolve('Search your library for up to three creature cards, reveal them, '
                         'then shuffle and put those cards on top in any order.')
        shuffled.assert_called_once_with(self.g.rng)
        self.assertEqual(set(self.a.library[-3:]),set(expected))
        self.assertEqual(len({id(c) for c in self.a.library}),5)
        self.assertEqual(len(self.a.hand),0)
        self.g.draw(self.a,3)
        self.assertEqual(set(self.a.hand),set(expected))

    def test_multiple_top_search_can_find_fewer_than_maximum(self):
        self.a.library.extend([SHOCK,LOW,ISLAND])
        selected=self.a.library[1]
        self.resolve('Search your library for up to three creature cards, reveal them, '
                     'then shuffle and put those cards on top in any order.')
        self.assertIs(self.a.library[-1],selected)
        self.assertEqual(len(self.a.library),3)

    def test_multi_hand_search_respects_mana_value_limit(self):
        self.a.library.extend([LOW,HIGH,LOW,SHOCK])
        expected={self.a.library[0],self.a.library[2]}
        self.resolve('Search your library for up to two creature cards with mana value 1 or less, '
                     'reveal them, put them into your hand, then shuffle.')
        self.assertEqual(set(self.a.hand),expected)
        self.assertEqual(len(self.a.library),2)

    def test_battlefield_filter_honors_mana_value_greater(self):
        self.a.library.extend([LOW,HIGH,SHOCK])
        selected=self.a.library[1]
        self.resolve('Search your library for a creature card with mana value 3 or greater, '
                     'put that card onto the battlefield tapped, then shuffle.')
        self.assertEqual(len(self.a.battlefield),1)
        self.assertIs(self.a.battlefield[0].front,selected)
        self.assertTrue(self.a.battlefield[0].tapped)

    def test_union_applies_limit_to_every_alternative(self):
        lowartifact=card('Test small artifact','{1}','Artifact')
        bigartifact=card('Test big artifact','{5}','Artifact')
        self.a.library.extend([LOW,HIGH,lowartifact,bigartifact,SHOCK])
        wanted=[self.a.library[0],self.a.library[2]]
        with patch('mtgsim.engine.choose_tutor',return_value=wanted[1]) as choose:
            self.resolve('Search your library for a creature or artifact card with mana value 1 or less, '
                         'put it onto the battlefield, then shuffle.')
        self.assertEqual(choose.call_args.args[2],wanted)

    def test_subtype_permanent_excludes_kindred_instant(self):
        rebel=card('Test rebel','{1}','Creature — Rebel','',1,1)
        spell=card('Test rebel instant','{1}','Kindred Instant — Rebel')
        self.a.library.extend([LOW,rebel,spell])
        selected=self.a.library[1]
        with patch('mtgsim.engine.choose_tutor',return_value=selected) as choose:
            self.resolve('Search your library for a Rebel permanent card with mana value 3 or less, '
                         'put it onto the battlefield, then shuffle.')
        self.assertEqual(choose.call_args.args[2],[selected])
        self.assertIs(self.a.battlefield[0].front,selected)

    def test_unrestricted_multi_card_search_includes_all_types(self):
        self.a.library.extend([LOW,SHOCK,ISLAND])
        expected=set(self.a.library)
        self.resolve('Search your library for three cards, put them into your hand, then shuffle.')
        self.assertEqual(set(self.a.hand),expected)
        self.assertEqual(len(self.a.library),0)

    def test_failed_search_still_shuffles_and_fires_library_search_event(self):
        self.a.library.extend([SHOCK,ISLAND])
        with patch.object(type(self.a.library),'shuffle') as shuffled, \
                patch.object(self.g,'library_searched') as searched:
            self.resolve('Search your library for a creature card with mana value 1 or less, '
                         'put it onto the battlefield, then shuffle.')
        shuffled.assert_called_once_with(self.g.rng)
        searched.assert_called_once_with(self.a)
        self.assertEqual(len(self.a.library),2)
        self.assertFalse(self.a.battlefield)

    def test_opponents_library_is_untouched(self):
        self.b.library.extend([LOW,HIGH])
        expected=list(self.b.library)
        self.resolve('Search your library for a creature card with mana value 2 or less, '
                     'put it onto the battlefield, then shuffle.')
        self.assertEqual(list(self.b.library),expected)

    def test_existing_activated_path_pays_and_uses_filter(self):
        scout=self.g.enter_battlefield(self.a,SCOUT)
        scout.sick=False
        rebel=card('Test rebel','{2}','Creature — Rebel','',2,2)
        self.a.library.extend([HIGH,rebel,SHOCK])
        selected=self.a.library[1]
        for _ in range(4):
            self.g.enter_battlefield(self.a,ISLAND)
        self.assertTrue(self.g.activate_ability(self.a,scout,0))
        self.assertTrue(scout.tapped)
        self.assertTrue(any(p.front is selected for p in self.a.battlefield))
        self.assertTrue(all(p.tapped for p in self.a.battlefield if p.card.is_land))

    def test_unknown_bound_filters_stay_ignored(self):
        for text in ('Search your library for a green creature card with mana value 3 or less, '
                     'put it onto the battlefield, then shuffle.',
                     'Search your library for a creature card with mana value X or less, '
                     'put it onto the battlefield, then shuffle.',
                     'Search your library for up to three creature cards with different names, '
                     'reveal them, then shuffle and put those cards on top in any order.'):
            with self.subTest(text=text):
                effects,ignored=_parse_effects(text)
                self.assertTrue(ignored)
                self.assertFalse(effects)

    @unittest.skipUnless(ALL_CARDS.exists(),'offline database unavailable')
    def test_candidate_cast_with_both_pilots_and_ranger_enters_search(self):
        spell=CardDB(offline=True).get('Congregation at Dawn')
        self.assertFalse(spell.unsupported)
        for pilot in (HeuristicAI,BaselineAI):
            with self.subTest(pilot=pilot.__name__):
                a,b=Player('a',[],pilot()),Player('b',[],pilot())
                g=Game(a,b,random.Random(12))
                g.turn,g.step=3,'main1'
                for p in g.players:
                    p.ai.respond=p.ai.respond_extras=lambda *args: None
                for _ in range(3):
                    g.enter_battlefield(a,card('Test mana','', 'Land','{T}: Add {G}{W}.'))
                a.library.extend([LOW,LOW,LOW,SHOCK])
                chosen=set(a.library[:3])
                a.hand.append(spell)
                self.assertIsNotNone(a.ai.plan_spell(g,a,spell))
                self.assertTrue(g.cast(a,spell))
                self.assertEqual(set(a.library[-3:]),chosen)
        ranger=CardDB(offline=True).get('Ranger of Eos')
        self.a.library.extend([LOW,HIGH,LOW])
        self.g.enter_battlefield(self.a,ranger)
        self.g.settle()
        self.assertEqual(len(self.a.hand),2)
        self.assertTrue(all(c.cmc==1 for c in self.a.hand))
