"""#314: counts of cards named ~ in graveyards ("for each card named ~ in each graveyard")."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card


class NamedCounts(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def cast(self, c, targets=None):
        self.assertEqual(c.unsupported, [], c.name)
        effects = list(c.spell_effects)
        self.g.stack.append(StackItem(self.a, effects, targets or [None] * len(effects), card=c, name=c.name))
        self.g.resolve_top()

    def test_each_graveyard_counts_both_players(self):
        burst = card("Test Burst", "{1}{W}", "Instant", "You gain 4 life for each card named ~ in each graveyard.")
        self.a.graveyard, self.b.graveyard = [burst], [burst, ISLAND]
        self.cast(burst)
        self.assertEqual(self.a.life, 28)

    def test_then_for_each_scales_only_the_last_part(self):
        # "gains 4 life, then gains 4 life for each ...": the grammar used to scale both gains; now it refuses
        burst = card("Life Burst", "{1}{W}", "Instant",
                     "Target player gains 4 life, then gains 4 life for each card named ~ in each graveyard.")
        self.assertNotEqual(burst.unsupported, [])

    def test_for_each_card_in_your_graveyard_makes_tokens(self):
        servant = card("Undead Servant", "{3}{B}", "Creature — Zombie",
                       "When ~ enters, create a 2/2 black Zombie creature token for each card named ~ in your "
                       "graveyard.", 3, 2)
        self.assertEqual(servant.unsupported, [])
        other = card("Other", "{1}", "Creature — Zombie", "", 1, 1)
        self.a.graveyard = [servant, servant, other]
        self.b.graveyard = [servant]
        self.g.enter_battlefield(self.a, servant)
        self.g.settle()
        self.assertEqual(sum(1 for x in self.a.battlefield if x.card.is_token), 2)


if __name__ == "__main__":
    unittest.main()
