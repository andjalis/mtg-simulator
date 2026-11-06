"""'Whenever you attack with ...' heads (cx_trig_events), resolved in real attacks on real cards."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None
FLYER = card("Test Flyer", "{1}{U}", "Creature — Bird", "Flying", 1, 1)
BRUTE = card("Test Brute", "{3}{R}", "Creature — Ogre", "", 4, 4)
BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
KING = card("Test King", "{2}{W}", "Legendary Creature — Human", "", 2, 2)
QUEEN = card("Test Queen", "{2}{W}", "Legendary Creature — Human", "", 2, 2)


@unittest.skipUnless(HAVE_DB, "card database not built")
class AttackHeads(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, c, who=None):
        perm = self.game.enter_battlefield(who or self.a, c)
        perm.sick = False
        self.game.settle()
        return perm

    def attack(self, perms):
        self.a.ai.attack = perms
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_parse(self):
        for n in ("Jolene, Plundering Pugilist", "Lulu, Vengeful Hollyphant", "Tactical Officer", "Tide Skimmer",
                  "Amazing Alliance", "Alluring Suitor // Deadly Dancer", "Hologram Janeway"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_other_flyers_that_many(self):
        self.put(DB.get("Lulu, Vengeful Hollyphant"))
        f1, f2 = self.put(FLYER), self.put(FLYER)
        bear = self.put(BEAR)
        self.attack([f1, f2, bear])
        self.assertEqual(self.b.life, 20 - 2 - 4)            # drained 2 (two other flyers, not the bear), then 1+1+2 combat
        self.assertEqual(self.a.life, 22)

    def test_lulu_itself_does_not_count(self):
        lulu = self.put(DB.get("Lulu, Vengeful Hollyphant"))
        self.attack([lulu])
        self.assertEqual(self.b.life, 20 - lulu.power)       # combat damage only: no "other" flyer attacked

    def test_power_four_attacker_makes_treasure(self):
        self.put(DB.get("Jolene, Plundering Pugilist"))
        small = self.put(BEAR)
        self.attack([small])
        self.assertFalse(any("Treasure" in x.card.name for x in self.a.battlefield))
        self.attack([self.put(BRUTE)])
        self.assertTrue(any("Treasure" in x.card.name for x in self.a.battlefield))

    def test_total_power_threshold(self):
        officer = self.put(DB.get("Tactical Officer"))
        bear = self.put(BEAR)
        self.attack([bear])
        self.assertEqual(officer.p1, 0)                      # total power 2 + officer's own, under 8
        for _ in range(2):
            self.put(BRUTE)
        self.game.turn += 2
        bear.tapped = False
        self.attack([bear])
        self.assertEqual(officer.p1, 1)

    def test_exactly_two(self):
        suitor = self.put(DB.get("Alluring Suitor // Deadly Dancer"))
        b1, b2 = self.put(BEAR), self.put(BEAR)
        self.attack([b1, b2, suitor])                        # three attackers: no transform
        self.assertFalse(getattr(suitor, "transformed", False) or suitor.card.name.startswith("Deadly"))
        suitor2 = self.put(DB.get("Alluring Suitor // Deadly Dancer"))
        self.game.turn += 2
        for x in (b1, b2, suitor):
            x.tapped = False
        self.attack([b1, b2])
        self.assertTrue(any(x.card.name.startswith("Deadly") or getattr(x, "transformed", False)
                            for x in self.a.battlefield if x in (suitor, suitor2)))

    def test_legendary_gain_that_much(self):
        self.put(DB.get("Amazing Alliance"))
        k1, k2 = self.put(KING), self.put(QUEEN)
        self.attack([k1, k2])
        self.assertEqual(self.a.life, 22)
