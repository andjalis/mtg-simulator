"""Conditional self statics: "~ gets +2/+2 as long as you have 25 or more life", "~ has flying as long as you
control an artifact"."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

ANGEL = card("Test Angel", "{3}{W}", "Creature — Angel", "~ gets +2/+2 as long as you have 25 or more life.", 2, 2)
TINKERER = card("Test Tinkerer", "{1}{U}", "Creature — Human", "~ has flying as long as you control an artifact.", 1, 1)
ARTILLERIST = card("Test Artillerist", "{2}{G}", "Creature — Human",
                   "~ has reach as long as it has a +1/+1 counter on it.", 2, 2)
VIGIL = card("Test Vigil", "{1}{W}", "Creature — Human",
             "~ has vigilance as long as there are three or more card types among cards in your graveyard.", 2, 2)
COHORT = card("Test Cohort", "{1}{B}", "Creature — Human", "~ gets +1/+1 as long as you control another black creature.", 2, 2)
UNDERLING = card("Test Underling", "{1}{R}", "Creature — Goblin",
                 "As long as you have seven or more cards in hand, ~ gets +2/+1 and has first strike.", 1, 1)
VANGUARD = card("Test Vanguard", "{1}{W}", "Creature — Human", "As long as ~ is attacking, it gets +2/+0.", 1, 1)
BLACKBEAR = card("Black Bear", "{1}{B}", "Creature — Bear", "", 2, 2)
ROCK = card("Test Rock", "{1}", "Artifact", "")


class Conditional(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"

    def put(self, c):
        perm = self.game.enter_battlefield(self.a, c)
        self.game.settle()
        return perm

    def test_fully_parsed(self):
        for c in (ANGEL, TINKERER, ARTILLERIST, VIGIL):
            self.assertEqual(c.unsupported, [], c.name)

    def test_life_pump(self):
        angel = self.put(ANGEL)
        self.a.life = 24
        self.assertEqual(angel.power, 2)
        self.a.life = 25
        self.assertEqual((angel.power, angel.toughness), (4, 4))

    def test_keyword_needs_artifact(self):
        t = self.put(TINKERER)
        self.assertFalse(t.has("flying"))
        self.put(ROCK)
        self.assertTrue(t.has("flying"))

    def test_counter_gate(self):
        a = self.put(ARTILLERIST)
        self.assertFalse(a.has("reach"))
        a.counters["+1/+1"] = 1
        self.assertTrue(a.has("reach"))

    def test_leading_form_and_another(self):
        for c in (COHORT, UNDERLING, VANGUARD):
            self.assertEqual(c.unsupported, [], c.name)
        cohort = self.put(COHORT)
        self.assertEqual(cohort.power, 2)       # itself is black but "another" is required
        self.put(BLACKBEAR)
        self.assertEqual(cohort.power, 3)
        under = self.put(UNDERLING)
        self.a.hand = [BEAR] * 6
        self.assertEqual(under.power, 1)
        self.a.hand = [BEAR] * 7
        self.assertEqual((under.power, under.toughness, under.has("first strike")), (3, 2, True))

    def test_graveyard_types(self):
        v = self.put(VIGIL)
        self.a.graveyard.extend([BEAR, ROCK])
        self.assertFalse(v.has("vigilance"))
        self.a.graveyard.append(ISLAND)
        self.assertTrue(v.has("vigilance"))


if __name__ == "__main__":
    unittest.main()
