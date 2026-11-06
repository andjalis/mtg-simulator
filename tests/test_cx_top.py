"""cx_top.py: playing lands and casting spells from the top of your library."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, SHOCK, card

COURSER = card("Test Courser", "{1}{G}{G}", "Enchantment", "You may play lands from the top of your library.")
RANGER = card("Test Ranger", "{1}{G}", "Enchantment", "You may cast creature spells from the top of your library.")
SIGHT = card("Test Sight", "{2}{U}", "Enchantment", "You may look at the top card of your library any time, and "
                                                    "you may play lands and cast spells from the top of your library.")
SIGARDA = card("Test Sigarda", "{2}{W}", "Enchantment",
               "You may cast Angel spells and Human spells from the top of your library.")


class Top(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"

    def test_parse(self):
        for c in (COURSER, RANGER, SIGHT, SIGARDA):
            self.assertEqual(c.unsupported, [], c.name)

    def test_play_land_from_top(self):
        self.game.enter_battlefield(self.a, COURSER)
        self.a.library = [BEAR, FOREST]
        top = self.a.library[-1]
        self.game.play_land(self.a, top)
        self.assertEqual([x.card.name for x in self.a.battlefield if x.card.is_land], ["Forest"])
        self.assertEqual(len(self.a.library), 1)

    def test_cast_creature_from_top(self):
        self.game.enter_battlefield(self.a, RANGER)
        for _ in range(2):
            self.game.enter_battlefield(self.a, FOREST).tapped = False
        self.a.library = [SHOCK, BEAR]
        opts = [o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "cx_top"]
        self.assertEqual([o.name for o in opts], [BEAR.name + " (cx_top)"])
        self.assertTrue(self.game.cast(self.a, opts[0], []))
        self.game.settle()
        self.assertIn(BEAR.name, [x.card.name for x in self.a.battlefield])
        self.assertEqual([c.name for c in self.a.library], [SHOCK.name])
        # Shock is now on top: not a creature spell, so no option
        self.assertFalse([o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "cx_top"])


if __name__ == "__main__":
    unittest.main()
