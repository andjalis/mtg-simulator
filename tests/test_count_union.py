"""#449: "and" between card types in a count is a union. "The number of instant and sorcery cards in your graveyard"
counts the cards that are an instant or a sorcery (it was refused since #385, and before that counted 0)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.copies import fits
from mtgsim.counting import count
from mtgsim.engine import Game, Permanent, Player

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class CountUnion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [self.db.get("Island")] * 20
        get = self.db.get
        # two instants, one sorcery, one creature, one land: three count
        self.a.graveyard = [get("Shock"), get("Opt"), get("Divination"), get("Grizzly Bears"), get("Mountain")]

    def perm(self, name, owner):
        p = Permanent(self.db.get(name), owner)
        p.sick = p.tapped = False
        owner.battlefield.append(p)
        return p

    def test_fits_reads_and_as_or(self):
        get = self.db.get
        for name, want in (("Shock", True), ("Divination", True), ("Grizzly Bears", False), ("Sol Ring", False)):
            self.assertEqual(fits(get(name), "instant and sorcery"), want, name)
        self.assertTrue(fits(get("Sol Ring"), "artifact, enchantment, and land"))
        self.assertTrue(fits(get("Forest"), "creature and land"))
        self.assertFalse(fits(get("Shock"), "creature and land"))
        self.assertTrue(fits(get("Divination"), "instant and/or sorcery"))

    def test_quantities(self):
        for text, n in (("You gain 1 life for each instant and sorcery card in your graveyard.", 3),
                        ("Draw a card for each creature and land card in your graveyard.", 2)):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [], text)
            data = effects[0].data
            got = self.game.x_quantity(self.a, data["xq"], None, None) if "xq" in data else count(self.game, self.a, data["per"])
            self.assertEqual(got, n, text)

    def test_battlefield_union(self):
        effects, bad = _parse_effects("You gain X life, where X is the number of creatures and lands you control.")
        self.assertEqual(bad, [])
        for name in ("Grizzly Bears", "Forest", "Sol Ring"):
            self.perm(name, self.a)
        self.assertEqual(self.game.x_quantity(self.a, effects[0].data["xq"], None, None), 2)   # not the artifact

    def test_near_misses_still_refused(self):
        for text in ("You gain 1 life for each instant and frob card in your graveyard.",
                     "Draw a card for each snow and land permanent you control."):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [text], text)

    def test_spite_of_mogis_deals_the_union_count(self):
        """HeuristicAI casts it at the opponent's creature, for 3 (two instants and a sorcery)."""
        spite = self.db.get("Spite of Mogis")
        self.assertEqual(spite.unsupported, [])
        giant = self.perm("Hill Giant", self.b)                 # 3/3: only the full count of 3 kills it
        mine = self.perm("Grizzly Bears", self.a)
        self.perm("Mountain", self.a)
        self.a.hand = [spite]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spite, self.a.hand)
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(giant, self.b.battlefield)
        self.assertIn(giant.card, self.b.graveyard)

    def test_ai_scales_the_count_once(self):
        from mtgsim.cx_abil_damage import scaled
        eff = self.db.get("Spite of Mogis").spell_effects[0]
        once = scaled(self.game, self.a, eff, self.db.get("Spite of Mogis"))
        self.assertEqual(once.amount, 3)
        self.assertEqual(scaled(self.game, self.a, once).amount, 3)         # plan_damage scales before the AI does

    def test_steal_the_show_is_full_and_deals_the_count(self):
        show = self.db.get("Steal the Show")
        self.assertEqual(show.unsupported, [])
        damage = show.modes[1][0]
        self.assertEqual(damage.data.get("xq"), ("gy", "instant and sorcery"))
        self.assertEqual(self.game.x_quantity(self.a, damage.data["xq"], None, None), 3)


if __name__ == "__main__":
    unittest.main()
