"""A Spacecraft is an artifact creature once it has its highest station tier's charge counters."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND


class Spacecraft(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_creature_only_at_the_threshold(self):
        card = self.db.get("Class-4 Tactical Cube")
        self.assertEqual(card.unsupported, [])
        perm = self.game.enter_battlefield(self.a, card)
        self.game.settle()
        perm.sick = False
        perm.counters["charge"] = 6
        self.assertFalse(perm.is_creature)
        perm.counters["charge"] = 7
        self.assertTrue(perm.is_creature)
        self.assertTrue(perm.has("flying"))
        self.assertIn("Artifact", perm.card.types)
        perm.counters["charge"] = 3
        self.assertFalse(perm.is_creature)

    def test_charged_spacecraft_attacks_and_hits(self):
        perm = self.game.enter_battlefield(self.a, self.db.get("Class-4 Tactical Cube"))
        self.game.settle()
        perm.sick = False
        perm.counters["charge"] = 7
        life = self.b.life
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertLess(self.b.life, life)

    def test_default_ai_stations_a_spacecraft_with_its_creature(self):
        from tests.test_templates import BEAR
        perm = self.game.enter_battlefield(self.a, self.db.get("Class-4 Tactical Cube"))
        bears = [self.game.enter_battlefield(self.a, BEAR) for _ in range(2)]
        self.game.settle()
        self.game.step = "main2"
        self.game.main_phase(self.a)
        self.assertGreater(perm.counters.get("charge", 0), 0)
        self.assertTrue(any(b.tapped for b in bears))

    def test_multi_tier_creature_threshold_is_recorded_as_simplified(self):
        card = self.db.get("D-7 Battle Cruiser")
        self.assertTrue(card.approximations)


if __name__ == "__main__":
    unittest.main()
