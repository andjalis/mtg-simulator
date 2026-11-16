"""#865 item A, slice 1: "an X/X ... creature token" sized by the X paid (spell, ETB of an X spell, {X} ability,
cycling {X}) or by a "where X is" quantity."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cx_tokens import describe, parse_create
from mtgsim.cards.model import NO_MATCH
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
FOREST = card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)")
MOUNTAIN = card("Mountain", "", "Basic Land — Mountain", "({T}: Add {R}.)")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 20, [ISLAND] * 20
    a.my_turn, b.my_turn = True, False
    return g, a, b


def lands(g, p, land, n):
    for _ in range(n):
        g.enter_battlefield(p, land)


def tokens(p):
    return [(x.card.name, x.power, x.toughness) for x in p.battlefield if x.card.is_token]


class Parse(unittest.TestCase):
    def test_x_sized_creature_token(self):
        spec = describe("X/X green Ooze creature token")
        self.assertTrue(spec["x_size"])
        self.assertEqual(spec["card"].power, 0)

    def test_where_x_sizes_instead_of_counting(self):
        effs = parse_create("you", "an X/X black Zombie creature token, where X is the number of creature cards in your graveyard")
        self.assertIsNot(effs, NO_MATCH)
        self.assertEqual(effs[0].amount, 1)
        self.assertTrue(effs[0].data["xq_size"])

    def test_refusals(self):
        self.assertIsNone(describe("X/X colorless Construct artifact token"))       # not a creature: no P/T
        self.assertIsNone(describe("X/Y green Ooze creature token"))
        self.assertIs(parse_create("you", "X X/X green Ooze creature tokens"), NO_MATCH)   # count and size both X
        self.assertIs(parse_create("you", "an X/X green Ooze creature token for each opponent you have"), NO_MATCH)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Play(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_ai_casts_slime_molding_for_all_its_mana(self):
        g, a, b = game()
        lands(g, a, FOREST, 5)
        a.hand = [self.db.get("Slime Molding")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual(tokens(a), [("Ooze token", 4, 4)])

    def test_etb_of_an_x_spell(self):
        g, a, b = game()
        lands(g, a, FOREST, 5)
        a.hand = [self.db.get("Arboreal Alliance")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual(tokens(a), [("Treefolk token", 3, 3)])

    def test_x_ability(self):
        g, a, b = game()
        mask = g.enter_battlefield(a, self.db.get("Mask of the Jadecrafter"))
        lands(g, a, FOREST, 4)
        self.assertTrue(g.activate_ability(a, mask, 0, x=4))
        g.settle()
        self.assertEqual(tokens(a), [("Golem token", 4, 4)])

    def test_cycling_x(self):
        g, a, b = game()
        lands(g, a, ISLAND, 3)
        a.hand = [self.db.get("Shark Typhoon")]
        g.cycle_spare(a)
        g.settle()
        sharks = [x for x in a.battlefield if x.card.is_token]
        self.assertEqual([(x.power, x.toughness, x.has("flying")) for x in sharks], [(1, 1, True)])

    def test_sacrificed_x(self):
        g, a, b = game()
        lands(g, a, MOUNTAIN, 6)
        a.hand = [self.db.get("Devastating Summons")]
        a.ai.main_phase(g, a)
        g.settle()
        made = tokens(a)
        self.assertEqual(len(made), 2)
        n = 6 - sum(x.card.is_land for x in a.battlefield)      # lands sacrificed = X
        self.assertTrue(all(p == t == n for _, p, t in made))


if __name__ == "__main__":
    unittest.main()
