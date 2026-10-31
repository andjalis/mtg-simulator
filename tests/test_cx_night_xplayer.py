import unittest

from mtgsim import cards


class XPlayerTests(unittest.TestCase):
    def parse(self, text):
        return cards._parse_effects(text)

    def test_target_player_draws_x(self):
        effects, unmatched = self.parse("Target player draws X cards.")
        self.assertEqual(unmatched, [])
        self.assertEqual((effects[0].kind, effects[0].data.get("x")), ("draw", True))

    def test_you_gain_x_life(self):
        effects, unmatched = self.parse("You gain X life.")
        self.assertEqual(unmatched, [])
        self.assertTrue(effects[0].data.get("x"))

    def test_unrelated_verb_is_not_guessed(self):
        _, unmatched = self.parse("Target player flips X cards.")
        self.assertTrue(unmatched)


if __name__ == "__main__":
    unittest.main()
