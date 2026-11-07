"""A colour chosen as a permanent enters (mtgsim/cx_static_choice.py)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from tests.test_templates import card

GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 3, 1)
SPHINX = card("Test Sphinx", "{3}{U}{U}", "Creature — Sphinx", "", 4, 4)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class ChosenColor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [SPHINX] * 20, HeuristicAI())     # a blue deck
        self.b = Player("b", [GOBLIN] * 20, HeuristicAI())     # a red deck
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        for p in (self.a, self.b):
            p.library = list(p.deck)
        self.game.turn, self.game.step = 3, "main1"

    def put(self, name, who=None):
        c = self.db.get(name) if isinstance(name, str) else name
        if isinstance(name, str):
            self.assertEqual(c.unsupported, [], name)
        return self.game.enter_battlefield(who or self.a, c)

    def sources(self, perm):
        return perm.produces_now if perm in self.game.mana_sources(self.a) else frozenset()

    def test_gate_adds_base_or_chosen(self):
        gate = self.put("Black Dragon Gate")              # choose a color other than black: the deck wants blue
        self.assertTrue(gate.tapped)
        self.assertEqual(gate.chosen_color, "U")
        gate.tapped = False
        self.assertEqual(set(self.sources(gate)), {"B", "U"})

    def test_thriving_land_enters_tapped(self):
        isle = self.put("Thriving Isle")                  # other than blue: the blue deck still needs another colour
        self.assertTrue(isle.tapped)
        self.assertNotEqual(isle.chosen_color, "U")
        self.assertIn("U", isle.card.produces)

    def test_protection_from_the_opponents_colour(self):
        self.put(GOBLIN, self.b)
        voice = self.put("Voice of All")
        self.assertEqual(voice.chosen_color, "R")
        self.assertTrue(voice.has("protection from red"))
        goblin = self.b.battlefield[0]
        self.game.deal_damage(voice, 3, self.b, source=goblin)
        self.assertEqual(voice.damage, 0)

    def test_choice_without_a_mana_ability_makes_no_mana(self):
        iona = self.put(self.db.get("Iona, Shield of Emeria"))   # its casting ban is another line
        iona.sick = False
        self.assertNotIn(iona, self.game.mana_sources(self.a))

    def test_mana_of_the_chosen_colour(self):
        grail = self.put("Sol Grail")
        self.assertEqual(grail.chosen_color, "U")
        self.assertEqual(set(self.sources(grail)), {"U"})


if __name__ == "__main__":
    unittest.main()
