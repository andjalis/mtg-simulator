"""Static maximum-hand-size modifiers parse into the card definition."""
import unittest

from tests.test_templates import card

ADVISOR = card("Test Advisor", "{1}{U}", "Creature — Human", "Your maximum hand size is increased by two.", 1, 1)
NIBBLER = card("Test Nibbler", "{1}{B}", "Creature — Imp", "Your maximum hand size is reduced by two.", 1, 1)
MISER = card("Test Miser", "{1}{B}", "Creature — Rat", "Each opponent's maximum hand size is reduced by one.", 1, 1)


class HandSize(unittest.TestCase):
    def test_parses(self):
        self.assertEqual((ADVISOR.hand_size_mod, NIBBLER.hand_size_mod, MISER.opp_hand_size_mod), (2, -2, -1))
        self.assertEqual((ADVISOR.unsupported, NIBBLER.unsupported, MISER.unsupported), ([], [], []))


if __name__ == "__main__":
    unittest.main()
