"""Bulk-format compatibility and safe replacement of an existing database."""
import gzip
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from mtgsim import build_carddb as builder


CARDS = [
    {"name": "Lim-Dûl", "layout": "normal", "oracle_text": "Draw a card.", "unused": 1},
    {"name": "Front // Back", "layout": "transform", "card_faces": [
        {"name": "Front", "oracle_text": "Flying", "unused": 1}, {"name": "Back"}]},
    {"name": "Token", "layout": "token"},
]


class TestScryfallBuild(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.out = self.folder / "cards.sqlite3"
        builder.write_db([{"name": "Original"}], self.out, "original")
        self.original = self.out.read_bytes()

    def fixture(self, data):
        path = self.folder / "bulk.data"  # format detection must not depend on the suffix
        path.write_bytes(data)
        return path

    def assert_preserved(self):
        self.assertEqual(self.out.read_bytes(), self.original)
        self.assertEqual(list(self.folder.glob("*.tmp*")), [])

    def test_formats(self):
        for lines in (False, True):
            for compressed in (False, True):
                with self.subTest(lines=lines, compressed=compressed):
                    text = ("\n" + "\n\n".join(json.dumps(c, ensure_ascii=False) for c in CARDS)
                            if lines else json.dumps(CARDS, indent=2, ensure_ascii=False))
                    data = text.encode("utf-8")
                    path = self.fixture(gzip.compress(data) if compressed else data)
                    cards = list(builder.scryfall_cards(path))
                    self.assertEqual(len(cards), 2)
                    self.assertEqual(cards[0]["name"], "Lim-Dûl")
                    self.assertNotIn("unused", cards[0])
                    self.assertNotIn("unused", cards[1]["card_faces"][0])
                    self.assertEqual(builder.write_db(iter(cards), self.out, "test"), 2)
                    with closing(sqlite3.connect(self.out)) as con:
                        self.assertEqual(con.execute("SELECT key FROM names WHERE alias='back'").fetchone(),
                                         ("front // back",))

    def test_download_formats(self):
        for field, data in (("jsonl_download_uri", gzip.compress(b'{"name":"Downloaded"}\n')),
                            ("download_uri", b'[{"name":"Downloaded"}]')):
            with self.subTest(field=field):
                uri = "https://data.scryfall.io/dynamic-bulk-file"
                metadata = {field: uri}
                with patch.object(builder.urllib.request, "urlopen", side_effect=[
                        io.BytesIO(json.dumps(metadata).encode()), io.BytesIO(data)]) as opening:
                    path = builder.download_scryfall(self.folder)
                self.assertEqual(list(builder.scryfall_cards(path)), [{"name": "Downloaded"}])
                self.assertEqual(opening.call_args_list[0].args[0].full_url,
                                 "https://api.scryfall.com/bulk-data/oracle_cards")
                self.assertEqual(opening.call_args_list[1].args[0].full_url, uri)
                for call in opening.call_args_list:
                    self.assertNotIn("context", call.kwargs)  # use urllib's verified TLS default
                    self.assertGreater(call.kwargs["timeout"], 0)

    def test_malformed_metadata(self):
        for metadata in ([], None, {}, {"download_uri": 42}, {"jsonl_download_uri": "http://bad/file"},
                         {"download_uri": "file:///etc/passwd"}, {"download_uri": "https:///file"}):
            with self.subTest(metadata=metadata):
                with patch.object(builder.urllib.request, "urlopen", return_value=io.BytesIO(
                        json.dumps(metadata).encode())) as opening:
                    with self.assertRaisesRegex(ValueError, "Scryfall bulk metadata"):
                        builder.download_scryfall(self.folder)
                    self.assertEqual(opening.call_count, 1)
                self.assert_preserved()

    def test_invalid_metadata_json(self):
        with patch.object(builder.urllib.request, "urlopen", return_value=io.BytesIO(b'not json')):
            with self.assertRaises(ValueError):
                builder.download_scryfall(self.folder)
        self.assert_preserved()

    def test_partial_download_removed(self):
        class BrokenResponse(io.BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise OSError("connection interrupted")
                return super().read(4)
        with patch.object(builder.urllib.request, "urlopen", side_effect=[
                io.BytesIO(b'{"download_uri":"https://example.test/bulk"}'),
                BrokenResponse(b'partial data')]):
            with self.assertRaisesRegex(OSError, "connection interrupted"):
                builder.download_scryfall(self.folder)
        self.assertFalse((self.folder / "oracle-cards.bulk").exists())
        self.assert_preserved()

    def test_bad_input_preserves_database(self):
        for data in (b'', b'[]', b'[{"name":"Valid"},', b'{"name":"Valid"}\n{broken}\n',
                     b'null\n', b'{"error":"not a card"}\n', b'[{"name":""}]',
                     gzip.compress(b'{"name":"Valid"}\n')[:-5], b'\xff'):
            with self.subTest(data=data):
                path = self.fixture(data)
                with self.assertRaises((ValueError, EOFError, OSError)):
                    builder.write_db(builder.scryfall_cards(path), self.out, "bad")
                self.assert_preserved()

    def test_local_file_cli(self):
        for data in (b'[{"name":"Local"}]', gzip.compress(b'{"name":"Local"}\n')):
            with self.subTest(data=data):
                with patch('sys.stdout', new_callable=io.StringIO):
                    builder.main(["--scryfall", str(self.fixture(data)), "-o", str(self.out)])
                with closing(sqlite3.connect(self.out)) as con:
                    self.assertEqual(con.execute("SELECT name FROM cards").fetchall(), [("Local",)])

    def test_explicit_scryfall_failure_preserves_database(self):
        path = self.fixture(b'{"name":"Valid"}\n{broken}\n')
        with patch.object(builder, "download_scryfall", return_value=path), \
                patch.object(builder, "clone_forge") as clone, \
                patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaisesRegex(SystemExit, "Scryfall build failed:.*line 2"):
                builder.main(["--source", "scryfall", "-o", str(self.out)])
            clone.assert_not_called()
        self.assert_preserved()

    def test_auto_fallback_after_download_or_parse_failure(self):
        for failure in (OSError("download failed"), None):
            with self.subTest(failure=failure):
                path = self.fixture(b'{"name":"Valid"}\n{broken}\n')
                with patch.object(builder, "download_scryfall", side_effect=failure, return_value=path), \
                        patch.object(builder, "clone_forge", return_value=self.folder), \
                        patch.object(builder, "forge_cards", return_value=iter([{"name": "Forge"}])), \
                        patch.object(builder.subprocess, "run") as run, \
                        patch('sys.stderr', new_callable=io.StringIO) as stderr, \
                        patch('sys.stdout', new_callable=io.StringIO):
                    run.return_value.stdout = "testrev\n"
                    builder.main(["-o", str(self.out)])
                    self.assertIn("using Forge's card scripts", stderr.getvalue())
                with closing(sqlite3.connect(self.out)) as con:
                    self.assertEqual(con.execute("SELECT name FROM cards").fetchall(), [("Forge",)])

    def test_failed_fallback_preserves_database(self):
        with patch.object(builder, "download_scryfall", side_effect=OSError("download failed")), \
                patch.object(builder, "clone_forge", side_effect=OSError("Forge failed")), \
                patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaisesRegex(OSError, "Forge failed"):
                builder.main(["-o", str(self.out)])
        self.assert_preserved()
