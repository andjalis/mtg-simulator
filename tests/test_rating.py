import io
import json
import unittest
from contextlib import redirect_stdout

from mtgsim.__main__ import run_tiers
from mtgsim.ladder_report import render_fragment, render_page, sparkline, text_summary
from mtgsim.rating import (RANKS, LadderTracker, expected, next_rank, performance_rating, pool_anchors,
                           rank_for)
from mtgsim.runner import MatchResult
from mtgsim.tiers import TIERS


class RatingTests(unittest.TestCase):
    def test_ranks(self):
        self.assertEqual(rank_for(0).name, "Bronze")
        self.assertEqual(rank_for(1199).name, "Silver")
        self.assertEqual(rank_for(1200).name, "Gold")
        self.assertEqual(rank_for(2600).name, "Grandmaster")
        self.assertEqual(next_rank(1450).name, "Diamond")
        self.assertIsNone(next_rank(2100))
        self.assertAlmostEqual(expected(1800, 1400), 10 / 11)

    def test_performance_rating(self):
        self.assertAlmostEqual(performance_rating([(1500, 50, 100)], prior=None), 1500, delta=1)
        # 10:1 odds is 400 points
        self.assertAlmostEqual(performance_rating([(1500, 100, 110)], prior=None), 1900, delta=1)
        # a clean sweep stays finite, and the prior keeps one game from swinging far
        self.assertLess(performance_rating([(1500, 10, 10)], prior=None), 3001)
        self.assertLess(performance_rating([(1500, 1, 1)]), 1500)
        self.assertAlmostEqual(performance_rating([]), 1000)

    def test_pool_anchors(self):
        self.assertEqual(pool_anchors(["bronze", "Gold", "grandmaster"]),
                         {"bronze": 900, "Gold": 1300, "grandmaster": 2100})
        spread = pool_anchors([t.key for t in TIERS])
        self.assertEqual(spread["trash"], RANKS[0].anchor)
        self.assertEqual(spread["pro"], RANKS[-1].anchor)
        self.assertEqual(list(spread.values()), sorted(spread.values()))

    def test_tracker_and_views(self):
        seen = []
        t = LadderTracker("me", [("gold", "Gold", ["gold/a", "gold/b"]), ("master", "Master", ["master/c"])])
        t.listeners.append(lambda tr: seen.append(tr.mmr))
        t.start_match("gold/a", 20)
        for g in range(1, 21):
            t.update_match("gold/a", wins=g, draws=0, games=g)
        self.assertGreater(t.mmr, 1500)
        self.assertEqual(len(t.history), 21)
        t.end_pool("gold", cleared=True)
        t.finish("done")
        d = json.loads(json.dumps(t.to_dict()))
        self.assertEqual(d["status"], "done")
        self.assertEqual(d["rank"], t.rank.name)
        self.assertEqual(d["pools"][0]["rate"], 1.0)
        self.assertEqual(d["opponents"][1]["win_rate"], None)
        self.assertGreater(len(seen), 20)
        self.assertIn("◀ me", text_summary(d))
        self.assertIn("MMR over the run", render_fragment(d))
        self.assertNotIn("http-equiv", render_page(d))
        d["status"] = "running"
        self.assertIn("http-equiv", render_page(d))
        self.assertEqual(len(sparkline([(i, i) for i in range(100)], width=10)), 10)

    def test_run_tiers_feeds_tracker(self):
        rates = {"trash": 0.9, "beginner": 0.6, "advanced": 0.4, "semipro": 0.8, "pro": 0.1}
        tracker = LadderTracker("me", [(t.key, t.label, [t.key]) for t in TIERS], ladder=True)

        def play(me, opp):
            res = MatchResult(me, opp, games=10)
            res.wins_a = round(rates[opp] * 10)
            res.wins_b = 10 - res.wins_a
            tracker.update_match(opp, res.wins_a, 0, 10)
            return res

        with redirect_stdout(io.StringIO()) as out:
            run_tiers("me", TIERS, {t.key: [t.key] for t in TIERS}, play, ladder=True, tracker=tracker)
        d = tracker.to_dict()
        self.assertEqual(d["status"], "done")
        self.assertIn("stopped at Advanced", d["verdict"])
        self.assertEqual([p["cleared"] for p in d["pools"]], [True, True, False, None, None])
        self.assertIn("Rank: me is", out.getvalue())


if __name__ == "__main__":
    unittest.main()
