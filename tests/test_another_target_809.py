"""#809: "another target creature you control" never lets the source target itself."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_first_target_excludes_the_source(self):
        for text in ("Put a +1/+1 counter on another target creature you control.",
                     "Another target creature you control gains indestructible until end of turn."):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertTrue(effects[0].data["selector"]["other_than_source"], text)

    def test_a_shape_without_an_other_than_form_keeps_its_reading(self):
        # the rewrite is kept only when the "other than ~" sentence parses fully: no card is lost
        for name in ("Charmed Clothier", "Redtooth Genealogist", "Syr Armont, the Redeemer"):
            self.assertTrue(db(name).fully_supported, name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def test_scuttling_sentinel_targets_another_creature(self):
        a = Player("a", [], HeuristicAI())
        b = Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 3, "main1"
        a.library = b.library = [ISLAND] * 20
        bear = game.enter_battlefield(a, BEAR)
        sentinel = game.enter_battlefield(a, db("Scuttling Sentinel"))
        game.settle()
        self.assertEqual(bear.counters.get("+1/+1"), 1)
        self.assertTrue(bear.has("hexproof"))
        self.assertFalse(sentinel.counters.get("+1/+1"))

    def test_alone_it_has_no_legal_target(self):
        a = Player("a", [], HeuristicAI())
        b = Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 3, "main1"
        a.library = b.library = [ISLAND] * 20
        sentinel = game.enter_battlefield(a, db("Scuttling Sentinel"))
        game.settle()
        self.assertFalse(sentinel.counters.get("+1/+1"))


if __name__ == "__main__":
    unittest.main()
