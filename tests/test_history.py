import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from mtgsim import history
from mtgsim.rating import LadderTracker

V1 = {"Mountain": 24, "Lightning Bolt": 4, "Shock": 4, "Goblin Guide": 28}
V2 = {"Mountain": 22, "Lightning Bolt": 4, "Lava Spike": 4, "Goblin Guide": 30}


def ladder(deck, wins):
    t = LadderTracker(deck, [("gold", "Gold", ["gold/a"])], ladder=True)
    t.update_match("gold/a", wins=wins, draws=0, games=10)
    t.end_pool("gold", wins >= 5)
    t.finish("done")
    return t.to_dict()


def assessment(deck, mmr, rank, scores):
    return {"deck": deck, "assessed": "2026-10-15", "format": "Standard",
            "rating": {"mmr": mmr, "rank": rank},
            "criteria": {k: {"label": k, "score": s, "grade": "ABCDF"[min(4, (100 - s) // 15)], "summary": "",
                             "details": {"matchups": [{"games": 10}]} if k == "meta" else {}}
                         for k, s in scores.items()}}


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "h.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fingerprint_ignores_order_and_case(self):
        self.assertEqual(history.fingerprint({"Shock": 4, "Mountain": 20}),
                         history.fingerprint({"mountain": 20, "Shock": 4, "Island": 0}))
        self.assertNotEqual(history.fingerprint({"Shock": 4}), history.fingerprint({"Shock": 3}))

    def test_versions_runs_and_compare(self):
        history.record_ladder(ladder("burn", 3), V1, path=self.db)
        history.record_assessment(assessment("burn", 1250, "Gold", {"meta": 40, "mana": 80}), V1, path=self.db)
        history.record_ladder(ladder("burn", 3), dict(reversed(list(V1.items()))), path=self.db)  # same list
        history.record_ladder(ladder("burn", 8), V2, engine="forge", path=self.db)
        history.record_assessment(assessment("burn", 1500, "Platinum", {"meta": 70, "mana": 85}), V2, path=self.db)
        history.record_ladder(ladder("other", 5), V1, source="web", path=self.db)

        vs = history.versions("burn", self.db)
        self.assertEqual([v["version"] for v in vs], [1, 2])
        self.assertEqual([len(v["runs"]) for v in vs], [3, 2])
        self.assertEqual(history.runs("other", self.db)[0]["version"], 1)  # versions count per deck

        rows = {d["deck"]: d for d in history.decks(self.db)}
        self.assertEqual(rows["burn"]["versions"], 2)
        self.assertEqual(rows["burn"]["latest"]["version"], 2)
        self.assertEqual(rows["burn"]["latest"]["mmr"], 1500)
        self.assertEqual(rows["burn"]["best"]["mmr"], max(r["mmr"] for r in history.runs("burn", self.db)))

        c = history.compare("burn", path=self.db)
        self.assertEqual((c["from"]["version"], c["to"]["version"]), (1, 2))
        self.assertEqual(c["added"], {"Lava Spike": 4})
        self.assertEqual(c["removed"], {"Shock": 4})
        self.assertEqual(c["changed"], {"Goblin Guide": [28, 30], "Mountain": [24, 22]})
        self.assertEqual(c["from"]["mmr"], ladder("burn", 3)["mmr"])  # each side: its latest rated run
        self.assertEqual(c["mmr"]["delta"], 1500 - c["from"]["mmr"])
        self.assertEqual(c["rank"], {"from": ladder("burn", 3)["rank"], "to": "Platinum"})
        self.assertEqual(c["scores"]["meta"], [40, 70])
        self.assertEqual(c["to"]["ladder"]["engine"], "forge")
        self.assertEqual(history.compare("burn", 2, 1, path=self.db)["added"], {"Shock": 4})
        self.assertEqual(history.compare("burn", vs[0]["fingerprint"][:6], path=self.db)["to"]["version"], 2)
        with self.assertRaises(KeyError):
            history.compare("nope", path=self.db)

        out = io.StringIO()
        with redirect_stdout(out):
            history.main(["compare", "burn.txt", "--db", str(self.db)])
            history.main(["list", "--db", str(self.db)])
            history.main(["show", "burn", "--db", str(self.db)])
        text = out.getvalue()
        self.assertIn("+ 4 Lava Spike", text)
        self.assertIn("Platinum 1500", text)
        self.assertIn("v2", text)


if __name__ == "__main__":
    unittest.main()
