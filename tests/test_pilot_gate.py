"""Synthetic checks for the local-model review gate (no database required)."""
from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from scripts.pilot_gate import census, compare_coverage, exercise_cards, markdown, run, select_tests, suspicious, verdict


class PilotGateTests(unittest.TestCase):
    def setUp(self):
        self.checks = {"lint": {"returncode": 0}, "tests": {"returncode": 0}}
        self.smoke = {"completed": 50, "failures": []}

    def test_unchanged_passes_with_zero_deltas(self):
        snapshot = {"cards": {"A": "full", "B": "partial"},
                    "all": {"full": 1, "partial": 1, "total": 2},
                    "standard": {"full": 1, "total": 1}}
        comparison = compare_coverage(snapshot, snapshot)
        self.assertTrue(all(v == 0 for d in comparison["deltas"].values() for v in d.values()))
        self.assertEqual(verdict(self.checks, comparison, [], self.smoke), ("PASS", []))

    def test_gains_do_not_cancel_regressions(self):
        before = {"cards": {"A": "full", "B": "partial", "C": "full", "D": "parse_error"},
                  "all": {"full": 2, "partial": 1, "parse_error": 1}, "standard": {"full": 1}}
        after = {"cards": {"A": "partial", "B": "full", "C": "parse_error", "D": "parse_error"},
                 "all": {"full": 1, "partial": 1, "parse_error": 2}, "standard": {"partial": 1}}
        comp = compare_coverage(before, after)
        self.assertEqual(comp["regressions"], ["A", "C"])
        self.assertEqual(comp["newly_full"], ["B"])
        self.assertEqual(comp["newly_raising"], ["C"])
        self.assertEqual(comp["deltas"]["standard"], {"full": -1, "partial": 1})
        status, reasons = verdict(self.checks, comp, [], self.smoke)
        self.assertEqual(status, "FAIL")
        self.assertEqual(len(reasons), 2)

    def test_newly_full_passes_without_flags(self):
        self.assertEqual(verdict(self.checks, {"newly_full": ["A"]},
                                 [{"name": "A", "flags": []}], self.smoke), ("PASS", []))

    def test_each_failed_check_fails(self):
        for check in ("lint", "tests", "parse_diff", "coverage_head", "sample"):
            with self.subTest(check=check):
                status, reasons = verdict({check: {"returncode": 1}}, {}, [], self.smoke)
                self.assertEqual(status, "FAIL")
                self.assertIn(check, reasons[0])

    def test_timeout_crash_and_missing_games_fail(self):
        status, reasons = verdict({"tests": {"returncode": -9, "timeout": True}}, {}, [],
                                 {"completed": 49, "failures": [{"seed": 1}]})
        self.assertEqual(status, "FAIL")
        self.assertIn("timeout", reasons[0])
        self.assertIn("49/50", reasons[1])
        self.assertEqual(verdict({}, {}, [], {"completed": 0})[0], "FAIL")

    def test_suspicious_fields_include_hidden_defaults(self):
        @dataclass
        class Effect:
            target: str = "none"
        flags = suspicious({"effects": [Effect()], "data": {"what": "", "filter": "{unresolved}"},
                            "oracle": "{CARDNAME} costs {2}{R}", "mana": "{2}{R}"})
        self.assertEqual(len(flags), 3)
        self.assertTrue(any("target='none'" in f for f in flags))
        self.assertTrue(any("what is empty" in f for f in flags))
        self.assertTrue(any("placeholder" in f for f in flags))
        self.assertEqual(verdict({}, {}, [{"name": "A", "flags": flags}], self.smoke)[0], "FAIL")

    def test_untargeted_none_is_advisory(self):
        sample = {"name": "Innocent Blood", "flags": ["parse.spell_effects[0].target='none'"]}
        self.assertEqual(verdict({}, {}, [sample], self.smoke)[0], "PASS")

    def test_removed_cards_fail(self):
        self.assertEqual(verdict({}, {"removed": ["A"]}, [], self.smoke)[0], "FAIL")

    def test_crash_on_resolution_fails(self):
        crash = {"name": "A", "ok": False, "step": "cast", "error": "AttributeError: x", "at": "damage.py:1"}
        status, reasons = verdict({}, {}, [], self.smoke, [crash, {"name": "B", "ok": True}])
        self.assertEqual(status, "FAIL")
        self.assertIn("1 newly-full cards crash when resolved: A", reasons)
        self.assertEqual(verdict({}, {}, [], self.smoke, [{"name": "B", "ok": True}])[0], "PASS")

    def test_exercise_resolves_effects_and_records_crashes(self):
        import json
        from unittest.mock import patch
        from mtgsim.engine import Game

        with tempfile.TemporaryDirectory() as tmp:
            names, out = Path(tmp) / "names.json", Path(tmp) / "out.json"
            names.write_text(json.dumps(["Lightning Bolt"]))
            exercise_cards(Path("."), names, out)
            self.assertEqual(json.loads(out.read_text()), [{"name": "Lightning Bolt", "ok": True}])
            with patch.object(Game, "deal_damage", side_effect=AttributeError("no subtype")):
                exercise_cards(Path("."), names, out)
            result = json.loads(out.read_text())[0]
            self.assertEqual((result["ok"], result["step"], result["error"]), (False, "cast", "AttributeError: no subtype"))

    def test_fast_tests_related_and_safe_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests/test_pilot_gate.py").touch()
            self.assertEqual(select_tests(["scripts/pilot_gate.py"], root), ["tests.test_pilot_gate"])
            self.assertEqual(select_tests(["tests/test_pilot_gate.py"], root), ["tests.test_pilot_gate"])
            self.assertEqual(select_tests(["mtgsim/cards/parse.py"], root)[0], "discover")
            self.assertEqual(select_tests(["mtgsim/unmapped.py"], root)[0], "discover")
            self.assertEqual(select_tests([], root)[0], "discover")

    def test_process_timeout_is_recorded(self):
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            result = run([sys.executable, "-c", "import time; time.sleep(30)"],
                         Path(tmp), Path(tmp) / "log", timeout=.05)
        self.assertTrue(result["timeout"])
        self.assertNotEqual(result["returncode"], 0)

    def test_census_preserves_overrides_and_counts_distinct_entries(self):
        import json
        import sqlite3
        from unittest.mock import patch
        from mtgsim.carddb import CardDB
        from mtgsim import standard_coverage

        db = object.__new__(CardDB)
        raw = {"name": "Test A", "mana_cost": "", "cmc": 0,
               "type_line": "Creature", "oracle_text": "", "power": "2", "toughness": "2"}
        db.raw = {"test a": dict(raw, oracle_text="Unsupported wording.")}
        db._defs = {}
        db.offline = True
        db._all = sqlite3.connect(":memory:")
        db._all.execute("CREATE TABLE cards (key TEXT, name TEXT, data TEXT)")
        db._all.executemany("INSERT INTO cards VALUES (?, ?, ?)",
                            [("a", "Test A", json.dumps(raw)),
                             ("b", "Test B", json.dumps(dict(raw, name="Test B")))])
        with tempfile.TemporaryDirectory() as tmp, \
                patch("mtgsim.carddb.CardDB", return_value=db), \
                patch.object(standard_coverage, "standard_cards", return_value=({}, ["Test A", "Test B"])):
            dest = Path(tmp) / "census.json"
            census(Path(tmp), tmp, dest)
            result = json.loads(dest.read_text())
        self.assertEqual(result["cards"], {"Test A": "partial", "Test B": "full"})
        self.assertEqual(result["all"], {"partial": 1, "full": 1, "total": 2})
        self.assertEqual(result["standard"], result["all"])

    def test_markdown_contains_samples_and_failure_reasons(self):
        report = {"verdict": "FAIL", "base": "a" * 40, "head": "b" * 40, "fast": True,
                  "seconds": 1, "reasons": ["bad parse"], "checks": {}, "smoke": self.smoke,
                  "comparison": {"regressions": ["A"]},
                  "samples": [{"name": "A", "oracle": "draw\nthen | scry", "parsed": "Effect()", "flags": []}]}
        report["exercise"] = [{"name": "A", "ok": False, "step": "cast", "error": "KeyError: 'x'", "at": "damage.py:3"}]
        md = markdown(report)
        for expected in ("FAIL", "bad parse", "regressions (1): A", "Effect()", "&#124;", "50/50",
                         "Exercise: 0/1", "**A** (cast): KeyError"):
            self.assertIn(expected, md)


if __name__ == "__main__":
    unittest.main()
