"""Static keyword removal, "can't have or gain", and "is every creature type" (#406 tails, cx_static_chars)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")
FLIER = card("Test Flier", "{1}{U}", "Creature — Bird", "Flying", 2, 2)
ARCHETYPE = card("Test Archetype", "{4}{U}", "Enchantment Creature — Human Wizard",
                 "Creatures your opponents control lose flying and can't have or gain flying.", 3, 2)
GROUNDED = card("Test Grounded", "{1}{G}", "Enchantment — Aura", "Enchant creature\nEnchanted creature loses flying.")
STALACTITE = card("Test Stalactite", "{1}", "Artifact — Equipment",
                  "Equipped creature gets +1/+1 and is every creature type.\nEquip {2}")
LORD = card("Test Elf Lord", "{1}{G}", "Creature — Elf", "Other Elves you control get +1/+1.", 2, 2)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20


class Locks(Base):
    def test_parse(self):
        for c in (ARCHETYPE, GROUNDED, STALACTITE):
            self.assertEqual((c.unsupported, c.approximations), ([], []), c.name)
        self.assertTrue(GROUNDED.aura_hostile)
        self.assertTrue(card("T", "{1}", "Enchantment", "Creatures lose frobbing.").unsupported)

    def test_archetype_lock_beats_later_grants(self):
        theirs, mine = self.game.enter_battlefield(self.b, FLIER), self.game.enter_battlefield(self.a, FLIER)
        self.game.enter_battlefield(self.a, ARCHETYPE)
        self.assertFalse(theirs.has("flying"))
        self.assertTrue(mine.has("flying"))
        self.game.add_continuous_effect(theirs, "grant", keyword="flying", until_eot=True)
        self.assertFalse(theirs.has("flying"))                    # can't gain it

    def test_loses_flying_then_a_later_grant_wins(self):
        flier = self.game.enter_battlefield(self.b, FLIER)
        self.game._aura_host = flier
        self.game.enter_battlefield(self.a, GROUNDED)
        self.game.settle()
        self.assertFalse(flier.has("flying"))
        self.game.add_continuous_effect(flier, "grant", keyword="flying", until_eot=True)
        self.assertTrue(flier.has("flying"))

    def test_every_creature_type(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.enter_battlefield(self.a, LORD)
        hat = self.game.enter_battlefield(self.a, STALACTITE)
        self.assertEqual(bear.power, 2)
        hat.attached_to = bear
        self.assertEqual(bear.power, 4)                           # +1 Stalactite, +1 as an Elf
        hat.attached_to = None
        self.assertEqual(bear.power, 2)

    def test_ai_puts_grounded_on_their_flier(self):
        from mtgsim.auras import choose_host
        self.game.enter_battlefield(self.a, FLIER)
        theirs = self.game.enter_battlefield(self.b, FLIER)
        self.assertIs(choose_host(self.game, self.a, GROUNDED), theirs)


@unittest.skipUnless(os.path.exists(DB), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Archetype of Endurance", "Archetype of Courage", "Archetype of Aggression",
                     "Archetype of Finality", "Archetype of Imagination", "Gravity Sphere", "Grounded",
                     "Mystic Decree", "Sky Tether", "Runed Stalactite", "Amorphous Axe", "Arachnoform",
                     "Mistform Ultimus"):
            with self.subTest(name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")
        self.assertTrue(db.get("Mistform Ultimus").changeling)


if __name__ == "__main__":
    unittest.main()


class ChangelingLords(Base):
    def test_a_changeling_gets_a_tribal_lords_bonus(self):
        shape = card("Test Changeling", "{1}", "Creature — Shapeshifter", "Changeling", 1, 1)
        x = self.game.enter_battlefield(self.a, shape)
        self.game.enter_battlefield(self.a, LORD)
        self.assertEqual(x.power, 2)
