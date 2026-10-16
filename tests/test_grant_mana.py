"""Permanents that give other permanents a mana ability."""
import unittest

from mtgsim.cards import make_token

from tests.test_templates import BEAR, card
from tests.test_empower_discover import Base

VITALITY = card("Test Vitality", "{2}{G}", "Enchantment Creature — Dog",
                'Creatures you control have "{T}: Add one mana of any color."', 3, 3)
GUIDE = card("Test Guide", "{1}{G}", "Creature — Ally",
             'Each land and Ally you control has "{T}: Add one mana of any color."', 1, 1)
REBORN = card("Test Reborn", "{3}{G}", "Enchantment",
              'Other permanents you control have "{T}: Add one mana of any color."')
SWEETS = card("Test Sweets", "{2}{G}", "Enchantment",
              'Foods you control have "{T}: Add {G}."')


class GrantMana(Base):
    def test_templates(self):
        for c in (VITALITY, GUIDE, REBORN, SWEETS):
            self.assertEqual(c.unsupported, [], c.name)

    def test_creatures_tap_for_any_color(self):
        self.perm(VITALITY)
        bear = self.perm(BEAR)
        src = self.game.mana_sources(self.a)
        self.assertIn(bear, src)
        self.assertEqual(len(bear.produces_now), 5)

    def test_summoning_sick_creature_cannot_tap(self):
        self.perm(VITALITY)
        bear = self.perm(BEAR)
        bear.sick = True
        self.assertNotIn(bear, self.game.mana_sources(self.a))

    def test_guide_gives_lands_and_allies(self):
        from tests.test_templates import ISLAND
        guide = self.perm(GUIDE)
        land = self.perm(ISLAND)
        bear = self.perm(BEAR)
        src = self.game.mana_sources(self.a)
        self.assertIn(land, src)
        self.assertIn(guide, src)
        self.assertNotIn(bear, src)
        self.assertEqual(len(land.produces_now), 5)

    def test_other_permanents_excludes_source(self):
        reborn = self.perm(REBORN)
        bear = self.perm(BEAR)
        src = self.game.mana_sources(self.a)
        self.assertIn(bear, src)
        self.assertNotIn(reborn, src)

    def test_food_taps_for_green(self):
        self.perm(SWEETS)
        food = self.perm(make_token("Food", 0, 0, (), None, "food", True))
        self.assertIn(food, self.game.mana_sources(self.a))
        self.assertEqual(food.produces_now, frozenset("G"))


if __name__ == "__main__":
    unittest.main()
