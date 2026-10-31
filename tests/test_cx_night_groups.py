"""Group effects on "each opponent controls" / "target opponent controls" permanents."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

FREEZE = card("Test Freeze", "{2}{U}", "Instant", "Tap all creatures target opponent controls.")
CURSE = card("Test Curse", "{1}{G}", "Sorcery", "Put a +1/+1 counter on each creature each opponent controls.")


class OpponentGroups(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        self.mine, self.theirs = (self._perm(BEAR, p) for p in (self.a, self.b))

    def _perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c):
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_parses(self):
        self.assertEqual((FREEZE.unsupported, CURSE.unsupported), ([], []))

    def test_tap_only_their_creatures(self):
        self.cast(FREEZE)
        self.assertTrue(self.theirs.tapped)
        self.assertFalse(self.mine.tapped)

    def test_counters_only_on_their_creatures(self):
        self.cast(CURSE)
        self.assertEqual(self.theirs.counters.get("+1/+1", 0), 1)
        self.assertEqual(self.mine.counters.get("+1/+1", 0), 0)


if __name__ == "__main__":
    unittest.main()
