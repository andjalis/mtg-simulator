"""#639: equip discounts, type-list taxes, and conditional reductions that read the combat or the opponent's casts."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

SCAVENGER = card("Test Scavenger", "{2}", "Creature — Human", "Equip abilities you activate cost {1} less to activate.", 1, 1)
SWORD = card("Test Sword", "{2}", "Artifact — Equipment", "Equipped creature gets +1/+1.\nEquip {2}")
GUARD = card("Test Guard", "{2}", "Enchantment",
             "Artifact, instant, and sorcery spells your opponents cast cost {1} more to cast.")
ALERT = card("Test Alert", "{3}{R}", "Instant", "~ costs {2} less to cast if a creature is attacking you.\n"
             "~ deals 2 damage to any target.")
BOLT = card("Test Bolt", "{1}{R}", "Instant", "Test Bolt deals 3 damage to any target.")
RING = card("Test Ring", "{2}", "Artifact", "{T}: Add {C}.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class CostMods(unittest.TestCase):
    def test_parse(self):
        for c in (SCAVENGER, GUARD, ALERT):
            self.assertEqual(c.unsupported, [], c.name)

    def test_equip_discount(self):
        g, a, b = game()
        sword = g.enter_battlefield(a, SWORD)
        bear = g.enter_battlefield(a, card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        self.assertEqual(g.equip_cost(sword, bear).get("generic"), 2)
        g.enter_battlefield(a, SCAVENGER)
        self.assertEqual(g.equip_cost(sword, bear).get("generic"), 1)

    def test_type_list_tax_hits_only_opponents_and_listed_types(self):
        g, a, b = game()
        g.enter_battlefield(a, GUARD)
        self.assertEqual(g.cost_of(b, RING)["generic"], 3)         # an artifact spell of the opponent
        self.assertEqual(g.cost_of(a, RING)["generic"], 2)         # its controller's own spells are untaxed
        self.assertEqual(g.cost_of(b, BOLT).get("generic", 0), 2)  # an instant: {1} -> {2}
        bear = card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
        self.assertEqual(g.cost_of(b, bear).get("generic", 0), 1)  # a creature spell is not on the list

    def test_attacked_discount(self):
        g, a, b = game()
        base = g.cost_of(a, ALERT).get("generic")
        g.active_idx = 1                                        # the opponent's turn
        g.attackers = [g.enter_battlefield(b, card("Ogre", "{3}", "Creature — Ogre", "", 3, 3))]
        self.assertEqual(g.cost_of(a, ALERT).get("generic"), base - 2)


if __name__ == "__main__":
    unittest.main()
