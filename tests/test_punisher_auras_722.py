"""#722: Auras whose only abilities hurt the enchanted permanent's controller are hostile: the caster puts them on an
opponent's permanent, not on its own."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
UISLAND = card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class PunisherAuras(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_hostile_flags(self):
        for name in ("Cursed Land", "Feedback", "Warp Artifact", "Festering Wound", "Power Taint", "Psychic Venom",
                     "Spreading Algae", "Blight", "Brink of Disaster", "Backfire"):
            self.assertTrue(db(name).aura_hostile, name)
        for name in ("Essence Flare", "Rancor"):        # a bonus to the host keeps it friendly
            self.assertFalse(db(name).aura_hostile, name)

    def test_ai_puts_cursed_land_on_the_opponents_land(self):
        for _ in range(4):
            self.game.enter_battlefield(self.a, SWAMP)
        theirs = self.game.enter_battlefield(self.b, UISLAND)
        self.a.hand = [db("Cursed Land")]
        self.a.ai.main_phase(self.game, self.a)
        self.game.settle()
        aura = next(x for x in self.a.battlefield if x.card.name == "Cursed Land")
        self.assertIs(aura.aura_host, theirs)

    def test_cursed_land_on_their_land_hurts_them(self):
        for _ in range(4):
            self.game.enter_battlefield(self.a, SWAMP)
        theirs = self.game.enter_battlefield(self.b, UISLAND)
        self.a.hand = [db("Cursed Land")]
        self.assertTrue(self.game.cast(self.a, self.a.hand[0], [theirs]))
        self.game.settle()
        self.game.active_idx = 1
        self.game.begin_upkeep(self.b)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.assertLess(self.b.life, 20)


if __name__ == "__main__":
    unittest.main()
