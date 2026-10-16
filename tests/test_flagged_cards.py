"""Cards from the flagged cross-check decks: nonbasic land swap and type-filtered keyword grants."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

HELLKITE = card("Hellkite", "{4}{R}", "Creature — Dragon", "Flying\\nWhen this creature enters, destroy target nonbasic land an "
                "opponent controls. Its controller searches their library for a basic land card, puts it onto the battlefield "
                "tapped with a stun counter on it, then shuffles.".replace("\\n", "\n"), 4, 4)
NURSERY = card("Nursery", "{3}{G}", "Enchantment", "{1}{G}, Exile this enchantment: Treefolk and Forests you control gain "
               "indestructible until end of turn.")
CAVE = card("Odd Cave", types="Land", text="{T}: Add {C}.")


class Flagged(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def test_templates(self):
        self.assertEqual(HELLKITE.unsupported, [])
        self.assertEqual(NURSERY.unsupported, [])

    def test_hellkite_swaps_nonbasic_for_stunned_basic(self):
        self.b.library = [MOUNTAIN] * 5
        cave = Permanent(CAVE, self.b)
        self.b.battlefield.append(cave)
        self.game.enter_battlefield(self.a, HELLKITE)
        self.game.settle()
        self.assertNotIn(cave, self.b.battlefield)
        basics = [x for x in self.b.battlefield if x.card.name == "Mountain"]
        self.assertEqual(len(basics), 1)
        self.assertTrue(basics[0].tapped)
        self.assertEqual(basics[0].counters.get("stun"), 1)

    def test_nursery_grants_indestructible_to_forests_and_treefolk(self):
        fc = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
        forest, pay = Permanent(fc, self.a), Permanent(fc, self.a)
        ent = Permanent(card("Ent", "{3}", "Creature — Treefolk", "", 3, 3), self.a)
        other = Permanent(BEAR, self.a)
        nursery = Permanent(NURSERY, self.a)
        for x in (forest, pay, ent, other, nursery):
            x.sick = False
        self.a.battlefield += [forest, pay, ent, other, nursery]
        self.assertTrue(self.game.activate(self.a, nursery, "ability:0"))
        self.game.settle()
        self.assertTrue(forest.has("indestructible") and ent.has("indestructible"))
        self.assertFalse(other.has("indestructible"))
        self.assertNotIn(nursery, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()
