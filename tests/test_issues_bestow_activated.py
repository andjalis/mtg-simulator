"""Issue 285: a bestowed Aura keeps the card's activated abilities (CR 702.103)."""
import random
import unittest

from mtgsim.batch1_templates import bestow_face, unbestow
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import PLAINS, card

TEXT = "Bestow {5}{B}{B}\n{1}: You gain 1 life.\nEnchanted creature gets +3/+3."
COST = {"generic": 5, "B": 2}


def spirit():
    return card("Test Spirit", "{1}{B}", "Enchantment Creature — Spirit", TEXT, 3, 3)


def setup(face):
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 2, "main1"
    a.library = b.library = [PLAINS] * 10
    host = g.enter_battlefield(a, card("Test Host", "{1}", "Creature — Human", "", 1, 1))
    aura = g.enter_battlefield(a, face)
    aura.attached_to = host
    g.settle()
    return g, a, aura


class BestowKeepsActivated(unittest.TestCase):
    def test_parsed(self):
        self.assertEqual(len(spirit().activated), 1)

    def test_face_keeps_activated(self):
        self.assertEqual(len(bestow_face(spirit(), COST).activated), 1)

    def test_usable_while_bestowed(self):
        g, a, aura = setup(bestow_face(spirit(), COST))
        a.battlefield.append(g.enter_battlefield(a, PLAINS))
        self.assertFalse(aura.is_creature)
        self.assertTrue(g.can_activate(a, aura, 0))
        life = a.life
        self.assertTrue(g.activate_ability(a, aura, 0))
        g.settle()
        self.assertEqual(a.life, life + 1)

    def test_usable_after_falling_off(self):
        g, a, aura = setup(bestow_face(spirit(), COST))
        unbestow(g, aura)
        aura.attached_to = None
        g.enter_battlefield(a, PLAINS)
        self.assertTrue(aura.is_creature)
        self.assertTrue(g.can_activate(a, aura, 0))

    def test_creature_only_ability_does_not_break(self):
        c = card("Test Tapper", "{1}{B}", "Enchantment Creature — Spirit",
                 "Bestow {5}{B}{B}\n{T}: Draw a card.\nEnchanted creature gets +1/+1.", 1, 1)
        g, a, aura = setup(bestow_face(c, COST))
        self.assertFalse(g.can_activate(a, aura, 0) and aura.is_creature)
        unbestow(g, aura)
        aura.attached_to = None
        aura.sick = False
        self.assertTrue(g.can_activate(a, aura, 0))


if __name__ == "__main__":
    unittest.main()
