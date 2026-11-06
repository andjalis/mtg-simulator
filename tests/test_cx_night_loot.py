"""Optional loot riders fold into one conditional loot effect."""
import random
import unittest

from mtgsim import cards
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.engine.kinds.cx_night_loot import loot
from tests.test_templates import BEAR, card

AWAY = card("Test Away", "{1}{U}", "Instant",
            "Return target creature to its owner's hand.\nFerocious — If you control a creature with power 4 or greater, "
            "you may draw a card. If you do, discard a card.")


class Loot(unittest.TestCase):
    def test_the_condition_covers_the_whole_loot(self):
        self.assertEqual(AWAY.unsupported, [])
        self.assertEqual([(e.kind, e.cond) for e in AWAY.spell_effects], [("bounce", ""), ("loot", "power_ge:4")])

    def test_unconditional_wording_is_left_to_the_pay_gate(self):
        effects, unmatched = cards._parse_effects("You may draw a card. If you do, discard a card.")
        self.assertEqual(("loot" in [e.kind for e in effects], unmatched), (False, []))

    def test_draws_then_discards(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        a.library = list(a.deck)
        a.hand = [BEAR]
        loot(game, a, eff=cards.Effect("loot", 1))
        self.assertEqual((len(a.hand), len(a.graveyard)), (1, 1))


if __name__ == "__main__":
    unittest.main()
