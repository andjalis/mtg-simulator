"""Colour and type changes "of your choice" and "in addition to its other types"."""
import random
import unittest

from mtgsim import copies
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

DREAMER = card("Test Dreamer", "{2}{U}", "Creature — Illusion", "{1}: ~ becomes the creature type of your choice until end of turn.", 2, 1)
KAVU = card("Test Kavu", "{3}{R}", "Creature — Kavu", "{1}: ~ becomes the color of your choice until end of turn.", 3, 3)
THRUSH = card("Test Thrush", "{4}{U}", "Creature — Bird", "{T}: Target land becomes the basic land type of your choice until end of turn.", 2, 2)
MUTATION = card("Test Mutation", "{2}{U}", "Instant", "Target permanent becomes an artifact in addition to its other types until end of turn.")
ELF = card("Test Elf", "{G}", "Creature — Elf Druid", "", 1, 1)


class Recolor(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def run_ability(self, perm, target=None):
        eff = perm.card.activated[0].effects[0]
        self.game.resolve(self.a, eff, target, item=StackItem(self.a, [eff], [target], source=perm))

    def test_parse(self):
        for c in (DREAMER, KAVU, THRUSH, MUTATION):
            self.assertEqual(c.unsupported, [], c.name)

    def test_creature_type_until_end_of_turn(self):
        dreamer = self.game.enter_battlefield(self.a, DREAMER)
        self.game.enter_battlefield(self.a, ELF)
        self.run_ability(dreamer)
        self.assertIn(dreamer.card.subtypes & {"Elf", "Druid"}, ({"Elf"}, {"Druid"}))
        copies.revert(dreamer)
        self.assertEqual(dreamer.card.subtypes, {"Illusion"})

    def test_color(self):
        kavu = self.game.enter_battlefield(self.a, KAVU)
        self.game.enter_battlefield(self.a, BEAR)
        self.run_ability(kavu)
        self.assertEqual(kavu.card.colors, {"G"})
        copies.revert(kavu)
        self.assertEqual(kavu.card.colors, {"R"})

    def test_land_type(self):
        thrush = self.game.enter_battlefield(self.a, THRUSH)
        land = self.game.enter_battlefield(self.a, MOUNTAIN)
        self.a.hand = [card("Test Blue", "{U}{U}", "Instant", "Draw a card.")]
        self.run_ability(thrush, land)
        self.assertIn("Island", land.card.subtypes)
        self.assertNotIn("Mountain", land.card.subtypes)
        self.assertEqual(land.card.produces, {"U"})

    def test_add_types(self):
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.resolve(self.a, MUTATION.spell_effects[0], bear)
        self.assertTrue(bear.card.is_artifact and bear.is_creature)


if __name__ == "__main__":
    unittest.main()
