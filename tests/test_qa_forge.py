"""Regression checks for Forge release card archives."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from mtgsim.forge import ForgeError, forge_card_names, run_forge_match


class ForgeArchiveQATests(unittest.TestCase):
    def test_reads_archive_inside_cardsfolder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cards = root / "res" / "cardsfolder"
            cards.mkdir(parents=True)
            with zipfile.ZipFile(cards / "cardsfolder.zip", "w") as archive:
                archive.writestr("m/mountain.txt", "Name:Mountain\n")
            self.assertEqual(forge_card_names(root), {"mountain"})

    def test_combines_loose_scripts_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cards = root / "res" / "cardsfolder"
            cards.mkdir(parents=True)
            (cards / "forest.txt").write_text("Name:Forest\n", encoding="utf-8")
            with zipfile.ZipFile(cards / "cardsfolder.zip", "w") as archive:
                archive.writestr("m/mountain.txt", "Name:Mountain\n")
            self.assertEqual(forge_card_names(root), {"forest", "mountain"})

    def test_archive_unknown_cards_are_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cards = root / "res" / "cardsfolder"
            cards.mkdir(parents=True)
            (root / "forge-gui-desktop-2.0.0-jar-with-dependencies.jar").touch()
            with zipfile.ZipFile(cards / "cardsfolder.zip", "w") as archive:
                archive.writestr("m/mountain.txt", "Name:Mountain\n")
            with self.assertRaisesRegex(ForgeError, "Lightning Blot"):
                run_forge_match("a", {"Lightning Blot": 4}, "b", {"Mountain": 60},
                                games=1, forge_dir=str(root), java="nonexistent-java")
