"""#324 tail: where spent mana came from. A spell's payment records how much mana came from Treasures, artifacts,
creatures, Deserts and Caves (cx_spent.source_counts); the permanent it becomes keeps it. Conditions "if mana from a
Treasure was spent to cast it" / "three or more mana from creatures", and the quantity "for each mana from a
Treasure spent to cast ~/it"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SWAMP, card


class ManaFromSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    @classmethod
    def tearDownClass(cls):
        if cls.db._all is not None:
            cls.db._all.close()

    def real(self, name):
        if self.db._all is None:
            self.skipTest("card database not built")
        return self.db.get(name)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick = p.tapped = False
        owner.battlefield.append(p)
        return p

    def treasures(self, n):
        effects, _ = _parse_effects(f"Create {['a', 'two', 'three'][n - 1]} Treasure token{'s' if n > 1 else ''}.")
        item = StackItem(self.a, effects, [None] * len(effects))
        self.g.stack.append(item)
        self.g.resolve_top()
        for t in self.a.battlefield:
            t.sick = False
        return [t for t in self.a.battlefield if t.card.token_kind == "treasure"]

    def cast(self, c, targets=None):
        self.a.hand = [c]
        self.assertTrue(self.g.cast(self.a, c, targets))
        self.g.settle()

    def test_real_cards_are_full(self):
        for name in ("Hired Hexblade", "Jaded Sell-Sword", "Smaug, Wicked Worm", "Marut", "Spoils of the Hunt",
                     "Cataclysmic Prospecting", "Price of Loyalty", "Alchemist's Talent", "Bat Colony"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_codes(self):
        from mtgsim.cx_condlib import parse
        self.assertEqual(parse("mana from a Treasure was spent to cast it"), 'lib:["mana_from","treasure",1]')
        self.assertEqual(parse("three or more mana from creatures was spent to cast it"),
                         'lib:["mana_from","creature",3]')
        self.assertEqual(parse("mana from a Planeswalker was spent to cast it"), "")

    def test_source_counts(self):
        from mtgsim.cx_spent import source_counts
        from mtgsim.engine.state import pool_mana
        treasure = self.treasures(1)[0]
        land = self.perm(SWAMP, self.a)
        floating = Permanent(pool_mana("R"), self.a)
        self.assertEqual(source_counts([treasure, land, floating]), {"treasure": 1, "artifact": 1})

    def test_hexblade_with_treasure_draws(self):
        self.perm(SWAMP, self.a)
        self.treasures(1)
        self.cast(self.real("Hired Hexblade"))
        self.assertEqual((len(self.a.hand), self.a.life), (1, 19))

    def test_hexblade_without_treasure_does_not(self):
        self.perm(SWAMP, self.a)
        self.perm(SWAMP, self.a)
        self.cast(self.real("Hired Hexblade"))
        self.assertEqual((len(self.a.hand), self.a.life), (0, 20))

    def test_marut_one_treasure_per_treasure_mana(self):
        for _ in range(6):
            self.perm(ISLAND, self.a)
        self.treasures(2)
        self.cast(self.real("Marut"))
        self.assertEqual(len([t for t in self.a.battlefield if t.card.token_kind == "treasure"]), 2)

    def test_smaug_reads_the_cast_spell(self):
        self.perm(self.real("Smaug, Wicked Worm"), self.a)
        self.treasures(1)
        bolt = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
        self.cast(bolt, [self.b])
        self.assertEqual((len(self.a.hand), self.a.life), (1, 19))

    def test_smaug_land_paid_spell_does_nothing(self):
        self.perm(self.real("Smaug, Wicked Worm"), self.a)
        self.perm(MOUNTAIN, self.a)
        bolt = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
        self.cast(bolt, [self.b])
        self.assertEqual((len(self.a.hand), self.a.life), (0, 20))


if __name__ == "__main__":
    unittest.main()
