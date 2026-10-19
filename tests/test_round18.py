"""Round 18: +1/+1 counters on each tapped / legendary / <subtype> creature you control."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import ISLAND, card

TAPPER = card("Test Tapper", "{2}", "Creature — Human", "Whenever ~ attacks, put a +1/+1 counter on each tapped creature you control.", 1, 1)
HERO = card("Test Hero", "{2}", "Creature — Human Hero", "{T}: Put a +1/+1 counter on each other Hero you control.", 1, 1)
BEAR = card("Test Bear", "{2}", "Creature — Bear", "", 2, 2)


class Round18(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 10, HeuristicAI())
        self.b = Player("b", [ISLAND] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def perm(self, c):
        p = Permanent(c, self.a)
        p.sick = False
        self.a.battlefield.append(p)
        return p

    def test_templates(self):
        for c in (TAPPER, HERO):
            self.assertEqual(c.unsupported, [], c.name)

    def test_only_tapped_and_subtype(self):
        t, h1, h2, bear = self.perm(TAPPER), self.perm(HERO), self.perm(HERO), self.perm(BEAR)
        t.tapped = True
        self.game.resolve(self.a, TAPPER.triggers[0].effects[0], None)
        self.assertEqual((t.p1, h1.p1, h2.p1, bear.p1), (1, 0, 0, 0))
        eff = HERO.activated[0].effects[0]
        self.assertEqual(eff.data["only"], "Hero")
        self.assertTrue(eff.data["other"])

    def test_blink_returns_at_end_step(self):
        flicker = card("Test Flicker", "{1}{W}", "Instant", "Exile target creature you control. Return it to the battlefield "
                       "under its owner's control at the beginning of the next end step.")
        self.assertEqual(flicker.unsupported, [])
        bear = self.perm(BEAR)
        self.game.resolve(self.a, flicker.spell_effects[0], bear)
        self.assertNotIn(bear, self.a.battlefield)
        self.assertEqual(len(self.game.blinked), 1)


if __name__ == "__main__":
    unittest.main()
