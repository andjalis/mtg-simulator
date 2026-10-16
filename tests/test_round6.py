"""Discover X follow-ups, Firebending, two-target bites."""
import unittest

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card
from tests.test_empower_discover import Base

HURL = card("Test Hurl", "{3}{U}{U}", "Instant",
            "Counter target artifact or creature spell. Discover X, where X is that spell's mana value.")
LODE = card("Test Lode", "{4}{R}{R}{R}", "Sorcery",
            "Discover 10. If the discovered card's mana value is less than 10, create a number of tapped Treasure "
            "tokens equal to the difference.")
WIPE = card("Test Overwrite", "{4}{B}{B}", "Sorcery",
            "Exile all creatures. Empower Jace X, where X is the number of creatures exiled this way.")
FIRE = card("Test Firebender", "{2}{R}", "Creature — Human", "Firebending 2", 2, 2)
VAULT = card("Test Vault", "{4}{G}{G}", "Sorcery",
             "Target creature you control deals damage equal to its power to each of two other target creatures.")
BISHOP = card("Test Bishop", "{1}{W}", "Sorcery",
              "Put a +1/+1 counter on each of up to two target creatures.")


class Round6(Base):
    def test_templates(self):
        for c in (HURL, LODE, WIPE, FIRE, VAULT, BISHOP):
            self.assertEqual(c.unsupported, [], c.name)

    def test_discover_ten_makes_treasures_for_the_difference(self):
        three = card("Three", "{3}", "Creature — Giant", "", 3, 3)
        self.a.library = [three, ISLAND]
        self.game.resolve(self.a, LODE.spell_effects[0], None)
        self.game.resolve(self.a, LODE.spell_effects[1], None)
        self.assertEqual(sum(x.card.token_kind == "treasure" and x.tapped for x in self.a.battlefield), 7)

    def test_overwrite_exiles_all_and_empowers(self):
        self.perm(BEAR)
        self.perm(BEAR, self.b)
        for eff in WIPE.spell_effects:
            self.game.resolve(self.a, eff, None)
        self.assertEqual(len(self.a.creatures) + len(self.b.creatures), 0)
        jace = next(x for x in self.a.battlefield if "Jace" in x.card.subtypes)
        self.assertEqual(jace.loyalty, 2)

    def test_firebending_adds_attack_mana_that_pays_in_combat(self):
        fb = self.perm(FIRE)
        self.game.resolve(self.a, FIRE.triggers[0].effects[0], None, self._item(fb))
        self.assertEqual(len(self.a.pool), 2)
        self.assertEqual(len(self.game.mana_sources(self.a)), 2)
        self.assertTrue(self.game.pay(self.a, {"R": 2}) is not None)

    def _item(self, src):
        from mtgsim.engine import StackItem
        return StackItem(self.a, [], [], kind="trigger", source=src)

    def test_two_target_bite_hits_both(self):
        self.perm(card("Hulk", "{3}", "Creature — Giant", "", 4, 4))
        x, y = self.perm(BEAR, self.b), self.perm(BEAR, self.b)
        from tests.test_templates import FOREST
        for _ in range(6):
            self.perm(FOREST)
        mine = self.a.creatures[0]
        self.a.hand.append(VAULT)
        self.assertTrue(self.game.cast(self.a, VAULT, [mine, x, y]))
        self.game.settle()
        self.assertEqual(len(self.b.creatures), 0)

    def test_counters_on_two_distinct_creatures(self):
        a, b = self.perm(BEAR), self.perm(BEAR)
        self.perm(card("W", "", "Land", ""))
        self.a.hand.append(BISHOP)
        from tests.test_templates import PLAINS
        self.perm(PLAINS), self.perm(PLAINS)
        self.assertTrue(self.game.cast(self.a, BISHOP, [a, b]))
        self.game.settle()
        self.assertEqual((a.power, b.power), (3, 3))


if __name__ == "__main__":
    unittest.main()
