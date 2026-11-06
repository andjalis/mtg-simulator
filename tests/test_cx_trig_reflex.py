"""Reflexive "When you do" after plain actions (cx_trig_reflex), on real cards from the database."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND

DB = CardDB()
HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")


def real(name):
    return DB.get(name)


@unittest.skipUnless(HAVE_DB, "card database not built")
class ReflexParse(unittest.TestCase):
    def test_cards_fully_parse(self):
        for n in ("Faebloom Trick", "Eastfarthing Farmer"):
            self.assertEqual(real(n).unsupported, [], n)


@unittest.skipUnless(HAVE_DB, "card database not built")
class ReflexEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_farmer_pumps_after_food(self):
        farmer = self.game.enter_battlefield(self.a, real("Eastfarthing Farmer"))
        self.game.settle()
        self.assertTrue(any(x.card.is_token and "Food" in x.card.name for x in self.a.battlefield))
        self.assertEqual(farmer.power, farmer.card.power + 1)       # +1/+1 for the one Food

    def test_faebloom_taps_after_tokens(self):
        victim = self.game.enter_battlefield(self.b, BEAR)
        victim.tapped = False
        self.game.cast_free(self.a, real("Faebloom Trick"))
        self.game.settle()
        self.assertEqual(sum(1 for x in self.a.battlefield if x.card.is_token), 2)
        self.assertTrue(victim.tapped)

    def test_backreference_payoffs_stay_unsupported(self):
        self.assertTrue(real("Back for More").unsupported)      # "it fights ...": no remembered object yet
