"""Fixes from the opus-refs behaviour audit, round 6 (2026-11-16): the AI valued "Target player discards N cards"
(Mind Rot, Raven's Crime, Hypnotic Cloud) as its own discard and never cast it."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
SWAMP = card("Swamp", "", "Basic Land — Swamp", "({T}: Add {B}.)")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 20, [ISLAND] * 20
    a.my_turn, b.my_turn = True, False
    for _ in range(3):
        g.enter_battlefield(a, SWAMP)
    return g, a, b


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class TargetPlayerDiscards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_ai_casts_mind_rot_at_the_opponent(self):
        g, a, b = game()
        b.hand = [BEAR] * 4
        a.hand = [self.db.get("Mind Rot")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual(len(b.hand), 2)
        self.assertEqual(a.hand, [])

    def test_plan_aims_at_the_opponent(self):
        g, a, b = game()
        b.hand = [BEAR] * 2
        value, targets = a.ai.plan_spell(g, a, self.db.get("Raven's Crime"), True)
        self.assertGreater(value, 0)
        self.assertEqual(targets, [b])

    def test_not_cast_into_an_empty_hand(self):
        g, a, b = game()
        b.hand = []
        self.assertIsNone(a.ai.plan_spell(g, a, self.db.get("Mind Rot"), True))

    def test_own_discard_still_costs(self):
        """An untargeted "discard a card" (Sift's "then discard a card") is still the caster's own loss."""
        g, a, b = game()
        sift = self.db.get("Sift")
        draw_only = sift.spell_effects[0].amount * 1.5
        value, _ = a.ai.plan_spell(g, a, sift, True)
        self.assertLess(value, draw_only)


if __name__ == "__main__":
    unittest.main()
