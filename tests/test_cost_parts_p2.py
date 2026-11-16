"""#636: more activated-ability cost parts: half your life, a counter from any permanent, a card from hand onto the
library, "artifacts and/or creatures" taps."""
import random
import unittest

from mtgsim import cx_abil_costs as C
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

HALF = card("Test Half", "{1}", "Artifact", "Pay half your life, rounded up: Draw a card.")
SPARK = card("Test Spark", "{1}", "Artifact", "{T}, Remove a counter from a permanent you control: You gain 3 life.")
BREW = card("Test Brew", "{1}", "Artifact", "Put a card from your hand on top of your library: You gain 1 life.")
SYNC = card("Test Sync", "{1}", "Artifact",
            "Tap two untapped artifacts and/or creatures you control: You gain 2 life.")


class CostPartsP2(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parse(self):
        for c in (HALF, SPARK, BREW, SYNC):
            self.assertEqual(c.unsupported, [], c.name)
        extra = {}
        self.assertFalse(C.parse_part("Pay half your life", extra))        # no rounding named: not understood

    def test_half_life_up(self):
        self.a.life = 15
        perm = self.game.enter_battlefield(self.a, HALF)
        perm.sick = False
        self.assertTrue(self.game.activate_ability(self.a, perm, 0))
        self.game.settle()
        self.assertEqual(self.a.life, 7)

    def test_remove_counter_from_any_permanent(self):
        perm = self.game.enter_battlefield(self.a, SPARK)
        perm.sick = False
        other = self.game.enter_battlefield(self.a, card("Cairn", "{1}", "Artifact", ""))
        other.counters["charge"] = 1
        life = self.a.life
        self.assertTrue(self.game.activate_ability(self.a, perm, 0))
        self.game.settle()
        self.assertEqual(other.counters["charge"], 0)
        self.assertEqual(self.a.life, life + 3)

    def test_hand_card_to_library_top(self):
        perm = self.game.enter_battlefield(self.a, BREW)
        perm.sick = False
        self.a.hand = [ISLAND]
        before = len(self.a.library)
        self.assertTrue(self.game.activate_ability(self.a, perm, 0))
        self.assertEqual((len(self.a.hand), len(self.a.library)), (0, before + 1))

    def test_cannot_pay_without_the_resource(self):
        perm = self.game.enter_battlefield(self.a, BREW)
        perm.sick = False
        self.a.hand = []
        self.assertFalse(self.game.activate_ability(self.a, perm, 0))


if __name__ == "__main__":
    unittest.main()
