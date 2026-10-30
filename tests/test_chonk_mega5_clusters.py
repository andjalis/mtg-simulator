"""mega-batch6 (4): live-census clusters in the graveyard/search/removal/hand families.

- "Search your library for (any number of|up to N) cards named ~ ..." (Howling Wolf,
  Andromedan Automatons) is a ``tutor_named`` effect: the copies of the resolving
  source's own name go to the hand.
- "Put any number of target <desc> cards from your graveyard on top of your library"
  (Bone Harvest) is a ``gy_top`` effect.
- "Put target creature you control on top of its owner's library" (Civic Guildmage) and
  Dire Downdraft's owner-chooses-top-or-bottom rider reuse ``tuck_perm``.
- "Discard all the cards in your hand, then draw that many cards" (Decaying Time Loop)
  is a ``discard_redraw`` effect.
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_combat_triggers import BEAR
from tests.test_templates import ISLAND, card

WOLF = card("Test Wolf", "{1}{G}", "Creature — Wolf",
            "Search your library for up to three cards named Test Wolf, reveal them, put "
            "them into your hand, then shuffle.", 2, 2)
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to target creature.", cmc=1)


class ClusterBehavior(Batch1):
    def resolve_text(self, text, targets=(), card=None, source=None):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets, card=card, source=source)
        for eff, target in zip(effects, targets):
            self.g.resolve(self.a, eff, target, item)
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.settle()

    def test_tutor_named_takes_the_sources_own_copies(self):
        self.a.library = [WOLF, ISLAND, WOLF, WOLF, BOLT]
        self.resolve_text("Search your library for up to three cards named ~, reveal them, put "
                   "them into your hand, then shuffle.", card=WOLF)
        self.assertEqual(sorted(c.name for c in self.a.hand), ["Test Wolf"] * 3)

    def test_tutor_named_any_number_takes_every_copy(self):
        self.a.library = [WOLF, WOLF, WOLF, WOLF]
        self.resolve_text("Search your library for any number of cards named ~, reveal them, "
                   "put them into your hand, then shuffle.", card=WOLF)
        self.assertEqual(len(self.a.hand), 4)
        self.assertEqual(self.a.library, [])

    def test_bone_harvest_puts_the_dead_on_top(self):
        self.a.graveyard.append(BOLT)
        self.a.graveyard.append(BEAR)
        self.a.graveyard.append(ISLAND)
        self.resolve_text("Put any number of target creature cards from your graveyard on top "
                   "of your library.")
        self.assertEqual(sorted(c.name for c in self.a.graveyard), ["Island", "Test Bolt"])
        self.assertEqual(self.a.library[-1].name, "Test Bear")

    def test_own_creature_tuck(self):
        bear = self.put(BEAR)
        self.resolve_text("Put target creature you control on top of its owner's library.", [bear])
        self.assertNotIn(bear, self.a.battlefield)
        self.assertEqual(self.a.library[-1].name, "Test Bear")

    def test_dire_downdraft_damage_and_tuck(self):
        big = self.put(card("Test Veteran", "{2}{W}", "Creature — Soldier", "", 2, 4), self.b)
        self.resolve_text("~ deals 3 damage to target creature. Target creature's "
                  "owner puts it on their choice of the top or bottom of their library.",
                   [big, big])
        self.assertEqual(big.damage, 3)
        self.assertNotIn(big, self.b.battlefield)
        self.assertEqual(self.b.library[-1].name, "Test Veteran")

    def test_discard_redraw_keeps_the_hand_size(self):
        self.a.hand = [BOLT, BOLT, BOLT]
        self.resolve_text("Discard all the cards in your hand, then draw that many cards.")
        self.assertEqual(len(self.a.hand), 3)
        self.assertEqual([c.name for c in self.a.graveyard], ["Test Bolt"] * 3)


if __name__ == "__main__":
    unittest.main()
