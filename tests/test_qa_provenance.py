"""Resume must reject or replay structurally corrupted saved state."""
import json
from pathlib import Path
import tempfile
import unittest

from mtgsim import benchmark, provenance
from tests import test_benchmark


class CorruptedResumeTests(unittest.TestCase):
    def test_corrupted_entry_shapes_are_replayed(self):
        for replacement in (None, [], "broken", {"status": "complete", "result": None},
                            {"status": "complete", "result": []}):
            with self.subTest(replacement=replacement):
                fixture = test_benchmark.BenchmarkTests()
                fixture.setUp()
                try:
                    self.assertEqual(fixture.execute(), (0, 1))
                    checkpoint = fixture.args.out / "results.json"
                    state = json.loads(checkpoint.read_text())
                    state["results"]["a-vs-b/builtin"] = replacement
                    checkpoint.write_text(json.dumps(state))
                    self.assertEqual(fixture.execute(), (0, 1))
                finally:
                    fixture.tearDown()

    def test_corrupted_artifact_mapping_is_replayed(self):
        fixture = test_benchmark.BenchmarkTests()
        fixture.setUp()
        try:
            fixture.execute()
            checkpoint = fixture.args.out / "results.json"
            for replacement in ([], ["log"], None, {"log": None}):
                with self.subTest(replacement=replacement):
                    state = json.loads(checkpoint.read_text())
                    state["results"]["a-vs-b/builtin"]["artifacts"] = replacement
                    checkpoint.write_text(json.dumps(state))
                    self.assertEqual(fixture.execute(), (0, 1))
        finally:
            fixture.tearDown()

    def test_malformed_checkpoint_rejected_with_value_error(self):
        fixture = test_benchmark.BenchmarkTests()
        fixture.setUp()
        try:
            fixture.args.out.mkdir()
            checkpoint = fixture.args.out / "results.json"
            for state in ([], None, {"results": [], "coverage": {}}):
                with self.subTest(state=state):
                    checkpoint.write_text(json.dumps(state))
                    with self.assertRaisesRegex(ValueError, "malformed checkpoint"):
                        fixture.execute()
        finally:
            fixture.tearDown()

    def test_artifact_paths_must_stay_inside_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "out"
            output.mkdir()
            external = root / "outside.log"
            external.write_text("outside")
            sha = provenance.file_hash(external)
            self.assertFalse(provenance.valid_artifacts(output, {"../outside.log": sha}))
            self.assertFalse(provenance.valid_artifacts(output, {str(external): sha}))
            (output / "linked.log").symlink_to(external)
            self.assertFalse(provenance.valid_artifacts(output, {"linked.log": sha}))
            local = output / "actual.log"
            local.write_text("inside")
            self.assertTrue(provenance.valid_artifacts(output, {"actual.log": provenance.file_hash(local)}))
