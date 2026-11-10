"""Issue 274: a bestowed Aura keeps the card's triggered abilities (CR 702.103)."""
import random
import unittest

from mtgsim.batch1_templates import bestow_face
from mtgsim.cards.model import Effect, Trigger
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import PLAINS, card

HERALD = "Bestow {5}{B}{B}\nAt the beginning of your upkeep, you lose 1 life.\nEnchanted creature gets +3/+3."


def herald():
    return card("Test Herald", "{1}{B}", "Enchantment Creature — Spirit", HERALD, 3, 3)


class BestowKeepsTriggers(unittest.TestCase):
    def test_trigger_kept_on_face(self):
        face = bestow_face(herald(), {"generic": 5, "B": 2})
        self.assertEqual([t.event for t in face.triggers], ["upkeep"])

    def test_self_targeting_trigger_dropped(self):
        base = herald()
        base.triggers = list(base.triggers) + [Trigger("heroic", [Effect("p1_counters", amount=1, target="self")])]
        self.assertTrue(any(e.target == 'self' for t in base.triggers for e in t.effects))
        face = bestow_face(base, {"generic": 5, "B": 2})
        self.assertEqual([t.event for t in face.triggers], ["upkeep"])

    def test_upkeep_trigger_fires_while_bestowed(self):
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 2, "main1"
        a.library = b.library = [PLAINS] * 10
        host = g.enter_battlefield(a, card("Test Host", "{1}", "Creature — Human", "", 1, 1))
        aura = g.enter_battlefield(a, bestow_face(herald(), {"generic": 5, "B": 2}))
        aura.attached_to = host
        g.settle()
        life = a.life
        self.assertFalse(aura.is_creature)
        g.fire(a, "upkeep")
        g.settle()
        self.assertEqual(a.life, life - 1)


if __name__ == "__main__":
    unittest.main()
