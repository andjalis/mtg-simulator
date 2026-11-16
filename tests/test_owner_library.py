"""#628: "put it on top of / on the bottom of / Nth from the top of its owner's library" after a dies / put into
exile trigger (mtgsim.cx_owner_library)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, MOUNTAIN, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Dark Revenant", "Undying Beast", "Avenging Angel", "Arashin Sovereign", "Fell Horseman // Deathly Ride",
        "Murderous Rider // Swift End", "Gandalf, White Rider", "God-Eternal Oketra", "Ilharg, the Raze-Boar",
        "Enigma Sphinx", "Saprazzan Outrigger")


class Parse(unittest.TestCase):
    def test_positions(self):
        cases = {"put it on top of its owner's library": "top", "put it on the bottom of its owner's library": "bottom",
                 "you may put it on your choice of the top or bottom of its owner's library": "choice",
                 "you may put it into its owner's library fifth from the top": 5}
        for body, where in cases.items():
            c = card("Test Ghost", "{1}", "Creature — Spirit", f"When ~ dies, {body}.", 1, 1)
            self.assertEqual(c.unsupported, [], body)
            eff = next(e for e in c.triggers[0].effects if e.kind == "owner_library")
            self.assertEqual((eff.target, eff.data["where"]), ("none", where))

    def test_refusals(self):
        for body in ("put it into its owner's library tenth from the top",
                     "put it on top of its owner's library unless that player pays {1}",
                     "put it into its owner's graveyard fifth from the top"):
            c = card("Test Ghost", "{1}", "Creature — Spirit", f"When ~ dies, {body}.", 1, 1)
            self.assertTrue(c.unsupported, body)
        # another creature's death: the trigger doesn't carry that creature, so "it" can't be followed
        c = card("Test Cauldron", "{1}", "Artifact", "Whenever a creature you control dies, put it on the bottom of "
                                                     "its owner's library.")
        self.assertTrue(c.unsupported)
        # "it" is the cast spell (Neera, Wild Mage), not the source
        c = card("Test Neera", "{1}", "Creature — Human", "Whenever you cast a spell, you may put it on the bottom of "
                                                         "its owner's library.", 2, 2)
        self.assertTrue(c.unsupported)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = [ISLAND] * 6
        self.b.library = [ISLAND] * 6

    def ghost(self, body, owner=None):
        c = card("Test Ghost", "{1}", "Creature — Spirit", f"When ~ dies, {body}.", 1, 1)
        perm = self.g.enter_battlefield(owner or self.a, c)
        self.g.settle()
        return perm

    def kill(self, perm):
        self.g.destroy(perm)
        self.g.settle()

    def test_top(self):
        self.kill(self.ghost("put it on top of its owner's library"))
        self.assertEqual(self.a.library[-1].name, "Test Ghost")
        self.assertFalse(any(c.name == "Test Ghost" for c in self.a.graveyard))

    def test_bottom(self):
        self.kill(self.ghost("put it on the bottom of its owner's library"))
        self.assertEqual(self.a.library[0].name, "Test Ghost")

    def test_fifth_from_the_top(self):
        self.kill(self.ghost("you may put it into its owner's library fifth from the top"))
        self.assertEqual(self.a.library[-5].name, "Test Ghost")
        self.assertEqual(len(self.a.library), 7)

    def test_short_library_puts_it_at_the_bottom(self):
        self.a.library = [ISLAND, ISLAND]
        self.kill(self.ghost("you may put it into its owner's library fifth from the top"))
        self.assertEqual(self.a.library[0].name, "Test Ghost")

    def test_exiled_from_the_battlefield(self):
        c = card("Test God", "{1}", "Creature — God", "When ~ dies or is put into exile from the battlefield, you may "
                                                      "put it into its owner's library third from the top.", 1, 1)
        perm = self.g.enter_battlefield(self.a, c)
        self.g.settle()
        self.g.leave_battlefield(perm, "exile")
        self.g.settle()
        self.assertEqual(self.a.library[-3].name, "Test God")
        self.assertFalse(any(x.name == "Test God" for x in self.a.exile))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)

    def test_saprazzan_outrigger_goes_on_top_at_end_of_combat(self):
        from mtgsim.carddb import CardDB
        from tests.test_combat_triggers import Scripted
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 2, "main1"
        for pl in (a, b):
            pl.library = [ISLAND] * 5
            pl.ai.attack, pl.ai.block = (), {}
        boat = g.enter_battlefield(a, db.get("Saprazzan Outrigger"))
        boat.sick = False
        g.settle()
        a.ai.attack = [boat]
        g.combat(a, b)
        g.settle()
        self.assertEqual(b.life, 15)                      # it dealt its damage first
        self.assertEqual(a.library[-1].name, "Saprazzan Outrigger")
        self.assertNotIn(boat, a.battlefield)

    def test_dark_revenant(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library, b.library = [MOUNTAIN] * 5, [ISLAND] * 5
        rev = g.enter_battlefield(a, db.get("Dark Revenant"))
        g.settle()
        g.destroy(rev)
        g.settle()
        self.assertEqual(a.library[-1].name, "Dark Revenant")


if __name__ == "__main__":
    unittest.main()
