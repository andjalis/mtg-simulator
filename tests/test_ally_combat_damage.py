"""#458: "Whenever a creature you control deals combat damage to a player" knows the creature ("it", "that
creature"), the damaged player ("that player") and the damage ("that many")."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None


@unittest.skipUnless(HAVE_DB, "card database not built")
class AllyCombatDamage(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def attack(self, *attackers):
        self.a.ai.attack = list(attackers)
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_counter_on_that_creature(self):
        self.put(self.a, DB.get("Shaman of the Great Hunt"))
        bear = self.put(self.a, BEAR)
        self.attack(bear)
        self.assertEqual(bear.counters.get("+1/+1", 0), 1)

    def test_that_many_counters_on_it(self):
        regent = self.put(self.a, DB.get("Necropolis Regent"))
        bear = self.put(self.a, BEAR)
        self.attack(bear)
        self.assertEqual(bear.counters.get("+1/+1", 0), 2)
        self.assertEqual(regent.counters.get("+1/+1", 0), 0)

    def test_that_player_discards(self):
        self.put(self.a, DB.get("Larceny"))
        bear = self.put(self.a, BEAR)
        self.b.hand = [ISLAND, ISLAND]
        self.a.hand = [ISLAND]
        self.attack(bear)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 1))

    def test_self_named_payoff_stays_on_self(self):
        lava = self.put(self.a, DB.get("Lavacore Elemental"))
        before = lava.counters.get("time", 0)
        bear = self.put(self.a, BEAR)
        self.attack(bear)
        self.assertEqual(lava.counters.get("time", 0), before + 1)
        self.assertEqual(bear.counters, {})


if __name__ == "__main__":
    unittest.main()
