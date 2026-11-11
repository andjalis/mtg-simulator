"""Blink templates (mtgsim.blink): exile, then return as a new object. Card text is written out."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, PLAINS, card

FLICKER = card("Test Flicker", "{1}{W}", "Instant",
               "Exile target nontoken permanent, then return it to the battlefield under its owner's control.")
HIDE = card("Test Hide", "{2}{W}", "Instant",
            "Exile target creature you control. Return it to the battlefield under its owner's control at the beginning of the next end step.")
SPACE = card("Test Space", "{1}{W}", "Instant",
             "Exile target artifact or creature, then return that card to the battlefield under its owner's control with a +1/+1 counter on it.")
TAPPED = card("Test Tapped", "{1}{W}", "Instant",
              "Exile target creature, then return it to the battlefield tapped under its owner's control.")
TWO = card("Test Two", "{2}{W}", "Instant",
           "Exile up to two target creatures you control, then return those cards to the battlefield under their owner's control.")
LATER = card("Test Later", "{2}{W}", "Instant",
             "Exile target creature. Return it to the battlefield tapped under your control at the beginning of the next end step.")
GOBLIN = card("Test Etb", "{2}", "Creature — Goblin", "When ~ enters, you gain 2 life.", 1, 1)
SPIRIT = card("Test Spirit", "{1}", "Creature — Spirit", "{1}: Exile ~, then return it to the battlefield under its owner's control.", 1, 1)


class BlinkTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        for _ in range(4):
            self.perm(PLAINS, self.a)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (FLICKER, HIDE, LATER, SPACE, TAPPED, TWO, SPIRIT):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_returns_a_new_object_and_triggers_etb(self):
        old = self.perm(GOBLIN, self.a)
        old.counters["+1/+1"] = 2
        old.damage = 1
        life = self.a.life
        self.a.hand = [FLICKER]
        self.game.cast(self.a, FLICKER, [old])
        self.game.settle()
        new = [x for x in self.a.battlefield if x.card.name == "Test Etb"]
        self.assertEqual(len(new), 1)
        self.assertIsNot(new[0], old)
        self.assertEqual((new[0].counters.get("+1/+1", 0), new[0].damage), (0, 0))
        self.assertEqual(self.a.life, life + 2)

    def test_returns_under_its_owners_control(self):
        theirs = self.perm(BEAR, self.b)
        self.b.battlefield.remove(theirs)
        theirs.controller = self.a
        self.a.battlefield.append(theirs)
        self.a.hand = [FLICKER]
        self.game.cast(self.a, FLICKER, [theirs])
        self.game.settle()
        self.assertEqual(len([x for x in self.b.battlefield if x.card.name == BEAR.name]), 1)

    def test_extra_counter_and_tapped(self):
        bear = self.perm(BEAR, self.a)
        self.a.hand = [SPACE]
        self.game.cast(self.a, SPACE, [bear])
        self.game.settle()
        new = [x for x in self.a.battlefield if x.card.name == BEAR.name]
        self.assertEqual(new[0].counters.get("+1/+1"), 1)
        other = self.perm(BEAR, self.b)
        self.a.hand = [TAPPED]
        self.game.cast(self.a, TAPPED, [other])
        self.game.settle()
        back = [x for x in self.b.battlefield if x.card.name == BEAR.name]
        self.assertEqual(len(back), 1)
        self.assertTrue(back[0].tapped)

    def test_delayed_return_waits_for_the_end_step(self):
        bear = self.perm(BEAR, self.b)
        self.a.hand = [LATER]
        self.game.cast(self.a, LATER, [bear])
        self.game.settle()
        for p in (self.a, self.b):
            self.assertFalse([x for x in p.battlefield if x.card.name == BEAR.name])
        self.game.begin_end_step(self.a)
        self.game.settle()
        back = [x for x in self.a.battlefield if x.card.name == BEAR.name]
        self.assertEqual(len(back), 1)
        self.assertTrue(back[0].tapped)

    def test_up_to_two_targets(self):
        one, two = self.perm(GOBLIN, self.a), self.perm(GOBLIN, self.a)
        life = self.a.life
        self.a.hand = [TWO]
        self.game.cast(self.a, TWO, [one, two])
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.name == "Test Etb"]), 2)
        self.assertEqual(self.a.life, life + 4)

    def test_self_blink(self):
        spirit = self.perm(SPIRIT, self.a)
        self.assertTrue(self.game.activate(self.a, spirit, "ability:0"))
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.name == "Test Spirit"]), 1)


if __name__ == "__main__":
    unittest.main()
