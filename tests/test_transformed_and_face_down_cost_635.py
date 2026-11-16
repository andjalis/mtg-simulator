"""#635: the "transformed" selector trait (Mutagen Connoisseur) and face-down cost reductions (Dream Chisel, Obscuring
Aether, Kadena)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_selector_and_discounts(self):
        from mtgsim.permanent_templates import selector
        self.assertEqual(selector("transformed permanent you control")["traits"], ["transformed"])
        self.assertEqual(db("Dream Chisel").cost_discount, (("face_down", 1),))
        self.assertEqual(db("Kadena, Slinking Sorcerer").cost_discount, (("face_down_first", 3),))

    def test_refusals(self):
        # a discount only "this turn" (Goblin Maskmaker) or for "the next" spell (Panoptic Projektor): not read
        for name in ("Goblin Maskmaker", "Panoptic Projektor", "Oculus Whelp"):
            self.assertFalse(db(name).fully_supported, name)
        # "face-down" in other templates' descriptions is untouched (Cryptid Inspector stays full)
        self.assertTrue(db("Cryptid Inspector").fully_supported)

    def test_real_cards_full(self):
        for name in ("Dream Chisel", "Kadena, Slinking Sorcerer", "Mutagen Connoisseur", "Obscuring Aether"):
            self.assertTrue(db(name).fully_supported, name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, p, name):
        x = self.game.enter_battlefield(p, db(name))
        self.game.settle()
        return x

    def test_mutagen_counts_my_transformed_permanents(self):
        mutagen = self.put(self.a, "Mutagen Connoisseur")
        mine = self.put(self.a, "Geier Reach Bandit // Vildin-Pack Alpha")
        self.assertEqual(mutagen.power, 0)
        self.game.transform(mine)
        self.assertEqual(mutagen.power, 1)
        theirs = self.put(self.b, "Geier Reach Bandit // Vildin-Pack Alpha")
        self.game.transform(theirs)
        self.assertEqual(mutagen.power, 1)              # theirs doesn't count
        self.game.transform(mine)
        self.assertEqual(mutagen.power, 0)              # front face up again

    def face_down_costs(self):
        return [self.game.cost_of(self.a, o) for o in self.game.spell_options(self.a) if "morph" in o.name.lower()]

    def test_dream_chisel_only_face_down(self):
        self.put(self.a, "Dream Chisel")
        self.a.hand = [db("Skinthinner")]
        costs = {o.name: self.game.cost_of(self.a, o) for o in self.game.spell_options(self.a)}
        self.assertEqual(costs["Skinthinner (morph)"], {"generic": 2})
        self.assertEqual(costs["Skinthinner"], {"generic": 1, "B": 1})

    def test_kadena_first_face_down_spell_each_turn(self):
        self.put(self.a, "Kadena, Slinking Sorcerer")
        self.a.hand = [db("Skinthinner"), db("Skinthinner")]
        self.assertEqual(self.face_down_costs()[0], {"generic": 0})
        first = next(o for o in self.game.spell_options(self.a) if "morph" in o.name.lower())
        self.assertTrue(self.game.cast(self.a, first))
        self.game.settle()
        self.assertEqual(self.face_down_costs()[0], {"generic": 3})
        self.game.turn += 1
        self.assertEqual(self.face_down_costs()[0], {"generic": 0})     # a new turn


if __name__ == "__main__":
    unittest.main()
