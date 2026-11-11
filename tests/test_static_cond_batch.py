"""Static-condition batch: capitalised 'Protection from X and from Y' lines."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import ISLAND, MOUNTAIN, card


class ProtectionAndFrom(unittest.TestCase):
    def test_capitalised_double_protection(self):
        c = card("Test Crusader", "{3}", "Creature — Human", "Protection from black and from red", 2, 2)
        self.assertEqual(c.unsupported, [])
        self.assertEqual(set(c.keywords), {"protection from black", "protection from red"})


WHISKER = card("Test Whisker", "{1}{U}", "Creature — Human",
               "Threshold — As long as there are seven or more cards in your graveyard, creatures your opponents control get -1/-0.", 1, 1)
BEAR = card("Test Bear", "{2}", "Creature — Bear", "", 2, 2)


class OpponentThresholdDebuff(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 10, HeuristicAI())
        self.b = Player("b", [ISLAND] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.whisker = self._put(self.a, WHISKER)
        self.mine = self._put(self.a, BEAR)
        self.theirs = self._put(self.b, BEAR)

    def _put(self, player, c):
        p = Permanent(c, player)
        player.battlefield.append(p)
        return p

    def test_parses(self):
        self.assertEqual(WHISKER.unsupported, [])

    def test_threshold_gates_and_scope(self):
        self.a.graveyard[:] = [ISLAND] * 6
        self.assertEqual(self.theirs.power, 2)
        self.a.graveyard.append(ISLAND)
        self.assertEqual(self.theirs.power, 1)
        self.assertEqual(self.theirs.toughness, 2)
        self.assertEqual(self.mine.power, 2)       # own creatures are untouched
        self.assertEqual(self.whisker.power, 1)


FIRE = card("Test Fire", "{2}{R}", "Instant", "~ deals 3 damage to any target. If at least three red mana was spent to cast ~, it deals 4 damage instead.")
DRAW = card("Test Insight", "{2}{U}", "Sorcery", "Draw a card. If at least three blue mana was spent to cast ~, draw two cards instead.")
PEEK = card("Test Peek", "{1}{G}", "Instant", "~ deals 1 damage to any target. If four or more mana was spent to cast ~, it deals 2 damage instead.")
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


class ManaSpentColour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 10, HeuristicAI())
        self.b = Player("b", [ISLAND] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def lands(self, *cards):
        for c in cards:
            p = Permanent(c, self.a)
            self.a.battlefield.append(p)

    def fire_at_face(self, spell, *lands):
        self.lands(*lands)
        self.b.life = 20
        self.a.hand[:] = [spell]
        self.assertTrue(self.game.cast(self.a, spell, [self.b]))
        self.game.settle()
        return 20 - self.b.life

    def test_templates(self):
        for c in (FIRE, DRAW, PEEK):
            self.assertEqual(c.unsupported, [], c.name)

    def test_three_red_mana_upgrades(self):
        self.assertEqual(self.fire_at_face(FIRE, MOUNTAIN, MOUNTAIN, MOUNTAIN), 4)

    def test_two_red_mana_does_not(self):
        self.assertEqual(self.fire_at_face(FIRE, MOUNTAIN, MOUNTAIN, ISLAND), 3)

    def test_total_mana_count(self):
        self.assertEqual(self.fire_at_face(PEEK, FOREST, FOREST), 1)

    def test_total_mana_count_met(self):
        peek4 = card("Test Peek Four", "{3}{G}", "Instant", PEEK.oracle_text if hasattr(PEEK, "oracle_text") else
                     "~ deals 1 damage to any target. If four or more mana was spent to cast ~, it deals 2 damage instead.")
        self.assertEqual(self.fire_at_face(peek4, FOREST, FOREST, FOREST, FOREST), 2)


PALADIN = card("Test Paladin", "{2}{R}", "Creature — Human Knight",
               "Adamant — If at least three red mana was spent to cast this spell, this creature enters with a +1/+1 counter on it.", 2, 2)


class AdamantEntry(unittest.TestCase):
    def cast_with(self, *lands):
        a = Player("a", [ISLAND] * 10, HeuristicAI())
        b = Player("b", [ISLAND] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 1, "main1"
        for c in lands:
            a.battlefield.append(Permanent(c, a))
        a.hand[:] = [PALADIN]
        self_ok = game.cast(a, PALADIN, [])
        game.settle()
        self.assertTrue(self_ok)
        return next(x for x in a.battlefield if x.card is PALADIN or x.card.name == PALADIN.name)

    def test_templates(self):
        self.assertEqual(PALADIN.unsupported, [])

    def test_adamant(self):
        self.assertEqual(self.cast_with(MOUNTAIN, MOUNTAIN, MOUNTAIN).counters.get("+1/+1", 0), 1)
        self.assertEqual(self.cast_with(MOUNTAIN, MOUNTAIN, ISLAND).counters.get("+1/+1", 0), 0)


if __name__ == "__main__":
    unittest.main()
