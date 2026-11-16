"""#831: the AI casts "{X}" permanents (Endless One, Hangarback Walker, Sigil of Distinction) at the largest X its
mana pays for; X = 0 is never worth casting."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class XPermanents(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def board(self, lands):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        for _ in range(lands):
            g.enter_battlefield(a, self.db.get("Forest")).sick = False
        g.enter_battlefield(a, BEAR)
        g.settle()
        return g, a

    def cast_with(self, name, lands):
        g, a = self.board(lands)
        a.hand = [self.db.get(name)]
        a.ai.main_phase(g, a)
        g.settle()
        return next((x for x in a.battlefield if x.card.name == name), None)

    def test_cast_at_the_largest_x(self):
        self.assertEqual(self.cast_with("Endless One", 4).counters.get("+1/+1"), 4)
        self.assertEqual(self.cast_with("Hangarback Walker", 4).counters.get("+1/+1"), 2)     # {X}{X}
        self.assertEqual(self.cast_with("Sigil of Distinction", 3).counters.get("charge"), 3)

    def test_never_at_x_zero(self):
        for name in ("Endless One", "Hangarback Walker", "Sigil of Distinction"):
            self.assertIsNone(self.cast_with(name, 0), name)


if __name__ == "__main__":
    unittest.main()
