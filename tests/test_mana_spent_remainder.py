"""Casting-payment predicates refer to the watched or targeted spell."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cards import Effect, _parse_effects
from mtgsim.cx_condlib import parse
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card


class ManaRemainder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    @classmethod
    def tearDownClass(cls):
        if cls.db._all is not None:
            cls.db._all.close()

    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step, self.g._priority_depth = 2, 'main1', 1
        for p in self.g.players:
            p.library = [ISLAND] * 30
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def real_card(self, name):
        if self.db._all is None:
            self.skipTest('card database not built')
        return self.db.get(name)

    def drain(self):
        while self.g.stack or self.g.pending:
            self.g.flush_triggers()
            self.g.resolve_top()

    def watch(self, name):
        return self.g.enter_battlefield(self.a, self.real_card(name))

    def mana(self, p, *colors):
        for i, color in enumerate(colors):
            land = card(f'{color} source {i}', types='Land', text=f'{{T}}: Add {{{color}}}.')
            self.g.enter_battlefield(p, land)

    def cast(self, p, cost, types='Instant', text='', name='Watched spell'):
        c = card(name, cost=cost, types=types, text=text)
        p.hand.append(c)
        c = p.hand[-1]
        self.assertTrue(self.g.cast(p, c))
        return next(s for s in self.g.stack if s.card is not None and s.card.name == name)

    def condition(self, phrase, *, item=None, prev=None):
        code = parse(phrase)
        self.assertTrue(code, phrase)
        return self.g.check_cond(self.a, Effect('condition', cond=code), item, prev)

    def test_no_mana_self_condition_uses_cast_not_mana_value(self):
        spell = StackItem(self.a, [], [], card=card('Large spell', '{8}', 'Sorcery'))
        self.assertTrue(self.condition('no mana was spent to cast ~', item=spell))
        spell.mana_spent = 1
        self.assertFalse(self.condition('no mana was spent to cast ~', item=spell))

    def test_spell_target_precedes_counterspells_own_payment(self):
        target = StackItem(self.b, [], [], card=card('Target', '{8}', 'Sorcery'))
        counter = StackItem(self.a, [], [], card=self.real_card('Nix'))
        counter.mana_spent = 1
        self.assertTrue(self.condition('no mana was spent to cast it', item=counter, prev=target))
        target.mana_spent = 1
        counter.mana_spent = 0
        self.assertFalse(self.condition('no mana was spent to cast it', item=counter, prev=target))

    def test_missing_that_spell_reference_does_not_use_watcher(self):
        src = self.g.enter_battlefield(self.a, card('Expensive watcher', '{9}', 'Enchantment'))
        src.mana_spent = 9
        trigger = StackItem(self.a, [], [], source=src)
        self.assertFalse(self.condition('four or more mana was spent to cast that spell', item=trigger))
        self.assertFalse(self.condition('no mana was spent to cast that spell', item=trigger))

    def test_bauble_counters_either_players_free_cast(self):
        self.watch('Vexing Bauble')
        for p in (self.a, self.b):
            item = self.cast(p, '{0}')
            self.g.flush_triggers()
            self.assertTrue(any(s.context is item for s in self.g.stack if s.kind == 'trigger'))
            self.drain()
            self.assertNotIn(item, self.g.stack)
            self.assertTrue(any(c.name == 'Watched spell' for c in p.graveyard))

    def test_bauble_allows_paid_cast(self):
        self.watch('Vexing Bauble')
        self.mana(self.b, 'C')
        self.cast(self.b, '{1}', text='Draw a card.')
        self.assertFalse(self.g.pending)
        self.drain()
        self.assertEqual(len(self.b.hand), 1)

    def test_bauble_does_not_trigger_for_copy(self):
        from mtgsim.copies import copy_spell
        self.watch('Vexing Bauble')
        original = StackItem(self.b, [], [], card=card('Original', types='Instant'))
        original.x = 4
        self.g.stack.append(original)
        copy_spell(self.g, self.b, original)
        self.assertFalse(self.g.pending)

    def test_bauble_uncounterable_and_removed_spell(self):
        self.watch('Vexing Bauble')
        item = self.cast(self.b, '{0}')
        item.uncounterable = True
        self.g.flush_triggers()
        self.g.resolve_top()
        self.assertIn(item, self.g.stack)
        item.uncounterable = False
        self.g.stack.remove(item)
        # A trigger that outlives the spell must not counter a different item.
        self.g.queue_trigger(self.a, [Effect('counter_context')], context=item)
        other = StackItem(self.b, [], [], card=card('Other', types='Instant'))
        self.g.stack.append(other)
        self.g.flush_triggers()
        self.g.resolve_top()
        self.assertIn(other, self.g.stack)

    def test_vortex_damages_the_caster_in_both_directions(self):
        self.watch('Roiling Vortex')
        self.cast(self.b, '{0}')
        self.drain()
        self.assertEqual((self.a.life, self.b.life), (20, 15))
        self.cast(self.a, '{0}')
        self.drain()
        self.assertEqual((self.a.life, self.b.life), (15, 15))

    def test_void_mirror_distinguishes_colorless_from_colored(self):
        self.watch('Void Mirror')
        self.mana(self.b, 'C')
        self.cast(self.b, '{1}', text='Draw a card.')
        self.drain()
        self.assertEqual(len(self.b.hand), 0)
        self.mana(self.b, 'U')
        self.cast(self.b, '{1}', text='Draw a card.')
        self.drain()
        self.assertEqual(len(self.b.hand), 1)

    def test_void_mirror_free_cast_and_unused_source_colors(self):
        self.watch('Void Mirror')
        self.mana(self.b, 'U')
        self.cast(self.b, '{0}', text='Draw a card.')
        self.drain()
        self.assertEqual(len(self.b.hand), 0)

    def test_nix_resolves_against_target_payment(self):
        c = self.real_card('Nix')
        self.assertFalse(c.unsupported)
        self.mana(self.a, 'U')
        target = self.cast(self.b, '{0}', text='Draw a card.')
        self.a.hand.append(c)
        self.assertTrue(self.g.cast(self.a, self.a.hand[-1], [target]))
        self.drain()
        self.assertEqual(len(self.b.hand), 0)

    def test_nix_does_not_counter_paid_spell(self):
        c = self.real_card('Nix')
        self.mana(self.a, 'U')
        self.mana(self.b, 'C')
        target = self.cast(self.b, '{1}', text='Draw a card.')
        self.a.hand.append(c)
        self.assertTrue(self.g.cast(self.a, self.a.hand[-1], [target]))
        self.drain()
        self.assertEqual(len(self.b.hand), 1)

    def test_tellah_threshold_reads_cast_context_and_x(self):
        c = self.real_card('Tellah, Great Sage')
        self.assertFalse(any('four or more' in s for s in c.unsupported))
        src = self.g.enter_battlefield(self.a, c)
        src.mana_spent = 9
        self.mana(self.a, 'C', 'C', 'C', 'C')
        self.cast(self.a, '{X}', name='X Spell')
        self.drain()
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(len([x for x in self.a.creatures if x.card.is_token]), 1)

    def test_mana_spent_it_uses_spell_not_source(self):
        c = self.real_card('Blazing Bomb')
        self.assertFalse(c.unsupported)
        src = self.g.enter_battlefield(self.a, c)
        src.mana_spent = 9
        self.cast(self.a, '{0}')
        self.drain()
        self.assertEqual(src.p1, 0)
        self.mana(self.a, 'C', 'C', 'C', 'C')
        self.cast(self.a, '{4}')
        self.drain()
        self.assertEqual(src.p1, 1)

    def test_no_mana_includes_additional_cost_on_free_spell(self):
        self.watch('Vexing Bauble')
        self.g.enter_battlefield(self.a, card('Tax', types='Artifact', text='Spells cost {1} more to cast.'))
        self.mana(self.b, 'C')
        self.cast(self.b, '{0}', text='Draw a card.')
        self.assertFalse(self.g.pending)
        self.drain()
        self.assertEqual(len(self.b.hand), 1)

    def test_self_and_trigger_referents_are_distinct(self):
        src = self.g.enter_battlefield(self.a, card('Watcher', types='Enchantment'))
        src.mana_spent = 1
        spell = StackItem(self.b, [], [], card=card('Spell', '{7}', 'Instant'))
        spell.mana_spent = 7
        item = StackItem(self.a, [], [], source=src, context=spell)
        self.assertTrue(self.condition('four or more mana was spent to cast that spell', item=item))
        self.assertFalse(self.condition('four or more mana was spent to cast ~', item=item))

    def test_free_spell_with_paid_x_is_not_free(self):
        self.watch('Vexing Bauble')
        self.mana(self.b, 'C', 'C')
        item = self.cast(self.b, '{X}')
        self.assertEqual(item.x, 2)
        self.assertFalse(self.g.pending)

    def test_no_mana_conditional_body_parses(self):
        effects, bad = _parse_effects('If no mana was spent to cast ~, draw a card.')
        self.assertFalse(bad)
        self.assertEqual([e.kind for e in effects], ['draw'])


if __name__ == '__main__':
    unittest.main()
