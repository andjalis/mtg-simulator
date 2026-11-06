import unittest

from mtgsim import cards


class UntapLands(unittest.TestCase):
    def test_counted_lands(self):
        for text, n in (("Untap up to two lands.", 2), ("Untap three target lands.", 3)):
            effects, unmatched = cards._parse_effects(text)
            self.assertEqual(unmatched, [])
            self.assertEqual((effects[0].kind, effects[0].amount), ("untap_lands", n))

    def test_x_is_not_guessed(self):
        _, unmatched = cards._parse_effects("Untap up to X lands.")
        self.assertTrue(unmatched)


if __name__ == "__main__":
    unittest.main()
