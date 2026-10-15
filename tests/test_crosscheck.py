import unittest

from mtgsim.crosscheck import classify, default_matchups, z_score


class CrossCheckTest(unittest.TestCase):
    def test_z_score(self):
        self.assertAlmostEqual(z_score(0.5, 100, 0.5, 100), 0.0)
        self.assertGreater(z_score(0.8, 500, 0.4, 40), 4)
        self.assertLess(z_score(0.4, 500, 0.8, 40), -4)

    def test_classify(self):
        self.assertEqual(classify({"gap": 0.30, "z": 4.0}, 0.15, 3.0), "DISAGREE")
        self.assertEqual(classify({"gap": 0.10, "z": 2.2}, 0.15, 3.0), "minor")
        self.assertEqual(classify({"gap": 0.30, "z": 1.0}, 0.15, 3.0), "")

    def test_default_matchups(self):
        pairs = default_matchups()
        self.assertTrue(all(a != b for a, _, b, _ in pairs))
        self.assertEqual(len(pairs), len({(a, b) for a, _, b, _ in pairs}))
        self.assertTrue(any(a == "ub_snow_control" for a, _, _, _ in pairs))


if __name__ == "__main__":
    unittest.main()
