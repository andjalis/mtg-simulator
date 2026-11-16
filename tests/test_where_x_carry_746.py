"""#746: a "where X is ..." definition reaches the later sentences of the same ability that use X (The Ice Dancer's
damage, Tezzeret's "+2: ... You gain X life"), instead of resolving as an X-cost amount of 0."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_later_sentence_gets_the_count(self):
        effects, bad = _parse_effects("You draw X cards, where X is the number of artifacts you control. "
                                      "~ deals X damage to each opponent.")
        self.assertEqual(bad, [])
        self.assertEqual([e.data.get("xq") for e in effects], [("count", "artifact")] * 2)
        self.assertNotIn("x", effects[1].data)

    def test_a_referent_quantity_is_not_carried(self):
        effects, _ = _parse_effects("You may pay X life, where X is its power. If you do, draw X cards.")
        self.assertFalse(any(e.data.get("xq") and e.kind == "draw" for e in effects))

    def test_without_a_definition_x_stays_the_cost(self):
        effects, _ = _parse_effects("~ deals X damage to any target.")
        self.assertTrue(effects[0].data.get("x"))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_the_ice_dancer_deals_x(self):
        g, a, b = self.game, self.a, self.b
        dancer = g.enter_battlefield(a, db("The Ice Dancer"))
        dancer.sick = False
        treasure = card("T Tr", "{1}", "Sorcery", "Create a Treasure token.")
        g.stack.append(StackItem(a, list(treasure.spell_effects), [None], card=treasure, name=treasure.name))
        g.resolve_top()
        g.settle()
        a.ai.choose_attackers = lambda game, p, o: [dancer]
        g.combat(a, b)
        g.settle()
        x = 2                                       # the Treasure and the new Gold
        self.assertEqual(len(a.hand), x)
        self.assertEqual(a.life, 20 + x)
        self.assertEqual(b.life, 20 - dancer.power - x)

    def test_tezzeret_plus_two_gains_x(self):
        g, a, b = self.game, self.a, self.b
        tez = g.enter_battlefield(a, db("Tezzeret, Master of the Bridge"))
        for _ in range(3):
            g.enter_battlefield(a, card("T Rock", "{1}", "Artifact", ""))
        g.activate_loyalty(a, tez, 0)
        g.settle()
        self.assertEqual(b.life, 17)
        self.assertEqual(a.life, 23)


if __name__ == "__main__":
    unittest.main()
