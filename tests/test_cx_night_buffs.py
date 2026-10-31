"""Auras and Equipment with a bonus and a granted activated ability in one line."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card

PINGER = card("Test Pinger", "{1}{R}", "Enchantment — Aura",
              "Enchant creature\nEnchanted creature gets +2/+2 and has \"{T}: ~ deals 1 damage to any target.\"")
CROWBAR = card("Test Crowbar", "{1}", "Artifact — Equipment",
               "Equipped creature gets +1/+1 and has \"{W}, {T}, Sacrifice ~: Destroy target artifact or "
               "enchantment.\"\nEquip {2}")
TRIGGERED = card("Test Blooder", "{1}", "Artifact — Equipment",
                 "Equipped creature gets +1/+0 and has \"Whenever ~ deals combat damage to a player, create a Blood "
                 "token.\"\nEquip {1}")


class Buffs(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_parses_with_bonus_and_grant(self):
        for c in (PINGER, CROWBAR):
            with self.subTest(c.name):
                self.assertEqual(c.unsupported, [])
                self.assertEqual(len(c.ability_grants), 1)
        self.assertEqual((PINGER.equip_bonus, CROWBAR.equip_bonus), ((2, 2), (1, 1)))

    def test_granted_trigger_stays_unsupported(self):
        self.assertEqual(len(TRIGGERED.unsupported), 1)

    def test_aura_gives_bonus_and_ability(self):
        host = self.game.enter_battlefield(self.a, BEAR)
        self.game._aura_host = host
        self.game.enter_battlefield(self.a, PINGER)
        self.game.settle()
        self.assertEqual((host.power, host.toughness), (4, 4))
        self.assertEqual(len(host.activated), 1)


if __name__ == "__main__":
    unittest.main()
