"""Kinship: the upkeep bonus applies only when the top card shares a creature type."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

SHAMAN = card("Test Shaman", "{1}{G}", "Creature — Elf Shaman",
              "Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a "
              "creature type with Test Shaman, you may reveal it. If you do, you gain 4 life.", 1, 1)
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)


class Kinship(unittest.TestCase):
    def fire(self, top):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        game.turn, game.step = 1, "upkeep"
        perm = Permanent(SHAMAN, a)
        a.battlefield.append(perm)
        a.library = [ISLAND] * 5 + [top]
        eff = SHAMAN.triggers[0].effects[0]
        life = a.life
        game.resolve(a, eff, None, StackItem(card=SHAMAN, controller=a, effects=[eff], targets=[], source=perm))
        return a.life - life

    def test_parses(self):
        self.assertEqual(SHAMAN.unsupported, [])
        self.assertEqual(SHAMAN.triggers[0].effects[0].kind, "kinship")

    def test_shared_type_pays_off(self):
        self.assertEqual(self.fire(ELF), 4)

    def test_other_type_does_nothing(self):
        self.assertEqual(self.fire(BEAR), 0)


if __name__ == "__main__":
    unittest.main()
