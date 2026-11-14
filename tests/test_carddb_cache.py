"""CardDB lookup order (#392): the per-user Scryfall cache must not shadow the offline database. Its entries keep
fewer fields (older ones lack colors and loyalty) and it is shared by every checkout, so a card's parse would
otherwise depend on which runs happened to fetch it, and on the order cards were looked up."""
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mtgsim import carddb

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
# Cards whose parse differed between two full-database runs, plus a planeswalker that lost its loyalty.
NAMES = ["Leovold's Operative", "Leovold, Emissary of Trest", "Leshrac's Sigil", "Lesser Werewolf",
         "Lethal Exploit", "Karn Liberated"]
OLD_KEEP = ("name", "mana_cost", "cmc", "type_line", "oracle_text", "power", "toughness", "card_faces")


def canon(obj, depth=0):
    """A stable text form of a parsed card (CardDef's repr is only its name)."""
    if depth > 12:
        return "..."
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return type(obj).__name__ + "(" + ",".join(
            f.name + "=" + canon(getattr(obj, f.name), depth + 1) for f in dataclasses.fields(obj)) + ")"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(canon(x, depth + 1) for x in obj) + "]"
    if isinstance(obj, (set, frozenset)):
        return "{" + ",".join(sorted(canon(x, depth + 1) for x in obj)) + "}"
    if isinstance(obj, dict):
        return "{" + ",".join(f"{k!r}:{canon(v, depth + 1)}" for k, v in sorted(obj.items(), key=lambda kv: repr(kv[0]))) + "}"
    return repr(obj)


@unittest.skipUnless(DB_FILE.exists(), "needs the card database")
class UserCacheDoesNotShadowTheDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.empty = Path(self.tmp.name) / "empty.json"
        self.stale = Path(self.tmp.name) / "stale.json"
        with mock.patch.object(carddb, "CACHE", self.empty):
            db = carddb.CardDB(offline=True)
            entries = [{k: v for k, v in db.lookup(n).items() if k in OLD_KEEP} for n in NAMES]
        entries.append({"name": "Zzz Cached Only", "mana_cost": "{1}{G}", "cmc": 2, "type_line": "Creature — Elf",
                        "oracle_text": "", "power": "2", "toughness": "2", "colors": ["G"]})
        self.stale.write_text(json.dumps(entries))

    def parse(self, cache, names):
        with mock.patch.object(carddb, "CACHE", cache):
            db = carddb.CardDB(offline=True)
            return {n: canon(db.get(n)) for n in names}

    def test_a_stale_cache_entry_parses_like_the_database(self):
        self.assertEqual(self.parse(self.stale, NAMES), self.parse(self.empty, NAMES))
        with mock.patch.object(carddb, "CACHE", self.stale):
            db = carddb.CardDB(offline=True)
            self.assertEqual(db.get("Karn Liberated").loyalty, 6)
            self.assertEqual(db.get("Leovold's Operative").color_override, frozenset("G"))

    def test_lookup_order_does_not_change_a_parse(self):
        forward = self.parse(self.stale, NAMES)
        backward = self.parse(self.stale, list(reversed(NAMES)))
        self.assertEqual(forward, backward)

    def test_cards_missing_from_the_database_still_come_from_the_cache(self):
        with mock.patch.object(carddb, "CACHE", self.stale):
            db = carddb.CardDB(offline=True)
            card = db.get("Zzz Cached Only")
        self.assertEqual((card.name, card.power, card.colors), ("Zzz Cached Only", 2, frozenset("G")))

    def test_saved_cache_entries_keep_the_parse_inputs(self):
        out = Path(self.tmp.name) / "saved.json"
        with mock.patch.object(carddb, "CACHE", out):
            carddb.CardDB._save_cache([{"name": "X", "colors": ["U"], "loyalty": "4", "defense": "5",
                                        "oracle_text": "", "type_line": "Planeswalker", "junk": 1}])
        saved = json.loads(out.read_text())[0]
        self.assertEqual((saved["colors"], saved["loyalty"], saved["defense"]), (["U"], "4", "5"))
        self.assertNotIn("junk", saved)


if __name__ == "__main__":
    unittest.main()
