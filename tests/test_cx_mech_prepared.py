"""cx_mech: "~ becomes prepared" (self and "it" targets) on prepare-spell creatures."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND


class Prepared(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parse_clean(self):
        for n in ("Abigale, Poet Laureate // Heroic Stanza", "Eccentric Pestfinder // Turn Stones",
                  "Paradox Shaper // Omit Variables", "Bloodline Recollector // Ancestral Craving"):
            self.assertEqual(self.db.get(n).unsupported, [], n)

    def test_becomes_prepared_then_spell_copy_is_castable(self):
        card = self.db.get("Abigale, Poet Laureate // Heroic Stanza")
        perm = self.game.enter_battlefield(self.a, card)
        self.game.settle()
        self.assertFalse(perm.prepared)
        self.assertFalse([v for v in self.game.spell_options(self.a) if "prepared" in v.name])
        trig = card.triggers[0]
        self.game.resolve(self.a, trig.effects[0], perm)
        self.assertTrue(perm.prepared)
        self.assertTrue([v for v in self.game.spell_options(self.a) if "prepared" in v.name])


class HexproofFrom(unittest.TestCase):
    def setUp(self):
        Prepared.setUp(self)

    def test_hexproof_from_black_blocks_only_black_sources(self):
        knight = self.game.enter_battlefield(self.a, self.db.get("Knight of Grace"))
        self.game.settle()
        black, red = self.db.get("Doom Blade"), self.db.get("Lightning Bolt")
        self.assertTrue(self.game.targetable(knight, self.a, black))     # its controller may
        self.assertFalse(self.game.targetable(knight, self.b, black))
        self.assertTrue(self.game.targetable(knight, self.b, red))

    def test_hexproof_from_monocolored(self):
        general = self.game.enter_battlefield(self.a, self.db.get("General Ferrous Rokiric"))
        self.game.settle()
        self.assertEqual(self.db.get("General Ferrous Rokiric").unsupported, [])
        self.assertFalse(self.game.targetable(general, self.b, self.db.get("Lightning Bolt")))
        multi = self.db.get("Terminate")
        self.assertTrue(self.game.targetable(general, self.b, multi))

    def test_ai_removal_avoids_the_creature_with_hexproof_from_its_colour(self):
        """Control: HeuristicAI's Reave Soul kills a plain Knight, but leaves the hexproof-from-black one alone."""
        from mtgsim.ai import HeuristicAI
        for name, dies in (("Knight of Meadowgrain", True), ("Knight of Grace", False)):
            self.setUp()
            self.a.ai = HeuristicAI()
            knight = self.game.enter_battlefield(self.b, self.db.get(name))
            for _ in range(3):
                self.game.enter_battlefield(self.a, self.db.get("Swamp"))
            self.game.settle()
            spell = self.db.get("Reave Soul")
            self.a.hand = [spell]
            self.game.main_phase(self.a)
            self.assertEqual(knight not in self.b.battlefield, dies, name)
            self.assertEqual(spell not in self.a.hand, dies, name)


if __name__ == "__main__":
    unittest.main()
