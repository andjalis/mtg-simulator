"""Several separate targets: "each of two target creatures", "two target creatures"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

BOLTS = card("Test Bolts", "{2}{R}", "Instant", "Test Bolts deals 3 damage to each of two target creatures.")
WIPE = card("Test Wipe", "{2}{B}", "Sorcery", "Destroy two target nonblack creatures.")
BOUNCE = card("Test Bounce", "{2}{U}", "Instant", "Return two target creatures to their owners' hands.")
LONE = card("Test Lone", "{1}", "Instant", "Destroy two target creatures and/or planeswalkers.")


class SeveralTargets(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        self.one, self.two = self._perm(self.b), self._perm(self.b)

    def _perm(self, owner):
        x = Permanent(BEAR, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c, targets):
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), targets, card=c, name=c.name))
        self.game.resolve_top()

    def test_parses_as_one_copy_per_target(self):
        for c in (BOLTS, WIPE, BOUNCE):
            with self.subTest(c.name):
                self.assertEqual(c.unsupported, [])
                self.assertEqual(len(c.spell_effects), 2)
                self.assertTrue(all(e.data.get("distinct") for e in c.spell_effects))

    def test_compound_target_noun_stays_unsupported(self):
        self.assertEqual(len(LONE.unsupported), 1)

    def test_damage_hits_both_targets(self):
        self.cast(BOLTS, [self.one, self.two])
        self.assertNotIn(self.one, self.b.battlefield)
        self.assertNotIn(self.two, self.b.battlefield)

    def test_bounce_returns_both(self):
        self.cast(BOUNCE, [self.one, self.two])
        self.assertEqual(len(self.b.battlefield), 0)
        self.assertEqual(len(self.b.hand), 2)


if __name__ == "__main__":
    unittest.main()
