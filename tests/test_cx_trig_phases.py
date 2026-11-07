"""Phase and day/night heads (cx_trig_events): day becomes night, each opponent's end step, ..., real cards."""
import os
import random
import unittest

from mtgsim import day_night
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import BEAR, Scripted
from tests.test_templates import ISLAND, MOUNTAIN

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None


@unittest.skipUnless(HAVE_DB, "card database not built")
class PhaseHeads(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_parse(self):
        for n in ("Firmament Sage", "Vadrik, Astral Archmage", "Brimstone Vandal", "Keeper of the Accord"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_day_becomes_night_triggers_not_the_first_day(self):
        self.game.enter_battlefield(self.a, DB.get("Firmament Sage"))     # it becomes day as it enters
        self.game.settle()
        self.assertEqual(self.game.day_night, "day")
        hand = len(self.a.hand)
        self.assertEqual(hand, len(self.a.hand))                          # the first "becomes day" is no change
        day_night.set_state(self.game, "night")
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)
        day_night.set_state(self.game, "day")
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 2)

    def test_both_players_permanents_see_the_change(self):
        self.game.enter_battlefield(self.a, DB.get("Vadrik, Astral Archmage"))
        vadrik = self.a.battlefield[-1]
        self.game.enter_battlefield(self.b, DB.get("Brimstone Vandal"))
        self.game.settle()
        life = self.a.life
        day_night.set_state(self.game, "night")
        self.game.settle()
        self.assertEqual(vadrik.p1, 1)
        self.assertEqual(self.a.life, life - 1)                           # the opponent's Vandal pinged us

    def test_each_opponent_end_step_only(self):
        self.game.enter_battlefield(self.a, DB.get("Keeper of the Accord"))
        for _ in range(3):
            self.game.enter_battlefield(self.b, BEAR)
        self.game.settle()
        tokens = lambda: sum(1 for x in self.a.battlefield if x.card.is_token)
        self.game.fire(self.a, "end_step")                                # our own end step: no trigger
        self.game.settle()
        self.assertEqual(tokens(), 0)
        self.game.fire(self.b, "end_step")                                # the opponent's end step
        self.game.settle()
        self.assertEqual(tokens(), 1)

    def test_sunstreak_phoenix_returns_from_the_graveyard(self):
        phoenix = DB.get("Sunstreak Phoenix")
        self.a.graveyard.append(phoenix)
        self.game.enter_battlefield(self.a, DB.get("Firmament Sage"))     # starts the day
        for _ in range(2):
            self.game.enter_battlefield(self.a, MOUNTAIN).tapped = False
        self.game.settle()
        day_night.set_state(self.game, "night")
        self.game.settle()
        self.assertTrue(any(x.card.name == "Sunstreak Phoenix" for x in self.a.battlefield))
        self.assertFalse(any(c.name == "Sunstreak Phoenix" for c in self.a.graveyard))


@unittest.skipUnless(HAVE_DB, "card database not built")
class SourceHeads(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_noncombat_damage_by_a_source_you_control(self):
        pyre = self.game.enter_battlefield(self.a, DB.get("Chandra's Pyreling"))
        self.game.settle()
        base = pyre.power
        self.game.deal_damage(self.b, 1, by=self.b, cause="x")      # their own source hurting them: not ours
        self.game.settle()
        self.assertEqual(pyre.power, base)
        self.game.deal_damage(self.a, 1, by=self.a, cause="x")      # damage to us
        self.game.settle()
        self.assertEqual(pyre.power, base)
        self.game.deal_damage(self.b, 1, by=self.a, cause="x", combat=True)
        self.game.settle()
        self.assertEqual(pyre.power, base)
        self.game.deal_damage(self.b, 1, by=self.a, cause="x")      # our noncombat damage to the opponent
        self.game.settle()
        self.assertEqual(pyre.power, base + 1)

    def test_land_or_spell_draws(self):
        self.game.enter_battlefield(self.a, DB.get("Infernal Sovereign"))
        self.game.settle()
        hand, life = len(self.a.hand), self.a.life
        self.a.hand.append(ISLAND)
        hand += 1
        self.game.play_land(self.a, ISLAND)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand - 1 + 1)           # land left the hand, one card drawn
        self.assertEqual(self.a.life, life - 1)
