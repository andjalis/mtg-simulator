"""Counting templates (mtgsim.counting). Card text is written out so no card DB is needed."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

GOYF = card("Landy", "{1}{G}", "Creature — Lhurgoyf", "Landy's power and toughness are each equal to the number of lands you control.", "*", "*")
FIRE = card("Fire Fan", "{1}{R}", "Creature — Elemental", "Fire Fan gets +2/+0 for each other Mountain you control.", 1, 1)
SEER = card("Seer", "{1}{U}", "Sorcery", "Draw a card for each Island you control.")
CHEER = card("Cheer", "{W}", "Sorcery", "You gain 2 life for each creature you control.")
LOOT = card("Loot", "{U}", "Sorcery", "Discard up to two cards, then draw that many cards.")


class CountingTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (GOYF, FIRE, SEER, CHEER, LOOT):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_power_and_toughness_equal_to_lands(self):
        goyf = self.perm(GOYF, self.a)
        for _ in range(3):
            self.perm(ISLAND, self.a)
        self.assertEqual((goyf.power, goyf.toughness), (3, 3))

    def test_other_mountain_scaling(self):
        fan = self.perm(FIRE, self.a)
        self.perm(MOUNTAIN, self.a)
        self.perm(MOUNTAIN, self.a)
        self.assertEqual((fan.power, fan.toughness), (5, 1))

    def test_draw_and_gain_for_each(self):
        for _ in range(3):
            self.perm(ISLAND, self.a)
        self.perm(BEAR, self.a)
        hand = len(self.a.hand)
        self.game.resolve(self.a, SEER.spell_effects[0], None, StackItem(self.a, SEER.spell_effects, [None], card=SEER))
        self.assertEqual(len(self.a.hand), hand + 3)
        life = self.a.life
        self.game.resolve(self.a, CHEER.spell_effects[0], None, StackItem(self.a, CHEER.spell_effects, [None], card=CHEER))
        self.assertEqual(self.a.life, life + 2)


if __name__ == "__main__":
    unittest.main()
