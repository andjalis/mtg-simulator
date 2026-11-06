"""'When that creature dies this turn' (cx_trig_watch), on real cards from the database."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")


@unittest.skipUnless(HAVE_DB, "card database not built")
class WatchTests(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parse(self):
        for n in ("A Good Day to Die", "Blessed Defiance"):
            self.assertEqual(self.db.get(n).unsupported, [], n)

    def test_draws_when_the_creature_dies(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.cast_free(self.a, self.db.get("A Good Day to Die"))
        self.game.settle()
        self.assertEqual(len(self.game.cx_watchers), 1)
        hand = len(self.a.hand)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)
        self.assertEqual(self.game.cx_watchers, [])

    def test_no_trigger_if_a_different_creature_dies(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        other = self.game.enter_battlefield(self.a, BEAR)
        self.game.cast_free(self.a, self.db.get("A Good Day to Die"))
        self.game.settle()
        target = self.game.cx_watchers[0][1]
        spare = other if target is bear else bear
        hand = len(self.a.hand)
        self.game.destroy(spare)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)

    def test_expires_at_end_of_turn(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.cast_free(self.a, self.db.get("A Good Day to Die"))
        self.game.settle()
        self.game.turn += 1
        hand = len(self.a.hand)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)

    def test_spirit_token_for_blessed_defiance(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.cast_free(self.a, self.db.get("Blessed Defiance"))
        self.game.settle()
        self.game.destroy(bear)
        self.game.settle()
        self.assertTrue(any(x.card.is_token and "Spirit" in x.card.name for x in self.a.battlefield))
