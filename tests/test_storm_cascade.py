"""Cast-triggered keywords must survive removal of their spell and never cast copies."""
import dataclasses
import random
import unittest
from unittest.mock import patch
from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card


class StormCascade(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(3))
        self.game.turn, self.game.step = 2, 'main1'
        self.a.library, self.b.library = [ISLAND]*30, [ISLAND]*30

    def cast(self, text='', who=None, name='Fixture spell', types='Sorcery', cmc=0, targets=()):
        c = card(name, types=types, text=text, cmc=cmc, power=2, toughness=2)
        self.assertFalse(c.unsupported)
        p = who or self.a
        p.hand.append(c)
        self.assertTrue(self.game.cast(p, c, list(targets)))
        self.game.settle()
        return c

    def test_storm_counts_both_players_spells_including_countered(self):
        self.cast(name='First')
        with patch.object(self.game, 'settle'):
            self.cast(who=self.b, name='Second')
        self.game.counter(self.a, Effect('counter', target='spell'), self.game.stack[-1])
        c = self.cast('Storm\nDraw a card.')
        self.assertEqual(len(self.a.hand), 3)
        self.assertEqual(self.game.spells_cast['a'], 2)
        self.assertEqual(self.game.spells_cast['b'], 1)
        self.assertEqual(self.a.graveyard.count(c), 1)

    def test_first_spell_storm_creates_no_copies(self):
        self.cast('Storm\nDraw a card.')
        self.assertEqual(len(self.a.hand), 1)

    def test_multiple_storm_instances_trigger_independently(self):
        self.cast(name='Prior')
        c = self.cast('Storm, storm\nDraw a card.')
        self.assertEqual(c.storm, 2)
        self.assertEqual(len(self.a.hand), 3)

    def test_four_cascade_instances_trigger_independently(self):
        self.a.library = [card(f'Found {i}', types='Creature',cmc=1,power=1,toughness=1) for i in range(4)]
        with patch.object(self.game, 'settle'):
            c = self.cast('Cascade, cascade, cascade, cascade',cmc=10,types='Creature')
        self.assertEqual(c.cascade, 4)
        self.game.flush_triggers()
        self.assertEqual(len(self.game.stack), 5)
        self.game.settle()
        self.assertEqual(len(self.a.creatures), 5)

    def test_storm_resets_next_turn(self):
        self.cast(name='Old spell')
        self.game.turn += 1
        self.cast('Storm\nDraw a card.')
        self.assertEqual(len(self.a.hand), 1)

    def test_storm_count_is_snapshot_at_cast_time(self):
        self.cast(name='Prior spell')
        with patch.object(self.game, 'settle'):
            self.cast('Storm\nDraw a card.')
            self.cast(who=self.b, name='Later spell')
        self.game.settle()
        self.assertEqual(len(self.a.hand), 2)

    def test_storm_trigger_survives_countered_original(self):
        self.cast(name='Prior')
        with patch.object(self.game, 'settle'):
            c = self.cast('Storm\nDraw a card.')
        self.game.counter(self.b, Effect('counter', target='spell'), self.game.stack[-1])
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.assertIn(c, self.a.graveyard)

    def test_countering_storm_trigger_leaves_original(self):
        self.cast(name='Prior')
        with patch.object(self.game, 'settle'):
            self.cast('Storm\nDraw a card.')
        self.game.flush_triggers()
        self.game.counter(self.b, Effect('counter'), self.game.stack[-1])
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_storm_copies_permanent_spells_as_tokens(self):
        self.cast(name='Prior')
        self.cast('Storm', types='Creature', name='Storm creature')
        self.assertEqual(len(self.a.creatures), 2)
        self.assertEqual(sum(x.card.is_token for x in self.a.creatures), 1)
        for x in list(self.a.creatures):
            self.game.destroy(x)
        self.assertEqual(sum(c.name=='Storm creature' for c in self.a.graveyard), 1)

    def test_cascade_strict_less_skips_lands_and_equal_value(self):
        low = card('Small', types='Creature', cmc=2, power=1, toughness=1)
        equal = card('Equal', types='Creature', cmc=4, power=2, toughness=2)
        self.a.library = [low, equal, ISLAND]
        self.cast('Cascade', name='Cascader', types='Creature', cmc=4)
        self.assertEqual({p.card.name for p in self.a.creatures}, {'Small','Cascader'})
        self.assertCountEqual([c.name for c in self.a.library], ['Equal','Island'])
        self.assertEqual(self.a.exile, [])

    def test_cascade_can_cast_sorcery_instantly_without_mana(self):
        found = card('Found', '{4}{U}', 'Sorcery', 'You gain 3 life.', cmc=5)
        self.a.library = [found]
        self.game.active_idx = 1
        self.game.step = 'upkeep'
        self.cast('Cascade', types='Instant', cmc=6)
        self.assertEqual(self.a.life, 23)
        self.assertEqual(self.a.graveyard.count(found), 1)

    def test_cascade_trigger_survives_countered_original(self):
        low = card('Found', types='Creature', cmc=1, power=2, toughness=2)
        self.a.library = [low]
        with patch.object(self.game, 'settle'):
            self.cast('Cascade', cmc=3)
        self.game.counter(self.b, Effect('counter', target='spell'), self.game.stack[-1])
        self.game.settle()
        self.assertEqual(self.a.creatures[0].card.name, 'Found')

    def test_declined_cascade_bottoms_the_hit_and_skipped_cards(self):
        found = card('Found', types='Creature', cmc=1, power=2, toughness=2)
        bottom = card('Untouched', types='Creature', cmc=9, power=2, toughness=2)
        self.a.library = [bottom,found,ISLAND]
        with patch.object(self.a.ai,'choose_cascade',create=True,return_value=False):
            self.cast('Cascade',cmc=3)
        self.assertEqual(self.a.library[-1].name,'Untouched')
        self.assertCountEqual([c.name for c in self.a.library[:2]], ['Found','Island'])
        self.assertEqual(self.a.exile, [])

    def test_cascade_without_a_hit_restores_all_cards(self):
        self.a.library = [ISLAND]*4
        self.cast('Cascade',cmc=1)
        self.assertEqual(self.a.library, [ISLAND]*4)
        self.assertEqual(self.a.exile, [])
        self.assertFalse(self.a.lost)

    def test_cascade_no_legal_target_bottoms_found_card(self):
        found = card('Removal', types='Instant',text='Destroy target creature.',cmc=1)
        self.a.library = [found]
        self.cast('Cascade',cmc=3)
        self.assertEqual(self.a.library, [found])
        self.assertEqual(self.a.exile, [])
        self.assertNotIn(found,self.a.graveyard)

    def test_cascade_obeys_opponents_casting_restriction(self):
        found = card('Found', types='Sorcery', text='You gain 3 life.',cmc=1)
        self.a.library = [found]
        self.game.active_idx = 1
        # Cast legally first, then establish the lock in response before the
        # cascade trigger resolves. The initiating spell is also subject to it.
        with patch.object(self.game, 'settle'):
            self.cast('Cascade',types='Instant',cmc=3)
        self.game.enter_battlefield(self.b, dataclasses.replace(ISLAND,opp_no_cast=True))
        self.game.settle()
        self.assertEqual(self.a.library, [found])
        self.assertEqual(self.a.life, 20)

    def test_cascade_does_not_consume_previously_exiled_identical_card(self):
        found = card('Found',types='Creature',cmc=1,power=2,toughness=2)
        self.a.exile.append(found)
        previously_exiled = self.a.exile[-1]
        self.a.library = [found]
        self.cast('Cascade',cmc=3)
        self.assertEqual(len(self.a.exile),1)
        self.assertIs(self.a.exile[0],previously_exiled)
        self.assertEqual(self.a.creatures[0].card.name,'Found')

    def test_cascade_can_chain_and_counts_each_cast(self):
        little = card('Little',types='Creature',cmc=1,power=1,toughness=1)
        middle = card('Middle',types='Creature',cmc=2,text='Cascade',power=2,toughness=2)
        self.a.library = [little,middle]
        self.cast('Cascade',types='Creature',cmc=3,name='Big')
        self.assertEqual(len(self.a.creatures),3)
        self.assertEqual(self.game.spells_cast['a'],3)

    def test_cascade_storm_permanent_copies_are_tokens(self):
        found = card('Storm body',types='Creature',cmc=1,text='Storm',power=1,toughness=1)
        self.a.library = [found]
        self.cast('Cascade',types='Creature',cmc=3,name='Big')
        bodies=[p for p in self.a.creatures if p.card.name=='Storm body']
        self.assertEqual(len(bodies),2)
        self.assertEqual(sum(p.card.is_token for p in bodies),1)

    def test_cascade_can_cast_adventure_when_main_face_has_no_host(self):
        # A qualifying Aura can have an Adventure; its Aura face cannot be cast here.
        adv = card('Adventure', '{1}', 'Sorcery','You gain 3 life.',cmc=1)
        main = card('Aura adventure', '{2}', 'Enchantment — Aura','Enchant creature',cmc=2)
        main.adventure = adv
        self.a.library = [main]
        self.cast('Cascade',cmc=3)
        self.assertEqual(self.a.life,23)
        self.assertEqual(self.a.on_adventure,[main])
        self.assertEqual(self.a.exile,[])
