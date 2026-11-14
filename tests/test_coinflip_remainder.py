"""Counted coin flips, retained replacement results, and honest unsupported wording."""
import dataclasses
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card
from tests.test_combat_triggers import Scripted


class Coins(random.Random):
    def __new__(cls, *wins):
        # Python 3.10's Random.__new__ rejects extra arguments in subclasses (fixed in 3.11).
        return super().__new__(cls)

    def __init__(self, *wins):
        super().__init__(0)
        self.results = iter(wins)
        self.calls = 0

    def random(self):
        self.calls += 1
        return 0.0 if next(self.results) else 0.99


class CoinRemainder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    @classmethod
    def tearDownClass(cls):
        if cls.db._all is not None:
            cls.db._all.close()

    def real_card(self, name):
        if self.db._all is None:
            self.skipTest("card database not built")
        return self.db.get(name)

    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 30
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def resolve(self, text, *wins, x=0):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, [None] * len(effects))
        item.x = x
        self.g.rng = Coins(*wins)
        self.g.stack.append(item)
        self.g.resolve_top()
        return item

    def test_loop_counts_wins_and_stops_at_first_loss(self):
        item = self.resolve('Flip a coin until you lose a flip. For each flip you won, draw a card.',
                            True, True, False)
        self.assertEqual((item.flips_won, item.flips_lost), (2, 1))
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(self.g.rng.calls, 3)

    def test_immediate_loss_has_no_payoff(self):
        self.resolve('Flip a coin until you lose a flip. For each flip you won, draw a card.', False)
        self.assertEqual(len(self.a.hand), 0)

    def test_fixed_count_and_both_payoffs(self):
        item = self.resolve('Flip three coins. For each flip you win, draw a card. '
                            'For each flip you lose, you lose 2 life.', True, False, True)
        self.assertEqual((item.flips_won, item.flips_lost), (2, 1))
        self.assertEqual((len(self.a.hand), self.a.life), (2, 18))

    def test_x_flips_and_zero_x(self):
        text = 'Flip X coins. For each flip you win, draw a card.'
        self.resolve(text, True, False, True, x=3)
        self.assertEqual(len(self.a.hand), 2)
        item = self.resolve(text, x=0)
        self.assertEqual(item.flips_won, 0)
        self.assertEqual(self.g.rng.calls, 0)
        self.assertEqual(len(self.a.hand), 2)

    def test_firecat_real_oracle_counter_payoff(self):
        cat = self.real_card('Crazed Firecat')
        self.assertFalse(cat.unsupported)
        self.g.rng = Coins(True, True, False)
        perm = self.g.enter_battlefield(self.a, cat)
        self.g.settle()
        self.assertEqual(perm.p1, 2)

    def test_traprunner_tokens_are_tapped_and_attacking(self):
        c = self.real_card('Goblin Traprunner')
        self.assertFalse(c.unsupported)
        perm = self.g.enter_battlefield(self.a, c)
        self.g.step = 'declare_attackers'
        self.g.rng = Coins(True, False, True)
        self.g.fire(self.a, 'attacks', perm)
        self.g.settle()
        tokens = [x for x in self.a.creatures if x.card.is_token]
        self.assertEqual(len(tokens), 2)
        self.assertTrue(all(x.tapped and x in self.g.attackers for x in tokens))

    def test_sheep_keep_the_oracle_token_name(self):
        c = self.real_card('Flock of Rabid Sheep')
        self.assertFalse(c.unsupported)
        item = StackItem(self.a, c.spell_effects, [None] * len(c.spell_effects))
        item.x = 2
        self.g.rng = Coins(True, False)
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual([(x.card.name, x.power, x.toughness) for x in self.a.creatures],
                         [('Rabid Sheep', 2, 2)])

    def test_each_retained_win_fires_both_players_watchers(self):
        c = self.real_card('Zndrsplt, Eye of Wisdom')
        self.assertFalse(c.unsupported)
        for p in (self.a, self.b):
            self.g.enter_battlefield(p, c)
        self.g.settle()
        self.resolve('Flip a coin until you lose a flip.', True, True, False)
        self.g.settle()
        self.assertEqual([len(p.hand) for p in (self.a, self.b)], [2, 2])

    def thumb(self, p=None):
        c = self.real_card("Krark's Thumb")
        self.assertFalse(c.unsupported)
        return self.g.enter_battlefield(p or self.a, c)

    def test_thumb_ignored_win_does_not_fire_trigger(self):
        self.thumb()
        watcher = card('Watcher', types='Enchantment', text='Whenever you win a coin flip, draw a card.')
        self.g.enter_battlefield(self.a, watcher)
        self.a.ai.choose_coin_result = lambda *args: False
        self.resolve('Flip a coin. If you lose the flip, you gain 1 life.', True, False)
        self.g.settle()
        self.assertEqual((len(self.a.hand), self.a.life, self.g.rng.calls), (0, 21, 2))

    def test_thumb_chooses_one_result_and_fires_once(self):
        self.thumb()
        watcher = card('Watcher', types='Enchantment', text='Whenever you win a coin flip, draw a card.')
        self.g.enter_battlefield(self.a, watcher)
        self.resolve('Flip a coin.', True, True)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(self.g.rng.calls, 2)

    def test_multiple_replacements_and_opponent_scope(self):
        first = self.thumb()
        self.g.enter_battlefield(self.a, dataclasses.replace(first.card, name="Thumb copy", legendary=False))
        self.thumb(self.b)
        item = self.resolve('Flip a coin.', False, False, False, True)
        self.assertTrue(item.gate_paid)
        self.assertEqual(self.g.rng.calls, 4)

    def test_suppressed_thumb_does_not_replace(self):
        thumb = self.thumb()
        thumb.silenced_by = thumb
        item = self.resolve('Flip a coin.', False)
        self.assertFalse(item.gate_paid)
        self.assertEqual(self.g.rng.calls, 1)

    def test_unsupported_riders_do_not_leak_markers(self):
        for name in ('Game of Chaos', 'Invert Polarity', 'Mogg Assassin', 'Goblin Lyre'):
            c = self.real_card(name)
            self.assertTrue(c.unsupported, name)
            self.assertNotIn('FLIPBOTH', str(c.unsupported))
            self.assertNotIn('FLIPCOIN', str(c.unsupported))

    def test_conditional_payoff_still_requires_winning(self):
        text = 'Flip a coin. If you win the flip, if you control a creature, draw a card.'
        self.g.enter_battlefield(self.a, card('Bear', types='Creature — Bear', power=2, toughness=2))
        self.resolve(text, False)
        self.assertEqual(len(self.a.hand), 0)
        self.resolve(text, True)
        self.assertEqual(len(self.a.hand), 1)

    def test_non_scalable_payoff_stays_unmatched(self):
        effects, bad = _parse_effects('Flip three coins. For each flip you win, scry 1.')
        self.assertEqual([e.kind for e in effects], ['flip_coin'])
        self.assertEqual(len(bad), 1)

    def test_unsupported_flip_instruction_keeps_payoffs_unmatched(self):
        c = self.real_card("Yusri, Fortune's Flame")
        self.assertTrue(any('For each flip you win' in s for s in c.unsupported))
        self.assertTrue(any('For each flip you lose' in s for s in c.unsupported))

    def test_mirror_march_copies_only_the_entering_creature(self):
        c = self.real_card('Mirror March')
        self.assertFalse(c.unsupported)
        self.g.enter_battlefield(self.a, c)
        self.g.rng = Coins(True, True, False)
        bear = card('Bear', types='Creature — Bear', power=2, toughness=2)
        original = self.g.enter_battlefield(self.a, bear)
        self.g.settle()
        tokens = [x for x in self.a.creatures if x.card.is_token]
        self.assertEqual(len(tokens), 2)
        self.assertTrue(all(x.card.name == original.card.name and x.has('haste') for x in tokens))
        self.assertEqual(self.g.end_cleanup, [(x, 'exile') for x in tokens])


if __name__ == '__main__':
    unittest.main()
