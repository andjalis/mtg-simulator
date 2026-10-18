"""Number words accepted by the library-selection templates, including Dovin's ultimate."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _num, card_from_scryfall
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND


class NumberWords(unittest.TestCase):
    def test_larger_number_words(self):
        for word, n in (("eight", 8), ("nine", 9), ("ten", 10), ("TEN", 10), ("10", 10)):
            with self.subTest(word=word):
                self.assertEqual(_num(word), n)

    def test_dovin_parses_and_ultimate_keeps_three_of_ten(self):
        c = card_from_scryfall({
            "name": "Dovin, Grand Arbiter", "mana_cost": "{1}{W}{U}", "cmc": 3,
            "type_line": "Legendary Planeswalker — Dovin", "loyalty": "3",
            "oracle_text": "+1: Until end of turn, whenever a creature you control deals combat damage to a player, put a loyalty counter on Dovin.\n"
                           "−1: Create a 1/1 colorless Thopter artifact creature token with flying. You gain 1 life.\n"
                           "−7: Look at the top ten cards of your library. Put three of them into your hand and the rest on the bottom of your library in a random order.",
        })
        cost, effects = c.loyalty_abilities[-1]
        self.assertEqual(cost, -7)
        self.assertEqual((effects[0].kind, effects[0].amount, effects[0].amount2), ("dig", 10, 3))
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0))
        a.library = [ISLAND] * 10 + [BEAR] * 3
        game.resolve(a, effects[0], None)
        self.assertEqual(len(a.hand), 3)
        self.assertEqual(len(a.library), 10)
        self.assertTrue(c.unsupported)  # the unimplemented +1 remains visible


if __name__ == "__main__":
    unittest.main()
