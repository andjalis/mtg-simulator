"""#345 slice: abilities that work while a card is suspended ("Whenever an opponent casts a spell, if this card is
suspended, remove a time counter from it" / "... that player may put a time counter on this card")."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import card

ISLAND = card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")
KRAKEN = card("Test Kraken", "{4}{U}{U}{U}", "Creature — Kraken",
              "This creature can't be blocked.\nSuspend 9—{2}{U}\nWhenever an opponent casts a spell, if this card is "
              "suspended, remove a time counter from it.", 6, 6)
DRAGON = card("Test Pardic", "{4}{R}{R}", "Creature — Dragon",
              "Flying\nSuspend 2—{R}{R}\nWhenever an opponent casts a spell, if this card is suspended, that player "
              "may put a time counter on this card.", 4, 4)
OPT = card("Test Opt", "{U}", "Instant", "Draw a card.")


def game():
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    for p in (a, b):
        for _ in range(2):
            g.enter_battlefield(p, ISLAND).sick = False
    g.settle()
    return g, a, b


def suspend(p, c, n):
    p.exile.append(c)
    entry = [c, n]
    p.suspended.append(entry)
    return entry


class SuspendedTriggers(unittest.TestCase):
    def test_opponents_spell_ticks_it_down(self):
        g, a, b = game()
        entry = suspend(a, KRAKEN, 5)
        b.hand.append(OPT)
        self.assertTrue(g.cast(b, OPT))
        g.settle()
        self.assertEqual(entry[1], 4)

    def test_my_own_spell_does_not(self):
        g, a, b = game()
        entry = suspend(a, KRAKEN, 5)
        a.hand.append(OPT)
        g.cast(a, OPT)
        g.settle()
        self.assertEqual(entry[1], 5)

    def test_last_counter_casts_it(self):
        g, a, b = game()
        suspend(a, KRAKEN, 1)
        b.hand.append(OPT)
        g.cast(b, OPT)
        g.settle()
        self.assertTrue(any(x.card.name == "Test Kraken" for x in a.battlefield))
        self.assertEqual(a.suspended, [])

    def test_on_the_battlefield_it_does_nothing(self):
        g, a, b = game()
        kraken = g.enter_battlefield(a, KRAKEN)
        g.settle()
        b.hand.append(OPT)
        g.cast(b, OPT)
        g.settle()
        self.assertIn(kraken, a.battlefield)
        self.assertFalse(any("Test Kraken" in e and "trigger" in e for e in g.events))

    def test_pardic_dragon_gets_delayed(self):
        g, a, b = game()
        entry = suspend(a, DRAGON, 2)
        b.hand.append(OPT)
        g.cast(b, OPT)
        g.settle()
        self.assertEqual(entry[1], 3)


if __name__ == "__main__":
    unittest.main()
