"""Trigger heads: dealt damage, deals damage to a player / combat damage to a creature, any creature dies, a player
or an opponent casts a spell, each combat, your draw step, and equipped / enchanted creature triggers."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

FUNGUSAUR = card("Test Fungusaur", "{3}{G}", "Creature — Fungus Dinosaur",
                 "Whenever ~ is dealt damage, put a +1/+1 counter on it.", 2, 2)
LU_XUN = card("Test Scholar", "{2}{U}", "Creature — Human Soldier",
              "Whenever ~ deals damage to an opponent, you may draw a card.", 1, 3)
HYBRID = card("Test Hybrid", "{4}{B}", "Creature — Zombie",
              "Whenever ~ deals combat damage to a creature, destroy that creature.", 1, 1)
GRINNER = card("Test Grinner", "{4}{B}", "Creature — Zombie", "Whenever a creature dies, ~ gets +2/+2 until end of turn.",
               3, 3)
SENTRY = card("Test Sentry", "{R}", "Creature — Goblin", "Whenever an opponent casts a spell, ~ gets +2/+2 until end of "
                                                          "turn.", 1, 1)
GLOVES = card("Test Gloves", "{2}", "Artifact — Equipment",
              "Whenever equipped creature deals combat damage to a player, you may draw a card.\nEquip {2}")
ARMS = card("Test Extra Arms", "{4}{R}", "Enchantment — Aura",
            "Enchant creature\nWhenever enchanted creature attacks, it deals 2 damage to any target.")
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
WALL = card("Test Wall", "{2}", "Creature — Wall", "", 0, 5)


class TriggerHeads(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def fight(self, attackers, blocks=None):
        self.a.ai.attack = attackers
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_templates(self):
        for c in (FUNGUSAUR, LU_XUN, HYBRID, GRINNER, SENTRY, GLOVES, ARMS):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual([t.event for t in GLOVES.host_triggers], ["combat_damage_player"])

    def test_dealt_damage_counter_goes_on_itself(self):
        fungusaur, bear = self.put(self.b, FUNGUSAUR), self.put(self.a, BEAR)
        self.game.deal_damage(fungusaur, 1, by=self.a, source=bear)
        self.game.settle()
        self.assertEqual((fungusaur.p1, bear.p1), (1, 0))

    def test_damage_to_opponent_and_combat_damage_to_creature(self):
        scholar = self.put(self.a, LU_XUN)
        hand = len(self.a.hand)
        self.fight([scholar])
        self.assertEqual(len(self.a.hand), hand + 1)
        hybrid, wall = self.put(self.a, HYBRID), self.put(self.b, WALL)
        self.fight([hybrid], {hybrid: [wall]})
        self.assertNotIn(wall, self.b.battlefield)

    def test_any_creature_dies_and_opponent_casts(self):
        grinner = self.put(self.a, GRINNER)
        self.game.destroy(self.put(self.b, BEAR))
        self.game.settle()
        self.assertEqual(grinner.power, 5)
        sentry = self.put(self.a, SENTRY)
        self.put(self.b, MOUNTAIN)
        self.b.hand.append(SHOCK)
        self.assertTrue(self.game.cast(self.b, SHOCK, [self.a]))
        self.game.settle()
        self.assertEqual(sentry.power, 3)
        self.put(self.a, MOUNTAIN)
        self.a.hand.append(SHOCK)
        self.assertTrue(self.game.cast(self.a, SHOCK, [self.b]))
        self.game.settle()
        self.assertEqual(sentry.power, 3)               # its controller's own spell doesn't count

    def test_equipment_and_aura_triggers(self):
        bear = self.put(self.a, BEAR)
        gloves = self.put(self.a, GLOVES)
        gloves.attached_to = bear
        hand = len(self.a.hand)
        self.fight([bear])
        self.assertEqual(len(self.a.hand), hand + 1)
        other = self.put(self.a, BEAR)
        self.game._aura_host = other
        self.put(self.a, ARMS)
        self.fight([other])
        self.assertEqual(self.b.life, 20 - 2 - 2 - 2)   # bear, then Extra Arms' 2 and the second bear


if __name__ == "__main__":
    unittest.main()
