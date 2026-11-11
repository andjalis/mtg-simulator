"""Static-condition batch: capitalised 'Protection from X and from Y' lines."""
import unittest

from tests.test_templates import card


class ProtectionAndFrom(unittest.TestCase):
    def test_capitalised_double_protection(self):
        c = card("Test Crusader", "{3}", "Creature — Human", "Protection from black and from red", 2, 2)
        self.assertEqual(c.unsupported, [])
        self.assertEqual(set(c.keywords), {"protection from black", "protection from red"})


if __name__ == "__main__":
    unittest.main()
