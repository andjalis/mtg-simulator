"""#641: "Exile all <filter> cards from all graveyards / your graveyard / target player's hand"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

ALL = card("Test Lantern", "{1}", "Sorcery", "Exile all cards from all graveyards, then draw a card.")
CREATURES = card("Test Purge", "{1}", "Sorcery", "Exile all creature cards from all graveyards.")
HAND = card("Test Mindwipe", "{1}", "Sorcery", "Exile target player's hand.")
EACH_HAND = card("Test Void", "{1}", "Sorcery", "Each player exiles all cards from their hand.")
BEAR = card("Bear", "{1}", "Creature — Bear", "", 2, 2)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class ZoneExile(unittest.TestCase):
    def test_parse(self):
        for c in (ALL, CREATURES, HAND, EACH_HAND):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(CREATURES.spell_effects[0].data["desc"], "creature card")

    def test_refuses_unknown_filter_and_all_hands(self):
        for text in ("Exile all frob cards from all graveyards.", "Exile all cards from all hands."):
            self.assertTrue(card("Test Odd", "{1}", "Sorcery", text).unsupported, text)

    def test_filtered_graveyards(self):
        g, a, b = game()
        a.graveyard, b.graveyard = [BEAR, ISLAND], [BEAR]
        a.hand = [CREATURES]
        g.enter_battlefield(a, ISLAND)
        self.assertTrue(g.cast(a, CREATURES, [None]))
        g.settle()
        self.assertEqual([c.name for c in a.graveyard], ["Island", "Test Purge"])
        self.assertEqual(b.graveyard, [])
        self.assertEqual(len(a.exile) + len(b.exile), 2)

    def test_each_player_hand(self):
        g, a, b = game()
        b.hand = [BEAR, BEAR]
        a.hand = [EACH_HAND, BEAR]
        g.enter_battlefield(a, ISLAND)
        self.assertTrue(g.cast(a, EACH_HAND, [None]))
        g.settle()
        self.assertEqual((a.hand, b.hand), ([], []))
        self.assertEqual((len(a.exile), len(b.exile)), (1, 2))

    def test_target_player_hand_aims_at_opponent(self):
        g, a, b = game()
        b.hand = [BEAR, BEAR, BEAR]
        a.hand = [HAND, BEAR]
        g.enter_battlefield(a, ISLAND)
        self.assertTrue(g.cast(a, HAND))
        g.settle()
        self.assertEqual(b.hand, [])
        self.assertEqual(len(a.hand), 1)


if __name__ == "__main__":
    unittest.main()
