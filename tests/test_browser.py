import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mtgsim.browser import bundle, package_zip, run_local
from mtgsim.carddb import ALL_CARDS

ROOT = Path(__file__).resolve().parent.parent


class BrowserBundleTest(unittest.TestCase):
    def test_engine_imports_without_sqlite3(self):
        # Pyodide's core has no sqlite3 module; the engine and runner must still load.
        code = "import sys; sys.modules['sqlite3'] = None; import mtgsim.browser"
        subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)

    def test_run_local_with_builtin_cards(self):
        cards = json.loads((ROOT / "mtgsim" / "data" / "builtin_cards.json").read_text())
        deck = {"Mountain": 20, "Raging Goblin": 20}
        r = run_local(cards, deck, deck, 4, seed=1)
        self.assertEqual(r["games"], 4)
        self.assertEqual(r["wins_a"] + r["wins_b"] + r["draws"], 4)
        self.assertEqual(r["games_a_on_play"], 2)

    def test_zipped_package_plays_a_game_on_its_own(self):
        # What the page's workers load: only mtgsim.zip on the path, no checkout and no sqlite3.
        code = ("import json, sys; sys.modules['sqlite3'] = None; sys.path.insert(0, sys.argv[1]); "
                "import mtgsim.browser as mb; assert mb.__file__.startswith(sys.argv[1]), mb.__file__; "
                "cards = json.load(sys.stdin); deck = {'Mountain': 20, 'Raging Goblin': 20}; "
                "print(json.dumps(mb.run_local(cards, deck, deck, 1, seed=1)))")
        with tempfile.TemporaryDirectory() as tmp:
            zipped = Path(tmp) / "mtgsim.zip"
            zipped.write_bytes(package_zip())
            out = subprocess.run([sys.executable, "-I", "-c", code, str(zipped)], cwd=tmp, check=True,
                                 capture_output=True, text=True,
                                 input=(ROOT / "mtgsim" / "data" / "builtin_cards.json").read_text())
        self.assertEqual(json.loads(out.stdout)["games"], 1)

    @unittest.skipUnless(ALL_CARDS.exists(), "card database not built")
    def test_bundle_holds_only_the_decks_cards(self):
        deck = ROOT / "decks" / "mono_red_aggro.txt"
        with tempfile.TemporaryDirectory() as out:
            info = bundle([deck], Path(out))
            cards = json.loads((Path(out) / "cards.json").read_text())
            decks = json.loads((Path(out) / "decks.json").read_text())
        self.assertEqual(list(decks), ["mono_red_aggro"])
        self.assertEqual(info["cards"], len(decks["mono_red_aggro"]))
        self.assertEqual(len(cards), info["cards"])
        r = run_local(cards, decks["mono_red_aggro"], decks["mono_red_aggro"], 2, seed=1)
        self.assertEqual(r["games"], 2)


if __name__ == "__main__":
    unittest.main()
