"""#314: conditions on named permanents ("if you control a creature named X", "four or more creatures named ~",
"creatures named A and B")."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.clauses import _if_cond
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


class Parsing(unittest.TestCase):
    def test_codes(self):
        self.assertIn('"name":"Bogbrew Witch"', _if_cond("you control a creature named Bogbrew Witch"))
        self.assertIn('"name":"~"', _if_cond("you control four or more creatures named ~"))
        both = _if_cond("you control creatures named Mine Worker and Power Plant Worker")
        self.assertTrue(both.startswith('lib:["and"'))
        self.assertEqual(_if_cond("you control creatures named mine worker and tower worker"), "")   # not names


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def put(self, owner, name):
        x = self.g.enter_battlefield(owner, self.db.get(name))
        x.sick = False
        return x

    def use(self, perm, idx=0):
        effects = perm.card.activated[idx].effects
        self.g.stack.append(StackItem(perm.controller, list(effects), [None] * len(effects), source=perm, name="x"))
        self.g.resolve_top()

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Liu Bei, Lord of Shu", "Mine Worker", "Faerie Miscreant", "Tower Worker", "Biovisionary",
                     "Throne of Empires", "Scepter of Empires"):
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_mine_worker_needs_both_other_workers(self):
        mine = self.put(self.a, "Mine Worker")
        self.use(mine)
        self.assertEqual(self.a.life, 21)
        self.put(self.a, "Power Plant Worker")
        self.use(mine)
        self.assertEqual(self.a.life, 22)
        self.put(self.b, "Tower Worker")            # the opponent's doesn't count
        self.use(mine)
        self.assertEqual(self.a.life, 23)
        self.put(self.a, "Tower Worker")
        self.use(mine)
        self.assertEqual(self.a.life, 26)

    def test_faerie_miscreant_draws_only_with_another(self):
        hand = len(self.a.hand)
        self.put(self.a, "Faerie Miscreant")
        self.g.settle()
        self.assertEqual(len(self.a.hand), hand)
        self.put(self.a, "Faerie Miscreant")
        self.g.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_liu_bei(self):
        liu = self.put(self.a, "Liu Bei, Lord of Shu")
        base = liu.power
        self.put(self.a, "Zhang Fei, Fierce Warrior")
        self.assertEqual(liu.power, base + 2)


if __name__ == "__main__":
    unittest.main()
