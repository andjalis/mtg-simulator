"""Whole-zone shuffling, physical identities, draw sequencing and casting modes."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI, BaselineAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, ISLAND, SHOCK, FOREST, card

TARGET = 'Target player shuffles their graveyard into their library.'
RESET = 'Each player shuffles their hand and graveyard into their library, then draws seven cards.'


class WholeZoneRecycling(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], HeuristicAI()), Player('b', [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(21))
        self.g.turn, self.g.step = 3, 'main1'
        self.g.active_idx = 0
        for p in self.g.players:
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def effects(self, text):
        effects, ignored = _parse_effects(text)
        self.assertEqual(ignored, [])
        self.assertEqual(len(effects), 1)
        return effects

    def resolve(self, text, target=None):
        effects = self.effects(text)
        item = StackItem(self.a, effects, [target])
        self.g.stack.append(item)
        self.g.settle()
        return item

    def test_exact_duplicates_move_to_library_with_new_zone_versions(self):
        self.a.library.extend([ISLAND, SHOCK])
        self.a.graveyard.extend([BEAR, BEAR])
        moved = list(self.a.graveyard)
        versions = [c.generation for c in moved]
        expected = set(self.a.library) | set(moved)
        item = self.resolve(TARGET, self.a)
        self.assertTrue(item.resolved)
        self.assertEqual(set(self.a.library), expected)
        self.assertFalse(self.a.graveyard)
        self.assertTrue(all(c.zone is self.a.library and c.owner is self.a for c in moved))
        self.assertTrue(all(c.generation > old for c, old in zip(moved, versions)))
        self.assertEqual(len({id(c) for c in self.a.library}), 4)

    def test_explicit_opponent_target_does_not_touch_caster_zones(self):
        self.a.library.extend([ISLAND, SHOCK])
        self.a.graveyard.append(BEAR)
        original_library = list(self.a.library)
        original_grave = list(self.a.graveyard)
        self.b.graveyard.extend([BEAR, SHOCK])
        expected = set(self.b.graveyard)
        self.resolve(TARGET, self.b)
        self.assertEqual(set(self.b.library), expected)
        self.assertFalse(self.b.graveyard)
        self.assertEqual(list(self.a.library), original_library)
        self.assertEqual(list(self.a.graveyard), original_grave)

    def test_both_players_graveyards_recycle_but_hands_and_exile_do_not(self):
        for p in self.g.players:
            p.library.append(ISLAND)
            p.graveyard.extend([BEAR, SHOCK])
            p.hand.append(BEAR)
            p.exile.append(SHOCK)
        hands = [list(p.hand) for p in self.g.players]
        exiles = [list(p.exile) for p in self.g.players]
        self.resolve('Each player shuffles their graveyard into their library.')
        for i,p in enumerate(self.g.players):
            self.assertEqual(len(p.library), 3)
            self.assertFalse(p.graveyard)
            self.assertEqual(list(p.hand), hands[i])
            self.assertEqual(list(p.exile), exiles[i])

    def test_self_scope_only(self):
        self.a.graveyard.append(BEAR)
        self.b.graveyard.append(SHOCK)
        self.resolve('Shuffle your graveyard into your library.')
        self.assertFalse(self.a.graveyard)
        self.assertEqual(len(self.a.library), 1)
        self.assertEqual(len(self.b.graveyard), 1)
        self.assertFalse(self.b.library)

    def test_one_shuffle_per_player_after_all_their_cards_move(self):
        for p in self.g.players:
            p.library.append(ISLAND)
            p.hand.extend([BEAR, SHOCK])
            p.graveyard.extend([BEAR, SHOCK])
        calls=[]
        real_shuffle=type(self.a.library).shuffle
        def shuffle(zone,rng):
            owner=next(p for p in self.g.players if p.library is zone)
            self.assertFalse(owner.hand)
            self.assertFalse(owner.graveyard)
            self.assertEqual(len(zone),5)
            calls.append(owner)
            return real_shuffle(zone,rng)
        with patch.object(type(self.a.library),'shuffle',shuffle):
            self.resolve('Each player shuffles their hand and graveyard into their library.')
        self.assertEqual(calls,[self.a,self.b])

    def test_all_libraries_recycled_before_first_draw(self):
        for p in self.g.players:
            p.hand.extend([BEAR] * 3)
            p.graveyard.extend([SHOCK] * 5)
        expected=[set(p.hand)|set(p.graveyard) for p in self.g.players]
        real_draw=self.g.draw
        seen=[]
        def draw(player,n=1,**kwargs):
            if not seen:
                self.assertTrue(all(not p.hand and not p.graveyard for p in self.g.players))
                self.assertTrue(all(len(p.library)==8 for p in self.g.players))
            seen.append(player)
            return real_draw(player,n,**kwargs)
        with patch.object(self.g,'draw',draw):
            self.resolve(RESET)
        self.assertEqual(seen,[self.a,self.b])
        for i,p in enumerate(self.g.players):
            self.assertEqual(len(p.hand),7)
            self.assertEqual(len(p.library),1)
            self.assertEqual(set(p.hand)|set(p.library),expected[i])

    def test_draws_use_active_player_order_when_caster_is_nonactive(self):
        self.g.active_idx=1
        for p in self.g.players:
            p.library.extend([ISLAND] * 8)
        actual=[]
        draw=self.g.draw
        def record(player,n=1,**kwargs):
            actual.append(player)
            return draw(player,n,**kwargs)
        with patch.object(self.g,'draw',record):
            self.resolve(RESET)
        self.assertEqual(actual,[self.b,self.a])

    def test_drawing_from_short_libraries_marks_both_losses_after_both_draw_instructions(self):
        for p in self.g.players:
            p.graveyard.append(BEAR)
        self.resolve(RESET)
        self.assertTrue(self.a.lost)
        self.assertTrue(self.b.lost)
        self.assertEqual((len(self.a.hand),len(self.b.hand)),(1,1))

    def test_recycle_without_drawing_does_not_cause_loss(self):
        self.resolve('Each player shuffles their graveyard into their library.')
        self.assertFalse(self.a.lost)
        self.assertFalse(self.b.lost)

    def test_not_discard_search_or_mill(self):
        self.a.hand.extend([BEAR,SHOCK])
        self.a.graveyard.append(ISLAND)
        with patch.object(self.g,'discard_card') as discard, \
                patch.object(self.g,'library_searched') as searched:
            self.resolve('Shuffle your hand and graveyard into your library.')
        discard.assert_not_called()
        searched.assert_not_called()
        self.assertEqual(self.a.milled_last,[])
        self.assertEqual(len(self.a.library),3)

    def test_followup_draw_count_is_general(self):
        self.a.hand.extend([BEAR,SHOCK,ISLAND,FOREST])
        self.resolve('Shuffle your hand and graveyard into your library, then draw two cards.')
        self.assertEqual(len(self.a.hand),2)
        self.assertEqual(len(self.a.library),2)
        self.assertFalse(self.b.hand)

    def test_target_player_is_required_and_illegal_missing_target_fizzles(self):
        self.a.graveyard.append(BEAR)
        item=self.resolve(TARGET,None)
        self.assertFalse(item.resolved)
        self.assertEqual(len(self.a.graveyard),1)

    def test_player_hexproof_prevents_opponent_target(self):
        veil = card('Test player veil', '{W}', 'Enchantment', 'You have hexproof.')
        self.g.enter_battlefield(self.b, veil)
        self.b.graveyard.append(BEAR)
        effect = self.effects(TARGET)[0]
        self.assertFalse(self.g.legal_target(self.a, effect, self.b))
        self.assertTrue(self.g.legal_target(self.a, effect, self.a))
        item = self.resolve(TARGET, self.b)
        self.assertFalse(item.resolved)
        self.assertEqual(len(self.b.graveyard), 1)

    def test_recycled_card_returning_to_graveyard_is_a_new_target_object(self):
        self.a.graveyard.append(BEAR)
        physical = self.a.graveyard[-1]
        effects, ignored = _parse_effects('Put target creature card from your graveyard on top of your library.')
        self.assertFalse(ignored)
        old = StackItem(self.a, effects, [physical])
        self.g.check_ward(old)
        effect = self.effects(TARGET)[0]
        self.g.resolve(self.a, effect, self.a, StackItem(self.a, [effect], [self.a]))
        self.g.move_card(physical, self.a.library, self.a.graveyard)
        self.g.stack.append(old)
        self.g.settle()
        self.assertFalse(old.resolved)
        self.assertIn(physical, self.a.graveyard)

    def test_unknown_subsets_and_non_whole_zone_targets_remain_ignored(self):
        for text in ('Target player shuffles up to four target cards from their graveyard into their library.',
                     'Each player shuffles their hand, graveyard, and all permanents they own into their library, then draws seven cards.',
                     'Shuffle all creature cards from your graveyard into your library.'):
            with self.subTest(text=text):
                effects,ignored=_parse_effects(text)
                self.assertTrue(ignored)
                self.assertFalse(effects)

    @unittest.skipUnless(ALL_CARDS.exists(),'offline database unavailable')
    def test_timetwister_source_is_excluded_and_both_pilots_plan_cast(self):
        spell=CardDB(offline=True).get('Timetwister')
        self.assertFalse(spell.unsupported)
        for pilot in (HeuristicAI,BaselineAI):
            with self.subTest(pilot=pilot.__name__):
                a,b=Player('a',[],pilot()),Player('b',[],pilot())
                g=Game(a,b,random.Random(8));g.turn,g.step=3,'main1'
                for p in g.players:
                    p.ai.respond=p.ai.respond_extras=lambda *args: None
                    p.library.extend([ISLAND] * 10)
                    p.graveyard.extend([BEAR,SHOCK])
                for _ in range(3): g.enter_battlefield(a,ISLAND)
                a.hand.append(spell)
                physical=a.hand[-1]
                plan=a.ai.plan_spell(g,a,spell)
                self.assertIsNotNone(plan)
                self.assertTrue(g.cast(a,spell,plan[1]))
                self.assertEqual((len(a.hand),len(b.hand)),(7,7))
                self.assertIn(physical,a.graveyard)
                self.assertNotIn(physical,a.library)
                self.assertNotIn(physical,a.hand)

    @unittest.skipUnless(ALL_CARDS.exists(),'offline database unavailable')
    def test_flashback_source_stays_on_stack_until_it_is_exiled(self):
        spell=CardDB(offline=True).get('Echo of Eons')
        self.assertFalse(spell.unsupported)
        for p in self.g.players:
            p.library.extend([ISLAND] * 12)
            p.graveyard.append(BEAR)
        self.a.graveyard.append(spell)
        physical=self.a.graveyard[-1]
        for _ in range(3): self.g.enter_battlefield(self.a,ISLAND)
        option=next(c for c in self.g.spell_options(self.a) if self.g._origin(c)[1]=='flashback')
        self.assertTrue(self.g.cast(self.a,option))
        self.assertIn(physical,self.a.exile)
        self.assertNotIn(physical,self.a.library)
        self.assertNotIn(physical,self.a.hand)
        self.assertEqual(len(self.a.hand),7)

    @unittest.skipUnless(ALL_CARDS.exists(),'offline database unavailable')
    def test_exiling_cane_cost_is_not_recycled(self):
        source=self.g.enter_battlefield(self.a,CardDB(offline=True).get("Feldon's Cane"))
        self.a.graveyard.extend([BEAR,SHOCK])
        moved=set(self.a.graveyard)
        self.assertTrue(self.g.activate_ability(self.a,source,0))
        self.assertEqual(set(self.a.library),moved)
        self.assertIn(source.front,self.a.exile)
        self.assertFalse(self.a.graveyard)
