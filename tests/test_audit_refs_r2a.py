"""Fixes from the opus-refs behaviour audit, round 2 (2026-11-16), the part without downgrades: copies.fits reads
colours, outlaw, historic, battle / nonbattle and multicolored / monocolored / colorless (#802), and Mark of Eviction
is a hostile Aura (#803). The refusal of unreadable descriptions stays in #807."""
import random
import unittest
from pathlib import Path

from mtgsim import copies
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
SHADE = card("Test Shade", "{1}{B}", "Creature — Shade", "", 2, 2)
ROGUE = card("Test Rogue", "{1}{B}", "Creature — Human Rogue", "", 2, 2)
PIRATE = card("Test Pirate", "{1}{U}", "Creature — Human Pirate", "", 2, 2)
RELIC = card("Test Relic", "{2}", "Artifact", "")
LEGEND = card("Test Legend", "{2}", "Legendary Creature — Human", "", 2, 2)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 20, [ISLAND] * 20
    return g, a, b


class Fits(unittest.TestCase):
    def test_new_words(self):
        self.assertTrue(copies.fits(SHADE, "black creature"))
        self.assertFalse(copies.fits(BEAR, "black creature"))
        self.assertTrue(copies.fits(BEAR, "blue or green creature"))
        self.assertTrue(copies.fits(ROGUE, "outlaw creature"))
        self.assertFalse(copies.fits(BEAR, "outlaw creature"))
        self.assertTrue(copies.fits(RELIC, "historic"))
        self.assertTrue(copies.fits(LEGEND, "historic"))
        self.assertFalse(copies.fits(BEAR, "historic"))
        self.assertTrue(copies.fits(BEAR, "nonbattle permanent"))
        gold = card("Test Gold", "{G}{W}", "Creature — Elf Soldier", "", 3, 3)
        self.assertTrue(copies.fits(gold, "multicolored"))
        self.assertFalse(copies.fits(BEAR, "multicolored"))
        self.assertTrue(copies.fits(BEAR, "monocolored"))
        self.assertTrue(copies.fits(RELIC, "colorless"))

    def test_readable(self):
        for desc in ("black creature", "outlaw creature", "non-Assassin historic", "Vampire or Wizard creature",
                     "noncreature nonland permanent"):
            self.assertTrue(copies.readable(desc), desc)
        for desc in ("another permanent", "other Klingon and Warrior creature",
                     "creature card from your graveyard to the battlefield, then return another creature"):
            self.assertFalse(copies.readable(desc), desc)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def lands(self, g, p, name, n):
        for _ in range(n):
            g.enter_battlefield(p, self.db.get(name)).sick = False
        g.settle()

    def test_back_in_town_returns_outlaws(self):
        g, a, b = game()
        self.lands(g, a, "Swamp", 5)
        a.graveyard = [BEAR, ROGUE, PIRATE]
        a.hand = [self.db.get("Back in Town")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual(sorted(x.card.name for x in a.battlefield if x.is_creature), ["Test Pirate", "Test Rogue"])

    def test_call_to_the_netherworld_returns_the_black_creature(self):
        g, a, b = game()
        self.lands(g, a, "Swamp", 1)
        a.graveyard = [BEAR, SHADE]
        c = self.db.get("Call to the Netherworld")
        a.hand = [c]
        self.assertTrue(g.cast(a, c, None))
        g.settle()
        self.assertEqual([x.name for x in a.hand], ["Test Shade"])

    def test_mark_of_eviction_goes_on_the_opponents_creature(self):
        g, a, b = game()
        self.lands(g, a, "Island", 1)
        g.enter_battlefield(a, BEAR)
        g.enter_battlefield(b, self.db.get("Craw Wurm"))
        g.settle()
        a.hand = [self.db.get("Mark of Eviction")]
        a.ai.main_phase(g, a)
        g.settle()
        g.step = "upkeep"
        g.fire(a, "upkeep")
        g.settle()
        self.assertIn("Grizzly Bears", [x.card.name for x in a.battlefield])
        self.assertIn("Craw Wurm", [x.name for x in b.hand])


if __name__ == "__main__":
    unittest.main()
