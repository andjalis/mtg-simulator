"""mtgsim.translated: the per-card translation format, its loader hook and its coverage label (pilot)."""
import json
import os
import unittest
from unittest import mock

from mtgsim import translated as T
from mtgsim.cards import Effect, Trigger
from mtgsim.coverage import TRANSLATED, card_coverage
from tests.test_templates import card
from tests.translated.harness import DB_FILE


class Format(unittest.TestCase):
    def test_roundtrip(self):
        c = card("Test Round", "{1}{R}", "Creature — Goblin",
                 "When this creature enters, it deals 2 damage to any target.\n{T}: Add {R}.", 2, 2)
        again = T.decode(json.loads(json.dumps(T.encode(c))))
        self.assertEqual(T.encode(again), T.encode(c))

    def test_check_rejects_unknown_kind_and_field(self):
        data = {"patches": [{"set": {"no_such_field": 1},
                             "add": {"triggers": T.encode([Trigger("etb", [Effect("no_such_kind")])])}}]}
        problems = T.check(data)
        self.assertTrue(any("no_such_field" in p for p in problems))
        self.assertTrue(any("no_such_kind" in p for p in problems))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Loader(unittest.TestCase):
    def db(self):
        from mtgsim.carddb import CardDB
        return CardDB(offline=True)

    def test_translated_card_is_labelled(self):
        c = self.db().get("Swarming Goblins")
        self.assertEqual(card_coverage(c).status, TRANSLATED)
        self.assertEqual(c.advanced_rules["translated"], "swarming_goblins.json")

    def test_opt_out(self):
        with mock.patch.dict(os.environ, {"MTGSIM_NO_TRANSLATIONS": "1"}):
            self.assertEqual(card_coverage(self.db().get("Swarming Goblins")).status, "partial")

    def test_stale_oracle_is_not_applied(self):
        index = T._index()
        path, data = index["Swarming Goblins"]
        with mock.patch.dict(index, {"Swarming Goblins": (path, dict(data, oracle_sha1="000000000000"))}):
            self.assertEqual(card_coverage(self.db().get("Swarming Goblins")).status, "partial")

    def test_stale_lines_are_not_applied(self):
        index = T._index()
        path, data = index["Swarming Goblins"]
        with mock.patch.dict(index, {"Swarming Goblins": (path, dict(data, covers=["something else"]))}):
            self.assertEqual(card_coverage(self.db().get("Swarming Goblins")).status, "partial")

    def test_every_file_applies(self):
        for name, (path, data) in T._index().items():
            self.assertEqual(T.check(data), [], path.name)
            self.assertEqual(card_coverage(self.db().get(name)).status, TRANSLATED, path.name)


if __name__ == "__main__":
    unittest.main()
