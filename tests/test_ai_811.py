"""#811: HeuristicAI casts Terrific Team-Up: its "+1/+0" pumps pick the damage sources (a bite run), not a combat
trick, and the damage is aimed at the opponent's creature."""
import random
import unittest

from mtgsim.ai import HeuristicAI, _is_trick
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class TerrificTeamUp(unittest.TestCase):
    def test_not_a_trick(self):
        self.assertFalse(_is_trick(db("Terrific Team-Up")))

    def test_ai_kills_their_creature_with_the_pumped_bear(self):
        a = Player("a", [], HeuristicAI())
        b = Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 3, "main1"
        a.library = b.library = [ISLAND] * 20
        for _ in range(4):
            game.enter_battlefield(a, FOREST)
        mine = game.enter_battlefield(a, BEAR)
        theirs = game.enter_battlefield(b, card("T 3/3", "{2}", "Creature — Elf", "", 3, 3))   # dies to 2 + 1
        a.hand = [db("Terrific Team-Up")]
        a.ai.main_phase(game, a)
        game.settle()
        self.assertEqual(a.hand, [])
        self.assertNotIn(theirs, b.battlefield)
        self.assertIn(mine, a.battlefield)
        self.assertEqual(mine.damage, 0)


if __name__ == "__main__":
    unittest.main()
