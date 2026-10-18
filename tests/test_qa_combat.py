"""Regression checks from independent combat QA."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import CardDef
from mtgsim.engine import Game, Permanent, Player


class CreaturePlaneswalkerTests(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(1))
        card = CardDef('Creature planeswalker', {}, 4,
                       frozenset({'Creature', 'Planeswalker'}),
                       power=4, toughness=6, loyalty=3)
        self.walker = Permanent(card, self.b)
        self.walker.counters['loyalty'] = 3
        self.b.battlefield.append(self.walker)

    def test_noncombat_damage_marks_damage_and_removes_loyalty(self):
        self.game.deal_damage(self.walker, 2, self.a)
        self.assertEqual(self.walker.damage, 2)
        self.assertEqual(self.walker.loyalty, 1)

    def test_combat_damage_marks_damage_and_removes_loyalty(self):
        card = CardDef('Attacker', {}, 2, frozenset({'Creature'}), power=2, toughness=4)
        attacker = Permanent(card, self.a)
        self.a.battlefield.append(attacker)
        self.game.combat_damage(self.a, self.b, [attacker], {attacker: [self.walker]}, lambda _: True)
        self.assertEqual(self.walker.damage, 2)
        self.assertEqual(self.walker.loyalty, 1)

    def test_zero_loyalty_kills_indestructible_creature_planeswalker(self):
        self.walker.counters['loyalty'] = 0
        self.walker.temp_kw.add('indestructible')
        self.game.state_based_actions()
        self.assertNotIn(self.walker, self.b.battlefield)
        self.assertIn(self.walker.card, self.b.graveyard)
