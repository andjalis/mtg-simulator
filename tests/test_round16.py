"""Round 16: sacrifice N of a kind as a cost, keyword-filtered enter triggers, teamwork-conditional counter."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import ISLAND, card

HOARD = card("Test Hoard Lord", "{1}{R}", "Creature — Dwarf", "Sacrifice three Treasures: Create a 4/4 red Dragon creature "
             "token with flying and haste. Activate only as a sorcery.", 2, 2)
WATCH = card("Test Watcher", "{W}", "Creature — Bat", "Whenever another creature you control with flying enters, ~ gets "
             "+1/+1 until end of turn.", 1, 1)
NAY = card("Test Nay", "{1}{U}", "Instant — Arcane", "Teamwork 2 (As an additional cost to cast this spell, you may tap any "
           "number of creatures you control with total power 2 or more.)\nCounter target spell unless its controller pays "
           "{2}. Counter that spell unless its controller pays {4} instead if this spell was cast using teamwork.")


class Round16(unittest.TestCase):
    def test_templates(self):
        for c in (HOARD, WATCH, NAY):
            self.assertEqual(c.unsupported, [], c.name)

    def test_sacrifice_cost_count(self):
        a, b = Player("a", [ISLAND] * 5, HeuristicAI()), Player("b", [ISLAND] * 5, HeuristicAI())
        g = Game(a, b, random.Random(0))
        g.turn, g.step = 1, "main1"
        lord = Permanent(HOARD, a)
        lord.sick = False
        a.battlefield.append(lord)
        act = HOARD.activated[0]
        self.assertEqual((act.extra_costs["sacrifice"], act.extra_costs["sac_n"]), ("treasure", 3))

    def test_teamwork_amount(self):
        eff = NAY.spell_effects[0]
        self.assertEqual((eff.amount, eff.data["tw"]), (2, 4))


if __name__ == "__main__":
    unittest.main()
