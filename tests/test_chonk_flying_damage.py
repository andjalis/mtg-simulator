"""Damage filter honoring eff.filter == "flying" (Hurricane / Squallmonger family)."""
import unittest

from mtgsim.cards import Effect
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_combat_triggers import BEAR
from tests.test_templates import card

BIRD = card("Test Bird", "{1}{U}", "Creature — Bird", "Flying", 1, 1)


class FlyingDamageFilter(Batch1):
    def apply_effect(self, eff):
        item = StackItem(self.a, [eff], [None])
        self.g.resolve(self.a, eff, None, item, prev=None)

    def test_each_creature_flying_only(self):
        bird = self.put(BIRD, self.b)
        bear = self.put(BEAR, self.b)
        self.apply_effect(Effect("damage", 2, target="each_creature", filter="flying"))
        self.assertEqual(bird.damage, 2)
        self.assertEqual(bear.damage, 0)

    def test_nonflying_still_excludes_flying(self):
        bird = self.put(BIRD, self.b)
        bear = self.put(BEAR, self.b)
        self.apply_effect(Effect("damage", 1, target="each_creature", filter="nonflying"))
        self.assertEqual(bird.damage, 0)
        self.assertEqual(bear.damage, 1)

    def test_unfiltered_hits_all(self):
        bird = self.put(BIRD, self.b)
        bear = self.put(BEAR, self.b)
        self.apply_effect(Effect("damage", 1, target="each_creature"))
        self.assertEqual(bird.damage, 1)
        self.assertEqual(bear.damage, 1)


if __name__ == "__main__":
    unittest.main()
