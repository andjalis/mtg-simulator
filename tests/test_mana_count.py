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


class AuraMana(ManaCount):
    def enchant(self, land, aura_name):
        aura = self.game.enter_battlefield(self.a, self.db.get(aura_name))
        aura.aura_host = land
        land.auras.append(aura)
        return aura

    def test_parse_keeps_named_colours(self):
        wg = self.db.get("Wild Growth")
        self.assertEqual(wg.advanced_rules["aura_mana_colors"], (frozenset("G"),))
        self.assertFalse(wg.approximations)

    def test_wild_growth_adds_green_not_the_lands_colour(self):
        from mtgsim.engine.mana import find_payment
        land = self.put("Mountain")
        self.assertIsNone(find_payment([land], {"G": 1, "R": 1}))
        self.enchant(land, "Wild Growth")
        self.assertIsNotNone(find_payment([land], {"G": 1, "R": 1}))      # {R} from the land, the extra {G}
        self.assertIsNone(find_payment([land], {"R": 2}))                 # the extra mana is not red

    def test_fertile_ground_adds_any_colour(self):
        from mtgsim.engine.mana import find_payment
        land = self.put("Mountain")
        self.enchant(land, "Fertile Ground")
        self.assertIsNotNone(find_payment([land], {"U": 1, "R": 1}))

    def test_ai_pays_with_enchanted_land(self):
        """A real turn: Mountain + Wild Growth alone pay {1}{G} for Grizzly Bears."""
        land = self.put("Mountain")
        self.enchant(land, "Wild Growth")
        self.a.hand = [self.db.get("Grizzly Bears")]
        self.a.library = [self.db.get("Giant Growth")] * 20
        self.game.take_turn(self.a)
        self.assertTrue(any(x.card.name == "Grizzly Bears" for x in self.a.battlefield))


if __name__ == "__main__":
    unittest.main()
