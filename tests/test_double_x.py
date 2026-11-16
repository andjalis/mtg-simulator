"""#531: {X}{X} costs two mana per X, for spells (Game.cast) and activated abilities (Game.ability_x)."""
import dataclasses
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import card


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class DoubleX(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def game(self, land, n):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [self.db.get("Island")] * 10
        lands = [g.enter_battlefield(a, self.db.get(land)) for _ in range(n)]
        for x in lands:
            x.sick = False
        g.settle()
        return g, a, b, lands

    def test_hangarback_walker_pays_two_per_x(self):
        g, a, _, lands = self.game("Wastes", 5)
        walker = self.db.get("Hangarback Walker")
        a.hand.append(walker)
        self.assertTrue(g.cast(a, walker))
        g.settle()
        perm = next(x for x in a.battlefield if x.card.name == "Hangarback Walker")
        self.assertEqual(perm.counters.get("+1/+1"), 2)        # 5 mana: X=2 (4 mana), not X=5
        self.assertEqual(sum(not x.tapped for x in lands), 1)

    def test_double_x_spell_effect(self):
        g, a, b, lands = self.game("Swamp", 6)
        drain = card("Test Drain", "{X}{X}{B}", "Sorcery", "Target player loses X life.")
        a.hand.append(drain)
        self.assertTrue(g.cast(a, drain, [b]))
        g.settle()
        self.assertEqual(b.life, 18)                                 # 6 mana: {B} + X=2 twice, not X=5
        self.assertEqual(sum(not x.tapped for x in lands), 1)

    def test_single_x_unchanged(self):
        g, a, b, lands = self.game("Mountain", 5)
        fireball = card("Test Blast", "{X}{R}", "Sorcery", "~ deals X damage to target player.")
        a.hand.append(fireball)
        self.assertTrue(g.cast(a, fireball, [b]))
        g.settle()
        self.assertEqual(b.life, 16)

    def test_ability_x_counts_each_x(self):
        g, a, _, lands = self.game("Wastes", 5)
        rod = card("Test Rod", "{0}", "Artifact", "{X}, {T}: You gain X life.")
        self.assertEqual(rod.unsupported, [])
        act = rod.activated[0]
        double = dataclasses.replace(rod, activated=[dataclasses.replace(act, cost=dict(act.cost, X=2))])
        perm = g.enter_battlefield(a, double)
        perm.sick = False
        self.assertEqual(g.ability_x(a, perm, perm.activated[0]), 2)     # 5 mana: {X}{X} with X=2
        self.assertTrue(g.activate_ability(a, perm, 0))
        g.settle()
        self.assertEqual(a.life, 22)
        self.assertEqual(sum(not x.tapped for x in lands), 1)


    def test_ai_sizes_double_x(self):
        g, a, b, lands = self.game("Swamp", 5)
        drain = card("Test Drain", "{X}{X}{B}", "Sorcery", "Target player loses X life.")
        sized = a.ai._sized(g, a, drain)
        self.assertEqual(sized.spell_effects[0].amount, 2)            # the AI expects X=2, not 4

if __name__ == "__main__":
    unittest.main()
