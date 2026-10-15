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


if __name__ == "__main__":
    unittest.main()
