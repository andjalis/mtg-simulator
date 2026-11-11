"""Behavior for the remaining conditional static families, using offline Oracle text."""
import random
import unittest
from pathlib import Path

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from mtgsim.cx_lures import is_lure
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card


@unittest.skipUnless(Path('mtgsim/data/cards.sqlite3').exists(), 'offline card database required')
class StaticRemainders(unittest.TestCase):
    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, 'main1'

    def put(self, name, player=None):
        return self.game.enter_battlefield(player or self.a, self.db.get(name))

    def threshold(self, n):
        self.a.graveyard[:] = [ISLAND] * n

    def test_conditional_lures_force_legal_blocks_and_expire(self):
        for name in ("Seton's Desire", 'Stone-Tongue Basilisk'):
            with self.subTest(name=name):
                self.setUp()
                source = self.put(name)
                self.assertEqual(source.card.unsupported, [])
                attacker = source
                if source.card.aura:
                    attacker = self.game.enter_battlefield(self.a, BEAR)
                    source.aura_host = attacker
                    attacker.auras.append(source)
                blocker = self.game.enter_battlefield(self.b, BEAR)
                tapped = self.game.enter_battlefield(self.b, BEAR)
                tapped.tapped = True
                self.threshold(6)
                self.assertFalse(is_lure(attacker))
                self.threshold(7)
                self.assertTrue(is_lure(attacker))
                self.assertEqual(self.game.force_blocks(self.b, [attacker], {}).get(attacker), [blocker])
                self.threshold(6)
                self.assertFalse(is_lure(attacker))

    def test_aura_condition_belongs_to_aura_controller(self):
        aura = self.put("Seton's Desire")
        attacker = self.game.enter_battlefield(self.b, BEAR)
        aura.aura_host = attacker
        attacker.auras.append(aura)
        self.b.graveyard[:] = [ISLAND] * 7
        self.assertFalse(is_lure(attacker))
        self.threshold(7)
        self.assertTrue(is_lure(attacker))
        attacker.auras.remove(aura)
        self.assertFalse(is_lure(attacker))

    def test_conditional_count_is_live_and_counts_only_opponents(self):
        cutter = self.put('Nantuko Blightcutter')
        self.assertEqual(cutter.card.unsupported, [])
        black = card('Test Black', '{B}', 'Creature', '', 1, 1)
        self.game.enter_battlefield(self.a, black)
        theirs = self.game.enter_battlefield(self.b, black)
        self.game.enter_battlefield(self.b, BEAR)
        self.threshold(6)
        self.assertEqual((cutter.power, cutter.toughness), (2, 2))
        self.threshold(7)
        self.assertEqual((cutter.power, cutter.toughness), (3, 3))
        self.game.enter_battlefield(self.b, black)
        self.assertEqual((cutter.power, cutter.toughness), (4, 4))
        self.b.battlefield.remove(theirs)
        self.assertEqual((cutter.power, cutter.toughness), (3, 3))
        self.threshold(6)
        self.assertEqual((cutter.power, cutter.toughness), (2, 2))

    def test_quoted_activated_ability_and_color_follow_threshold(self):
        aven = self.put('Possessed Aven')
        self.assertEqual(aven.card.unsupported, [])
        self.threshold(6)
        self.assertEqual(aven.card.colors, frozenset({'U'}))
        self.assertEqual(aven.activated, [])
        self.threshold(7)
        self.assertEqual(aven.card.colors, frozenset({'B'}))
        self.assertEqual(len(aven.activated), 1)
        self.assertEqual((aven.power, aven.toughness), (4, 4))
        self.game.add_continuous_effect(aven, 'set_colors', colors=frozenset({'R'}), until_eot=True)
        self.assertEqual(aven.card.colors, frozenset({'R'}))
        self.threshold(6)
        self.assertEqual(aven.activated, [])
        self.assertEqual(aven.card.colors, frozenset({'R'}))
        self.game.continuous_effects.clear()
        from mtgsim.continuous import refresh
        refresh(aven)
        self.assertEqual(aven.card.colors, frozenset({'U'}))
        self.threshold(7)
        self.game.leave_battlefield(aven, 'graveyard')
        self.threshold(0)
        self.assertEqual(aven.last_card.colors, frozenset({'B'}))
        self.assertEqual(aven.front.colors, frozenset({'U'}))

    def test_granted_ability_uses_normal_targeting_and_costs(self):
        aven = self.put('Possessed Aven')
        blue = self.game.enter_battlefield(self.b, card('Test Blue', '{U}', 'Creature', '', 2, 2))
        green = self.game.enter_battlefield(self.b, BEAR)
        for name in ('Swamp', 'Island', 'Island'):
            self.put(name)
        aven.sick = False
        self.threshold(6)
        self.assertFalse(self.game.activate_ability(self.a, aven, 0, [blue]))
        self.threshold(7)
        self.assertFalse(self.game.activate_ability(self.a, aven, 0, [green]))
        self.assertTrue(self.game.activate_ability(self.a, aven, 0, [blue]))
        self.assertNotIn(blue, self.b.battlefield)
        self.assertIn(green, self.b.battlefield)

    def test_granted_dies_trigger_uses_last_known_threshold(self):
        for n, loss in ((6, 0), (7, 4)):
            with self.subTest(n=n):
                self.setUp()
                self.threshold(n)
                wolf = self.put('Treacherous Werewolf')
                self.assertEqual(wolf.card.unsupported, [])
                self.game.dies(wolf)
                # The dead creature reaching the graveyard cannot grant it a trigger.
                self.threshold(0)
                self.game.settle()
                self.assertEqual(self.a.life, 20 - loss)

    def test_granted_etb_checks_at_trigger_time_only(self):
        self.a.library = [ISLAND] * 10
        self.threshold(6)
        self.put('Cephalid Sage')
        self.game.settle()
        self.assertEqual(len(self.a.hand), 0)
        self.threshold(7)
        self.put('Cephalid Sage')
        self.assertTrue(self.game.pending)
        self.threshold(0)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(len(self.a.library), 7)

    def test_unsupported_quote_never_applies_partial_modifiers(self):
        c = card('Test Conditional Quote', '{W}', 'Creature',
                 'Threshold — As long as there are seven or more cards in your graveyard, '
                 '~ gets +3/+3, is black, and has "Do something unknown."', 1, 1)
        self.assertTrue(c.unsupported)
        self.assertEqual(c.pt_if, ())
        self.assertNotIn('self_colors_if', c.advanced_rules)
