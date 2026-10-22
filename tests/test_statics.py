"""General static anthems and keyword grants (statics.py)."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

TRAMPLER = card("Test Lord", "{2}{G}", "Creature — Elf", "Other creatures you control have trample.", 2, 2)
CRUSADE = card("Test Crusade", "{W}{W}", "Enchantment", "White creatures get +1/+1.")
SLIVER = card("Test Sliver", "{1}{R}", "Creature — Sliver", "All Sliver creatures have haste.", 2, 2)
CHIEF = card("Test Chief", "{2}{R}", "Creature — Goblin", "Other Goblin creatures you control get +1/+1 and have haste.", 2, 2)
GLOOM = card("Test Gloom", "{2}{B}", "Enchantment", "Creatures your opponents control get -1/-1.")
FURY = card("Test Fury", "{2}{R}", "Enchantment", "Attacking creatures you control have double strike.")
GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
TROLL = card("Test Troll", "{2}{R}", "Creature — Troll", "~ gets +1/+2 as long as you control a Plains.", 2, 2)
ROC = card("Test Roc", "{3}{W}", "Creature — Bird", "~ has flying as long as you control a Mountain or a Plains.", 2, 2)
PLAINS = card("Plains", "", "Basic Land — Plains", "({T}: Add {W}.)")
DARTER = card("Test Darter", "{2}{U}", "Creature — Merfolk", "~ can't be blocked by black or green creatures.", 2, 2)
KNIGHT = card("Test Knight", "{1}{W}", "Creature — Human Knight", "", 2, 2)


class Statics(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_templates(self):
        for c in (TRAMPLER, CRUSADE, SLIVER, CHIEF, GLOOM, FURY, TROLL, ROC, DARTER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_other_keyword_and_color_anthem(self):
        lord = self.put(self.a, TRAMPLER)
        bear = self.put(self.a, BEAR)
        self.assertTrue(bear.has("trample"))
        self.assertFalse(lord.has("trample"))
        self.put(self.a, CRUSADE)
        knight, theirs = self.put(self.a, KNIGHT), self.put(self.b, KNIGHT)
        self.assertEqual((knight.power, theirs.power, bear.power), (3, 3, 2))   # every white creature

    def test_type_lords_and_opponents(self):
        self.put(self.b, SLIVER)
        mine = self.put(self.a, card("Test Sliver 2", "{1}", "Creature — Sliver", "", 1, 1))
        self.assertTrue(mine.has("haste"))                      # "All Sliver creatures": theirs too
        self.put(self.a, CHIEF)
        goblin = self.put(self.a, GOBLIN)
        self.assertEqual(goblin.power, 2)
        self.assertTrue(goblin.has("haste"))
        theirs = self.put(self.b, GOBLIN)
        self.put(self.a, GLOOM)
        self.game.settle()
        self.assertNotIn(theirs, self.b.battlefield)            # 1/1 with -1/-1 dies
        self.assertIn(goblin, self.a.battlefield)

    def test_as_long_as_you_control(self):
        troll, roc = self.put(self.a, TROLL), self.put(self.a, ROC)
        self.assertEqual((troll.power, troll.toughness, roc.has("flying")), (2, 2, False))
        self.put(self.a, PLAINS)
        self.assertEqual((troll.power, troll.toughness, roc.has("flying")), (3, 4, True))

    def test_cant_be_blocked_by(self):
        from mtgsim.engine.state import can_block
        darter = self.put(self.a, DARTER)
        self.assertFalse(can_block(self.put(self.b, BEAR), darter))        # green
        self.assertTrue(can_block(self.put(self.b, KNIGHT), darter))       # white

    def test_attacking_creatures(self):
        self.put(self.a, FURY)
        bear = self.put(self.a, BEAR)
        self.assertFalse(bear.has("double strike"))
        self.a.ai.attack = [bear]
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 16)


if __name__ == "__main__":
    unittest.main()
