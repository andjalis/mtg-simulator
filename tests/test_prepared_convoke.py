"""Enters prepared (cast a copy of the creature's spell once) and Convoke. Card text is written out."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card


def two_faced(front, back):
    return card_from_scryfall({"name": f"{front['name']} // {back['name']}", "layout": "prepare", "cmc": front["cmc"],
                               "type_line": f"{front['type_line']} // {back['type_line']}",
                               "card_faces": [front, back]})


WRANGLER = two_faced(
    {"name": "Test Wrangler", "mana_cost": "{4}{R}", "cmc": 5, "type_line": "Creature — Orc",
     "oracle_text": "This creature enters prepared. (While it's prepared, you may cast a copy of its spell.)",
     "power": "4", "toughness": "4"},
    {"name": "Test Spark", "mana_cost": "{R}", "cmc": 1, "type_line": "Sorcery",
     "oracle_text": "Test Spark deals 2 damage to any target."})
SEER = card("Convoke Seer", "{3}{U}", "Instant", "Convoke\nDraw two cards.")


class PreparedAndConvoke(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main2"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c):
        p = Permanent(c, self.a)
        p.sick = False
        self.a.battlefield.append(p)
        return p

    def test_templates(self):
        self.assertTrue(WRANGLER.prepared)
        self.assertEqual(WRANGLER.unsupported, [])
        self.assertTrue(SEER.convoke)
        self.assertEqual(SEER.unsupported, [])

    def test_prepared_copy_is_cast_once(self):
        self.game.enter_battlefield(self.a, WRANGLER)
        wr = self.a.battlefield[0]
        self.assertTrue(wr.prepared)
        self.perm(MOUNTAIN)
        options = [c for c in self.game.spell_options(self.a) if c.name.endswith("(prepared)")]
        self.assertEqual(len(options), 1)
        self.assertTrue(self.game.cast(self.a, options[0], [self.b]))
        self.assertEqual(self.b.life, 18)
        self.assertFalse(wr.prepared)
        self.assertEqual(self.a.graveyard, [])                 # a copy: nothing goes to the graveyard
        self.assertEqual([c for c in self.game.spell_options(self.a) if c.name.endswith("(prepared)")], [])

    def test_convoke_taps_creatures_for_generic(self):
        for _ in range(2):
            self.perm(BEAR)
        self.perm(ISLAND)
        self.perm(ISLAND)
        self.a.hand = [SEER]
        self.assertTrue(self.game.cast(self.a, SEER))
        self.assertTrue(all(c.tapped for c in self.a.creatures))
        self.assertEqual(len(self.a.hand), 2)


if __name__ == "__main__":
    unittest.main()
