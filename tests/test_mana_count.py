"""Counted mana amounts: Gaea's Cradle, Cloudpost, Gyre Sage, Marwyn; the default AI uses them to cast spells."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND


class ManaCount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, name, owner=None):
        perm = self.game.enter_battlefield(owner or self.a, self.db.get(name))
        perm.sick = False
        return perm

    def test_parse_is_full(self):
        for name in ("Gaea's Cradle", "Cloudpost", "Gyre Sage", "Marwyn, the Nurturer", "Tolarian Academy", "Elvish Archdruid"):
            c = self.db.get(name)
            self.assertTrue(c.mana_dyn, name)
            self.assertFalse(c.approximations, name)

    def amount(self, perm):
        from mtgsim.engine.mana import _amount
        return _amount(perm)

    def test_cradle_counts_creatures(self):
        cradle = self.put("Gaea's Cradle")
        self.assertEqual(self.amount(cradle), 0)
        self.put("Grizzly Bears"), self.put("Grizzly Bears")
        self.assertEqual(self.amount(cradle), 2)

    def test_cradle_with_no_creatures_pays_nothing(self):
        from mtgsim.engine.mana import find_payment
        cradle = self.put("Gaea's Cradle")
        self.assertIsNone(find_payment([cradle], {"G": 1}))
        self.put("Grizzly Bears")
        self.assertIsNotNone(find_payment([cradle], {"G": 1}))

    def test_cloudpost_counts_all_loci(self):
        post = self.put("Cloudpost")
        self.put("Cloudpost", self.b)
        self.assertEqual(self.amount(post), 2)

    def test_counters_and_power(self):
        sage = self.put("Gyre Sage")
        sage.counters["+1/+1"] = 3
        self.assertEqual(self.amount(sage), 3)
        marwyn = self.put("Marwyn, the Nurturer")
        self.assertEqual(self.amount(marwyn), marwyn.power)

    def test_ai_casts_with_counted_mana(self):
        """In a real turn the default AI pays {1}{G} for a Grizzly Bears with Gaea's Cradle (two creatures out)."""
        self.put("Gaea's Cradle")
        self.put("Grizzly Bears"), self.put("Grizzly Bears")
        self.a.hand = [self.db.get("Grizzly Bears")]
        self.a.library = [self.db.get("Giant Growth")] * 20      # keeps the draw from adding a land
        self.game.take_turn(self.a)
        bears = [x for x in self.a.battlefield if x.card.name == "Grizzly Bears"]
        self.assertEqual(len(bears), 3)


if __name__ == "__main__":
    unittest.main()
