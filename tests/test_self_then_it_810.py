"""#810: in an activated ability, "it" after an effect on ~ is ~ (Possessed Goat, Drudge Sentinel, Bristling Hydra,
Icehide Troll); a trigger's own subject or spell stays its "that ..." (Prismari Apprentice)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

SNOW = card("Snow-Covered Forest", types="Basic Snow Land — Forest", text="({T}: Add {G}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class SelfThenIt(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, name, lands=0, land=ISLAND):
        x = self.game.enter_battlefield(self.a, db(name))
        x.sick = False
        for _ in range(lands):
            self.game.enter_battlefield(self.a, land)
        return x

    def activate(self, perm):
        self.assertTrue(self.game.activate_ability(self.a, perm, 0))
        self.game.settle()

    def test_possessed_goat_becomes_a_black_demon(self):
        goat = self.put("Possessed Goat", 3)
        self.a.hand = [ISLAND]
        self.activate(goat)
        self.assertEqual(goat.counters.get("+1/+1"), 3)
        self.assertIn("Demon", goat.card.subtypes)
        self.assertIn("B", goat.card.colors)

    def test_drudge_sentinel_tapped_and_indestructible(self):
        sentinel = self.put("Drudge Sentinel", 3)
        self.activate(sentinel)
        self.assertTrue(sentinel.tapped and sentinel.has("indestructible"))

    def test_bristling_hydra_gains_hexproof(self):
        hydra = self.put("Bristling Hydra")
        self.a.counters["energy"] = 3
        self.activate(hydra)
        self.assertTrue(hydra.has("hexproof"))

    def test_icehide_troll_taps_itself(self):
        troll = self.put("Icehide Troll", 2, SNOW)
        self.activate(troll)
        self.assertTrue(troll.tapped and troll.has("indestructible"))


if __name__ == "__main__":
    unittest.main()
