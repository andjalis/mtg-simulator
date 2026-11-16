"""'If its <mechanic> cost was paid' (#405): the alternative cost the spell, or the spell a permanent resolved from,
was cast for (surge, spectacle, prowl, freerunning, madness, mayhem, sneak, emerge, ...)."""
import os
import random
import unittest

from mtgsim.cx_condlib import parse
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, MOUNTAIN, SHOCK, SWAMP

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
if HAVE_DB:
    from mtgsim.carddb import CardDB
    DB = CardDB()


class Parse(unittest.TestCase):
    def test_shapes(self):
        for phrase, kind in (("~'s surge cost was paid", "surge"), ("its prowl cost was paid", "prowl"),
                             ("this spell's madness cost was paid", "madness"), ("his sneak cost was paid", "sneak"),
                             ("this creature's spectacle cost was paid", "spectacle")):
            self.assertEqual(parse(phrase), f'lib:["cast_kind","{kind}"]', phrase)

    def test_refusals(self):
        for phrase in ("its additional cost was paid", "~'s flubber cost was paid", "her sneak cost was paid this turn"):
            self.assertEqual(parse(phrase), "", phrase)


@unittest.skipUnless(HAVE_DB, "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def get(self, name):
        c = DB.get(name)
        self.assertEqual(c.unsupported, [], name)
        return c

    def lands(self, land, n):
        for _ in range(n):
            self.game.enter_battlefield(self.a, land).sick = False

    def option(self, card, kind):
        """card as cast for the alternative cost kind ("" = its normal cost)."""
        return next(v for v in self.game.spell_options(self.a)
                    if self.game._origin(v)[0].name == card.name and self.game._origin(v)[1] == kind)

    def test_crush_of_tentacles_surge(self):
        crush = self.get("Crush of Tentacles")
        for surge, octopi in ((False, 0), (True, 1)):
            self.setUp()
            self.lands(ISLAND, 6)
            self.lands(MOUNTAIN, 1)
            if surge:                                   # surge: another spell cast this turn
                self.a.hand = [SHOCK]
                self.assertTrue(self.game.cast(self.a, SHOCK, [self.b]))
                self.game.settle()
            self.a.hand = [crush]
            spell = self.option(crush, "surge" if surge else "")
            self.assertTrue(self.game.cast(self.a, spell, []))
            self.game.settle()
            self.assertEqual(sum(x.card.name.startswith("Octopus") for x in self.a.battlefield), octopi, f"surge={surge}")

    def test_rafter_demon_spectacle_on_its_enters_trigger(self):
        demon = self.get("Rafter Demon")
        for spectacle in (False, True):
            self.setUp()
            self.lands(SWAMP, 3)
            self.lands(MOUNTAIN, 2)
            self.b.hand = [ISLAND, ISLAND]
            if spectacle:
                self.game.change_life(self.b, -1, None)
                self.b.lost_life_turn = True
            self.a.hand = [demon]
            spell = self.option(demon, "spectacle" if spectacle else "")
            self.assertTrue(self.game.cast(self.a, spell, []))
            self.game.settle()
            perm = next(x for x in self.a.battlefield if x.card.name == demon.name)
            self.assertEqual(perm.cast_kind, "spectacle" if spectacle else "")
            self.assertEqual(len(self.b.hand), 1 if spectacle else 2, f"spectacle={spectacle}")


if __name__ == "__main__":
    unittest.main()
