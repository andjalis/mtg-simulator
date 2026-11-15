"""Entry cast history for copy triggers (#527)."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card


class EntryCast(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, 'main1'
        for p in self.game.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        self.db = CardDB(offline=True)
        self.preston = self.game.enter_battlefield(self.a, self.db.get('Preston, the Vanisher'))
        self.game.settle()

    def tokens(self):
        return [p for p in self.a.battlefield if p.card.is_token]

    def test_put_into_play_creates_a_white_illusion_copy(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.assertFalse(bear.entered_was_cast)
        self.game.settle()
        token = self.tokens()[0]
        self.assertEqual((token.card.name, token.power, token.toughness, token.card.colors),
                         (BEAR.name, 0, 1, frozenset({'W'})))
        self.assertEqual(token.card.subtypes, frozenset({'Illusion'}))
        self.assertEqual(len(self.tokens()), 1)

    def test_cast_creature_does_not_trigger(self):
        creature = card('Cast Creature', '{1}', 'Creature — Bear', '', 2, 2)
        self.a.hand.append(creature)
        land = self.game.enter_battlefield(self.a, ISLAND)
        land.sick = False
        self.assertTrue(self.game.cast(self.a, self.a.hand[0]))
        self.game.settle()
        permanent = next(x for x in self.a.battlefield if x.card.name == 'Cast Creature')
        self.assertTrue(permanent.entered_was_cast)
        self.assertFalse(self.tokens())

    def test_copy_of_permanent_spell_was_not_cast_and_is_a_token(self):
        spell = card('Copied Creature', '{1}', 'Creature — Bear', '', 2, 2)
        self.game.stack.append(StackItem(self.a, [], [], card=spell, kind='spell'))
        original = self.game.stack[-1]
        from mtgsim.copies import copy_spell
        copy_spell(self.game, self.a, original)
        self.game.resolve_top()
        token = self.tokens()[0]
        self.assertFalse(token.entered_was_cast)
        self.game.settle()
        self.assertEqual(len(self.tokens()), 1)

    def test_other_players_and_tokens_do_not_trigger(self):
        self.game.enter_battlefield(self.b, BEAR)
        from mtgsim.cards import make_token
        self.game.enter_battlefield(self.a, make_token('Bear', 2, 2))
        self.game.settle()
        self.assertEqual(len(self.tokens()), 1)

    def test_last_known_copy_when_entering_creature_leaves_before_resolution(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.flush_triggers()
        self.game.leave_battlefield(bear, 'graveyard')
        self.game.settle()
        self.assertEqual([p.card.name for p in self.tokens()], [BEAR.name])

    def test_noncreature_card_entering_as_a_creature_triggers(self):
        animator = card('Animator', types='Enchantment',
                        text='Artifacts you control are creatures in addition to their other types.')
        self.assertFalse(animator.unsupported)
        self.game.enter_battlefield(self.a, animator)
        self.game.enter_battlefield(self.a, card('Relic', types='Artifact'))
        self.game.settle()
        self.assertEqual([p.card.name for p in self.tokens()], ['Relic'])
