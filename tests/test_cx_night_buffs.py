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

    def test_granted_trigger_becomes_a_host_trigger(self):
        self.assertEqual(TRIGGERED.unsupported, [])
        self.assertEqual([t.event for t in TRIGGERED.host_triggers], ["combat_damage_player"])
        self.assertEqual(TRIGGERED.equip_bonus, (1, 0))

    def test_keywords_and_granted_ability(self):
        c = card("Test Kite", "{1}", "Artifact — Equipment",
                 "Equipped creature has flying and \"{T}: Add {C}.\"\nEquip {1}")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.equip_keywords, frozenset({"flying"}))
        self.assertEqual(len(c.ability_grants), 1)

    def test_upkeep_grant_stays_unsupported(self):
        c = card("Test Fervor", "{1}{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +3/+3 and has "
                 "\"At the beginning of your upkeep, put a -1/-1 counter on ~.\"")
        self.assertEqual(len(c.unsupported), 1)

    def test_aura_gives_bonus_and_ability(self):
        host = self.game.enter_battlefield(self.a, BEAR)
        self.game._aura_host = host
        self.game.enter_battlefield(self.a, PINGER)
        self.game.settle()
        self.assertEqual((host.power, host.toughness), (4, 4))
        self.assertEqual(len(host.activated), 1)


if __name__ == "__main__":
    unittest.main()
