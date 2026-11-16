"""Aura restrictions the plain "Enchant creature" list doesn't know: colour alternatives, "nonblack", tapped
creatures, a Mountain (#637 residue: Controlled Instincts)."""
import random
import unittest

from mtgsim import auras
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card


def aura(restriction):
    return card("Test Aura", "{1}{U}", "Enchantment — Aura",
                f"Enchant {restriction}\nEnchanted creature doesn't untap during its controller's untap step.")


class AuraRestrictions(unittest.TestCase):
    def setUp(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(a, b, random.Random(0), log=True)
        self.g.turn, self.g.step = 1, "main1"
        a.library = b.library = [ISLAND] * 10
        self.a, self.b = a, b
        mk = lambda n, c, t: card(n, c, "Creature — Test", "", 2, 2)
        self.red = self.g.enter_battlefield(b, mk("Red Guy", "{1}{R}", ""))
        self.green = self.g.enter_battlefield(b, mk("Green Guy", "{1}{G}", ""))
        self.black = self.g.enter_battlefield(b, mk("Black Guy", "{1}{B}", ""))

    def hosts(self, restriction):
        c = aura(restriction)
        self.assertEqual(c.unsupported, [], restriction)
        return set(map(id, auras.hosts(self.g, self.a, c)))

    def test_red_or_green(self):
        self.assertEqual(self.hosts("red or green creature"), {id(self.red), id(self.green)})

    def test_nonblack(self):
        self.assertEqual(self.hosts("nonblack creature"), {id(self.red), id(self.green)})

    def test_tapped(self):
        self.black.tapped = True
        self.assertEqual(self.hosts("tapped creature"), {id(self.black)})

    def test_enters_tapped_and_stays_tapped(self):
        c = card("Test Traxos", "{4}", "Artifact Creature — Construct",
                 "~ enters tapped and doesn't untap during your untap step.", 7, 7)
        self.assertEqual(c.unsupported, [])
        self.assertTrue(c.no_untap and c.enters_tapped)

    def test_unknown_restriction_stays_unsupported(self):
        self.assertTrue(aura("creature that frobs").unsupported)


if __name__ == "__main__":
    unittest.main()
