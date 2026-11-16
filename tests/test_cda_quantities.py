"""#397 slice: characteristic-defining P/T with any quantity cards._xq reads ("~'s power is equal to the greatest
mana value among creatures you control", "... the number of cards in your hand", "... 1 plus the number of lands
you control"). Read after every other face-line reader (cx_cda.late_line), evaluated as the P/T is read."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, ISLAND, card


class CdaQuantities(unittest.TestCase):
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

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick = p.tapped = False
        owner.battlefield.append(p)
        return p

    def test_real_cards_are_full(self):
        for name in ("Towering Gibbon", "Kraven, Proud Predator", "Allosaurus Rider"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_existing_readers_keep_their_lines(self):
        c = card("T", "{2}", "Creature — X", "~'s power is equal to the number of creatures you control.", 0, 1)
        self.assertEqual(c.pt_per, "creature")
        self.assertNotIn("cda_q", c.advanced_rules)

    def test_refusals(self):
        for text in ("~'s power is equal to its toughness.", "~'s power is equal to the number of frobs."):
            with self.subTest(text=text):
                self.assertTrue(card("T", "{2}", "Creature — X", text, 0, 1).unsupported)

    def test_greatest_mana_value(self):
        gibbon = self.perm(self.real("Towering Gibbon"), self.a)
        base_t = gibbon.toughness
        self.assertEqual(gibbon.power, 4)                  # itself: mana value 4
        self.perm(card("Big", "{6}", "Creature — Giant", "", 6, 6), self.a)
        self.assertEqual((gibbon.power, gibbon.toughness), (6, base_t))
        self.perm(card("Bigger", "{8}", "Creature — Giant", "", 8, 8), self.b)   # not mine
        self.assertEqual(gibbon.power, 6)

    def test_one_plus_lands(self):
        rider = self.perm(self.real("Allosaurus Rider"), self.a)
        self.assertEqual((rider.power, rider.toughness), (1, 1))
        for _ in range(3):
            self.perm(ISLAND, self.a)
        self.assertEqual((rider.power, rider.toughness), (4, 4))

    def test_cards_in_hand(self):
        c = card("Handy", "{2}", "Creature — X", "~'s power is equal to the number of cards in your hand.", 0, 3)
        handy = self.perm(c, self.a)
        self.a.hand = [ISLAND, ISLAND]
        self.assertEqual((handy.power, handy.toughness), (2, 3))


if __name__ == "__main__":
    unittest.main()
