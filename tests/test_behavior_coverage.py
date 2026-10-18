import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mtgsim import behavior_coverage as bc
from mtgsim.cards import CardDef
from mtgsim.provenance import digest, file_hash
from tests.test_rules_contracts import ISAMARU
from tests.test_templates import BEAR


class EvidenceFixture(unittest.TestCase):
    # Deliberately not named test_*: invoked only by the runner characterization below.
    def intentional_failure(self):
        self.assertEqual(1, 2)

    def intentional_skip(self):
        self.skipTest("unsupported setup")


class BehaviorCoverageTests(unittest.TestCase):
    def setUp(self):
        self.catalog, self.manifest = bc.load_catalogs()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.one = {**self.manifest, "scenarios": [self.manifest["scenarios"][0]]}
        self.scenario = self.one["scenarios"][0]

    def record(self, outcome="pass"):
        trace = self.folder / "trace.txt"
        trace.write_text("actual test output")
        return {"schema": 1, "scenario_id": self.scenario["id"], "scenario_hash": digest(self.scenario),
                "run_identity": "current", "engine": "builtin", "outcome": outcome,
                "trace": "trace.txt", "trace_sha256": file_hash(trace)}

    def test_empty_denominator_is_not_measured(self):
        self.assertEqual(bc.evidence_status([], complete=True), "not_measured")
        rows = bc.evaluate(self.one, [], "current", self.folder)
        self.assertEqual(rows[0]["outcome"], "not_run")

    def test_stale_identity_version_and_trace_never_pass(self):
        for field, value in (("run_identity", "old"), ("scenario_hash", "old"),
                             ("trace_sha256", "old"), ("trace", "missing.txt")):
            record = self.record()
            record[field] = value
            rows = bc.evaluate(self.one, [record], "current", self.folder)
            self.assertEqual(rows[0]["outcome"], "stale", field)
            self.assertEqual(bc.evidence_status(rows, complete=True), "not_measured")

    def test_duplicates_and_removed_scenarios_rejected(self):
        record = self.record()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            bc.evaluate(self.one, [record, record], "current", self.folder)
        record["scenario_id"] = "deleted"
        with self.assertRaisesRegex(ValueError, "removed/unknown"):
            bc.evaluate(self.one, [record], "current", self.folder)

    def test_failures_errors_and_incomplete_requirements(self):
        for outcome in ("fail", "error"):
            rows = bc.evaluate(self.one, [self.record(outcome)], "current", self.folder)
            self.assertEqual(bc.evidence_status(rows, complete=True), "has_failures")
        passing = [{"outcome": "pass"}]
        self.assertEqual(bc.evidence_status(passing), "some_scenarios_pass")
        self.assertEqual(bc.evidence_status(passing, complete=True), "scoped_suite_passes")
        self.assertEqual(bc.evidence_status(passing, complete=True, capabilities_supported=False), "some_scenarios_pass")

    def test_trace_path_cannot_escape(self):
        record = self.record()
        record["trace"] = "../outside.txt"
        with self.assertRaisesRegex(ValueError, "inside"):
            bc.evaluate(self.one, [record], "current", self.folder)

    def test_direct_and_inferred_card_evidence_separate(self):
        rows = [{**s, "outcome": "pass"} for s in self.manifest["scenarios"]]
        legend = bc.card_row(ISAMARU, rows, self.catalog)
        self.assertTrue(legend["current_direct_scenarios"])
        self.assertIn("sba.legend", legend["required_capabilities"])
        other = bc.card_row(CardDef("Other", {}, 0, frozenset({"Creature"}), legendary=True), rows, self.catalog)
        self.assertFalse(other["current_direct_scenarios"])
        self.assertTrue(other["current_capability_scenarios"])
        self.assertFalse(legend["requirements_complete"])
        self.assertNotEqual(legend["evidence_status"], "scoped_suite_passes")
        vanilla = bc.card_row(BEAR, rows, self.catalog)
        self.assertFalse(vanilla["current_direct_scenarios"])
        self.assertEqual(vanilla["evidence_status"], "some_scenarios_pass")

    def test_unknown_or_untested_requirement_visible(self):
        row = bc.card_row(ISAMARU, [], {"capabilities": []})
        self.assertEqual(row["evidence_status"], "not_measured")
        self.assertEqual(row["declared_gaps"], ["sba.legend"])
        self.assertEqual(row["untested_requirements"], ["sba.legend"])

    def test_catalog_rejects_unknown_mapping_and_duplicates(self):
        capfile, scenariofile = self.folder / "caps.json", self.folder / "scenarios.json"
        capfile.write_text(json.dumps(self.catalog))
        for mutate in (lambda m: m["scenarios"].append(m["scenarios"][0]),
                       lambda m: m["scenarios"][0].update(capabilities=["unknown"])):
            manifest = copy.deepcopy(self.manifest)
            mutate(manifest)
            scenariofile.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                bc.load_catalogs(capfile, scenariofile)

    def test_runner_records_actual_outcomes_and_trace_hashes(self):
        records = bc.execute(self.one, "current", self.folder)
        self.assertEqual(records[0]["outcome"], "pass")
        self.assertEqual(bc.evaluate(self.one, records, "current", self.folder)[0]["outcome"], "pass")
        broken = copy.deepcopy(self.one)
        broken["scenarios"][0]["test"] = "tests.test_rules_contracts.RulesContracts.test_missing"
        records = bc.execute(broken, "current", self.folder)
        self.assertEqual(records[0]["outcome"], "error")

    def test_card_source_changes_invalidate_identity(self):
        with patch.object(bc, "runtime_identity", return_value={"card_hash": "before"}):
            before = bc.identity(self.catalog, self.manifest)
        with patch.object(bc, "runtime_identity", return_value={"card_hash": "after"}):
            after = bc.identity(self.catalog, self.manifest)
        self.assertNotEqual(before, after)

    def test_runner_failure_and_skip_are_not_passes(self):
        for method, expected in (("intentional_failure", "fail"), ("intentional_skip", "not_run")):
            manifest = copy.deepcopy(self.one)
            manifest["scenarios"][0]["test"] = "tests.test_behavior_coverage.EvidenceFixture." + method
            records = bc.execute(manifest, "current", self.folder)
            self.assertEqual(records[0]["outcome"], expected)

    def test_catalog_rejects_dependency_cycles(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["capabilities"][0]["requires"] = [catalog["capabilities"][0]["id"]]
        capfile, scenariofile = self.folder / "caps.json", self.folder / "scenarios.json"
        capfile.write_text(json.dumps(catalog))
        scenariofile.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "cyclic"):
            bc.load_catalogs(capfile, scenariofile)
