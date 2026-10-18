"""Offline assessment regressions for edge cases found during parallel QA."""
import json
from pathlib import Path
import unittest

from mtgsim.assess import (Archetype, assess, assess_consistency, assess_meta,
                          assess_mana, main, p_on_curve)
from mtgsim.carddb import CardDB


class AssessmentEdgeTests(unittest.TestCase):
    def test_unanimous_tiny_samples_retain_uncertainty(self):
        archetypes = [Archetype("A", Path("a.txt"), {"test": 1}, 0.8),
                      Archetype("B", Path("b.txt"), {"test": 1}, 0.2)]
        for points in (0, 1):
            with self.subTest(points=points):
                _, criterion = assess_meta("deck", archetypes,
                                            {"a": (points, 1), "b": (points, 1)}, {})
                lo, hi = criterion["details"]["weighted_ci"]
                self.assertGreater(hi - lo, 0.5)
                self.assertLessEqual(lo, points)
                self.assertGreaterEqual(hi, points)

    def test_no_meta_samples_report_full_uncertainty(self):
        _, criterion = assess_meta("deck", [], {}, {})
        self.assertEqual(criterion["details"]["weighted_ci"], [0.0, 1.0])

    def test_small_deck_sources_use_available_cards(self):
        self.assertEqual(p_on_curve(5, 4, 4, 1, 1), 1.0)
        self.assertEqual(p_on_curve(5, 4, 0, 1, 1), 0.0)
        mana = assess_mana({"Mountain": 4, "Lightning Bolt": 1}, CardDB(offline=True))
        self.assertEqual(mana["score"], 100)

    def test_nonpositive_consistency_samples_raise_useful_error(self):
        for samples in (0, -1, True, 0.5):
            with self.subTest(samples=samples), self.assertRaisesRegex(ValueError, "positive integer"):
                assess_consistency([], samples=samples)

    def test_cli_rejects_zero_samples_before_reading_deck(self):
        from contextlib import redirect_stderr
        from io import StringIO
        err = StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            main(["does-not-exist.txt", "--samples", "0"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--samples must be positive", err.getvalue())

    def test_all_lands_offline_assessment_has_finite_json(self):
        result = assess("lands", {"Forest": 60}, CardDB(offline=True),
                        skip_meta=True, goldfish_games=1, samples=2, seed=23)
        json.dumps(result, allow_nan=False)
        self.assertIsNone(result["rating"])
        self.assertIsNone(result["reliability"])
        self.assertEqual(result["criteria"]["speed"]["details"]["no_kill_rate"], 1)
        self.assertEqual(result["criteria"]["consistency"]["details"]["flood_rate"], 1)


if __name__ == "__main__":
    unittest.main()
