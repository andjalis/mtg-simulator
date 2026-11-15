"""Copy exceptions conditioned on embalm (#527)."""
import dataclasses
import random
import unittest

from mtgsim import alt_casts
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card


class EmbalmedClone(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, 'main1'
        for p in self.game.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        self.vizier = CardDB(offline=True).get('Vizier of Many Faces')
        self.game.enter_battlefield(self.b, BEAR)

    def test_normal_and_other_token_copy_do_not_apply_embalm_exception(self):
        normal = self.game.enter_battlefield(self.a, self.vizier)
        self.assertEqual((normal.card.name, normal.card.colors, normal.card.cmc), (BEAR.name, BEAR.colors, BEAR.cmc))
        other_token = self.game.enter_battlefield(self.a, dataclasses.replace(self.vizier, is_token=True))
        self.assertEqual((other_token.card.name, other_token.card.colors, other_token.card.cmc),
                         (BEAR.name, BEAR.colors, BEAR.cmc))
        self.assertNotIn('Zombie', other_token.card.subtypes)

    def test_embalm_token_copies_creature_with_white_zombie_and_no_mana_cost(self):
        self.a.graveyard.append(self.vizier)
        for _ in range(5):
            self.game.enter_battlefield(self.a, ISLAND).sick = False
        alt_casts.graveyard_actions(self.game, self.a)
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual((token.card.name, token.card.colors, token.card.cmc, token.power, token.toughness),
                         (BEAR.name, frozenset({'W'}), 0, 2, 2))
        self.assertTrue(token.card.advanced_rules.get('no_mana_cost'))
        self.assertEqual(token.card.mana_cost, {})
        self.assertEqual(token.card.subtypes, frozenset({'Bear', 'Zombie'}))
        self.assertTrue(any(c.name == self.vizier.name for c in self.a.exile))

    def test_embalm_without_a_copy_candidate_retains_its_name_and_no_mana_cost(self):
        self.game.leave_battlefield(self.b.battlefield[0], 'graveyard')
        anthem = card('Anthem', types='Enchantment', text='Creatures you control get +1/+1.')
        self.game.enter_battlefield(self.a, anthem)
        self.a.graveyard.append(self.vizier)
        for _ in range(5):
            self.game.enter_battlefield(self.a, ISLAND).sick = False
        alt_casts.graveyard_actions(self.game, self.a)
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual(token.card.name, self.vizier.name)
        self.assertEqual(token.card.mana_cost, {})
        self.assertTrue(token.card.advanced_rules.get('no_mana_cost'))
        self.assertEqual(token.card.colors, frozenset({'W'}))
        self.assertIn('Zombie', token.card.subtypes)
