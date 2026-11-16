"""#535 group 1: 'create a number of <tokens> equal to its power' in a trigger whose head is about the card itself
(Goldvein Hydra, Threefold Thunderhulk, Nadier). Heads about another object keep the sentence unmatched."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.its_referent import rewrite
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 20
    return g, a, b


class Rewrite(unittest.TestCase):
    def test_self_heads_only(self):
        self.assertEqual(rewrite("When ~ dies, create a number of tapped Treasure tokens equal to its power."),
                         "When ~ dies, create X tapped Treasure tokens, where X is ~'s power.")
        for text in ("Whenever another creature you control dies, create a number of 1/1 tokens equal to its power.",
                     "Whenever ~ or another creature you control attacks, create a number of 1/1 Elf tokens equal "
                     "to its power.",
                     "When ~ dies, put a number of +1/+1 counters equal to its power on target creature."):
            self.assertEqual(rewrite(text), text, text)

    def test_unmatched_other_heads(self):
        c = card("Test Mourner", "{3}{G}", "Creature — Elf", "Whenever another creature you control dies, create a "
                 "number of 1/1 green Saproling creature tokens equal to its power.", 2, 2)
        self.assertTrue(c.unsupported)


class Engine(unittest.TestCase):
    def test_dies_uses_last_known_power(self):
        hydra = card("Test Hydra", "{X}{R}{G}", "Creature — Hydra", "This creature enters with X +1/+1 counters on "
                     "it.\nWhen this creature dies, create a number of tapped Treasure tokens equal to its power.", 0, 0)
        self.assertEqual(hydra.unsupported, [])
        g, a, b = game()
        h = g.enter_battlefield(a, hydra, x=4)
        g.settle()
        self.assertEqual(h.power, 4)
        g.destroy(h)
        g.settle()
        treasures = [x for x in a.battlefield if x.card.name == "Treasure"]
        self.assertEqual(len(treasures), 4)
        self.assertTrue(all(x.tapped for x in treasures))

    def test_enters_counts_its_power(self):
        hulk = card("Test Hulk", "{7}", "Artifact Creature — Construct", "This creature enters with three +1/+1 "
                    "counters on it.\nWhenever this creature enters or attacks, create a number of 1/1 colorless "
                    "Gnome artifact creature tokens equal to its power.", 0, 0)
        g, a, b = game()
        g.enter_battlefield(a, hulk)
        g.settle()
        self.assertEqual(sum(1 for x in a.battlefield if "Gnome" in x.card.name), 3)


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Goldvein Hydra", "Threefold Thunderhulk", "Nadier, Agent of the Duskenel"):
            self.assertEqual(db.get(name).unsupported, [], name)
        self.assertTrue(db.get("Infested Thrinax").unsupported)      # 'that creature's power' of another creature


if __name__ == "__main__":
    unittest.main()
