"""Conjure a card named X (mtgsim.conjure). Needs the card database for the conjured card."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from mtgsim.carddb import ALL_CARDS

from tests.test_templates import BEAR, ISLAND, card


def _spell(text):
    return card("Test Conjure", "{1}", "Sorcery", text)


@unittest.skipUnless(ALL_CARDS.exists(), "needs the offline card database")
class ConjureTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 20
        p = Permanent(ISLAND, self.a)
        p.sick, p.tapped = False, False
        self.a.battlefield.append(p)

    def cast(self, text):
        c = _spell(text)
        self.assertEqual(c.unsupported, [])
        self.a.hand = [c]
        self.assertTrue(self.game.cast(self.a, c))
        self.game.settle()

    def test_into_hand(self):
        self.cast("Conjure a card named Mox Jet into your hand.")
        self.assertEqual([c.name for c in self.a.hand], ["Mox Jet"])

    def test_several_into_graveyard(self):
        self.cast("Conjure three cards named Reassembling Skeleton into your graveyard.")
        self.assertEqual([c.name for c in self.a.graveyard].count("Reassembling Skeleton"), 3)

    def test_onto_the_battlefield_tapped(self):
        self.cast("Conjure a card named Mishra's Foundry onto the battlefield tapped.")
        found = [x for x in self.a.battlefield if x.card.name == "Mishra's Foundry"]
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].tapped)

    def test_into_the_top_of_the_library(self):
        self.cast("Conjure a card named Sanguine Bond into the top eight cards of your library at random.")
        depth = [c.name for c in reversed(self.a.library)].index("Sanguine Bond")
        self.assertLess(depth, 8)

    def test_library_then_shuffle(self):
        self.cast("Conjure four cards named Volcanic Geyser into your library, then shuffle.")
        self.assertEqual([c.name for c in self.a.library].count("Volcanic Geyser"), 4)

    def test_counter_goes_on_the_conjured_permanent(self):
        self.cast("Conjure a card named Hangarback Walker onto the battlefield, then put a +1/+1 counter on it.")
        found = [x for x in self.a.battlefield if x.card.name == "Hangarback Walker"]
        self.assertEqual([x.counters.get("+1/+1") for x in found], [1])

    def test_two_different_names_stay_unmatched(self):
        c = _spell("Conjure a card named Darksteel Ingot and a card named Darksteel Plate into your hand.")
        self.assertTrue(c.unsupported)

    def test_unknown_card_is_skipped(self):
        self.cast("Conjure a card named Nonexistent Test Card into your hand.")
        self.assertEqual(self.a.hand, [])


if __name__ == "__main__":
    unittest.main()
