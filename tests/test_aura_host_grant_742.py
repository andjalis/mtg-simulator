"""#742: "enchanted creature gains <keyword> until end of turn" from an Aura reaches the enchanted creature (the grant
kind read only an Equipment's attached_to)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


LAND = {c: card(n, types=f"Basic Land — {n}", text=f"({{T}}: Add {{{c}}}.)")
        for c, n in [("R", "Mountain"), ("U", "Island"), ("G", "Forest"), ("B", "Swamp")]}


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class AuraHostGrant(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def enchant(self, name, mana):
        for c in mana:
            self.game.enter_battlefield(self.a, LAND[c])
        bear = self.game.enter_battlefield(self.a, BEAR)
        aura = db(name)
        self.a.hand = [aura]
        self.assertTrue(self.game.cast(self.a, aura, [bear]))
        self.game.settle()
        return bear

    def test_aspect_of_manticore_enters_grant(self):
        bear = self.enchant("Aspect of Manticore", "RRR")
        self.assertEqual(bear.power, 4)
        self.assertTrue(bear.has("first strike"))

    def test_fae_flight_enters_grant(self):
        bear = self.enchant("Fae Flight", "UU")
        self.assertTrue(bear.has("flying"))
        self.assertTrue(bear.has("hexproof"))

    def test_keldon_mantle_activated_grant(self):
        bear = self.enchant("Keldon Mantle", "RRG")
        mantle = next(x for x in self.a.battlefield if x.card.name == "Keldon Mantle")
        idx = next(i for i, a in enumerate(mantle.card.activated)
                   if any(e.kind == "grant" for e in a.effects))
        self.game.enter_battlefield(self.a, LAND["G"])
        self.assertTrue(self.game.activate_ability(self.a, mantle, idx))
        self.game.settle()
        self.assertTrue(bear.has("trample"))


if __name__ == "__main__":
    unittest.main()
