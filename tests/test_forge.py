"""Exercise the Forge wrapper against a fake Forge install and a fake java that prints Forge-style output."""
import os
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path

from mtgsim.forge import ForgeError, parse_results, run_forge_match, to_dck

FAKE_JAVA = textwrap.dedent("""\
    #!/usr/bin/env python3
    import sys
    args = sys.argv[1:]
    d = args.index("-d")
    deck_dir = args[args.index("-D") + 1]
    names = [open(f"{deck_dir}/{f}").read().split("Name=")[1].split()[0] for f in args[d + 1:d + 3]]
    n = int(args[args.index("-n") + 1])
    print("Simulation mode")
    for i in range(1, n + 1):
        if i % 4 == 0:
            print(f"\\nGame Result: Game {i} ended in a Draw! Took 10 ms.")
        else:
            winner = names[0] if i % 4 != 3 else names[1]
            idx = 1 if winner == names[0] else 2
            print(f"\\nGame Result: Game {i} ended in 1234 ms. Ai({idx})-{winner} has won!\\n")
    """)


class ForgeWrapperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.forge = root / "forge"
        (self.forge / "res" / "cardsfolder" / "l").mkdir(parents=True)
        (self.forge / "forge-gui-desktop-2.0.0-jar-with-dependencies.jar").write_text("")
        for card in ("Lightning Bolt", "Mountain"):
            (self.forge / "res" / "cardsfolder" / "l" / f"{card}.txt").write_text(f"Name:{card}\nManaCost:R\n")
        self.java = root / "java"
        self.java.write_text(FAKE_JAVA)
        self.java.chmod(self.java.stat().st_mode | stat.S_IEXEC)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dck_format(self):
        self.assertEqual(to_dck("Burn", {"Lightning Bolt": 4}), "[metadata]\nName=Burn\n[Main]\n4 Lightning Bolt\n")

    def test_runs_and_counts(self):
        deck = {"Lightning Bolt": 4, "Mountain": 20}
        res = run_forge_match("burn", deck, "other", deck, games=8, forge_dir=str(self.forge), java=str(self.java))
        self.assertEqual((res.games, res.wins_a, res.wins_b, res.draws), (8, 4, 2, 2))
        self.assertNotIn("on the play", res.summary())

    def test_parallel_jobs_add_up(self):
        deck = {"Lightning Bolt": 4, "Mountain": 20}
        res = run_forge_match("burn", deck, "other", deck, games=8, forge_dir=str(self.forge),
                              java=str(self.java), jobs=3)
        self.assertEqual((res.games, res.wins_a, res.wins_b, res.draws), (8, 6, 2, 0))

    def test_unknown_card(self):
        with self.assertRaises(ForgeError) as e:
            run_forge_match("a", {"Lightning Blot": 4}, "b", {"Mountain": 20}, games=1,
                            forge_dir=str(self.forge), java=str(self.java))
        self.assertIn("Lightning Blot", str(e.exception))

    def test_same_deck_name_uses_seat(self):
        res = parse_results(["Game Result: Game 1 ended in 5 ms. Ai(2)-mirror has won!"], "mirror", "mirror")
        self.assertEqual(res.wins_b, 1)

    def test_per_game_first_player_and_length_from_full_logs(self):
        def game(number, first, turns, result):
            names = ["Ai(1)-a", "Ai(2)-b"]
            lines = [f"Turn: Turn {t} ({names[(first + t - 1) % 2]})" for t in range(1, turns + 1)]
            return lines + [f"Game Outcome: Turn {(turns + 1) // 2}", f"Game Result: Game {number} {result}"]
        lines = (game(1, 0, 9, "ended in 5 ms. Ai(1)-a has won!") +
                 game(2, 1, 17, "ended in 5 ms. Ai(2)-b has won!") +
                 game(3, 1, 12, "ended in a Draw! Took 10 ms.") +
                 game(4, 0, 6, "ended in a Draw! Took 10 ms."))
        res = parse_results(lines, "a", "b")
        self.assertTrue(res.play_draw_known)
        self.assertEqual([m["first_player"] for m in res.game_metadata], [0, 1, 1, 0])
        self.assertEqual(res.turns, [9, 17, 12, 6])
        self.assertEqual((res.games_a_on_play, res.wins_a_on_play, res.draws_a_on_play), (2, 1, 1))
        self.assertEqual((res.games_a_on_draw, res.wins_a_on_draw, res.draws_a_on_draw), (2, 0, 1))

    def test_quiet_or_partial_metadata_stays_unknown(self):
        quiet = parse_results(["Game Result: Game 1 ended in 5 ms. Ai(1)-a has won!"], "a", "b")
        self.assertFalse(quiet.play_draw_known)
        self.assertEqual((quiet.game_metadata[0]["first_player"], quiet.turns), (None, []))
        self.assertEqual(quiet.games_a_on_play + quiet.games_a_on_draw, 0)
        gap = ["Turn: Turn 1 (Ai(2)-b)", "Turn: Turn 3 (Ai(2)-b)", "Game Outcome: Turn 2",
               "Game Result: Game 1 ended in 5 ms. Ai(1)-a has won!"]
        res = parse_results(gap, "a", "b")
        self.assertEqual(res.game_metadata[0]["first_player"], 1)   # turn 1 itself is unambiguous
        self.assertEqual((res.game_metadata[0]["player_turns"], res.turns), (None, []))
        no_start = ["Turn: Turn 2 (Ai(2)-b)", "Game Result: Game 1 ended in 5 ms. Ai(1)-a has won!"]
        res = parse_results(no_start, "a", "b")
        self.assertFalse(res.play_draw_known)
        self.assertIsNone(res.game_metadata[0]["first_player"])
        odd = ["Turn: Turn 1 (Human-a)", "Game Result: Game 1 ended in 5 ms. Ai(1)-a has won!"]
        self.assertIsNone(parse_results(odd, "a", "b").game_metadata[0]["first_player"])

    def test_stored_review_log_if_present(self):
        log = (Path(__file__).resolve().parents[1] / "results" / "benchmark-review" / "logs" /
               "aggro-vs-midrange" / "forge" / "c2446f1aeca5" / "worker-0.log")
        if not log.exists():
            self.skipTest("local review log not present (results/benchmark*/ is gitignored)")
        res = parse_results(log.read_text(encoding="utf-8").splitlines(), "aggro", "midrange")
        self.assertEqual((res.games, res.games_a_on_play, res.turns), (2, 2, [19, 11]))

    def test_reject_unknown_malformed_and_duplicate_results(self):
        cases = [
            ["Game Result: Game 1 ended in 5 ms. Unknown has won!"],
            ["Game Result: unexpected output"],
            ["Game Result: Game 1 ended in a Draw!"] * 2,
        ]
        for lines in cases:
            with self.subTest(lines=lines), self.assertRaises(ForgeError):
                parse_results(lines, "a", "b")

    def test_reject_nonzero_or_incomplete_even_with_results_and_preserve_raw_logs(self):
        for script, games in ((FAKE_JAVA + "sys.exit(2)\n", 2),
                              (FAKE_JAVA.replace('range(1, n + 1)', 'range(1, n)'), 2)):
            self.java.write_text(script)
            logs = Path(self.tmp.name) / "logs"
            with self.assertRaisesRegex(ForgeError, "incomplete results rejected"):
                run_forge_match("a", {"Mountain": 60}, "b", {"Mountain": 60}, games=games,
                                forge_dir=str(self.forge), java=str(self.java), log_dir=logs)
            self.assertIn("Simulation mode", (logs / "worker-0.log").read_text())

    def test_raw_log_includes_review_detail_and_isolated_settings(self):
        self.java.write_text(FAKE_JAVA + textwrap.dedent('''
            import os
            from pathlib import Path
            assert "-q" not in args
            assert "-Duser.home=" in " ".join(args)
            assert Path("forge.profile.properties").exists()
            assert Path("res").is_dir()
            assert "JAVA_TOOL_OPTIONS" not in os.environ
            print("reviewable action")
        '''))
        logs = Path(self.tmp.name) / "logs"
        from unittest.mock import patch
        with patch.dict(os.environ, {"JAVA_TOOL_OPTIONS": "invalid inherited setting"}):
            res = run_forge_match("a", {"Mountain": 60}, "b", {"Mountain": 60}, games=2,
                                  forge_dir=str(self.forge), java=str(self.java), log_dir=logs,
                                  isolated=True, jobs=2)
        self.assertEqual(res.games, 2)
        self.assertEqual(len(list(logs.glob("*.log"))), 2)
        self.assertIn("reviewable action", (logs / "worker-0.log").read_text())

    def test_wall_timeout_keeps_partial_raw_log(self):
        self.java.write_text("#!/usr/bin/env python3\nimport time\nprint('started', flush=True)\ntime.sleep(20)\n")
        logs = Path(self.tmp.name) / "logs"
        with self.assertRaisesRegex(ForgeError, "wall timeout"):
            run_forge_match("a", {"Mountain": 60}, "b", {"Mountain": 60}, games=1,
                            forge_dir=str(self.forge), java=str(self.java), log_dir=logs, worker_timeout=1)
        self.assertEqual((logs / "worker-0.log").read_text(), "started\n")


if __name__ == "__main__":
    unittest.main()
