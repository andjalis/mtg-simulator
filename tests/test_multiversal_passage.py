"""Audit 2026-11-16 (opus-cast), round 6 (decks): Multiversal Passage ("As this land enters, choose a basic
land type ... This land is the chosen type.") chose a type but made no mana."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import card

PASSAGE_TEXT = ("As this land enters, choose a basic land type. Then you may pay 2 life. If you don't, it enters "
                "tapped.\nThis land is the chosen type.")
BLUE = card("Test Blue", "{U}", "Instant", "Draw a card.")


def game(text=PASSAGE_TEXT, deck=BLUE):
    passage = card("Test Passage", "", "Land", text)
    a = Player("A", [deck] * 10, HeuristicAI())
    b = Player("B", [deck] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0))
    g.turn, g.step = 3, "main1"
    a.library, a.hand = [deck] * 10, [passage]
    g.play_land(a, passage)
    g.settle()
    return g, a, a.battlefield[0]


class MultiversalPassage(unittest.TestCase):
    def test_makes_the_chosen_types_mana(self):
        g, a, land = game()
        self.assertEqual(land.chosen_color, "U")          # the colour its blue deck needs
        self.assertIn("Island", land.card.subtypes)
        self.assertTrue(g.can_pay(a, {"U": 1, "generic": 0}) or land.tapped)
        land.tapped = False
        self.assertTrue(g.can_pay(a, {"U": 1, "generic": 0}))
        self.assertFalse(g.can_pay(a, {"R": 1, "generic": 0}))

    def test_casts_a_spell_with_it(self):
        g, a, land = game()
        land.tapped = False
        a.hand = [BLUE]
        self.assertTrue(g.cast(a, BLUE, None))

    def test_other_choose_a_colour_lands_unchanged(self):
        """A chosen-colour land without "is the chosen type" (the Gates) keeps only its own mana lines."""
        g, a, land = game("As this land enters, choose a color other than black.\n{T}: Add {B} or one mana of the "
                          "chosen color.")
        self.assertEqual(set(land.card.produces), {"B", land.chosen_color})
        self.assertEqual(land.card.subtypes, frozenset())


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCard(unittest.TestCase):
    def test_real_card(self):
        from mtgsim.carddb import CardDB
        g, a, land = game(CardDB(offline=True).get("Multiversal Passage").oracle)
        land.tapped = False
        self.assertTrue(g.can_pay(a, {"U": 1, "generic": 0}))


if __name__ == "__main__":
    unittest.main()
