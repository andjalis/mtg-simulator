"""mega-batch6 (2): player-side prevention shields without a permanent carrier.

Divine Deflection ("you and/or permanents you control"), Deflecting Palm and
Intervention Pact ("the next time a source of your choice would deal damage to you
this turn") and Channel Harm ("prevent all damage ... by sources you don't control")
parse into prevent_shield / prevent_all_turn effects whose riders ride
``install_player_rider`` — a one-turn EventBus listener on the damage_prevented event
that queues the rider with the prevented amount snapshotted into "that much" effects.
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_combat_triggers import BEAR

DEFLECTION = ("Prevent the next X damage that would be dealt to you and/or permanents you "
               "control this turn. If damage is prevented this way, ~ deals "
               "that much damage to any target.")
PALM = ("The next time a source of your choice would deal damage to you this turn, prevent "
        "that damage. If damage is prevented this way, ~ deals that much damage to "
        "that source's controller.")
HARM = ("Prevent all damage that would be dealt to you and permanents you control this turn "
        "by sources you don't control. If damage is prevented this way, you may have ~ "
        "deal that much damage to target creature.")


class PlayerShieldParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_deflection_shields_the_player_with_the_rider(self):
        (shield,) = self.parse(DEFLECTION)
        self.assertEqual(shield.kind, "prevent_shield")
        self.assertEqual(shield.target, "youperms")
        self.assertTrue(shield.data["x"])
        (rider,) = shield.data["rider"]
        self.assertEqual((rider.kind, rider.target, rider.data["that_much"]), ("damage", "any", True))

    def test_palm_is_a_one_shot_pool_with_a_deflect_rider(self):
        (shield,) = self.parse(PALM)
        self.assertEqual(shield.kind, "prevent_shield")
        (rider,) = shield.data["rider"]
        self.assertEqual((rider.kind, rider.data["that_much"]), ("deflect", True))

    def test_harm_is_a_full_turn_shield(self):
        (shield,) = self.parse(HARM)
        self.assertEqual(shield.kind, "prevent_all_turn")
        (rider,) = shield.data["rider"]
        self.assertEqual((rider.kind, rider.target, rider.data["that_much"]), ("damage", "creature", True))


class PlayerShieldBehavior(Batch1):
    def resolve_shield(self, text, x=0):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        item = StackItem(self.a, effects, [None] * len(effects))
        if x:
            item.x = x
        self.g.resolve(self.a, effects[0], None, item)
        return item

    def drain(self):
        for _ in range(3):
            self.g.flush_triggers()
            while self.g.stack:
                self.g.resolve_top()
                self.g.settle()

    def attack_a(self, n):
        attacker = self.put(BEAR, self.b)
        self.g.deal_damage(self.a, n, by=self.b, cause="test", source=attacker)
        return attacker

    def test_deflection_prevents_and_rides_the_prevented_total(self):
        self.resolve_shield(DEFLECTION, x=2)
        attacker = self.attack_a(5)
        self.assertEqual(self.a.life, 17)          # 5 minus the 2 prevented
        self.drain()
        # the rider dealt the 2 prevented damage (auto-target: the damage source)
        self.assertEqual(attacker.damage + (20 - self.b.life), 2)

    def test_palm_prevents_the_source_damage_and_hits_its_controller(self):
        self.resolve_shield(PALM)
        attacker = self.attack_a(4)
        self.assertEqual((self.a.life, attacker.card.name), (20, "Test Bear"))
        self.drain()
        self.assertEqual(self.b.life, 16)         # Deflecting Palm's rider

    def test_harm_prevents_player_and_permanent_damage(self):
        self.g.enter_battlefield(self.a, BEAR)
        self.resolve_shield(HARM)
        guard = self.put(BEAR, self.b)
        self.attack_a(3)
        self.g.deal_damage(self.a.creatures[0], 3, by=self.b, cause="test", source=guard)
        self.assertEqual((self.a.life, self.a.creatures[0].damage), (20, 0))
        self.drain()
        # both prevented totals rode: the rider's 3 damage killed the guarding bear
        self.assertNotIn(guard, self.b.battlefield)

    def test_player_rider_expires_with_the_turn(self):
        self.resolve_shield(PALM)
        self.attack_a(4)
        self.drain()
        self.assertEqual(self.b.life, 16)         # Deflecting Palm's rider fired
        self.g.turn += 1
        self.a.prevent_next = 0                    # the turn cleanup resets the pool
        self.attack_a(3)
        self.drain()
        self.assertEqual((self.a.life, self.b.life), (17, 16))   # plain damage, no rider


if __name__ == "__main__":
    unittest.main()
