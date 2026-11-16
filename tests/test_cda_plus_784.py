"""#784 (split from #790): "P/T equal to the number of X plus the number of Y" and "... among ..." no longer become a
garbled count that evaluates to 0; the general quantity reader (cx_cda.late_line -> _xq) reads them."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
ZOMBIE = card("Test Zombie", "{B}", "Creature — Zombie", "", 1, 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class CdaCounts(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g, self.a, self.b = Game(a, b, random.Random(0), log=True), a, b
        self.g.turn, self.g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10

    def enter(self, p, c, n=1):
        for _ in range(n):
            self.g.enter_battlefield(p, c)
        self.g.settle()

    def test_x_plus_y(self):
        self.enter(self.a, ELF, 2)
        self.enter(self.b, ELF)
        self.a.graveyard = [ELF, BEAR]
        ab = self.g.enter_battlefield(self.a, self.db.get("Abomination of Llanowar"))
        self.g.settle()
        self.assertEqual((ab.power, ab.toughness), (4, 4))

    def test_zombies_on_the_battlefield_plus_in_graveyards(self):
        self.enter(self.a, ZOMBIE, 2)
        self.enter(self.b, ZOMBIE)
        self.a.graveyard, self.b.graveyard = [ZOMBIE], [ZOMBIE]
        so = self.g.enter_battlefield(self.a, self.db.get("Soulless One"))
        self.g.settle()
        self.assertEqual((so.power, so.toughness), (6, 6))

    def test_domain(self):
        for land in ("Mountain", "Forest", "Plains"):
            self.enter(self.a, self.db.get(land))
        kavu = self.g.enter_battlefield(self.a, self.db.get("Territorial Kavu"))
        self.g.settle()
        self.assertEqual((kavu.power, kavu.toughness), (3, 3))

    def test_no_garbled_count(self):
        for name in ("Abomination of Llanowar", "Dauntless Dourbark", "Soulless One", "Territorial Kavu",
                     "Matca Rioters", "Opulent Clomper"):
            self.assertFalse(any(w in self.db.get(name).pt_cda for w in (" plu ", " among ", " control")), name)


if __name__ == "__main__":
    unittest.main()
