"""Static damage prevention over a source filter and a protected subject (mtgsim/cx_static_prevent.py)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, card

GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 3, 1)
KNIGHT = card("Test Knight", "{W}", "Creature — Human Knight", "", 2, 2)
CLERIC = card("Test Cleric", "{W}", "Creature — Human Cleric", "", 1, 3)
RELIC = card("Test Relic", "{2}", "Artifact", "")


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class StaticPrevention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 20, HeuristicAI())
        self.b = Player("b", [BEAR] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        for p in (self.a, self.b):
            p.library = list(p.deck)
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0

    def put(self, c, who=None):
        if isinstance(c, str):
            c = self.db.get(c)
            self.assertEqual(c.unsupported, [], c.name)
        return self.game.enter_battlefield(who or self.a, c)

    def hit(self, target, n, source, combat=False):
        before = target.life if isinstance(target, Player) else target.damage
        self.game.deal_damage(target, n, source.controller, source=source, combat=combat)
        after = target.life if isinstance(target, Player) else target.damage
        return abs(after - before)

    def test_color_source(self):
        self.put("Sphere of Law")                       # red sources: prevent 2
        goblin, knight = self.put(GOBLIN, self.b), self.put(KNIGHT, self.b)
        self.assertEqual(self.hit(self.a, 3, goblin), 1)
        self.assertEqual(self.hit(self.a, 3, knight), 3)

    def test_artifact_source(self):
        self.put("Sphere of Purity")                    # artifacts: prevent 1
        relic = self.put(RELIC, self.b)
        self.assertEqual(self.hit(self.a, 2, relic), 1)
        self.assertEqual(self.hit(self.a, 2, self.put(GOBLIN, self.b)), 2)

    def test_conditional_combat_only(self):
        staff = self.put("Thunderstaff")                # as long as untapped: creatures' combat damage to you, prevent 1
        goblin = self.put(GOBLIN, self.b)
        self.assertEqual(self.hit(self.a, 3, goblin, combat=True), 2)
        self.assertEqual(self.hit(self.a, 3, goblin), 3)                 # noncombat
        staff.tapped = True
        self.assertEqual(self.hit(self.a, 3, goblin, combat=True), 3)

    def test_during_your_turn(self):
        self.put("Personal Sanctuary")
        goblin = self.put(GOBLIN, self.b)
        self.assertEqual(self.hit(self.a, 3, goblin), 0)
        self.game.active_idx = 1
        self.assertEqual(self.hit(self.a, 3, goblin), 3)

    def test_protected_group(self):
        self.put("Daunting Defender")                   # Cleric creatures you control: prevent 1
        cleric, knight = self.put(CLERIC), self.put(KNIGHT)
        goblin = self.put(GOBLIN, self.b)
        self.assertEqual(self.hit(cleric, 2, goblin), 1)
        self.assertEqual(self.hit(knight, 1, goblin), 1)
        self.assertEqual(self.hit(self.a, 2, goblin), 2)

    def test_two_subjects(self):
        self.put("Blessed Sanctuary")                   # noncombat damage to you and creatures you control
        knight, goblin = self.put(KNIGHT), self.put(GOBLIN, self.b)
        self.assertEqual(self.hit(self.a, 2, goblin), 0)
        self.assertEqual(self.hit(knight, 1, goblin), 0)
        self.assertEqual(self.hit(knight, 1, goblin, combat=True), 1)

    def test_to_and_by(self):
        bank = self.put("Fog Bank")                     # combat damage to and by it
        goblin = self.put(GOBLIN, self.b)
        self.assertEqual(self.hit(bank, 3, goblin, combat=True), 0)
        self.assertEqual(self.hit(goblin, 2, bank, combat=True), 0)
        self.assertEqual(self.hit(bank, 1, goblin), 1)

    def test_level_up_blocks_left_alone(self):
        self.assertEqual(len(self.db.get("Hedron-Field Purists").unsupported), 2)


if __name__ == "__main__":
    unittest.main()
