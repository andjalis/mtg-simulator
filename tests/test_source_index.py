"""#698: the battlefield source index behind Permanent.has (residual_templates.field_sources / has_source_key) must
see every keyword source a full scan would, also after the board changes."""
import unittest

from mtgsim.residual_templates import field_sources, has_source_key
from tests.test_cx_grammar import Base
from tests.test_templates import BEAR, card

ANTHEM = card("Test Wings", "{2}{U}", "Enchantment", "Creatures you control have flying.")
GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
CHIEF = card("Test Chief", "{1}{R}", "Creature — Goblin", "Other Goblins you control have haste.", 2, 2)


class SourceIndex(Base):
    def test_grant_entering_after_the_index_was_built_is_seen(self):
        bear = self.perm(BEAR, self.a)
        self.assertFalse(bear.has("flying"))                    # builds and caches the index
        self.assertEqual(field_sources(self.game, "static_keyword_grants"), [])
        wings = self.perm(ANTHEM, self.a)
        self.assertEqual(field_sources(self.game, "static_keyword_grants"), [wings])
        self.assertTrue(bear.has("flying"))
        self.assertFalse(self.perm(BEAR, self.b).has("flying"))  # the opponent's creature is not granted it

    def test_grant_leaving_is_dropped(self):
        bear = self.perm(BEAR, self.a)
        wings = self.perm(ANTHEM, self.a)
        self.assertTrue(bear.has("flying"))
        self.a.battlefield.remove(wings)
        self.assertFalse(bear.has("flying"))
        self.assertEqual(field_sources(self.game, "static_keyword_grants"), [])

    def test_only_sources_are_indexed_and_suppression_still_applies(self):
        goblin = self.perm(GOBLIN, self.a)
        bear = self.perm(BEAR, self.a)
        chief = self.perm(CHIEF, self.a)
        self.assertEqual(field_sources(self.game, "static_keyword_grants"), [chief])
        self.assertTrue(goblin.has("haste"))
        self.assertFalse(chief.has("haste"))                    # "other"
        chief.silenced_by = bear                                # loses its abilities while bear stays
        self.assertFalse(goblin.has("haste"))

    def test_rule_keys(self):
        self.perm(BEAR, self.a)
        self.assertFalse(has_source_key(self.game, "cx_chars@group"))
        self.assertFalse(has_source_key(self.game, "@static_keyword_grants"))
        self.perm(ANTHEM, self.b)
        self.assertTrue(has_source_key(self.game, "@static_keyword_grants"))


if __name__ == "__main__":
    unittest.main()
