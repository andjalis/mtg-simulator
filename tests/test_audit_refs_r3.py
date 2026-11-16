"""Fix from the opus-refs behaviour audit, round 3 (2026-11-16): job select attaches an Equipment whose equip cost
isn't mana (Dark Knight's Greatsword, #828)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class JobSelect(unittest.TestCase):
    def test_greatsword_attaches_to_its_hero(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        sword = g.enter_battlefield(a, db.get("Dark Knight's Greatsword"))
        g.settle()
        hero = next(x for x in a.battlefield if x.is_creature)
        self.assertIs(sword.attached_to, hero)
        self.assertEqual((hero.power, hero.toughness), (4, 1))


if __name__ == "__main__":
    unittest.main()
