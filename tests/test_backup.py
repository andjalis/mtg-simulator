"""Backup: the target gains all the abilities listed below it until end of turn, not only keywords."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND


class Backup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        self.ally = self.game.enter_battlefield(self.a, self.db.get("Hill Giant"))
        self.ally.sick = False

    def back_up(self, name):
        self.game.enter_battlefield(self.a, self.db.get(name))
        self.game.settle()

    def test_parse_has_no_approximation(self):
        for name in ("Archpriest of Shadows", "Bola Slinger", "Chomping Kavu", "Voldaren Thrillseeker", "Sigiled Sentinel"):
            self.assertFalse(self.db.get(name).approximations, name)

    def test_keyword_and_counter(self):
        self.back_up("Archpriest of Shadows")
        self.assertEqual(self.ally.p1, 1)
        self.assertTrue(self.ally.has("deathtouch"))

    def test_triggered_ability_is_granted(self):
        before = len(self.ally.triggers)
        self.back_up("Bola Slinger")
        slinger = self.db.get("Bola Slinger")
        granted = [t for t in self.ally.triggers if t not in self.ally.card.triggers]
        self.assertTrue(granted)
        self.assertGreater(len(self.ally.triggers), before)
        self.assertFalse(any(e.kind == "backup" for t in granted for e in t.effects))
        self.assertTrue(slinger.triggers)

    def test_activated_ability_is_granted(self):
        self.assertEqual(len(self.ally.card.activated), 0)
        self.back_up("Voldaren Thrillseeker")
        self.assertEqual(len(self.ally.temp_activated), 1)
        self.assertEqual(self.ally.p1, 2)

    def test_blocking_restriction_is_granted_and_ends(self):
        self.back_up("Chomping Kavu")
        self.assertEqual(self.ally.temp_min_blocker, 3)
        from mtgsim.engine.state import can_block
        small = self.game.enter_battlefield(self.b, BEAR)
        self.assertFalse(can_block(small, self.ally))

    def test_ai_casts_backup_creature_onto_its_ally(self):
        """A real turn: HeuristicAI casts Archpriest of Shadows ({3}{B}{B}) and backs up its Hill Giant."""
        for _ in range(5):
            self.game.enter_battlefield(self.a, self.db.get("Swamp")).sick = False
        self.a.hand = [self.db.get("Archpriest of Shadows")]
        self.a.library = [self.db.get("Giant Growth")] * 20
        self.game.take_turn(self.a)
        self.assertTrue(any(x.card.name == "Archpriest of Shadows" for x in self.a.battlefield))
        counters = sorted(x.p1 for x in self.a.battlefield if x.is_creature)
        self.assertEqual(counters, [0, 1])


if __name__ == "__main__":
    unittest.main()
