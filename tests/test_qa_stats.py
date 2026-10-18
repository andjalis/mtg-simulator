"""Regression checks for statistics inputs and outcome accounting."""
import tempfile
import unittest
from pathlib import Path

from mtgsim.rating import LadderTracker, load_ratings
from mtgsim.runner import MatchResult, clear_result, pool_rate, wilson


class StatisticsQATests(unittest.TestCase):
    def test_nonfinite_rating_file_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ratings.json"
            for number in ("1e999", "-1e999", "Infinity", "-Infinity", "NaN"):
                with self.subTest(number=number):
                    path.write_text('{"decks": {"gold/a": {"rating": ' + number + '}}}')
                    self.assertEqual(load_ratings(path), {})

    def test_mixed_outcomes_preserve_draws_and_unknown_seats(self):
        result = MatchResult("a", "b")
        for winner, first in ((0, 0), (None, 0), (1, 1), (None, 1), (0, None)):
            result.add_game(winner, first, None)
        self.assertEqual((result.games, result.wins_a, result.wins_b, result.draws), (5, 2, 1, 2))
        self.assertEqual(result.win_rate_a, 0.6)
        self.assertEqual((result.games_a_on_play, result.games_a_on_draw), (2, 2))
        self.assertEqual((result.draws_a_on_play, result.draws_a_on_draw), (1, 1))
        self.assertFalse(result.play_draw_known)
        self.assertIn("unknown first player 1", result.summary())

    def test_unequal_matchup_sizes_use_equal_opponent_weight(self):
        tracker = LadderTracker("a", [("gold", "Gold", ["gold/b", "gold/c"])], ratings={})
        tracker.update_match("gold/b", wins=20, draws=0, games=20)
        tracker.update_match("gold/c", wins=0, draws=0, games=100)
        tracker.end_pool("gold")
        self.assertEqual(tracker.pool_results["gold"]["rate"], pool_rate([(20, 20), (0, 100)]))
        self.assertEqual(tracker.pool_results["gold"]["rate"], 0.5)

    def test_draw_only_matchups_never_trigger_early_stop(self):
        for games in (20, 100, 1000):
            self.assertFalse(clear_result(games / 2, games))
            lo, hi = wilson(games / 2, games)
            self.assertLess(lo, 0.5)
            self.assertGreater(hi, 0.5)
