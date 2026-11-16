"""#330 slice: "each opponent sacrifices a creature unless they discard a card" (The Long Reach of Night) and the
counted discard cost "unless they discard two cards"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class EdictAndDiscard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [self.db.get("Island")] * 5

    def resolve(self, text):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [], text)
        self.g.stack.append(StackItem(self.a, effects, [None] * len(effects), name="test"))
        self.g.resolve_top()
        self.g.settle()

    def test_long_reach_parses(self):
        self.assertEqual(self.db.get("The Long Reach of Night // Animus of Night's Reach").unsupported, [])

    def test_edict_unless_discard(self):
        bear = self.g.enter_battlefield(self.b, self.db.get("Grizzly Bears"))
        self.b.hand = [self.db.get("Island")]
        self.resolve("Each opponent sacrifices a creature unless they discard a card.")
        self.assertIn(bear, self.b.battlefield)                   # they discarded instead
        self.assertEqual(self.b.hand, [])
        self.resolve("Each opponent sacrifices a creature unless they discard a card.")
        self.assertNotIn(bear, self.b.battlefield)                # no card: the creature goes

    def test_counted_discard(self):
        self.b.hand = [self.db.get("Island")]
        self.resolve("Each opponent loses 6 life unless they discard two cards.")
        self.assertEqual(self.b.life, 14)                         # one card can't pay two: no partial payment
        self.assertEqual(len(self.b.hand), 1)
        self.b.hand = [self.db.get("Island"), self.db.get("Forest"), self.db.get("Swamp")]
        self.resolve("Each opponent loses 6 life unless they discard two cards.")
        self.assertEqual(len(self.b.hand), 1)
        self.assertEqual(self.b.life, 14)

    def test_refusal(self):
        self.assertTrue(_parse_effects("Each opponent loses 6 life unless they discard X cards.")[1])


if __name__ == "__main__":
    unittest.main()
