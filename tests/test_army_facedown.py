"""Fixes #248: "Armies you control have trample" and "Face-down creatures you control get +0/+1" now do something."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from mtgsim.manifest import manifest_one

from tests.test_templates import BEAR


class ArmyFaceDown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [BEAR] * 20

    def test_parse(self):
        goblin = self.db.get("Great Goblin, Foul-Hearted")
        self.assertEqual(goblin.keyword_sub, (("Army", "trample", False),))
        self.assertEqual(self.db.get("Secret Plans").anthem_sub, (("Face-down", 0, 1, False),))

    def test_amassed_army_has_trample(self):
        self.game.enter_battlefield(self.a, self.db.get("Great Goblin, Foul-Hearted"))
        self.game.settle()
        army = next(x for x in self.a.battlefield if "Army" in x.card.subtypes)
        self.assertEqual(army.p1, 3)
        self.assertTrue(army.has("trample"))
        other = self.game.enter_battlefield(self.a, BEAR)
        self.assertFalse(other.has("trample"))

    def test_face_down_creatures_get_the_bonus(self):
        self.game.enter_battlefield(self.a, self.db.get("Secret Plans"))
        face_down = manifest_one(self.game, self.a)
        up = self.game.enter_battlefield(self.a, BEAR)
        self.assertEqual((face_down.power, face_down.toughness), (2, 3))
        self.assertEqual((up.power, up.toughness), (BEAR.power, BEAR.toughness))

    def test_ai_casts_great_goblin_and_gets_a_trampling_army(self):
        for land in ("Mountain", "Mountain", "Swamp", "Swamp", "Swamp"):
            self.game.enter_battlefield(self.a, self.db.get(land)).sick = False
        self.a.hand = [self.db.get("Great Goblin, Foul-Hearted")]
        self.game.take_turn(self.a)
        self.assertTrue(any(x.card.name.startswith("Great Goblin") for x in self.a.battlefield))
        army = next(x for x in self.a.battlefield if "Army" in x.card.subtypes)
        self.assertTrue(army.has("trample"))


if __name__ == "__main__":
    unittest.main()
