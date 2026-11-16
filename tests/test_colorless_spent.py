"""#324 tail: "if {C} was / wasn't spent to cast it" read from the payment's colourless count, on "When you cast this
spell" triggers (whose condition reads the cast spell, the trigger's context), and Wumpus Aberration's "target
opponent may put a creature card from their hand onto the battlefield" (the opponent's own choice)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, ISLAND, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


class ColorlessSpent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    @classmethod
    def tearDownClass(cls):
        if cls.db._all is not None:
            cls.db._all.close()

    def real(self, name):
        if self.db._all is None:
            self.skipTest("card database not built")
        return self.db.get(name)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def lands(self, *cards):
        for c in cards:
            c = self.real("Wastes") if c == "Wastes" else c
            p = Permanent(c, self.a)
            p.sick = p.tapped = False
            self.a.battlefield.append(p)

    def cast(self, c):
        self.a.hand = [c]
        self.assertTrue(self.g.cast(self.a, c, None))
        self.g.settle()

    def spawns(self):
        return [x for x in self.a.creatures if x.card.is_token]

    def test_real_cards_are_full(self):
        for name in ("Drowner of Truth // Drowned Jungle", "Wumpus Aberration"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_condition_codes(self):
        from mtgsim.cx_condlib import parse
        self.assertEqual(parse("{C} was spent to cast it"), 'lib:["mana_color","C",1]')
        self.assertTrue(parse("{C} wasn't spent to cast it").startswith('lib:["not"'))
        self.assertEqual(parse("{C}{C} was spent to cast it"), "")      # an amount, not read here

    def test_opponent_put_refuses_riders(self):
        effects, bad = _parse_effects("Target opponent may put a creature card from their hand onto the battlefield "
                                      "tapped and attacking.")
        self.assertTrue(bad, effects)

    def test_drowner_with_colorless_makes_spawn(self):
        self.lands("Wastes", "Wastes", "Wastes", "Wastes", "Wastes", FOREST, FOREST)
        self.cast(self.real("Drowner of Truth // Drowned Jungle"))
        self.assertEqual(len(self.spawns()), 2)

    def test_drowner_without_colorless_makes_none(self):
        self.lands(*([FOREST] * 7))
        self.cast(self.real("Drowner of Truth // Drowned Jungle"))
        self.assertEqual(len(self.spawns()), 0)

    def test_wumpus_without_colorless_lets_the_opponent_put_a_creature(self):
        giant = card("Hill Giant", "{3}{R}", "Creature — Giant", "", 3, 3)
        self.b.hand = [giant]
        self.lands(FOREST, FOREST, FOREST, FOREST)
        self.cast(self.real("Wumpus Aberration"))
        self.assertIn(giant.name, [x.card.name for x in self.b.battlefield])
        self.assertNotIn(giant, self.b.hand)

    def test_wumpus_with_colorless_does_not(self):
        giant = card("Hill Giant", "{3}{R}", "Creature — Giant", "", 3, 3)
        self.b.hand = [giant]
        self.lands("Wastes", "Wastes", "Wastes", FOREST)
        self.cast(self.real("Wumpus Aberration"))
        self.assertEqual(self.b.hand, [giant])
        self.assertNotIn(giant.name, [x.card.name for x in self.b.battlefield])


if __name__ == "__main__":
    unittest.main()
