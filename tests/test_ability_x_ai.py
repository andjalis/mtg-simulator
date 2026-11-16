"""#379: the AI activates {X} abilities with the X it can afford, and judges "mana value X or less" with that X."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.engine.policy import ability_worth, use_abilities
from tests.test_cx_grammar import DB_FILE


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class FiendArtisan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def game(self, swamps, library):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main2"          # the AI uses general abilities in its second main phase
        a.library = [self.db.get(n) for n in library]
        b.library = [self.db.get("Island")] * 10
        for _ in range(swamps):
            g.enter_battlefield(a, self.db.get("Swamp")).sick = False
        artisan = g.enter_battlefield(a, self.db.get("Fiend Artisan"))
        artisan.sick = False
        fodder = g.enter_battlefield(a, self.db.get("Grizzly Bears"))
        g.settle()
        return g, a, artisan, fodder

    def test_ai_activates_with_x_and_fetches_within_x(self):
        self.assertEqual(self.db.get("Fiend Artisan").unsupported, [])
        g, a, artisan, fodder = self.game(5, ["Craw Wurm", "Hill Giant", "Llanowar Elves"])
        self.assertEqual(g.ability_x(a, artisan, artisan.activated[0]), 4)      # 5 Swamps: {B} + X=4
        self.assertTrue(ability_worth(g, a, artisan, 0))
        use_abilities(g, a)
        g.settle()
        names = [x.card.name for x in a.battlefield]
        self.assertNotIn("Grizzly Bears", names)                # sacrificed
        self.assertIn("Hill Giant", names)                      # the best creature with mana value <= 4
        self.assertNotIn("Craw Wurm", names)                    # mana value 6: out of reach at X=4
        self.assertTrue(artisan.tapped)

    def test_no_upgrade_within_x(self):
        g, a, artisan, fodder = self.game(2, ["Craw Wurm", "Llanowar Elves"])     # X=1: only Llanowar Elves
        self.assertFalse(ability_worth(g, a, artisan, 0))       # not worth a Grizzly Bears
        use_abilities(g, a)
        self.assertIn(fodder, a.battlefield)


if __name__ == "__main__":
    unittest.main()
