import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mtgsim.__main__ import main
from mtgsim.runner import MatchResult


class CliTests(unittest.TestCase):
    def test_equal_filename_stems_preserve_each_deck(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for folder, card in (("a", "Mountain"), ("b", "Forest"), ("c", "Island")):
                path = Path(tmp) / folder / "deck.txt"
                path.parent.mkdir()
                path.write_text(f"60 {card}\n", encoding="utf-8")
                paths.append(str(path))
            calls = []
            def play(a, deck_a, b, deck_b, **kwargs):
                calls.append((a, deck_a[0].name, b, deck_b[0].name))
                return MatchResult(a, b), []
            for flags, expected in ((paths[:2], [
                    ("deck", "Mountain", "deck (2)", "Forest")]),
                    ([paths[0], "--gauntlet", *paths[1:]], [
                    ("deck", "Mountain", "deck (2)", "Forest"),
                    ("deck", "Mountain", "deck (3)", "Island")])):
                calls.clear()
                with patch("mtgsim.__main__.run_match", side_effect=play), redirect_stdout(io.StringIO()):
                    main([*flags, "--offline", "-n", "1"])
                self.assertEqual(calls, expected)
