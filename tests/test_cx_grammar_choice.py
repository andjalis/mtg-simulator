"""#627: "gains / loses your choice of A, B, or C" (mtgsim.cx_grammar_choice)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Alchemist's Gift", "Argivian Avenger", "Assassin Initiate", "Butcher of the Horde", "Ezrim, Agency Chief",
        "Golem Artisan", "Hungering Puppetbeast", "Hunter's Axe", "Jodah's Avenger", "Lunar Avenger", "Manifold Mouse",
        "Rattleback Apothecary", "Shifting Ceratops", "Silverquill Pledgemage", "Veteran Warleader", "Walking Sponge",
        "Wingnut, Bat on the Belfry")
GIFT = card("Test Gift", "{B}", "Instant", "Target creature gets +1/+1 and gains your choice of deathtouch or lifelink "
                                           "until end of turn.")
SPONGE = card("Test Sponge", "{2}{U}", "Creature — Sponge", "{T}: Target creature loses your choice of flying, first "
                                                           "strike, or trample until end of turn.", 1, 1)


class Parse(unittest.TestCase):
    def test_gains(self):
        self.assertEqual(GIFT.unsupported, [])
        self.assertEqual([(e.kind, e.data.get("keyword")) for e in GIFT.spell_effects],
                         [("pump", None), ("grant", "choice:deathtouch|lifelink")])

    def test_four_options_with_protection(self):
        c = card("Test Avenger", "{3}", "Creature — Avatar", "{0}: Until end of turn, ~ gets -1/-1 and gains your "
                 "choice of double strike, protection from red, vigilance, or shadow.", 4, 4)
        self.assertEqual(c.unsupported, [])
        grant = c.activated[0].effects[-1]
        self.assertEqual(grant.data["keyword"], "choice:double strike|protection from red|vigilance|shadow")

    def test_loses(self):
        self.assertEqual(SPONGE.unsupported, [])
        eff = SPONGE.activated[0].effects[0]
        self.assertEqual((eff.kind, eff.data["keyword"], eff.data["side"]),
                         ("cx_lose_kw", "choice:flying|first strike|trample", "theirs"))

    def test_refusals(self):
        for text in ("~ gains your choice of banding or flying until end of turn.",       # not an engine keyword
                     "~ gains your choice of flying or +1/+1 until end of turn.",
                     "~ gains your choice of flying or flying until end of turn.",
                     "Target creature gains your choice of flying or haste."):           # no duration
            c = card("Test Odd", "{1}", "Creature — Bird", "{1}: " + text, 1, 1)
            self.assertTrue(c.unsupported, text)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def creature(self, owner, text=""):
        x = self.g.enter_battlefield(owner, card("Bird", "{1}", "Creature — Bird", text, 2, 2))
        x.sick = False
        return x

    def test_picks_a_keyword_it_lacks(self):
        x = self.creature(self.a, "Deathtouch")
        effects = list(GIFT.spell_effects)
        self.g.stack.append(StackItem(self.a, effects, [x, None], card=GIFT, name=GIFT.name))
        self.g.resolve_top()
        self.assertEqual(x.power, 3)
        self.assertTrue(x.has("lifelink"))

    def test_sponge_takes_the_flying_away_and_ai_aims_at_the_opponent(self):
        sponge = self.creature(self.a)
        sponge_perm = self.g.enter_battlefield(self.a, SPONGE)
        sponge_perm.sick = False
        mine = self.creature(self.a, "Flying")
        theirs = self.creature(self.b, "Flying")
        effects = list(SPONGE.activated[0].effects)
        targets = self.g.auto_targets(self.a, effects, sponge_perm)
        self.assertIs(targets[0], theirs)
        self.g.stack.append(StackItem(self.a, effects, targets, source=sponge_perm, name="sponge"))
        self.g.resolve_top()
        self.assertFalse(theirs.has("flying"))
        self.assertTrue(mine.has("flying") and not sponge.has("flying"))


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
