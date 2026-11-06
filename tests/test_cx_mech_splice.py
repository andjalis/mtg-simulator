"""cx_mech: Splice onto Arcane."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, BEAR


class Splice(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parses_with_no_ignored_text(self):
        for n in ("Blessed Breath", "Candles' Glow", "Consuming Vortex"):
            self.assertEqual(self.db.get(n).unsupported, [], n)

    def test_spliced_effects_resolve_and_card_stays_in_hand(self):
        arcane, vortex = self.db.get("Ethereal Haze"), self.db.get("Consuming Vortex")
        self.a.hand = [arcane, vortex]
        victim = self.game.enter_battlefield(self.b, BEAR)
        self.game.settle()
        for land in ["Plains"] + ["Island"] * 5:
            self.game.enter_battlefield(self.a, self.db.get(land))
        self.game.settle()
        opts = [v for v in self.game.spell_options(self.a) if v.name.startswith("Ethereal Haze (splice")]
        self.assertEqual(len(opts), 1)
        self.assertTrue(self.game.cast(self.a, opts[0]))
        self.game.settle()
        self.assertNotIn(victim, self.b.battlefield)
        self.assertEqual([c.name for c in self.b.hand], [BEAR.name])
        self.assertIn(vortex, self.a.hand)

    def test_no_splice_onto_non_arcane(self):
        shock = self.db.get("Lightning Bolt")
        self.a.hand = [shock, self.db.get("Consuming Vortex")]
        self.assertFalse([v for v in self.game.spell_options(self.a) if "splice" in v.name])

    def test_several_cards_can_be_spliced_onto_one_spell(self):
        arcane = self.db.get("Ethereal Haze")
        vortex, breath = self.db.get("Consuming Vortex"), self.db.get("Blessed Breath")
        self.a.hand = [arcane, vortex, breath]
        victim = self.game.enter_battlefield(self.b, BEAR)
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        for land in ["Plains", "Plains"] + ["Island"] * 4:
            self.game.enter_battlefield(self.a, self.db.get(land))
        self.game.settle()
        opts = [v for v in self.game.spell_options(self.a) if v.name.startswith("Ethereal Haze (splice")]
        self.assertEqual(len(opts), 3)                  # Vortex, Breath, and both
        both = max(opts, key=lambda v: len(v.spliced))
        self.assertEqual(len(both.spliced), 2)
        self.assertTrue(self.game.cast(self.a, both))
        self.game.settle()
        self.assertNotIn(victim, self.b.battlefield)    # Consuming Vortex's effect
        self.assertTrue(any(k.startswith("protection from") for k in mine.temp_kw))   # Blessed Breath's
        self.assertIn(vortex, self.a.hand)
        self.assertIn(breath, self.a.hand)


if __name__ == "__main__":
    unittest.main()
