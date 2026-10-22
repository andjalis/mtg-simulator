"""Storage lands: banking counters at the end of the opponent's turn, holding a land tapped, spending stored mana."""
import random
import unittest

from mtgsim import storage
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, PLAINS, card

FOUNTAIN = card("Test Fountain", "", "Land", "~ enters tapped.\n{T}: Put a storage counter on ~.\n{T}, Remove any number "
                                             "of storage counters from ~: Add {W} for each storage counter removed this way.")
POOLS = card("Test Pools", "", "Land", "{T}: Add {C}.\n{1}, {T}: Put a storage counter on ~.\n{1}, Remove X storage "
                                       "counters from ~: Add X mana in any combination of {W} and/or {U}.")
VAULT = card("Test Vault", "", "Land", "~ enters tapped.\nYou may choose not to untap ~ during your untap step.\nAt the "
                                       "beginning of your upkeep, if ~ is tapped, put a storage counter on it.\n{T}, "
                                       "Remove any number of storage counters from ~: Add {B} for each storage counter "
                                       "removed this way.")
ANGEL = card("Test Angel", "{2}{W}{W}", "Creature — Angel", "Flying", 4, 4)


class StorageLands(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, tapped=False):
        perm = self.game.enter_battlefield(who, c)
        perm.sick, perm.tapped = False, tapped
        self.game.settle()
        return perm

    def test_templates(self):
        for c in (FOUNTAIN, POOLS, VAULT):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(POOLS.storage["bank"], {"generic": 1})
        self.assertTrue(VAULT.storage["hold"] and VAULT.storage["upkeep"])

    def test_untapped_land_banks_then_untaps(self):
        fountain = self.put(self.a, FOUNTAIN)
        storage.before_untap(self.game, self.a)
        self.assertEqual(fountain.counters["storage"], 1)
        self.assertTrue(fountain.tapped)

    def test_bank_cost_paid_by_another_land(self):
        pools = self.put(self.a, POOLS)
        island = self.put(self.a, ISLAND)
        storage.before_untap(self.game, self.a)
        self.assertEqual(pools.counters["storage"], 1)
        self.assertTrue(island.tapped)
        lone = self.put(self.b, POOLS)
        storage.before_untap(self.game, self.b)
        self.assertEqual(lone.counters.get("storage", 0), 0)    # nothing else to pay the {1}

    def test_stored_mana_pays_for_a_spell(self):
        fountain = self.put(self.a, FOUNTAIN)
        fountain.counters["storage"] = 3
        self.put(self.a, PLAINS)
        self.a.hand[:] = [ANGEL]
        self.assertTrue(self.game.cast(self.a, ANGEL))
        self.game.settle()
        self.assertTrue(any(x.card.name == ANGEL.name for x in self.a.battlefield))
        self.assertEqual(fountain.counters["storage"], 0)
        self.assertTrue(fountain.tapped)

    def test_vault_holds_until_its_mana_is_needed(self):
        vault = self.put(self.a, VAULT, tapped=True)
        self.put(self.a, PLAINS)
        self.a.hand[:] = [ANGEL]
        self.game.take_turn(self.a)
        self.assertTrue(vault.tapped)                           # kept tapped, banked a counter in upkeep
        self.assertEqual(vault.counters["storage"], 1)
        vault.counters["storage"] = 3
        self.assertFalse(storage.keeps_tapped(self.game, self.a, vault))


if __name__ == "__main__":
    unittest.main()
