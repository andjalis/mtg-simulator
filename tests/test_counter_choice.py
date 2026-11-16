"""#627: "~ enters with your choice of a X counter or a Y counter on it" and Grimdancer's two different counters
(mtgsim.cx_counter_choice)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Boot Nipper", "Ferocious Tigorilla", "Flycatcher Giraffid", "Helica Glider", "Wingfold Pteron", "Grimdancer")
NIPPER = card("Test Nipper", "{1}{B}", "Creature — Beast", "~ enters with your choice of a deathtouch counter or a "
                                                           "lifelink counter on it.", 2, 1)
DANCER = card("Test Dancer", "{1}{B}{B}", "Creature — Human Rogue", "~ enters with your choice of two different "
              "counters on it from among menace, deathtouch, and lifelink.", 3, 3)


class Parse(unittest.TestCase):
    def test_entry_choice(self):
        self.assertEqual(NIPPER.unsupported, [])
        self.assertEqual(NIPPER.etb_named_counters, ("choice:deathtouch|lifelink", 1))
        self.assertEqual(DANCER.unsupported, [])
        self.assertEqual(DANCER.etb_named_counters, ("choice2:menace|deathtouch|lifelink", 1))

    def test_refusals(self):
        for text in ("~ enters with your choice of a +1/+1 counter or a flying counter on it.",
                     "~ enters with your choice of a flying counter or a flying counter on it.",
                     "~ enters with your choice of a flying counter or a banding counter on it.",
                     "~ enters with your choice of three different counters on it from among menace, deathtouch, "
                     "and lifelink."):
            self.assertTrue(card("Test Odd", "{1}", "Creature — Bird", text, 1, 1).unsupported, text)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def test_one_counter_it_lacks(self):
        x = self.g.enter_battlefield(self.a, NIPPER)
        kinds = {k for k, v in x.counters.items() if v}
        self.assertEqual(len(kinds & {"deathtouch", "lifelink"}), 1)
        self.assertTrue(x.has("deathtouch") or x.has("lifelink"))

    def test_skips_a_keyword_it_already_has(self):
        c = card("Test Nipper", "{1}{B}", "Creature — Beast", "Deathtouch\n~ enters with your choice of a deathtouch "
                 "counter or a lifelink counter on it.", 2, 1)
        x = self.g.enter_battlefield(self.a, c)
        self.assertEqual(x.counters.get("lifelink"), 1)
        self.assertFalse(x.counters.get("deathtouch"))

    def test_two_different(self):
        x = self.g.enter_battlefield(self.a, DANCER)
        got = sorted(k for k in ("menace", "deathtouch", "lifelink") if x.counters.get(k))
        self.assertEqual(len(got), 2)
        self.assertTrue(all(x.has(k) for k in got))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()
