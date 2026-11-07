"""Aura 'upkeep of enchanted permanent's controller' heads and 'your combat step' (cx_trig_events), real cards."""
import os
import random
import unittest

from mtgsim import auras
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from mtgsim.engine.state import Permanent
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None


@unittest.skipUnless(HAVE_DB, "card database not built")
class HostPhase(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        x = Permanent(c, owner)
        x.sick, x.tapped = False, False
        owner.battlefield.append(x)
        return x

    def test_parse(self):
        for n in ("Cursed Land", "Essence Flare", "Numbing Dose", "Aggressive Crag", "Warp Artifact"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_damage_goes_to_the_hosts_controller_on_their_upkeep(self):
        land = self.perm(DB.get("Forest") if False else ISLAND, self.b)
        aura = self.perm(DB.get("Cursed Land"), self.a)         # a casts it on b's land
        auras.attach(self.game, aura, land)
        self.game.fire(self.a, "upkeep")                          # a's upkeep: not the land's controller
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 20))
        self.game.fire(self.b, "upkeep")
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 19))

    def test_counter_lands_on_the_enchanted_creature(self):
        bear = self.perm(BEAR, self.b)
        aura = self.perm(DB.get("Essence Flare"), self.a)
        auras.attach(self.game, aura, bear)
        toughness = bear.toughness
        self.game.fire(self.b, "upkeep")
        self.game.settle()
        self.assertEqual(bear.toughness, toughness - 1)

    def test_combat_step_head_taps_the_crag(self):
        crag = self.perm(DB.get("Aggressive Crag"), self.a)
        self.a.ai.attack = ()
        self.b.ai.block = {}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertTrue(crag.tapped)
