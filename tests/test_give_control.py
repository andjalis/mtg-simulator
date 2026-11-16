"""#640: "Target opponent gains control of target creature you control" / "... all other permanents you control"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

DONATE = card("Test Donate", "{2}{U}", "Sorcery", "Target player gains control of target artifact, creature, or land you control.")
SWALLOW = card("Test Swallow", "{2}{U}", "Sorcery", "Target opponent gains control of all other permanents you control.")
ELF = card("Elf", "{1}", "Creature — Elf", "", 1, 1)
OGRE = card("Ogre", "{3}", "Creature — Ogre", "", 3, 3)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class GiveControl(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(DONATE.unsupported, [])
        self.assertEqual(DONATE.spell_effects[0].kind, "give_control_choice")
        self.assertEqual(SWALLOW.spell_effects[0].kind, "give_control_all")

    def test_refusals(self):
        for text in ("Target opponent gains control of target creature you control until end of turn.",
                     "Target opponent gains control of target creature."):
            self.assertTrue(card("Test Odd", "{1}", "Sorcery", text).unsupported, text)

    def test_donate_gives_the_chosen_permanent(self):
        g, a, b = game()
        elf = g.enter_battlefield(a, ELF)
        for _ in range(3):
            g.enter_battlefield(a, ISLAND)
        a.hand = [DONATE]
        self.assertTrue(g.cast(a, DONATE, [elf]))
        g.settle()
        self.assertIn(elf, b.battlefield)
        self.assertNotIn(elf, a.battlefield)

    def test_other_permanents_all_go(self):
        g, a, b = game()
        ogre = g.enter_battlefield(a, OGRE)
        lands = [g.enter_battlefield(a, ISLAND) for _ in range(4)]
        a.hand = [SWALLOW]
        self.assertTrue(g.cast(a, SWALLOW, [None]))
        g.settle()
        self.assertIn(ogre, b.battlefield)
        self.assertTrue(any(x in b.battlefield for x in lands))

    def test_ai_does_not_give_away_for_nothing(self):
        g, a, b = game()
        g.enter_battlefield(a, OGRE)
        for _ in range(4):
            g.enter_battlefield(a, ISLAND)
        a.hand = [DONATE, SWALLOW]
        g.active_idx = 0
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual(b.battlefield, [])


if __name__ == "__main__":
    unittest.main()
