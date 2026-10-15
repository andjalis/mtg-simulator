import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mtgsim import benchmark, provenance
from mtgsim.crosscheck import checked_results
from mtgsim.runner import MatchResult


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.deck = self.root / "deck.txt"
        self.deck.write_text("24 Mountain\n36 Raging Goblin\n")
        self.manifest = {"schema": 1, "name": "test", "scope": "diagnostic fixtures",
                         "decks": [{"id": n, "archetype": a, "path": "deck.txt"} for n, a in
                                   (("a", "aggro"), ("b", "control"))],
                         "matchups": [["a", "b"]], "human_evidence": [],
                         "missing_evidence": "No applicable human game evidence.", "missing_coverage": ["combo"]}
        self.manifest_path = self.root / "manifest.json"
        self.save_manifest()
        self.args = argparse.Namespace(manifest=self.manifest_path, out=self.root / "out", engine="builtin",
                                       games=2, seed=7, jobs=1, clock=5, worker_timeout=None,
                                       forge_dir=None, java="java")
        self.result = MatchResult("a", "b", games=2, wins_a=1, draws=1)

    def tearDown(self):
        self.tmp.cleanup()

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def execute(self, runtime=None):
        with patch.object(benchmark, "runtime_identity", return_value=runtime or {"code": "v1"}), \
             patch.object(benchmark, "run_match", return_value=(self.result, ["first game"])) as play:
            code = benchmark.run(self.args)
            return code, play.call_count

    def test_default_manifest_existing_decks_and_limited_combo(self):
        m, decks = benchmark.load_manifest(benchmark.DEFAULT_MANIFEST)
        self.assertEqual({d["archetype"] for d in decks.values()}, {"aggro", "midrange", "control", "combo"})
        self.assertEqual(len(m["matchups"]), 4)
        self.assertEqual(m["human_evidence"], [])
        self.assertIn("combo", " ".join(m["missing_coverage"]))

    def test_draws_separate_from_win_probability_and_interval(self):
        r = benchmark.record(self.result)
        self.assertEqual(r["win_probability_a"], 0.5)
        self.assertEqual(r["score_a"], 0.75)
        self.assertEqual(r["draw_rate"], 0.5)
        self.assertLess(r["win_ci95"][0], 0.5)
        self.assertGreater(r["win_ci95"][1], 0.5)
        r = benchmark.record(MatchResult("a", "b", games=4, draws=4))
        self.assertEqual(r["win_probability_a"], 0)
        self.assertEqual(r["score_a"], 0.5)
        self.assertGreater(r["win_ci95"][1], 0)

    def test_resume_and_missing_log_replays_without_overwriting_old_attempt(self):
        self.assertEqual(self.execute(), (0, 1))
        self.assertEqual(self.execute(), (0, 0))
        log = next(self.args.out.rglob("first-game.log"))
        log.write_text("corrupt")
        self.assertEqual(self.execute(), (0, 1))
        self.assertEqual(log.read_text(), "corrupt")
        self.assertEqual(len(list(self.args.out.rglob("first-game.log"))), 2)
        report = (self.args.out / "report.md").read_text()
        for text in ("combo", "No applicable human", "no sideboarding", "not ground truth", "Wilson", "Arena"):
            self.assertIn(text, report)

    def test_changed_deck_refuses_resume(self):
        self.execute()
        self.deck.write_text("24 Mountain\n35 Raging Goblin\n")
        with self.assertRaisesRegex(ValueError, "Resume refused"):
            self.execute()

    def test_changed_runtime_and_settings_refuse_resume(self):
        self.execute()
        with self.assertRaisesRegex(ValueError, "Resume refused"):
            self.execute({"code": "v2"})
        self.args.seed += 1
        with self.assertRaisesRegex(ValueError, "Resume refused"):
            self.execute()

    def test_result_corruption_replays(self):
        self.execute()
        path = self.args.out / "results.json"
        data = json.loads(path.read_text())
        data["results"]["a-vs-b/builtin"]["result"]["wins_a"] = 2
        path.write_text(json.dumps(data))
        self.assertEqual(self.execute(), (0, 1))

    def test_inflight_change_invalidates_run(self):
        with patch.object(benchmark, "runtime_identity", side_effect=[{"code": "v1"}, {"code": "v2"}]), \
             patch.object(benchmark, "run_match", return_value=(self.result, ["log"])):
            self.assertEqual(benchmark.run(self.args), 1)
        data = json.loads((self.args.out / "results.json").read_text())
        self.assertEqual(data["status"], "invalid")
        with self.assertRaisesRegex(ValueError, "Resume refused"):
            self.execute()

    def test_forge_failure_preserved_and_retried(self):
        self.args.engine = "forge"
        def fail(*args, **kwargs):
            (kwargs["log_dir"] / "worker-0.log").write_text("failure evidence")
            raise benchmark.ForgeError("incomplete")
        with patch.object(benchmark, "runtime_identity", return_value={}), \
             patch.object(benchmark, "run_forge_match", side_effect=fail):
            self.assertEqual(benchmark.run(self.args), 1)
            self.assertEqual(benchmark.run(self.args), 1)
        self.assertEqual(len(list(self.args.out.rglob("worker-0.log"))), 2)
        state = json.loads((self.args.out / "results.json").read_text())
        self.assertEqual(state["results"]["a-vs-b/forge"]["status"], "failed")

    def test_reject_bo3_or_wrong_deck_evidence(self):
        self.manifest["human_evidence"] = [{"matchup": ["a", "b"], "unit": "BO3"}]
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "never BO3"):
            benchmark.load_manifest(self.manifest_path)
        self.manifest["human_evidence"][0].update(unit="main_deck_game", deck_sha256=["wrong", "wrong"])
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "exact deck"):
            benchmark.load_manifest(self.manifest_path)

    def test_legacy_and_changed_crosscheck_cache_rejected(self):
        path = self.root / "cross.json"
        path.write_text('{"a vs b": {"python": {"games": 500}}}')
        with self.assertRaisesRegex(ValueError, "Unsafe crosscheck"):
            checked_results(path, {"seed": 1})
        new = checked_results(path, {"seed": 1}, rerun=True)
        self.assertEqual(new, {"_provenance": {"seed": 1}})
        provenance.atomic_json(path, new)
        self.assertEqual(checked_results(path, {"seed": 1}), new)
        with self.assertRaises(ValueError):
            checked_results(path, {"seed": 2})

    def test_content_fingerprint_changes_even_with_same_size_and_mtime(self):
        resource = self.root / "res"
        resource.mkdir()
        p = resource / "script.txt"
        p.write_text("aaa")
        first = provenance.tree_hash(resource)
        stat = p.stat()
        p.write_text("bbb")
        import os
        os.utime(p, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertNotEqual(first, provenance.tree_hash(resource))
        p.unlink()
        self.assertNotEqual(first, provenance.tree_hash(resource))

    def test_output_lock_rejects_concurrent_writer(self):
        with provenance.output_lock(self.root / "locked"):
            with self.assertRaisesRegex(ValueError, "Run locked"):
                with provenance.output_lock(self.root / "locked"):
                    self.fail("Lock was ignored")
        self.assertFalse((self.root / "locked" / ".run.lock").exists())

    def test_runtime_identity_tracks_code_data_jar_and_resource_content(self):
        from types import SimpleNamespace
        forge = self.root / "forge"
        (forge / "res").mkdir(parents=True)
        jar = forge / "forge-gui-desktop-test-jar-with-dependencies.jar"
        resource = forge / "res" / "ai.properties"
        module = self.root / "mtgsim" / "engine.py"
        module.parent.mkdir()
        database = self.root / "cards.sqlite3"
        cache = self.root / "cards.json"
        bundled = self.root / "builtin.json"
        for p in (jar, resource, module, database, cache, bundled):
            p.write_text("v1")
        with patch.object(provenance, "ROOT", self.root), \
             patch.object(provenance.carddb, "ALL_CARDS", database), \
             patch.object(provenance.carddb, "CACHE", cache), \
             patch.object(provenance.carddb, "BUILTIN", bundled), \
             patch.object(provenance.subprocess, "run", return_value=SimpleNamespace(stdout="", stderr="Java test")):
            original = provenance.runtime_identity(True, str(forge))
            for p in (jar, resource, module, database, cache, bundled):
                with self.subTest(changed=p.name):
                    p.write_text("v2")
                    self.assertNotEqual(original, provenance.runtime_identity(True, str(forge)))
                    p.write_text("v1")
            with patch.object(provenance, "JAVA_ARGS", ["-Xmx1024m"]):
                self.assertNotEqual(original, provenance.runtime_identity(True, str(forge)))
