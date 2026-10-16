import tempfile
import unittest
from pathlib import Path

from mtgsim import standard_coverage as sc
from mtgsim.carddb import ALL_CARDS, CardDB


class FormatFilesTest(unittest.TestCase):
    def test_parse_format(self):
        fmt = sc.parse_format("[format]\nName:Standard\nSets:WOE, LCI ,MKM\nBanned:A; B C\n")
        self.assertEqual(fmt, {"name": "Standard", "sets": ["WOE", "LCI", "MKM"], "banned": ["A", "B C"]})

    def test_parse_edition_reads_only_the_cards_section(self):
        text = ("[metadata]\nCode=WOE\nName=Wilds of Eldraine\n\n[cards]\n1 R Archon of the Wild Rose @Chris Rahn\n"
                "2 C Archon's Glory @A\n262 L Plains @B\n\n[showcase]\n300 R Archon of the Wild Rose @C\n"
                "[tokens]\nw_1_1_human\n")
        self.assertEqual(sc.parse_edition(text),
                         ("WOE", "Wilds of Eldraine", ["Archon of the Wild Rose", "Archon's Glory", "Plains"]))

    def test_saved_standard_list(self):
        fmt, names = sc.standard_cards(sc.SAVED)
        self.assertEqual(len(fmt["sets"]), 20)
        self.assertEqual(fmt["sets"][0], "WOE")
        self.assertEqual(len(names), 4902)
        self.assertNotIn("Plains", names)

    def test_save_snapshot_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sc.save_snapshot(sc.SAVED, Path(tmp)), 20)
            self.assertEqual(sc.forge_res(Path(tmp)), Path(tmp))
            self.assertEqual(sc.standard_cards(Path(tmp)), sc.standard_cards(sc.SAVED))

    def test_forge_res_finds_install_and_checkout_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            for sub in ("res", "forge-gui/res"):
                root = Path(tmp) / sub.replace("/", "_")
                for d in ("formats", "editions"):
                    (root / sub / d).mkdir(parents=True)
                self.assertEqual(sc.forge_res(root), root / sub)
            with self.assertRaises(FileNotFoundError):
                sc.forge_res(Path(tmp) / "nothing")


class FamiliesTest(unittest.TestCase):
    def test_families(self):
        self.assertIn("tokens", sc.families("create a 1/1 white Human creature token."))
        self.assertIn("graveyard", sc.families("Return target creature card from your graveyard to the battlefield."))
        self.assertIn("activated abilities", sc.families("{T}, Sacrifice ~: Draw a card."))
        self.assertIn("sacrifice", sc.families("{T}, Sacrifice ~: Draw a card."))
        self.assertIn("set: saddle", sc.families("Saddle 2"))
        self.assertEqual(sc.families("Untap it."), [])


@unittest.skipUnless(ALL_CARDS.exists(), "card database not built")
class MeasureTest(unittest.TestCase):
    def test_measure_counts_every_card(self):
        db = CardDB(offline=True)
        names = ["Lightning Bolt", "Sheoldred, the Apocalypse", "A Killer Among Us", "No Such Card Exists"]
        rep = sc.measure(names, db, {"name": "Test", "sets": []})
        self.assertEqual(rep.total, 4)
        self.assertEqual(sum(rep.status.values()), 4)
        self.assertEqual(rep.status["full"], 2)
        self.assertEqual(rep.status["unknown"], 1)
        self.assertIn("A Killer Among Us", rep.partial)
        self.assertGreater(rep.families["tokens"], 0)
        self.assertLess(rep.sentence_share, 1)
        text = sc.format_report(rep)
        self.assertIn("Fully supported", text)
        self.assertIn("tokens", text)

    def test_cli_runs_offline_from_the_saved_lists(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(sc.main(["--top", "3"]), 0)
        self.assertIn("Standard: 4,902 distinct non-basic cards from 20 sets (WOE to FRA)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
