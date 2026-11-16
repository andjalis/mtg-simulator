"""scripts/kind_check.py: every effect kind a parsed card produces has a handler."""
import dataclasses
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import kind_check  # noqa: E402

from mtgsim.cards import Effect  # noqa: E402
from tests.test_templates import card  # noqa: E402


class KindCheck(unittest.TestCase):
    def test_collects_nested_kinds(self):
        c = card("Test", "{1}", "Creature — Bear", "When ~ enters, draw a card.\n{T}: ~ deals 1 damage to any target.",
                 2, 2)
        self.assertLessEqual({"draw", "damage"}, kind_check.kinds_of(c))
        group = Effect("cx_group", data={"effects": [Effect("pump", 1, 1)]})
        self.assertLessEqual({"cx_group", "pump"}, kind_check.kinds_of(dataclasses.replace(c, spell_effects=[group])))

    def test_flags_a_kind_without_a_handler(self):
        c = dataclasses.replace(card("Test", "{1}", "Instant", "Draw a card."), spell_effects=[Effect("no_such_kind")])
        self.assertEqual(kind_check.kinds_of(c) - kind_check.handled(), {"no_such_kind"})

    def test_every_kind_this_parser_names_for_common_cards_is_handled(self):
        for text in ("Target creature gets +2/+2 until end of turn.", "Destroy target creature.",
                     "Create a 1/1 white Soldier creature token."):
            c = card("Test", "{1}", "Instant", text)
            self.assertEqual(kind_check.kinds_of(c) - kind_check.handled(), set(), text)


if __name__ == "__main__":
    unittest.main()
