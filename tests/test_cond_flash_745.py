"""#745: "This spell has flash as long as <condition>" lets the spell be cast at instant speed while the condition holds
for its caster (cond_keywords were read only on the battlefield)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
MERFOLK = card("Test Merfolk", "{U}", "Creature — Merfolk", "", 1, 1)
DESERT = card("Test Desert", types="Land — Desert", text="({T}: Add {C}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class ConditionalFlash(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn = 3
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        self.game.active_idx = 1            # the opponent's turn, end step: only instant-speed spells
        for p in (self.a, self.b):
            p.my_turn = p is self.b
        self.game.step = "end"

    def lands(self, land, n):
        for _ in range(n):
            self.game.enter_battlefield(self.a, land)

    def castable(self, name):
        c = db(name)
        self.a.hand = [c]
        return self.game.can_cast_now(self.a, c)

    def test_graveyard_shift_five_mana_values(self):
        self.lands(SWAMP, 5)
        self.a.graveyard.extend([db(n) for n in ("Craw Wurm", "Shock", "Grizzly Bears", "Divination")])
        self.assertFalse(self.castable("Graveyard Shift"))
        self.a.graveyard.append(db("Serra Angel"))
        self.assertTrue(self.castable("Graveyard Shift"))

    def test_crashing_tide_with_a_merfolk(self):
        self.lands(ISLAND, 6)
        self.assertFalse(self.castable("Crashing Tide"))
        self.game.enter_battlefield(self.a, MERFOLK)
        self.assertTrue(self.castable("Crashing Tide"))

    def test_colossal_rattlewurm_with_a_desert(self):
        self.lands(FOREST, 7)
        self.assertFalse(self.castable("Colossal Rattlewurm"))
        self.game.enter_battlefield(self.a, DESERT)
        self.assertTrue(self.castable("Colossal Rattlewurm"))

    def test_take_for_a_ride_after_a_crime(self):
        for land in ("Mountain", "Mountain", "Mountain"):
            self.game.enter_battlefield(self.a, card(land, types=f"Basic Land — {land}", text="({T}: Add {R}.)"))
        self.assertFalse(self.castable("Take for a Ride"))
        self.game.fire(self.a, "crime")
        self.assertTrue(self.castable("Take for a Ride"))

    def test_the_condition_is_the_casters(self):
        self.lands(ISLAND, 6)
        self.game.enter_battlefield(self.b, MERFOLK)            # their Merfolk doesn't count
        self.assertFalse(self.castable("Crashing Tide"))
        self.game.enter_battlefield(self.a, BEAR)
        self.assertFalse(self.castable("Crashing Tide"))


if __name__ == "__main__":
    unittest.main()
