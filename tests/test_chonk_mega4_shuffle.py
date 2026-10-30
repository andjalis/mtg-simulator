"""mega-batch4 (5): shuffle-on-dies and the hand-to-library rider.

"When this creature dies, shuffle it into its owner's library." (Angel of Fury, Cavalier
of Gales) and the Lorwyn-incarnation wording ("When ~ is put into a graveyard from
anywhere, ...", approximated as a dies trigger) parse into a ``shuffle_away`` effect aimed
at the source; the kind handler takes the card out of its owner's graveyard — it has
already left the battlefield when the trigger resolves — and shuffles it into the library.

The same family covers the Brainstorm rider: "put two cards from your hand on top of your
library in any order" (also the bottom variant) is a ``hand_to_library`` kind.
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, Permanent, StackItem
from tests.test_batch1 import Batch1
from tests.test_templates import ISLAND, card

DRAGON = card("Test Alabaster", "{4}{W}{W}", "Creature — Dragon",
              "Flying\nWhen this creature dies, shuffle it into its owner's library.", 4, 4)
MAYBE = card("Test Angel of Fury", "{4}{W}{W}", "Creature — Angel",
              "Flying\nWhen this creature dies, you may shuffle it into its owner's library.", 3, 5)
CAVALIER = card("Test Cavalier", "{2}{U}{U}{U}", "Creature — Elemental Knight",
                "Flying\nWhen Test Cavalier enters, draw three cards, then put two cards from "
                "your hand on top of your library in any order.\nWhen Test Cavalier dies, shuffle "
                "it into its owner's library, then scry 2.", 5, 5)
INCARNATION = card("Test Dread", "{3}{B}{B}{B}", "Creature — Elemental Incarnation",
                   "Fear\nWhen Test Dread is put into a graveyard from anywhere, shuffle it into "
                   "its owner's library.", 6, 6)


class ShuffleOnDiesParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_plain_dies_shuffle(self):
        (shuf,) = self.parse("shuffle it into its owner's library")
        self.assertEqual((shuf.kind, shuf.target), ("shuffle_away", "self"))

    def test_may_dies_shuffle_gates_with_pay_gate(self):
        effects = self.parse("you may shuffle it into its owner's library")
        self.assertEqual([e.kind for e in effects], ["pay_gate", "shuffle_away"])

    def test_dies_shuffle_then_scry_compound(self):
        effects = self.parse("shuffle it into its owner's library, then scry 2")
        self.assertEqual([e.kind for e in effects], ["shuffle_away", "scry"])

    def test_hand_to_library_top_and_bottom(self):
        (top,) = self.parse("put two cards from your hand on top of your library in any order")
        (bottom,) = self.parse("put a card from your hand on the bottom of your library")
        self.assertEqual((top.kind, top.amount, top.data["bottom"]), ("hand_to_library", 2, False))
        self.assertEqual((bottom.kind, bottom.amount, bottom.data["bottom"]),
                         ("hand_to_library", 1, True))

    def test_templates(self):
        for c in (DRAGON, MAYBE, CAVALIER, INCARNATION):
            self.assertEqual(c.unsupported, [], c.name)


class ShuffleOnDiesBehavior(Batch1):
    def destroy_and_resolve(self, perm):
        self.g.destroy(perm)
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.settle()

    def test_dying_creature_shuffles_out_of_the_graveyard(self):
        perm = self.g.enter_battlefield(self.a, DRAGON)
        self.destroy_and_resolve(perm)
        self.assertNotIn(perm, self.a.battlefield)
        self.assertNotIn(perm.front, self.a.graveyard)
        self.assertIn(perm.front, self.a.library)

    def test_from_anywhere_wording_leaves_no_graveyard_copy(self):
        perm = self.g.enter_battlefield(self.a, INCARNATION)
        self.destroy_and_resolve(perm)
        self.assertNotIn(perm.front, self.a.graveyard)
        self.assertIn(perm.front, self.a.library)

    def test_token_dies_shuffle_is_a_noop(self):
        import dataclasses
        token = self.g.enter_battlefield(self.a, dataclasses.replace(DRAGON, is_token=True))
        n_lib = len(self.a.library)
        self.destroy_and_resolve(token)
        self.assertEqual(len(self.a.library), n_lib)
        self.assertEqual(self.a.graveyard, [])

    def test_battlefield_shuffle_away_still_works(self):
        from mtgsim.cards import Effect
        victim = self.g.enter_battlefield(self.b, DRAGON)
        mine = self.g.enter_battlefield(self.a, CAVALIER)
        item = StackItem(self.a, [Effect("shuffle_away", target="creature")], [victim], source=mine)
        self.g.resolve(self.a, item.effects[0], victim, item)
        self.g.settle()
        self.assertNotIn(victim, self.b.battlefield)
        self.assertIn(victim.front, self.b.library)
        self.assertNotIn(mine, self.a.battlefield)
        self.assertIn(mine.front, self.a.library)

    def test_hand_to_library_top_moves_cards_out_of_the_hand(self):
        one = card("Test One", "{1}", "Creature — One", "", 1, 1)
        two = card("Test Two", "{2}", "Creature — Two", "", 2, 2)
        three = card("Test Three", "{3}", "Creature — Three", "", 3, 3)
        self.a.hand = [one, two, three]
        effects, ignored = _parse_effects(
            "put two cards from your hand on top of your library in any order")
        self.assertFalse(ignored, ignored)
        item = StackItem(self.a, effects, [None])
        self.g.resolve(self.a, effects[0], None, item)
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual({c.name for c in self.a.library[-2:]},
                         {one.name, two.name, three.name} - {self.a.hand[0].name})

    def test_draw_then_hand_to_library_compound(self):
        n_lib = len(self.a.library)
        self.a.hand = []
        effects, ignored = _parse_effects(
            "Draw three cards, then put two cards from your hand on top of your library in any order")
        self.assertFalse(ignored, ignored)
        item = StackItem(self.a, effects, [None, None])
        for eff, tgt in zip(effects, item.targets):
            self.g.resolve(self.a, eff, tgt, item)
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(len(self.a.library), n_lib - 1)

    def test_hand_to_library_bottom(self):
        self.a.hand = []
        effects, ignored = _parse_effects(
            "Draw three cards, then put a card from your hand on the bottom of your library")
        self.assertFalse(ignored, ignored)
        item = StackItem(self.a, effects, [None, None])
        for eff, tgt in zip(effects, item.targets):
            self.g.resolve(self.a, eff, tgt, item)
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(len(self.a.library), 20 - 3 + 1)

    def test_hand_to_library_with_empty_hand(self):
        self.a.hand = []
        effects, ignored = _parse_effects("put two cards from your hand on top of your library")
        self.assertFalse(ignored, ignored)
        item = StackItem(self.a, effects, [None])
        self.g.resolve(self.a, effects[0], None, item)
        self.assertEqual(self.a.hand, [])


class ShuffleOnDiesDatabase(unittest.TestCase):
    """The promoted cards parse fully (or leave only unrelated lines ignored)."""

    def test_cards(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        full = ("Angel of Fury", "Alabaster Dragon", "Cavalier of Gales", "Brainstorm",
                "Amass the Components")
        for name in full:
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))
        for name in ("Dread", "Worldspine Wurm", "Aquatic Subtlety", "Hidetsugu and Kairi"):
            row = card_coverage(db.get(name))
            self.assertFalse([l for l in row.ignored if "shuffle" in l.lower()
                              or "from your hand on" in l.lower()], (name, row.ignored))


if __name__ == "__main__":
    unittest.main()
