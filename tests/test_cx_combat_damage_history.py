"""Damage-history attack conditions distinguish dealt damage from losing life."""
import os
import random
import unittest
from unittest.mock import patch

from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class CombatDamageHistory(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 3, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        c = CardDB(offline=True).get("Bloodcrazed Goblin")
        self.assertEqual(c.unsupported, [])
        self.goblin = self.g.enter_battlefield(self.a, c)
        self.goblin.sick = False

    def test_life_loss_and_payments_do_not_enable_attack(self):
        self.g.change_life(self.b, -2, "lose life")
        self.assertFalse(self.goblin.can_attack())
        self.g.change_life(self.b, -2, "pay life")
        self.assertFalse(self.goblin.can_attack())
        self.g.deal_damage(self.a, 1, by=self.b)
        self.assertFalse(self.goblin.can_attack())
        self.g.deal_damage(self.b, 1, by=self.a)
        self.assertTrue(self.goblin.can_attack())

    def test_zero_and_prevented_damage_do_not_count(self):
        self.g.deal_damage(self.b, 0, by=self.a)
        self.b.prevent_next = 3
        self.g.deal_damage(self.b, 3, by=self.a)
        self.assertFalse(self.goblin.can_attack())
        self.b.prevent_next = 1
        self.g.deal_damage(self.b, 2, by=self.a)
        self.assertTrue(self.goblin.can_attack())

    def test_infect_damage_counts_without_life_loss(self):
        source = self.g.enter_battlefield(self.a, card("Test Infector", "{B}", text="Infect", power=1, toughness=1))
        self.g.deal_damage(self.b, 1, by=self.a, source=source)
        self.assertEqual(self.b.life, 20)
        self.assertEqual(self.b.counters.get("poison"), 1)
        self.assertTrue(self.goblin.can_attack())

    def test_life_floor_damage_counts_without_life_loss(self):
        floor = card("Test Floor", "{R}", text="Damage that would reduce your life total to less than 1 reduces it to 1 instead.",
                     power=1, toughness=1)
        self.assertEqual(floor.unsupported, [])
        self.g.enter_battlefield(self.b, floor)
        self.b.life = 1
        self.g.deal_damage(self.b, 2, by=self.a)
        self.assertEqual(self.b.life, 1)
        self.assertTrue(self.goblin.can_attack())

    def test_creature_damage_does_not_count(self):
        bear = self.g.enter_battlefield(self.b, BEAR)
        self.g.deal_damage(bear, 1, by=self.a)
        self.assertFalse(self.goblin.can_attack())

    def test_condition_is_recorded_before_damage_triggers(self):
        fire = self.g.fire
        seen = []
        def observe(p, event, *args, **kwargs):
            if p is self.b and event == "player_damaged":
                seen.append(self.goblin.can_attack())
            return fire(p, event, *args, **kwargs)
        with patch.object(self.g, "fire", side_effect=observe):
            self.g.deal_damage(self.b, 1, by=self.a)
        self.assertEqual(seen, [True])

    def test_history_expires_and_resets_before_next_turn(self):
        self.g.deal_damage(self.b, 1, by=self.a)
        self.g.change_life(self.b, 1, "gain life")
        self.assertTrue(self.goblin.can_attack())
        self.g.turn += 1
        self.assertFalse(self.goblin.can_attack())
        # Stop at untap to inspect the turn-start reset without running AI turns.
        class StopTurn(Exception):
            pass
        with patch.object(self.g, "untap_step", side_effect=StopTurn), self.assertRaises(StopTurn):
            self.g.take_turn(self.b)
        self.assertIsNone(self.b.last_damage_turn)

    def test_damage_opens_the_actual_attack_declaration(self):
        self.a.ai.attack = [self.goblin]
        self.g.combat(self.a, self.b)
        self.assertFalse(self.goblin.tapped)
        self.g.deal_damage(self.b, 1, by=self.a)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.g.last_attackers, [self.goblin])
        self.assertEqual(self.b.life, 17)


if __name__ == "__main__":
    unittest.main()
