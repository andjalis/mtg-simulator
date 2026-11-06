"""A bestowed Aura keeps the card's activated abilities (it only loses its creature characteristics)."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import PLAINS, card


class BestowKeepsAbilities(unittest.TestCase):
    def test_activated_ability_works_while_an_aura(self):
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 2, "main1"
        a.library = b.library = [PLAINS] * 10
        for _ in range(7):
            g.enter_battlefield(a, PLAINS).sick = False
        host = g.enter_battlefield(a, card("Test Host", "{1}", "Creature — Human", "", 1, 1))
        g.settle()
        spirit = card("Test Eidolon", "{1}{W}", "Enchantment Creature — Spirit",
                      "Bestow {3}{W}\nEnchanted creature gets +3/+3.\n{1}: You gain 2 life.", 2, 2)
        a.hand.append(spirit)
        variant = next(v for v in g.spell_options(a) if g._origin(v)[1] == "bestow")
        self.assertTrue(variant.activated)
        g.cast(a, variant)
        g.settle()
        aura = next(x for x in a.battlefield if x.card.name.startswith("Test Eidolon"))
        self.assertFalse(aura.is_creature)
        self.assertEqual(host.power, 4)
        life = a.life
        self.assertTrue(g.activate(a, aura, "ability:0"))
        g.settle()
        self.assertEqual(a.life, life + 2)


if __name__ == "__main__":
    unittest.main()
