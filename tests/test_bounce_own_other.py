"""#435 follow-up: 'return up to one other target permanent you control to its owner's hand' (Mischievous Pup,
Exosuit Savior, Stickytongue Sentinel) can't target its own source, may choose nothing, and may return a land."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

PUP = card("Test Pup", "{2}{W}", "Creature — Dog", "Flash\nWhen this creature enters, return up to one other "
           "target permanent you control to its owner's hand.", 1, 1)
ELF = card("Test Elf", "{G}", "Creature — Elf", "When this creature enters, you gain 2 life.", 1, 1)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class BounceOwnOther(unittest.TestCase):
    def setUp(self):
        self.g, self.a, self.b = game()
        self.eff = PUP.triggers[0].effects[0]

    def legal(self, source):
        with self.g.targeting(StackItem(self.a, [self.eff], [None], source=source, kind="trigger")):
            return self.g.legal_targets(self.a, self.eff)

    def test_parse(self):
        self.assertEqual(PUP.unsupported, [])
        self.assertEqual((self.eff.kind, self.eff.target, self.eff.filter), ("bounce_own", "permanent", "mine"))
        self.assertTrue(self.eff.data["other"])
        self.assertTrue(self.eff.data["optional_target"])

    def test_legal_targets(self):
        pup = self.g.enter_battlefield(self.a, card("Plain Pup", "{2}{W}", "Creature — Dog", "", 1, 1))
        land = self.g.enter_battlefield(self.a, ISLAND)
        elf = self.g.enter_battlefield(self.a, card("Plain Elf", "{G}", "Creature — Elf", "", 1, 1))
        foe = self.g.enter_battlefield(self.b, card("Foe", "{1}", "Creature — Ogre", "", 2, 2))
        legal = self.legal(pup)
        self.assertNotIn(pup, legal)
        self.assertNotIn(foe, legal)
        self.assertIn(land, legal)
        self.assertIn(elf, legal)

    def test_alone_it_targets_nothing_and_stays(self):
        self.a.hand = [PUP]
        self.g.enter_battlefield(self.a, card("Plains", "", "Basic Land — Plains", "({T}: Add {W}.)"))
        pup = self.g.enter_battlefield(self.a, PUP)
        self.g.settle()
        self.assertIn(pup, self.a.battlefield)

    def test_replays_an_enters_creature(self):
        elf = self.g.enter_battlefield(self.a, ELF)
        self.g.settle()
        pup = self.g.enter_battlefield(self.a, PUP)
        self.g.settle()
        self.assertIn(pup, self.a.battlefield)
        self.assertNotIn(elf, self.a.battlefield)
        self.assertIn(ELF, self.a.hand)

    @unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Mischievous Pup", "Exosuit Savior", "Stickytongue Sentinel"):
            c = db.get(name)
            self.assertEqual(c.unsupported, [], name)
            e = c.triggers[0].effects[0]
            self.assertEqual((e.kind, e.target), ("bounce_own", "permanent"), name)
            self.assertTrue(e.data.get("other") and e.data.get("optional_target"), name)


if __name__ == "__main__":
    unittest.main()
