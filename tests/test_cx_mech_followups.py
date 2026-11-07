"""Follow-ups: cost reductions survive alternative-cost variants (#276), explore with an empty library (#278)."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, BEAR, card


class FollowUps(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_splice_keeps_the_spells_own_cost_reduction(self):
        arcane = card("Test Arcane", "{4}{W}", "Instant — Arcane", "Undaunted\nYou gain 1 life.")
        self.assertEqual(arcane.cost_reduction, "undaunted")
        breath = self.db.get("Blessed Breath")                       # splice {W}
        self.a.hand = [arcane, breath]
        (v,) = [x for x in self.game.spell_options(self.a) if "splice" in x.name]
        cost = self.game.cost_of(self.a, v)
        self.assertEqual(sum(cost.values()), 4 + 1 + 1 - 1)         # {4}{W} + {W}, one less for the opponent

    def test_explore_with_an_empty_library_still_adds_the_counter(self):
        creature = self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        self.a.library = []
        (eff,) = _parse_effects("Target creature you control explores.")[0]
        self.game.resolve(self.a, eff, creature)
        self.assertEqual(creature.counters.get("+1/+1"), 1)


if __name__ == "__main__":
    unittest.main()
