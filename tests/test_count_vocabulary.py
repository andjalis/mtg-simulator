"""Counts are only parsed over descriptions count()/copies.fits can evaluate (#372): an unknown word used to make
the count silently 0 while the card counted as full."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.clauses import _xq
from mtgsim.cards.parse import _parse_effects
from mtgsim.counting import known
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
OGRE = card("Test Ogre", "{R}", "Creature — Ogre", "", 2, 2)


class Vocabulary(unittest.TestCase):
    def test_known(self):
        for what in ("creature", "Elf", "other artifact", "nonland permanent", "artifact, creature, or land",
                     "basic land", "non-Human creature", "nontoken creature", "ctr:charge", ""):
            self.assertTrue(known(what), what)
        for what in ("snow permanent", "green creature", "attacking creature", "instant and sorcery",
                     "nonlegendary creature", "frob", "card types among", "modified creature"):
            self.assertFalse(known(what), what)

    def test_xq_refuses_or_rereads(self):
        self.assertEqual(_xq("the number of Elves you control"), ("count", "Elf"))
        self.assertEqual(_xq("the number of lands you control"), ("count", "land"))
        self.assertNotEqual(_xq("the number of frobs you control"), ("count", "frob"))
        self.assertNotEqual((_xq("the number of instant and sorcery cards in your graveyard") or ("",))[0], "gy")
        # "X plus Y": the gy reading used to swallow the whole phrase
        self.assertEqual(_xq("the number of Caves you control plus the number of Cave cards in your graveyard"),
                         ("arith", ("count", "Cave"), "+", ("gy", "Cave")))

    def test_templates_refuse_unknown_words(self):
        for text in ("Draw a card for each snow permanent you control.",
                     "Create a 1/1 green Saproling creature token for each snow land you control.",
                     "Add {G} for each snow Forest you control."):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [text.rstrip()], text)
        pumped = card("Snow Bear", "{2}{G}", "Creature — Bear", "Snow Bear gets +1/+1 for each snow land you control.",
                      1, 1)
        self.assertNotEqual(pumped.unsupported, [])
        self.assertEqual(pumped.pt_per, "")
        forest = card("Wood Bear", "{2}{G}", "Creature — Bear", "Wood Bear gets +1/+1 for each Forest you control.",
                      1, 1)
        self.assertEqual((forest.unsupported, forest.pt_per), ([], "Forest"))

    def test_known_counts_still_count(self):
        effects, bad = _parse_effects("Draw a card for each Elf you control.")
        self.assertEqual((bad, effects[0].data["per"]), ([], {"what": "Elf", "zone": "battlefield"}))


class Evaluation(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 5, HeuristicAI())
        self.b = Player("b", [BEAR] * 5, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, "main1"
        self.a.battlefield = [Permanent(c, self.a) for c in (BEAR, BEAR, ELF, OGRE)]

    def test_green_creatures_count_through_the_selector_reading(self):
        effects, bad = _parse_effects("Draw a card for each green creature you control.")
        self.assertEqual(bad, [])
        self.assertEqual(self.game.x_quantity(self.a, effects[0].data["xq"], None, None), 3)

    def test_attacking_creatures(self):
        effects, bad = _parse_effects("You gain 1 life for each attacking creature you control.")
        self.assertEqual(bad, [])
        self.game.attackers = list(self.a.battlefield[:2])
        self.assertEqual(self.game.x_quantity(self.a, effects[0].data["xq"], None, None), 2)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_statuses(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Regal Force", "Take Heart", "Lucid Dreams", "Calamitous Cave-In", "Wandering Stream"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)       # now through readings that count
        for name in ("Skred", "Conifer Wurm", "Spite of Mogis", "Herd Migration", "Golden Ratio"):
            self.assertEqual(card_coverage(db.get(name)).status, "partial", name)    # no reading counts these yet


if __name__ == "__main__":
    unittest.main()
