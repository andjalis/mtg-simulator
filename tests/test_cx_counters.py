"""cx_counters.py: counters on several targets at once."""
import random
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.state import Permanent
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND


def effects(text):
    effs, bad = _parse_effects(text)
    assert not bad, bad
    return effs


class MultiTarget(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, p, n):
        out = []
        for _ in range(n):
            perm = Permanent(BEAR, p)
            p.battlefield.append(perm)
            out.append(perm)
        return out

    def run_effects(self, text):
        effs = effects(text)
        targets = self.game.auto_targets(self.a, effs)
        for e, t in zip(effs, targets):
            self.game.resolve(self.a, e, t)
        return targets

    def test_each_of_up_to_two_stun(self):
        bears = self.put(self.a, 3)
        self.run_effects("Put a stun counter on each of up to two target creatures.")
        self.assertEqual(sorted(b.counters.get("stun", 0) for b in bears), [0, 1, 1])

    def test_each_of_up_to_three_other_mine(self):
        bears = self.put(self.a, 2)
        self.run_effects("Put two +1/+1 counters on each of up to three other target creatures you control.")
        self.assertEqual(sum(b.counters.get("+1/+1", 0) for b in bears), 4)

    def test_fewer_targets_than_up_to(self):
        bears = self.put(self.a, 1)
        self.run_effects("Put a shield counter on each of up to two target creatures.")
        self.assertEqual(bears[0].counters.get("shield", 0), 1)


if __name__ == "__main__":
    unittest.main()
