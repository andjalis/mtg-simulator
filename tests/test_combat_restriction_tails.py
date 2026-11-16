"""#518: attack/block restriction tails: max speed (Hazoret), "an enchanted permanent" (Godhunter Octopus),
"can't attack alone unless he has a +1/+1 counter on him" (Pipsqueak), soulbond pairing (Flowering Lumberknot)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cx_condlib import as_static
from mtgsim.cx_static_combat import declaration_group
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class RestrictionTails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [self.db.get("Island")] * 5

    def put(self, name, who=None):
        x = self.g.enter_battlefield(who or self.a, self.db.get(name))
        x.sick = False
        return x

    def test_parse(self):
        for name in ("Hazoret, Godseeker", "Godhunter Octopus", "Pipsqueak, Rebel Strongarm", "Flowering Lumberknot"):
            self.assertEqual(self.db.get(name).unsupported, [], name)
        self.assertEqual(as_static("you have high speed"), "")
        self.assertEqual(as_static("it's paired with a Human"), "")
        self.assertTrue(self.db.get("Joint Assault").unsupported)          # "that creature" is the partner: not read
        rules = self.db.get("Shardmage's Rescue").advanced_rules        # "enchanted creature" is still the host
        self.assertNotIn("anthem_if", rules)
        self.assertIn("gated", rules)

    def test_hazoret_needs_max_speed(self):
        hazoret = self.put("Hazoret, Godseeker")
        self.a.speed = 3
        self.assertFalse(hazoret.can_attack())
        self.a.speed = 4
        self.assertTrue(hazoret.can_attack())

    def test_godhunter_octopus(self):
        octopus = self.put("Godhunter Octopus")
        bear = self.put("Grizzly Bears", self.b)
        self.assertFalse(octopus.can_attack())
        from mtgsim.auras import attach
        aura = self.g.enter_battlefield(self.a, self.db.get("Pacifism"))     # my Aura on their creature
        if aura not in bear.auras:
            attach(self.g, aura, bear)
        self.g.settle()
        self.assertTrue(bear.auras)
        self.assertTrue(octopus.can_attack())                                # they control an enchanted permanent
        self.g.leave_battlefield(aura, "graveyard")
        self.g.settle()
        self.assertFalse(octopus.can_attack())
        self.put("Glorious Anthem", self.b)
        self.assertTrue(octopus.can_attack())                                # an enchantment

    def test_pipsqueak_alone(self):
        pip = self.put("Pipsqueak, Rebel Strongarm")
        friend = self.put("Grizzly Bears")
        self.assertEqual(declaration_group([pip], "attack"), [])
        self.assertEqual(declaration_group([pip, friend], "attack"), [pip, friend])
        pip.counters["+1/+1"] = 1
        self.assertEqual(declaration_group([pip], "attack"), [pip])

    def test_lumberknot_needs_a_partner(self):
        knot = self.put("Flowering Lumberknot")
        self.assertFalse(knot.can_attack())
        partner = self.put("Grizzly Bears")
        knot.partner, partner.partner = partner, knot
        self.assertTrue(knot.can_attack())
        self.g.leave_battlefield(partner, "graveyard")
        self.g.settle()
        self.assertFalse(knot.can_attack())


if __name__ == "__main__":
    unittest.main()
