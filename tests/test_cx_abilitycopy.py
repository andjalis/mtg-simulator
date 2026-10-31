"""cx_abilitycopy.py and copies.py: copying activated and triggered abilities."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

RINGS = card("Test Rings", "{3}", "Artifact", "Whenever you activate an ability, if it isn't a mana ability, you may "
                                              "pay {2}. If you do, copy that ability. You may choose new targets for "
                                              "the copy.")
FONT = card("Test Font", "{1}", "Artifact", "{1}: You gain 1 life.")
TAWNOS = card("Test Tawnos", "{U}{R}", "Creature — Human Artificer",
              "{1}, {T}: Copy target activated or triggered ability you control from an artifact source. "
              "You may choose new targets for the copy.", 1, 3)


class AbilityCopy(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.a.library = [ISLAND] * 5

    def lands(self, n):
        for _ in range(n):
            self.game.enter_battlefield(self.a, ISLAND).tapped = False

    def test_parse(self):
        for c in (RINGS, TAWNOS):
            self.assertEqual(c.unsupported, [], c.name)

    def test_rings_copies_paid_ability(self):
        self.game.enter_battlefield(self.a, RINGS)
        font = self.game.enter_battlefield(self.a, FONT)
        self.lands(3)
        self.assertTrue(self.game.activate_ability(self.a, font, 0))
        self.game.settle()
        self.assertEqual(self.a.life, 22)

    def test_rings_without_mana_does_not_copy(self):
        self.game.enter_battlefield(self.a, RINGS)
        font = self.game.enter_battlefield(self.a, FONT)
        self.lands(1)
        self.assertTrue(self.game.activate_ability(self.a, font, 0))
        self.game.settle()
        self.assertEqual(self.a.life, 21)

    def test_source_filter(self):
        from mtgsim.copies import _source_fits
        font = self.game.enter_battlefield(self.a, FONT)
        tawnos = self.game.enter_battlefield(self.a, TAWNOS)
        self.assertTrue(_source_fits(font, "artifact"))
        self.assertFalse(_source_fits(tawnos, "artifact"))
        self.assertTrue(_source_fits(font, "colorless"))
        self.assertFalse(_source_fits(tawnos, "colorless"))


if __name__ == "__main__":
    unittest.main()
