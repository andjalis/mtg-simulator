"""Pack attack triggers, "becomes the target ... an opponent controls", and counted P/T."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SHOCK, card

ELITE = card("Test Elite", "{1}{R}{W}", "Creature — Human",
             "Whenever ~ and at least two other creatures attack, ~ gets +2/+2 until end of turn.", 2, 2)
MOSSDOG = card("Test Mossdog", "{2}{G}", "Creature — Plant Dog",
               "Whenever ~ becomes the target of a spell or ability an opponent controls, put a +1/+1 counter on ~.", 1, 1)
BURDEN = card("Test Burden", "{3}", "Creature — Beast",
              "~'s power and toughness are each equal to the number of creatures on the battlefield.", 0, 0)
MYCO = card("Test Myco", "{3}", "Creature — Fungus",
            "~'s power and toughness are each equal to the number of other creature cards in your graveyard.", 0, 0)


class Events(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parse(self):
        for c in (ELITE, MOSSDOG, BURDEN, MYCO):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual((ELITE.triggers[0].event, ELITE.triggers[0].filter), ("attacks", "pack:2"))

    def test_counted_pt(self):
        burden = self.game.enter_battlefield(self.a, BURDEN)
        self.game.enter_battlefield(self.b, BEAR)
        self.game.settle()
        self.assertEqual(burden.power, 2)
        self.a.graveyard.extend([BEAR, BEAR, ISLAND])
        myco = self.game.enter_battlefield(self.a, MYCO)
        self.assertEqual((myco.power, myco.toughness), (2, 2))

    def test_opponent_targeting_triggers(self):
        dog = self.game.enter_battlefield(self.a, MOSSDOG)
        self.game.settle()
        self.game.enter_battlefield(self.b, MOUNTAIN).tapped = False
        self.b.hand = [SHOCK]
        self.game.active_idx = 1
        self.assertTrue(self.game.cast(self.b, SHOCK, [dog]))
        self.game.settle()
        self.assertEqual(dog.counters.get("+1/+1", 0), 1)


if __name__ == "__main__":
    unittest.main()
