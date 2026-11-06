"""Stand-alone "Untap them." after a "creatures you control" sentence untaps your creatures."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, card

ROAR = card("Test Roar", "{2}{W}", "Instant", "Creatures you control get +1/+1 until end of turn. Untap them.")


class UntapThem(unittest.TestCase):
    def test_parses(self):
        self.assertEqual(ROAR.unsupported, [])
        self.assertEqual([e.kind for e in ROAR.spell_effects], ["pump_all", "untap_all"])

    def test_untaps_and_pumps_my_creatures_only(self):
        from mtgsim.engine.kinds.stats import pump_all, untap_all
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        mine, theirs = Permanent(BEAR, a), Permanent(BEAR, b)
        mine.tapped = theirs.tapped = True
        a.battlefield.append(mine)
        b.battlefield.append(theirs)
        for eff in ROAR.spell_effects:
            {"pump_all": pump_all, "untap_all": untap_all}[eff.kind](game, a, eff=eff, item=None)
        self.assertFalse(mine.tapped)
        self.assertTrue(theirs.tapped)
        self.assertEqual(mine.pump_p, 1)


if __name__ == "__main__":
    unittest.main()
