"""mega-batch6 (1): the graveyard-cast kind.

"You may cast target <desc> card from a graveyard [without paying its mana cost]"
(Wrexial, Toshiro Umezawa, Memory Plunder, Torrential Gearhulk, the Dreadhorde
Arcanist power cap, the Chandra loyalty abilities) parses into a ``gy_cast`` effect;
the "If that spell would be put into a graveyard, exile it instead" rider parse.py
attaches as ``gy_instead``. The kind casts the best matching spell — free or for its
own cost — and, with the rider, queues a one-shot that moves the resolved spell from
its owner's graveyard on (to exile, or the bottom of the library).
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_combat_triggers import BEAR
from tests.test_templates import card

BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to target creature.", cmc=1)
EXPENSIVE = card("Test Cascade", "{3}{U}{U}", "Instant",
                 "Draw three cards. Test Cascade deals 1 damage to target creature.", cmc=5)
SORCERY = card("Test Wind", "{1}{U}", "Sorcery", "Draw a card.", cmc=2)
MOUNTAIN = card("Test Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
WREXIAL_TEXT = ("You may cast target instant or sorcery card from that player's graveyard "
                "without paying its mana cost. If that spell would be put into a graveyard, "
                "exile it instead.")
TOSHIRO_TEXT = ("You may cast target instant card from your graveyard. "
                "If that spell would be put into a graveyard, exile it instead.")
HEIST_TEXT = ("You may cast target instant or sorcery card from an opponent's graveyard "
              "without paying its mana cost. If that spell would be put into their graveyard, "
              "exile it instead.")


class GyCastParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_yours_with_exile_rider(self):
        (cast,) = self.parse(TOSHIRO_TEXT)
        self.assertEqual(cast.kind, "gy_cast")
        self.assertEqual((cast.data["gy"], cast.data["desc"], cast.data["gy_instead"]),
                         ("yours", "instant", "exile"))
        self.assertNotIn("free", cast.data)

    def test_context_graveyard_free(self):
        (cast,) = self.parse(WREXIAL_TEXT)
        self.assertEqual((cast.data["gy"], cast.data["free"], cast.data["gy_instead"]),
                         ("context", True, "exile"))

    def test_mana_value_cap(self):
        (cast,) = self.parse("You may cast target instant or sorcery card with mana value "
                             "3 or less from your graveyard without paying its mana cost.")
        self.assertEqual((cast.data["max_cmc"], cast.data["free"]), (3, True))

    def test_power_cap(self):
        (cast,) = self.parse("You may cast target instant or sorcery card with mana value "
                             "less than or equal to this creature's power from your graveyard "
                             "without paying its mana cost.")
        self.assertEqual(cast.data["max_cmc"], "power")

    def test_opponents_graveyard_without_rider(self):
        (cast,) = self.parse("You may cast target instant or sorcery card from an opponent's "
                             "graveyard without paying its mana cost.")
        self.assertEqual(cast.data["gy"], "opponents")
        self.assertNotIn("gy_instead", cast.data)

    def test_colored_descriptor_stays_ignored(self):
        effects, ignored = _parse_effects("You may cast target red instant or sorcery card "
                                          "from your graveyard.")
        self.assertFalse(effects)
        self.assertTrue(ignored)


class GyCastBehavior(Batch1):
    def lands(self, n=3):
        for _ in range(n):
            self.g.enter_battlefield(self.a, MOUNTAIN)

    def resolve_gy_cast(self, text, context=None, source=None):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        item = StackItem(self.a, effects, [None] * len(effects), source=source, context=context)
        self.g.resolve(self.a, effects[0], None, item)
        for _ in range(2):        # the cast spell resolves, then the queued rider
            self.g.flush_triggers()
            while self.g.stack:
                self.g.resolve_top()
                self.g.settle()

    def test_free_cast_from_own_graveyard_exiles_after_resolving(self):
        self.a.graveyard.append(BOLT)
        victim = self.put(BEAR, self.b)
        self.resolve_gy_cast("You may cast target instant card from your graveyard without "
                             "paying its mana cost. If that spell would be put into a "
                             "graveyard, exile it instead.")
        self.assertEqual(victim.damage, 3)
        self.assertEqual([c.name for c in self.a.exile], ["Test Bolt"])
        self.assertEqual(self.a.graveyard, [])

    def test_paid_cast_pays_the_spells_own_cost(self):
        self.lands(3)
        self.a.graveyard.append(BOLT)
        victim = self.put(BEAR, self.b)
        self.resolve_gy_cast(TOSHIRO_TEXT)
        self.assertEqual(victim.damage, 3)
        self.assertEqual([c.name for c in self.a.exile], ["Test Bolt"])
        self.assertTrue(any(m.tapped for m in self.a.battlefield if m.card.is_land))

    def test_cast_without_rider_returns_to_owners_graveyard(self):
        self.a.graveyard.append(BOLT)
        victim = self.put(BEAR, self.b)
        self.resolve_gy_cast("You may cast target instant card from your graveyard without "
                             "paying its mana cost.")
        self.assertEqual(victim.damage, 3)
        self.assertEqual([c.name for c in self.a.graveyard], ["Test Bolt"])

    def test_cast_from_opponents_graveyard_with_rider(self):
        self.b.graveyard.append(BOLT)
        victim = self.put(BEAR, self.b)
        self.resolve_gy_cast(HEIST_TEXT)
        self.assertEqual(victim.damage, 3)
        self.assertEqual([c.name for c in self.b.exile], ["Test Bolt"])
        self.assertEqual([c.name for c in self.b.graveyard], ["Test Bear"])   # it died to the bolt

    def test_mana_value_cap_skips_expensive_cards(self):
        self.a.graveyard.append(EXPENSIVE)
        self.a.graveyard.append(BOLT)
        victim = self.put(BEAR, self.b)
        self.resolve_gy_cast("You may cast target instant card with mana value 1 or less "
                             "from your graveyard without paying its mana cost.")
        self.assertEqual(victim.damage, 3)
        self.assertEqual(sorted(c.name for c in self.a.graveyard), ["Test Bolt", "Test Cascade"])

    def test_power_cap_uses_the_sources_power(self):
        wizard = self.put(card("Test Arcanist", "{1}{R}", "Creature — Wizard", "", 2, 3))
        self.a.graveyard.append(EXPENSIVE)
        self.a.graveyard.append(BOLT)
        victim = self.put(BEAR, self.b)
        self.resolve_gy_cast("You may cast target instant or sorcery card with mana value "
                             "less than or equal to this creature's power from your "
                             "graveyard without paying its mana cost.", source=wizard)
        self.assertEqual(victim.damage, 3)
        self.assertEqual(sorted(c.name for c in self.a.graveyard), ["Test Bolt", "Test Cascade"])

    def test_that_players_graveyard_uses_the_context(self):
        self.b.graveyard.append(SORCERY)
        before = len(self.b.hand)
        self.resolve_gy_cast(WREXIAL_TEXT, context=self.b)
        self.assertEqual(len(self.b.hand), before)          # b draws nothing: it was a's cast
        self.assertEqual(len(self.a.hand), before + 1)
        self.assertEqual([c.name for c in self.b.exile], ["Test Wind"])


if __name__ == "__main__":
    unittest.main()
