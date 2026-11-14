"""#435: "return another target creature / other target nonland permanent ... to its owner's hand" can't target the
source itself (the "other" was dropped)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_templates import ISLAND, card

LUNARCH = card("Test Mage", "{2}{U}", "Creature — Human Wizard",
               "When this creature enters, return up to one other target creature to its owner's hand.", 2, 2)
ROAMER = card("Test Roamer", "{3}{U}", "Creature — Beast",
              "When this creature enters, return another target nonland permanent you don't control to its "
              "owner's hand.", 3, 3)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class BounceOther(unittest.TestCase):
    def test_parsed_other(self):
        self.assertTrue(LUNARCH.triggers[0].effects[0].data.get("other"))
        self.assertTrue(ROAMER.triggers[0].effects[0].data["selector"].get("other"))   # "another": the grammar

    def test_source_is_not_a_legal_target(self):
        g, a, b = game()
        ogre = g.enter_battlefield(b, card("Ogre", "{3}", "Creature — Ogre", "", 3, 3))
        mage = g.enter_battlefield(a, card("Plain Mage", "{2}{U}", "Creature — Human Wizard", "", 2, 2))
        g.settle()                                   # the source of the trigger checked below
        eff = LUNARCH.triggers[0].effects[0]
        with g.targeting(StackItem(a, [eff], [None], source=mage, kind="trigger")):
            legal = g.legal_targets(a, eff)
        self.assertIn(ogre, legal)
        self.assertNotIn(mage, legal)


if __name__ == "__main__":
    unittest.main()
