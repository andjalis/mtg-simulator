"""Whole-database census, resilient error accounting, and conservative gap ranking."""
import contextlib
import csv
import dataclasses
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mtgsim import database_coverage as dc
from tests.test_templates import BEAR


def definition(name, ignored=(), simplified=(), **extra):
    return dataclasses.replace(BEAR, name=name, unsupported=list(ignored), approximations=list(simplified), **extra)


class FakeDB:
    def __init__(self, cards):
        self.cards = cards
        self._all = sqlite3.connect(":memory:")
        self._all.execute("CREATE TABLE cards (key TEXT, name TEXT)")
        self._all.executemany("INSERT INTO cards VALUES (?, ?)", [(n.lower(), n) for n in cards])

    def get(self, name):
        value = self.cards[name]
        if isinstance(value, Exception):
            raise value
        return value


class DatabaseCoverage(unittest.TestCase):
    def db(self, cards):
        db = FakeDB(cards)
        self.addCleanup(db._all.close)
        return db

    def test_counts_every_database_entry_including_basics_and_errors(self):
        db = self.db({"Plains": definition("Plains"), "Loose": definition("Loose", simplified=["approximation"]),
                      "Partial": definition("Partial", ["Protection from red."]), "Broken": ValueError("bad amount")})
        progress = []
        report = dc.measure(db, lambda i, total: progress.append((i, total)))
        self.assertEqual(report.as_dict()["counts"], {"full": 1, "simplified": 1, "partial": 1, "parse_error": 1})
        self.assertEqual(len(report.rows), 4)
        self.assertEqual(report.errors, [{"name": "Broken", "error": "ValueError: bad amount"}])
        self.assertEqual(progress, [(4, 4)])

    def test_family_candidates_need_every_gap_and_no_simplifications(self):
        token = "Create a Bird creature token."
        db = self.db({"Only tokens": definition("Only tokens", [token, "Create two treasure tokens."]),
                      "Other gaps": definition("Other gaps", [token, "Untap it."]),
                      "Still loose": definition("Still loose", [token], ["approximation"])})
        gap = dc.measure(db).families["tokens"]
        self.assertEqual(gap.affected, {"Only tokens", "Other gaps", "Still loose"})
        self.assertEqual(gap.candidates, {"Only tokens"})

    def test_exact_wording_normalizes_case_whitespace_and_duplicate_lines(self):
        db = self.db({"A": definition("A", ["Protection  from red.", "PROTECTION from red."]),
                      "B": definition("B", ["Protection from red.", "Untap it."])})
        gap = dc.measure(db).wording["protection from red."]
        self.assertEqual(gap.affected, {"A", "B"})
        self.assertEqual(gap.candidates, {"A"})

    def test_face_names_do_not_split_the_same_missing_wording(self):
        db = self.db({"A": definition("A", back=definition("First Back", ["Protection from red."])),
                      "B": definition("B", adventure=definition("Second Adventure", ["Protection from red."]))})
        report = dc.measure(db)
        self.assertEqual(report.wording["protection from red."].candidates, {"A", "B"})
        self.assertIn("First Back:", report.rows[0].ignored[0])

    def test_wording_keeps_distinct_amounts_separate(self):
        db = self.db({"A": definition("A", ["Mill eight cards."]), "B": definition("B", ["Mill nine cards."])})
        self.assertEqual(set(dc.measure(db).wording), {"mill eight cards.", "mill nine cards."})

    def test_distinct_database_entries_with_same_front_name_count_separately(self):
        db = self.db({"Shared // First": definition("Shared", ["Protection from red."]),
                      "Shared // Second": definition("Shared", ["Protection from red."])})
        report = dc.measure(db)
        self.assertEqual(report.wording["protection from red."].candidates,
                         {"Shared // First", "Shared // Second"})
        self.assertEqual(len({r.name for r in report.rows}), 2)
        data = report.as_dict()
        self.assertEqual(data["unclassified"]["affected_cards"], 2)
        self.assertNotIn("unclassified", {g["gap"] for g in data["families"]})

    def test_overlapping_family_counts_are_not_added_together(self):
        db = self.db({"A": definition("A", ["Whenever ~ attacks, create a Bird creature token."])})
        report = dc.measure(db)
        self.assertEqual(report.families["tokens"].candidates, {"A"})
        self.assertEqual(report.families["triggered (whenever/when)"].candidates, {"A"})
        self.assertEqual(report.as_dict()["total"], 1)
        self.assertIn("must not be summed", report.as_dict()["ranking_method"])

    def test_rank_by_candidates_before_affected_count_with_stable_ties(self):
        gaps = {"frequent": dc.Gap("frequent", {"a", "b", "c"}),
                "b": dc.Gap("b", {"d"}, {"d"}), "a": dc.Gap("a", {"e"}, {"e"})}
        self.assertEqual([g.label for g in dc.ranked(gaps)], ["a", "b", "frequent"])

    def test_empty_database_is_valid_and_has_no_division_by_zero(self):
        report = dc.measure(self.db({}))
        self.assertEqual(report.as_dict()["total"], 0)
        self.assertIn("| Total | 0 | 0% |", dc.format_report(report))

    def test_exports_preserve_counts_and_multiline_text(self):
        c = definition("Æther Test", ["Missing | text.\nAnother missing line."])
        report = dc.measure(self.db({c.name: c}))
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            dc.save_report(report, dest)
            self.assertNotIn(b"\r\n", (dest / "cards.csv").read_bytes())
            self.assertNotIn(b"\r\n", (dest / "gaps.csv").read_bytes())
            data = json.loads((dest / "summary.json").read_text())
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["counts"]["partial"], 1)
            with (dest / "cards.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["ignored_text"], c.unsupported[0])
            self.assertEqual(rows[0]["name"], c.name)
            with (dest / "gaps.csv").open(newline="") as stream:
                gaps = list(csv.DictReader(stream))
            self.assertTrue(any(g["kind"] == "exact_wording" for g in gaps))
            self.assertIn("Missing \\| text.", (dest / "README.md").read_text().replace("missing", "Missing"))

    def test_cli_json_save_and_offline_lookup(self):
        db = self.db({"A": definition("A")})
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, patch.object(dc, "CardDB", return_value=db) as factory, \
                contextlib.redirect_stdout(out):
            self.assertEqual(dc.main(["--json", "--top", "0", "--save", tmp]), 0)
            self.assertTrue((Path(tmp) / "cards.csv").exists())
        factory.assert_called_once_with(offline=True)
        self.assertEqual(json.loads(out.getvalue())["counts"]["full"], 1)

    def test_cli_reports_parse_errors_with_nonzero_exit_after_saving(self):
        db = self.db({"Broken": ValueError("bad amount"), "A": definition("A")})
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, patch.object(dc, "CardDB", return_value=db), contextlib.redirect_stdout(out):
            self.assertEqual(dc.main(["--save", tmp]), 1)
            self.assertEqual(json.loads((Path(tmp) / "summary.json").read_text())["counts"]["full"], 1)
        self.assertIn("Broken: ValueError: bad amount", out.getvalue())

    def test_cli_missing_database_and_negative_top_fail_clearly(self):
        err = io.StringIO()
        with patch.object(dc, "CardDB", return_value=SimpleNamespace(_all=None)), contextlib.redirect_stderr(err):
            self.assertEqual(dc.main([]), 2)
        self.assertIn("build_carddb", err.getvalue())
        with patch.object(dc, "CardDB") as factory, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                dc.main(["--top", "-1"])
            self.assertEqual(caught.exception.code, 2)
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
