"""#467: CR 119.4 lets a player pay life equal to their life total; only the AI declines paying itself to 0."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class LifeCosts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def game(self, life, lands, permanents=()):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [self.db.get("Island")] * 10
        a.life = life
        for name in lands:
            g.enter_battlefield(a, self.db.get(name)).sick = False
        for name in permanents:
            g.enter_battlefield(a, self.db.get(name)).sick = False
        g.enter_battlefield(b, BEAR)
        g.enter_battlefield(b, self.db.get("Forest"))
        g.settle()
        return g, a

    def variants(self, g, a, name, kind=None):
        card = self.db.get(name)
        a.hand.append(card)
        return [c for c in g.spell_options(a) if c.name.startswith(name)
                and (kind is None or kind in g._origin(c)[1])]

    def test_ability_life_cost_equal_to_life(self):
        g, a = self.game(2, ["Swamp"], ["Greed"])
        greed = next(x for x in a.battlefield if x.card.name == "Greed")
        self.assertTrue(g.can_activate(a, greed, 0))            # failed before: life 2 == "Pay 2 life"
        self.assertTrue(g.activate_ability(a, greed, 0))
        g.settle()
        self.assertEqual(a.life, 0)
        self.assertTrue(a.lost)
        g, a = self.game(1, ["Swamp"], ["Greed"])
        greed = next(x for x in a.battlefield if x.card.name == "Greed")
        self.assertFalse(g.can_activate(a, greed, 0))           # less life than the payment: can't


    def test_additional_life_cost(self):
        g, a = self.game(3, ["Swamp", "Mountain", "Swamp", "Swamp", "Swamp"])
        (fumarole,) = self.variants(g, a, "Fumarole")
        self.assertTrue(g.can_cast_now(a, fumarole))             # 3 life, pay 3
        self.assertFalse(a.ai._can_cast(g, a, fumarole))     # the AI won't
        g, a = self.game(4, ["Swamp", "Mountain", "Swamp", "Swamp", "Swamp"])
        (fumarole,) = self.variants(g, a, "Fumarole")
        self.assertTrue(a.ai._can_cast(g, a, fumarole))
        g, a = self.game(2, ["Swamp", "Mountain", "Swamp", "Swamp", "Swamp"])
        (fumarole,) = self.variants(g, a, "Fumarole")
        self.assertFalse(g.can_cast_now(a, fumarole))

    def test_alternative_life_cost(self):
        g, a = self.game(4, ["Swamp"])
        alts = [c for c in self.variants(g, a, "Snuff Out") if g._origin(c)[2] is not None]
        self.assertTrue(alts)
        self.assertTrue(any(g.can_cast_now(a, c) for c in alts))      # pay 4 life at 4
        self.assertFalse(any(a.ai._can_cast(g, a, c) for c in alts))
        g, a = self.game(3, ["Swamp"])
        alts = [c for c in self.variants(g, a, "Snuff Out") if g._origin(c)[2] is not None]
        self.assertFalse(any(g.can_cast_now(a, c) for c in alts))

    def test_choice_cost_life_part(self):
        from mtgsim import cx_spell_costs
        g, a = self.game(5, ["Plains", "Swamp"])
        (payment,) = self.variants(g, a, "Final Payment")
        self.assertTrue(g.can_cast_now(a, payment))             # only "pay 5 life" is available, at 5 life
        self.assertFalse(a.ai._can_cast(g, a, payment))
        g, a = self.game(5, ["Plains", "Swamp"], ["Grizzly Bears"])
        (payment,) = self.variants(g, a, "Final Payment")
        chosen = cx_spell_costs.choose(g, a, payment)
        self.assertEqual(chosen[1][0][0], "sac")                # paying to 0 is the last resort
        self.assertTrue(a.ai._can_cast(g, a, payment))


if __name__ == "__main__":
    unittest.main()
