"""#628: "Those creatures can't block this turn." / "Each of them gets +1/+1 ..." after a counted target ("up to two
target creatures") act on each chosen target."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, MOUNTAIN, card

GAMBIT = card("Test Gambit", "{R}", "Instant", "Test Gambit deals 1 damage to each of up to two target creatures. "
              "Those creatures can't block this turn.")
RALLY = card("Test Rally", "{W}", "Instant", "Up to two target creatures you control each get +1/+1 until end of turn. "
             "Each of them gains vigilance until end of turn.")


class PluralRiders(unittest.TestCase):
    def test_parse(self):
        for c in (GAMBIT, RALLY):
            self.assertEqual(c.unsupported, [], c.name)
        kinds = [e.kind for e in GAMBIT.spell_effects]
        self.assertEqual(kinds, ["damage", "cant_block_turn"] * 2)

    def test_refusals(self):
        # a rider naming something else stays unsupported
        c = card("Test Odd", "{R}", "Instant", "Test Odd deals 1 damage to each of up to two target creatures. "
                 "Those creatures can't block this turn unless they have flying and you control a Mountain.")
        self.assertTrue(c.unsupported)

    def test_resolves(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 1, "main1"
        a.library = b.library = [ISLAND] * 10
        g.enter_battlefield(a, MOUNTAIN)
        x = g.enter_battlefield(b, card("Ogre", "{3}", "Creature — Ogre", "", 3, 3))
        y = g.enter_battlefield(b, card("Elf", "{1}", "Creature — Elf", "", 1, 1))
        a.hand = [GAMBIT]
        seq = iter([x, y])
        effs = GAMBIT.spell_effects
        self.assertTrue(g.cast(a, GAMBIT, [next(seq) if e.target != "prev" else None for e in effs]))
        g.settle()
        self.assertEqual(x.damage, 1)
        self.assertIn("cant_block_now", x.temp_kw)       # the rider reached the surviving target
        self.assertNotIn(y, b.battlefield)


if __name__ == "__main__":
    unittest.main()
