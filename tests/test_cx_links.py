"""Linked results: "you may X. If you do, Y" with an outcome check, and the top-card "if it's a ... card" sequence."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, card

TAPPER = card("Test Tapper", "{2}{U}", "Creature — Human",
              "When ~ enters, you may tap two untapped creatures you control. If you do, draw two cards.", 1, 1)
SACKER = card("Test Sacker", "{2}{B}", "Creature — Vampire",
              "When ~ enters, you may sacrifice an artifact. If you do, you gain 4 life.", 2, 2)
SCOUT = card("Test Scout", "{1}{G}", "Creature — Elf",
             "When ~ enters, look at the top card of your library. If it's a land card, you may put it onto the "
             "battlefield tapped. Otherwise, put it into your hand.", 1, 1)
JESTER = card("Test Jester", "{2}{R}", "Creature — Human",
              "When ~ enters, exile the top card of your library. If that card is a land card, you gain 3 life. "
              "Otherwise, you lose 1 life.", 2, 2)
TRINKET = card("Test Trinket", "{1}", "Artifact", "")
SNARL = card("Test Snarl", "", "Land",
             "As ~ enters, you may reveal an Island or Mountain card from your hand. If you don't, ~ enters tapped.\n"
             "{T}: Add {U} or {R}.")
EXERTER = card("Test Exerter", "{1}{R}", "Creature — Human Warrior",
               "You may exert ~ as it attacks. When you do, it gets +2/+0 until end of turn.", 2, 2)


class LinkParse(unittest.TestCase):
    def test_parse(self):
        for c in (TAPPER, SACKER, SCOUT, SNARL, EXERTER, JESTER):
            self.assertEqual(c.unsupported, [], c.name)


class LinkEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_if_you_do_needs_the_action(self):
        hand = len(self.a.hand)
        self.game.enter_battlefield(self.a, TAPPER)          # only itself: can't tap two
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)
        self.game.enter_battlefield(self.a, BEAR).tapped = False
        self.game.enter_battlefield(self.a, TAPPER)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 2)

    def test_sacrifice_filter(self):
        self.game.enter_battlefield(self.a, SACKER)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.game.enter_battlefield(self.a, TRINKET)
        self.game.enter_battlefield(self.a, SACKER)
        self.game.settle()
        self.assertEqual(self.a.life, 24)
        self.assertFalse(any(x.card is TRINKET for x in self.a.battlefield))

    def test_top_card(self):
        self.a.library = [ISLAND, FOREST]
        lands = sum(x.card.is_land for x in self.a.battlefield)
        self.game.enter_battlefield(self.a, SCOUT)
        self.game.settle()
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), lands + 1)
        self.a.library = [ISLAND, BEAR]
        self.game.enter_battlefield(self.a, SCOUT)
        self.game.settle()
        self.assertIn(BEAR, self.a.hand)

    def test_exiled_top_card(self):
        self.a.library = [BEAR, ISLAND]
        self.game.enter_battlefield(self.a, JESTER)
        self.game.settle()
        self.assertEqual(self.a.life, 23)
        self.game.enter_battlefield(self.a, JESTER)
        self.game.settle()
        self.assertEqual(self.a.life, 22)

    def test_reveal_land(self):
        self.a.hand = []
        self.assertTrue(self.game.enter_battlefield(self.a, SNARL).tapped)
        self.a.hand = [ISLAND]
        self.assertFalse(self.game.enter_battlefield(self.a, SNARL).tapped)

    def test_exert(self):
        from mtgsim.engine.state import StackItem
        trig = EXERTER.triggers[0]
        self.assertEqual(trig.event, "attacks")
        self.assertEqual([e.kind for e in trig.effects][:3], ["link_start", "exert_self", "link_check"])
        perm = self.game.enter_battlefield(self.a, EXERTER)
        item = StackItem(self.a, list(trig.effects), [None] * len(trig.effects), source=perm)
        for eff in trig.effects:
            if self.game.check_cond(self.a, eff, item, None):
                self.game.resolve(self.a, eff, None, item, None)
        self.assertEqual(perm.skip_untap, 1)
        self.assertTrue(item.gate_paid)

if __name__ == "__main__":
    unittest.main()
