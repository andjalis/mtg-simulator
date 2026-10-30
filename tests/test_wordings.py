"""The wording data files: every entry loads, matches its example, and is the template that takes it."""
import re
import unittest

from mtgsim import cards
from mtgsim import wordings
from mtgsim.cards.model import NO_MATCH, Effect
from mtgsim.engine.kinds import HANDLERS

NO_HANDLER = {"revolt"}     # Fatal Push's rider: a marker; the destroy before it checks revolt in its target filter


def _taker(sentence):
    """The template the parser uses for a sentence: the first one that matches and doesn't pass."""
    for pat, build in cards._EFFECT_PATTERNS:
        m = re.fullmatch(pat, sentence, flags=re.IGNORECASE)
        if m and build(m) is not NO_MATCH:
            return build


class WordingFiles(unittest.TestCase):
    def entries(self):
        for name in wordings.FILES:
            for i, entry in enumerate(wordings.load(name)):
                yield f"{name}.json #{i + 1} {entry.get('match')!r}", entry

    def test_entries_load_and_match_their_examples(self):
        for where, entry in self.entries():
            with self.subTest(where):
                build = wordings.builder(entry)
                self.assertTrue(entry.get("example") and entry.get("cards"), "needs an example and cards")
                m = re.fullmatch(entry["match"], entry["example"], flags=re.IGNORECASE)
                self.assertIsNotNone(m, "the example doesn't match")
                out = build(m)
                for eff in out if isinstance(out, list) else [out]:
                    self.assertIsInstance(eff, Effect)
                    self.assertIn(eff.kind, HANDLERS.keys() | NO_HANDLER, "no engine handler for this effect kind")

    def test_each_entry_takes_its_example(self):
        for where, entry in self.entries():
            with self.subTest(where):
                taker = _taker(entry["example"])
                self.assertEqual(getattr(taker, "wording", None), entry, "an earlier template takes the example")

    def test_values(self):
        m = re.fullmatch(r"(\w+) and (\w+)( tapped)?( again)?", "Two and It tapped")
        self.assertEqual([wordings._value(v, m) for v in ("$1", "$1:num", "$2:lower", "$3:bool", "$4:bool", "$4")],
                         ["Two", 2, "it", True, False, None])
        self.assertEqual(wordings._value({"$map": "$2:lower", "values": {"it": "prev"}}, m), "prev")
        self.assertEqual(wordings._value({"n": "$1:num", "x": ["$2", 3]}, m), {"n": 2, "x": ["It", 3]})

    def test_bad_entries_are_refused(self):
        for bad in ({"match": "x", "effect": "draw", "amont": 1},
                    {"match": "x", "effect": "draw", "amount": "$1:float"},
                    {"match": "x", "effect": "draw", "effects": []},
                    {"match": "(x", "effect": "draw"}):
            with self.subTest(bad), self.assertRaises((ValueError, re.error)):
                wordings.builder(bad)

    def test_parser_uses_them(self):
        effects, unmatched = cards._parse_effects("~ deals 3 damage to any target.")
        self.assertEqual((effects[0].kind, effects[0].amount, effects[0].target, unmatched), ("damage", 3, "any", []))


if __name__ == "__main__":
    unittest.main()
