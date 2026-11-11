"""Resolving counter durations end once; replacing the counter never revives them."""
import random
import unittest
from pathlib import Path

from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / 'mtgsim/data/cards.sqlite3'
FEATHER = ('You may put a feather counter on target creature. If you do, that creature has base power and '
           'toughness 3/1 and has flying for as long as it has a feather counter on it.')
BOUNTY = ('Put a bounty counter on target creature an opponent controls. For as long as that creature has a '
          'bounty counter on it, it has "When ~ dies, each opponent draws a card and gains 2 life."')
BLAZE = ('Put a blaze counter on target land without a blaze counter on it. For as long as that land has a '
         'blaze counter on it, it has "At the beginning of your upkeep, ~ deals 1 damage to you."')


class CounterDurations(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(4))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def put(self, definition=BEAR, player=None):
        return self.g.enter_battlefield(player or self.a, definition)

    def apply(self, text, target, source=None):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [])
        targets = [target if e.target == 'permanent' else None for e in effects]
        self.g.stack.append(StackItem(self.a, effects, targets, source=source, kind='ability'))
        self.g.resolve_top()

    def test_base_stats_use_layers_and_survive_source_departure(self):
        bear, source = self.put(player=self.b), self.put()
        bear.counters['+1/+1'] = 2
        self.apply(FEATHER, bear, source)
        self.assertEqual((bear.power, bear.toughness), (5, 3))
        self.assertTrue(bear.has('flying'))
        self.g.destroy(source)
        self.g.settle()
        self.assertEqual((bear.power, bear.toughness), (5, 3))
        self.g.add_continuous_effect(bear, 'set_base', power=4, toughness=4)
        self.assertEqual((bear.power, bear.toughness), (6, 6))
        self.g.add_continuous_effect(bear, 'remove', keyword='flying')
        self.assertFalse(bear.has('flying'))
        self.apply(FEATHER, bear)
        self.assertEqual((bear.power, bear.toughness), (5, 3))
        self.assertTrue(bear.has('flying'))

    def test_last_counter_ends_effect_and_replacement_does_not_restart_it(self):
        bear = self.put()
        self.apply(FEATHER, bear)
        bear.counters['feather'] = 2
        bear.counters['feather'] -= 1
        self.assertEqual(bear.power, 3)
        bear.counters['feather'] = 0
        bear.counters['feather'] = 1  # no intermediate stat or keyword query
        self.assertEqual((bear.power, bear.toughness), (2, 2))
        self.assertFalse(bear.has('flying'))
        self.apply(FEATHER, bear)
        self.assertTrue(bear.has('flying'))

    def test_all_counter_removal_operations_expire(self):
        for remove in (lambda c: c.clear(), lambda c: c.pop('feather'),
                       lambda c: c.__delitem__('feather'), lambda c: c.popitem()):
            with self.subTest(remove=remove):
                bear = self.put()
                self.apply(FEATHER, bear)
                remove(bear.counters)
                bear.counters['feather'] = 1
                self.assertFalse(bear.has('flying'))

    def test_cannot_put_counters_does_not_create_if_you_do_effect(self):
        bear = self.put()
        bear.counters['feather'] = 1
        self.put(card('Test Solemnity', '{2}{W}', 'Enchantment',
                      "Counters can't be put on artifacts, creatures, enchantments, or lands."))
        self.apply(FEATHER, bear)
        self.assertEqual(bear.counters['feather'], 1)
        self.assertEqual(bear.power, 2)
        self.assertFalse(bear.has('flying'))

    def test_bounty_grants_die_trigger_after_source_leaves_and_control_changes(self):
        bear, source = self.put(player=self.b), self.put()
        self.apply(BOUNTY, bear, source)
        self.g.destroy(source)
        from mtgsim.counter_mechanics import add_control
        add_control(self.g, bear, self.a)
        self.g.destroy(bear)
        self.g.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 22))
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, 1))

    def test_bounty_removed_then_replaced_grants_no_die_trigger(self):
        bear = self.put(player=self.b)
        self.apply(BOUNTY, bear)
        bear.counters['bounty'] = 0
        bear.counters['bounty'] = 1
        self.g.destroy(bear)
        self.g.settle()
        self.assertEqual(self.a.life, 20)
        self.assertEqual(len(self.a.hand), 0)

    def test_blaze_is_damage_from_the_land_and_can_be_prevented(self):
        land, source = self.put(FOREST, self.b), self.put()
        self.apply(BLAZE, land, source)
        self.g.destroy(source)
        self.g.settle()
        land.temp_kw.add('lifelink')
        self.g.fire(self.b, 'upkeep')
        self.g.settle()
        self.assertEqual(self.b.life, 20)  # one damage and one life from the land's lifelink
        land.temp_kw.clear()
        self.b.prevent_next = 1
        self.g.fire(self.b, 'upkeep')
        self.g.settle()
        self.assertEqual(self.b.life, 20)
        self.assertEqual(self.b.prevent_next, 0)
        self.g.fire(self.b, 'upkeep')
        self.g.settle()
        self.assertEqual(self.b.life, 19)

    def test_blink_loses_effects_and_readding_counter_is_not_a_new_grant(self):
        bear = self.put()
        self.apply(FEATHER, bear)
        self.g.leave_battlefield(bear, 'exile')
        physical = self.a.exile.pop()
        new = self.g.enter_battlefield(self.a, physical)
        new.counters['feather'] = 1
        self.assertFalse(new.has('flying'))
        self.assertEqual(new.power, 2)

    def test_untracked_referents_and_unsupported_payloads_stay_unmatched(self):
        for text in ('Put a feather counter on target creature. If you do, that creature has base power and '
                     'toughness 3/1 and has flying for as long as it has a different counter on it.',
                     'For as long as that land has a blaze counter on it, it has "At the beginning of your '
                     'upkeep, ~ deals 1 damage to you."',
                     "Put a flood counter on target land. That land is an Island for as long as it has a flood counter on it."):
            self.assertTrue(_parse_effects(text)[1], text)

    @unittest.skipUnless(DB_FILE.exists(), 'offline card database not built')
    def test_real_oracle(self):
        db = CardDB(offline=True)
        for name in ('Aven Mimeomancer', 'Mathas, Fiend Seeker', 'Obsidian Fireheart'):
            self.assertEqual(db.get(name).unsupported, [], name)
