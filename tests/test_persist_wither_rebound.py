"""Counter damage, death returns and casting from a rebound delayed trigger."""
import dataclasses
import random
import unittest
from unittest.mock import patch
from mtgsim.ai import HeuristicAI, fight_group
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card


class PersistWitherRebound(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, 'main1'
        self.a.library, self.b.library = [ISLAND]*30, [ISLAND]*30

    def creature(self, text='', who=None, p=2, t=3):
        c = card('Fixture creature', text=text, power=p, toughness=t)
        self.assertFalse(c.unsupported)
        return self.game.enter_battlefield(who or self.a, c)

    def rebound(self, text='Draw a card.', types='Sorcery', targets=()):
        c = card('Fixture rebound', types=types, text='Rebound\n'+text)
        self.assertFalse(c.unsupported)
        self.a.hand.append(c)
        self.assertTrue(self.game.cast(self.a, c, list(targets)))
        self.game.settle()
        return c

    def upkeep(self, who):
        self.game.active_idx = self.game.players.index(who)
        self.game.step = 'upkeep'
        self.game.turn += 1
        self.game.begin_upkeep(who)
        self.game.settle()

    def test_persist_returns_once_with_minus_counter(self):
        a = self.creature('Persist')
        self.game.destroy(a)
        self.game.settle()
        b = self.a.creatures[0]
        self.assertIsNot(a, b)
        self.assertEqual((b.power, b.toughness, b.m1), (1, 2, 1))
        self.game.destroy(b)
        self.game.settle()
        self.assertEqual(self.a.creatures, [])

    def test_persist_can_trigger_with_plus_counter(self):
        a = self.creature('Persist')
        a.counters['+1/+1'] = 1
        self.game.destroy(a)
        self.game.settle()
        self.assertEqual((self.a.creatures[0].p1, self.a.creatures[0].m1), (0, 1))

    def test_persist_fails_after_graveyard_zone_change(self):
        a = self.creature('Persist')
        self.game.destroy(a)
        c = self.a.graveyard.pop()
        self.a.graveyard.append(c)
        self.game.settle()
        self.assertEqual(self.a.creatures, [])

    def test_persist_and_undying_share_card_but_only_one_returns(self):
        a = self.creature('Persist, undying')
        self.game.destroy(a)
        self.game.flush_triggers()
        self.assertEqual(len(self.game.stack), 2)
        self.game.settle()
        self.assertEqual(len(self.a.creatures), 1)
        self.assertEqual(self.a.graveyard, [])

    def test_persist_finality_does_not_return(self):
        a = self.creature('Persist')
        a.counters['finality'] = 1
        self.game.destroy(a)
        self.game.settle()
        self.assertEqual(self.a.creatures, [])

    def test_persist_lethal_counters_use_last_known_values(self):
        a = self.creature('Persist', t=2)
        a.counters.update({'+1/+1': 1, '-1/-1': 3})
        self.game.state_based_actions()
        self.game.settle()
        self.assertEqual(self.a.creatures, [])

    def test_wither_damages_players_normally_with_lifelink(self):
        a = self.creature('Wither, lifelink')
        self.game.deal_damage(self.b, 2, self.a, source=a)
        self.assertEqual((self.a.life, self.b.life, self.b.counters), (22, 18, {}))

    def test_wither_noncombat_and_indestructible(self):
        a = self.creature('Wither')
        b = self.creature('Indestructible', self.b, t=2)
        self.game.deal_damage(b, 2, self.a, source=a)
        self.game.state_based_actions()
        self.assertEqual((b.m1, b.damage), (2, 0))
        self.assertNotIn(b, self.b.battlefield)

    def test_first_strike_wither_reduces_return_damage_and_ai_agrees(self):
        a = self.creature('Wither, first strike')
        b = self.creature('', self.b, p=3, t=4)
        self.assertEqual(fight_group(a, [b])[0], set())
        self.game.combat_damage(self.a, self.b, [a], {a:[b]}, lambda c:c.has('first strike'))
        self.game.combat_damage(self.a, self.b, [a], {a:[b]}, lambda c:not c.has('first strike'))
        self.assertEqual((a.damage, b.m1, b.damage), (1, 2, 0))

    def test_wither_damage_spell_uses_its_card_as_source(self):
        b = self.creature('Indestructible', self.b, t=2)
        spell = card('Fixture blast', types='Instant', text='Wither\nFixture blast deals 2 damage to any target.')
        self.assertFalse(spell.unsupported)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, [b]))
        self.assertEqual((b.m1, b.damage), (2, 0))
        self.assertNotIn(b, self.b.battlefield)

    def test_rebound_recasts_sorcery_once_during_upkeep(self):
        c = self.rebound()
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(self.a.exile, [c])
        self.upkeep(self.b)
        self.assertEqual(len(self.a.hand), 1)
        self.upkeep(self.a)
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(self.a.exile, [])
        self.assertEqual(self.a.graveyard, [c])
        self.upkeep(self.a)
        self.assertEqual(len(self.a.hand), 2)

    def test_rebound_can_be_declined_and_stays_in_exile(self):
        c = self.rebound()
        with patch.object(self.a.ai, 'choose_rebound', create=True, return_value=False):
            self.upkeep(self.a)
        self.upkeep(self.a)
        self.assertEqual(self.a.exile, [c])
        self.assertEqual(len(self.a.hand), 1)

    def test_rebound_not_cast_without_legal_targets(self):
        victim = self.creature('', self.b)
        c = self.rebound('Destroy target creature.', targets=[victim])
        self.assertEqual(self.a.exile, [c])
        self.upkeep(self.a)
        self.assertEqual(self.a.exile, [c])
        self.assertEqual(self.a.graveyard, [])

    def test_rebound_selects_new_targets(self):
        first = self.creature('', self.b)
        second = self.creature('', self.b)
        c = self.rebound('Destroy target creature.', targets=[first])
        self.upkeep(self.a)
        self.assertNotIn(second, self.b.battlefield)
        self.assertEqual(self.a.graveyard, [c])

    def test_rebound_does_not_apply_to_countered_spell(self):
        with patch.object(self.game, 'settle'):
            c = self.rebound()
        self.game.counter(self.b, Effect('counter', target='spell'), self.game.stack[-1])
        self.game.settle()
        self.assertEqual(self.a.exile, [])
        self.assertEqual(self.a.graveyard, [c])
        self.assertEqual(self.game.rebound_upkeep, [])

    def test_fizzled_rebound_goes_to_graveyard(self):
        a = self.creature('', self.b)
        with patch.object(self.game, 'settle'):
            c = self.rebound('Destroy target creature.', targets=[a])
        self.game.leave_battlefield(a, 'hand')
        self.game.settle()
        self.assertEqual(self.a.graveyard, [c])
        self.assertEqual(self.game.rebound_upkeep, [])

    def test_rebound_not_from_free_cast_or_spell_copy(self):
        c = card('Free rebound', types='Sorcery', text='Rebound\nDraw a card.')
        self.assertTrue(self.game.cast_free(self.a, c))
        self.assertEqual(self.a.graveyard, [c])
        self.assertEqual(self.game.rebound_upkeep, [])
        copy = StackItem(self.a, list(c.spell_effects), [None], card=c, kind='copy')
        self.game.stack.append(copy)
        self.game.settle()
        self.assertEqual(self.game.rebound_upkeep, [])

    def test_rebound_fails_after_exile_card_leaves_and_returns(self):
        c = self.rebound()
        exiled = self.a.exile.pop()
        self.a.exile.append(exiled)
        self.upkeep(self.a)
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(self.a.exile, [c])

    def test_two_identical_rebounds_recast_independently(self):
        self.rebound()
        self.rebound()
        self.upkeep(self.a)
        self.assertEqual(len(self.a.hand), 4)
        self.assertEqual(len(self.a.graveyard), 2)
        self.assertEqual(self.a.exile, [])

    def test_rebound_obeys_opponent_casting_restrictions(self):
        blocker = self.creature('', self.b)
        blocker.card = dataclasses.replace(blocker.card, opp_no_cast=True)
        c = self.rebound()
        self.game.active_idx = 1
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertEqual(self.a.exile, [c])

    def test_rebound_trigger_and_recast_are_distinct_stack_items(self):
        self.rebound()
        self.game.begin_upkeep(self.a)
        self.game.flush_triggers()
        self.assertEqual(self.game.stack[-1].effects[0].kind, 'rebound_cast')
        with patch.object(self.game, 'settle'):
            self.game.resolve_top()
        self.assertTrue(self.game.stack[-1].is_spell)
        self.assertFalse(self.game.stack[-1].cast_from_hand)
