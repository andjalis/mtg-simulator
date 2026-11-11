"""Named-card references (#314): tutors for a card named X from the library and/or graveyard."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, card

TARGET = card("Test Dragon", "{4}{R}", "Creature — Dragon", "", 4, 4)
SCORN = card("Test Scorn", "{1}", "Sorcery",
             "You may search your library and/or graveyard for a card named Test Dragon, reveal it, and put it into your hand. "
             "If you search your library this way, shuffle.")


class NamedTutorTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 10
        p = Permanent(ISLAND, self.a)
        p.sick, p.tapped = False, False
        self.a.battlefield.append(p)

    def cast(self):
        self.a.hand = [SCORN]
        self.assertTrue(self.game.cast(self.a, SCORN))
        self.game.settle()

    def test_matches(self):
        self.assertEqual(SCORN.unsupported, [])

    def test_finds_it_in_the_library(self):
        self.a.library.insert(3, TARGET)
        self.cast()
        self.assertEqual([c.name for c in self.a.hand], ["Test Dragon"])
        self.assertNotIn(TARGET, self.a.library)

    def test_finds_it_in_the_graveyard_without_touching_the_library(self):
        self.a.graveyard.append(TARGET)
        before = list(self.a.library)
        self.cast()
        self.assertEqual([c.name for c in self.a.hand], ["Test Dragon"])
        self.assertEqual(self.a.library, before)

    def test_fails_to_find(self):
        self.cast()
        self.assertEqual(self.a.hand, [])


if __name__ == "__main__":
    unittest.main()
