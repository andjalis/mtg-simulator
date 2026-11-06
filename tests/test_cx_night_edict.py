"""Choose-then-destroy edicts."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, card

EDICT = card("Test Edict", "{1}{B}", "Sorcery", "Target opponent chooses a creature they control. Destroy that creature.")
ASSASSIN = card("Test Assassin", "{3}{B}", "Creature", "When ~ enters, target opponent chooses a creature they control. "
                "Destroy that creature.")


class Edict(unittest.TestCase):
    def test_parses_fully(self):
        self.assertEqual(EDICT.unsupported, [])
        self.assertEqual([(e.kind, e.data) for e in EDICT.spell_effects], [("edict", {"destroy": True})])
        self.assertEqual(ASSASSIN.unsupported, [])
        self.assertEqual(ASSASSIN.triggers[0].effects[0].kind, "edict")

    def test_destroys_one_creature(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        for _ in range(2):
            game.enter_battlefield(b, BEAR)
        game.resolve(a, EDICT.spell_effects[0], None, None)
        self.assertEqual(len(b.creatures), 1)
        self.assertEqual(len(b.graveyard), 1)


if __name__ == "__main__":
    unittest.main()
