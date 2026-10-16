import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout

from mtgsim.__main__ import run_tiers
from mtgsim.ladder_report import render_fragment, render_page, sparkline, text_summary
from mtgsim.calibrate import fit, predicted, readme_observations, summarize
from mtgsim.rating import (RANKS, RATINGS_FILE, LadderTracker, expected, load_ratings, next_rank,
                           performance_rating, pool_anchors, rank_for)
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
        self.assertEqual(pool_anchors([t.key for t in TIERS]), {r.key: r.anchor for r in RANKS})  # pools are ranks
        spread = pool_anchors(["trash", "beginner", "advanced", "semipro", "pro"])
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
        rates = {"bronze": 0.9, "silver": 0.6, "gold": 0.4, "platinum": 0.8, "diamond": 0.8, "master": 0.8,
                 "grandmaster": 0.1}
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
        self.assertIn("stopped at Gold", d["verdict"])
        self.assertEqual([p["cleared"] for p in d["pools"]], [True, True, False, None, None, None, None])
        self.assertIn("Rank: me is", out.getvalue())


class CalibrateTests(unittest.TestCase):
    POOLS = {"bronze": ["bronze/a", "bronze/b"], "silver": ["silver/c", "silver/d"], "gold": ["gold/e"]}

    def test_fit_recovers_ratings(self):
        rng = random.Random(3)
        true = {d: 900 + 150 * i + rng.uniform(-60, 60) for i, ds in enumerate(self.POOLS.values()) for d in ds}
        names = list(true)
        obs = [{"a": a, "b": b, "points": expected(true[a], true[b]) * 10000, "games": 10000, "engine": "python"}
               for i, a in enumerate(names) for b in names[i + 1:]]
        got = fit(obs, self.POOLS, shrink=0)
        shift = (true["bronze/a"] + true["bronze/b"]) / 2 - RANKS[0].anchor
        for d in names:
            self.assertAlmostEqual(got[d], true[d] - shift, delta=1)
        self.assertAlmostEqual((got["bronze/a"] + got["bronze/b"]) / 2, RANKS[0].anchor, delta=0.01)

    def test_rank_level_observations(self):
        # a rank-vs-rank result moves every deck of the rank; decks with no games of their own stay together
        obs = [{"a": "silver", "b": "bronze", "points": 76, "games": 100, "engine": "forge"},
               {"a": "gold", "b": "silver", "points": 24, "games": 100, "engine": "forge"}]
        got = fit(obs, self.POOLS)
        self.assertAlmostEqual(predicted(got, "silver", "bronze", self.POOLS), 0.76, delta=0.005)
        self.assertAlmostEqual(predicted(got, "gold", "silver", self.POOLS), 0.24, delta=0.005)
        self.assertAlmostEqual(got["silver/c"], got["silver/d"], delta=0.5)
        doc = summarize(got, obs, self.POOLS, when="2026-10-15")
        self.assertEqual(doc["decks"]["gold/e"]["engine"], "forge")
        self.assertEqual(doc["decks"]["silver/c"]["games"], 100)
        # gold sits below silver here, so it is out of its band
        self.assertIn("gold/e", [x["deck"] for x in doc["out_of_band"]])

    def test_readme_rank_order_reproduced(self):
        """The rank-order numbers in decks/ranks/README.md, fitted at rank level, come back within five
        points (the built-in rows are not perfectly transitive: Platinum beats Bronze less than Gold does)."""
        obs = readme_observations()
        got = fit(obs)
        for o in obs:
            se = (0.25 / o["games"]) ** 0.5
            margin = max(2.5 * se, 0.05) if o["engine"] == "python" else 2 * se
            self.assertAlmostEqual(predicted(got, o["a"], o["b"]), o["points"] / o["games"], delta=margin)

    def test_tracker_uses_fitted_ratings_and_falls_back(self):
        pools = [("gold", "Gold", ["gold/a", "gold/b"]), ("master", "Master", ["master/c"])]
        t = LadderTracker("me", pools, ratings={"gold/a": 1111, "master/c": 1250})
        self.assertEqual(t.opponents["gold/a"].rating, 1111)
        self.assertEqual(t.opponents["gold/b"].rating, RANKS[2].anchor)     # not in the file: band centre
        d = t.to_dict()
        self.assertEqual(d["pools"][0]["rating"], round((1111 + 1300) / 2))
        self.assertEqual(d["pools"][1]["rank"], "Master")                  # the pool keeps its own rank name
        self.assertEqual(LadderTracker("me", pools, ratings={}).opponents["master/c"].rating, RANKS[5].anchor)
        self.assertEqual(pool_anchors(["gold", "master"], {"gold/a": 1111, "gold/b": 1211})["gold"], 1161)

    def test_load_ratings(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "ratings.json"
            self.assertEqual(load_ratings(p), {})                          # missing file
            p.write_text("not json")
            self.assertEqual(load_ratings(p), {})
            p.write_text(json.dumps({"decks": {"gold/a": {"rating": 1234.4, "games": 5}}}))
            self.assertEqual(load_ratings(p), {"gold/a": 1234})
        if RATINGS_FILE.exists():                                          # the checked-in fit covers every pool deck
            from mtgsim.ranks import RANKS as POOLS
            shipped = load_ratings()
            for pool in POOLS:
                for deck in pool.decks():
                    self.assertIn(f"{pool.key}/{deck.stem}", shipped)


if __name__ == "__main__":
    unittest.main()
