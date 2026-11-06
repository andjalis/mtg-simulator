import gzip
import json
import tempfile
import unittest
from pathlib import Path

from mtgsim import play_weights
from mtgsim.database_coverage import DatabaseReport, card_weight, ranked, record_gaps
from mtgsim.coverage import CardCoverage, PARTIAL


class PlayWeights(unittest.TestCase):
    def test_mtgjson_rank_weights(self):
        data = {"data": {"Sol Ring": [{"edhrecRank": 1}], "Odd Card": [{}], "Front // Back": [{"edhrecRank": 100}]}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "AtomicCards.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump(data, f)
            w = play_weights.from_mtgjson(path)
        self.assertEqual(w["Sol Ring"], 1.0)
        self.assertEqual(w["Odd Card"], play_weights.UNRANKED)
        self.assertAlmostEqual(w["Front"], 0.1)
        self.assertAlmostEqual(w["Back"], 0.1)

    def test_deck_copies_and_load_sums(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.txt").write_text("4 Island\n// comment\n2 Opt\n", encoding="utf-8")
            (Path(d) / "b.txt").write_text("4x Opt\n", encoding="utf-8")
            counts = play_weights.from_decks(d)
            self.assertEqual(counts, {"Island": 4, "Opt": 6})
            (Path(d) / "w.json").write_text(json.dumps(counts))
            self.assertEqual(play_weights.load([Path(d) / "w.json", Path(d) / "w.json"])["Opt"], 12)

    def test_weighted_ranking_puts_played_cards_first(self):
        report = DatabaseReport(weights={"Staple": 5.0})
        record_gaps(report, CardCoverage("Staple", 1, PARTIAL, ["rare wording"]), ["rare wording"])
        for i in range(3):
            record_gaps(report, CardCoverage(f"Junk{i}", 1, PARTIAL, ["common wording"]), ["common wording"])
        self.assertEqual(ranked(report.wording)[0].label, "common wording")
        self.assertEqual(ranked(report.wording, True)[0].label, "rare wording")
        self.assertEqual(card_weight(report, "Staple"), 5.0)


if __name__ == "__main__":
    unittest.main()
