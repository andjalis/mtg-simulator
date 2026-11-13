"""#271: backup grants only the abilities printed below the keyword (CR 702.165a), not every ability of the card."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, PLAINS, card

TEXT = ("Whenever this creature attacks, you gain 1 life.\n"
        "{1}: This creature gets +1/+0 until end of turn.\n"
        "Backup 1\n"
        "Whenever this creature deals combat damage to a player, draw a card.\n"
        "{2}: This creature gets +0/+1 until end of turn.")


class BackupBelowOnly(unittest.TestCase):
    def test_only_abilities_below_backup_are_granted(self):
        c = card("Test Backer", "{2}{W}", "Creature — Human", TEXT, 2, 2)
        self.assertEqual(len(c.triggers), 3)
        self.assertEqual(len(c.activated), 2)
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 2, "main1"
        a.library = b.library = [PLAINS] * 10
        bear = g.enter_battlefield(a, BEAR)
        g.settle()
        g.enter_battlefield(a, c)
        g.settle()
        self.assertEqual(bear.counters.get("+1/+1"), 1)
        self.assertEqual([t.event for t in bear.temp_triggers], [c.triggers[2].event])
        self.assertEqual([x.text for x in bear.temp_activated], [c.activated[1].text])


if __name__ == "__main__":
    unittest.main()
