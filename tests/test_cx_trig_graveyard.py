"""'Whenever a <card> is put into <whose> graveyard [from <zone>]' (cx_trig_events.gy_head), real cards."""
import os
import random
import unittest

from mtgsim.cards import Effect
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import BEAR, Scripted
from tests.test_templates import ISLAND

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None


@unittest.skipUnless(HAVE_DB, "card database not built")
class GraveyardHeads(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, name, who=None):
        perm = self.game.enter_battlefield(who or self.a, DB.get(name))
        self.game.settle()
        return perm

    def discard(self, who, card):
        who.hand.append(card)
        self.game.move_card(card, who.hand, who.graveyard, reason="discard")
        self.game.settle()

    def test_parse(self):
        for n in ("Skola Grovedancer", "Sidisi, Brood Tyrant", "Vulturous Zombie", "Profane Memento",
                  "Devourer of Memory"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_land_from_anywhere_only_to_my_graveyard(self):
        self.put("Skola Grovedancer")
        life = self.a.life
        self.a.graveyard.append(self.a.library.pop())               # a land card from my library
        self.game.settle()
        self.assertEqual(self.a.life, life + 1)
        self.b.graveyard.append(self.b.library.pop())               # into their graveyard: not mine
        self.game.settle()
        self.assertEqual(self.a.life, life + 1)
        self.discard(self.a, BEAR)                                  # not a land
        self.assertEqual(self.a.life, life + 1)

    def test_opponents_graveyard_any_card(self):
        zombie = self.put("Vulturous Zombie")
        self.discard(self.b, BEAR)
        self.assertEqual(zombie.p1, 1)
        self.discard(self.a, BEAR)                                  # my own graveyard: no counter
        self.assertEqual(zombie.p1, 1)

    def test_creature_card_in_their_graveyard_gains_life(self):
        self.put("Profane Memento")
        life = self.a.life
        self.b.graveyard.append(self.b.library.pop())               # a land: no
        self.game.settle()
        self.assertEqual(self.a.life, life)
        self.discard(self.b, BEAR)
        self.assertEqual(self.a.life, life + 1)

    def test_one_or_more_from_library_triggers_once_per_mill(self):
        devourer = self.put("Devourer of Memory")
        base = devourer.power
        self.game.resolve(self.a, Effect("mill", 3), None)          # three cards, one trigger
        self.game.settle()
        self.assertEqual(devourer.power, base + 1)
        self.discard(self.a, BEAR)                                  # from the hand, not the library
        self.assertEqual(devourer.power, base + 1)

    def test_creature_dying_is_put_into_the_graveyard_from_the_battlefield(self):
        self.put("Profane Memento")
        victim = self.game.enter_battlefield(self.b, BEAR)
        life = self.a.life
        self.game.destroy(victim)
        self.game.settle()
        self.assertEqual(self.a.life, life + 1)                     # the permanent card reached their graveyard
