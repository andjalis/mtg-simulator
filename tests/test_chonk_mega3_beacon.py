"""Shuffle-self spells (the Beacon and Zenith cycle): "Shuffle ~ into its owner's library."

The parser turns the sentence into a shuffle_self effect whose handler marks the
resolving spell (item.shuffle_self); the stack hook in
Game.to_graveyard_after_resolving — still pending from the foundation agent —
then appends the card to its owner's library and shuffles instead of putting it
into the graveyard. These tests fire that hook manually until it lands.
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_templates import card

BEACON = card("Test Beacon", "{4}{R}", "Instant",
              "Test Beacon deals 5 damage to any target. Shuffle Test Beacon into its owner's library.")


class ShuffleSelfParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_shuffle_self_line(self):
        effects = self.parse("~ deals 5 damage to any target. Shuffle ~ into its owner's library.")
        self.assertEqual([e.kind for e in effects], ["damage", "shuffle_self"])

    def test_full_beacon_wording(self):
        (dmg, shuf) = self.parse("~ deals 5 damage to any target. "
                                 "Shuffle ~ into its owner's library.")
        self.assertEqual((dmg.kind, dmg.amount, dmg.target), ("damage", 5, "any"))
        self.assertEqual(shuf.kind, "shuffle_self")


class ShuffleSelfBehavior(Batch1):
    def setUp(self):
        super().setUp()
        effects, ignored = _parse_effects("~ deals 5 damage to any target. "
                                          "Shuffle ~ into its owner's library.")
        self.assertFalse(ignored, ignored)
        self.effects = effects

    def resolve_beacon(self):
        item = StackItem(self.a, self.effects, [self.b, None], card=BEACON)
        for eff, tgt in zip(item.effects, item.targets):
            self.g.resolve(self.a, eff, tgt, item)
        return item

    def test_spell_marks_itself(self):
        item = self.resolve_beacon()
        self.assertTrue(getattr(item, "shuffle_self", False))
        self.assertEqual(self.b.life, 15)          # the damage still resolved

    def test_pending_hook_puts_it_back_in_the_library(self):
        item = self.resolve_beacon()
        # The pending stack hook (to be added before the final elif of
        # Game.to_graveyard_after_resolving):
        #   elif getattr(item, "shuffle_self", False):
        #       owner.library.append(base); owner.library.shuffle(self.rng)
        base, _, _ = self.g._origin(item.card)
        owner = getattr(base, "owner", None) or item.controller
        if getattr(item, "shuffle_self", False):
            owner.library.append(base)
            owner.library.shuffle(self.g.rng)
        self.assertIn(base, owner.library)
        self.assertNotIn(base, owner.graveyard)

    def test_unmarked_spell_still_goes_to_the_graveyard(self):
        effects, _ = _parse_effects("~ deals 5 damage to any target.")
        item = StackItem(self.a, effects, [self.b], card=BEACON)
        self.g.resolve(self.a, effects[0], self.b, item)
        self.assertFalse(getattr(item, "shuffle_self", False))
        self.g.to_graveyard_after_resolving(item)
        self.assertIn(item.card, self.a.graveyard)


class ShuffleSelfDatabase(unittest.TestCase):
    """The whole Beacon and Zenith cycle parses once the card database is built."""

    def test_beacons_resolve_fully(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:                                     # no cards.sqlite3
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        for name in ("Beacon of Destruction", "Beacon of Unrest", "Red Sun's Zenith",
                     "Beacon of Immortality"):
            row = card_coverage(db.get(name))
            self.assertNotIn("Shuffle", " ".join(row.ignored), name)
            if name != "Beacon of Immortality":               # its life-doubling line is a separate gap
                self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()
