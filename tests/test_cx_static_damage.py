"""Damage modifiers over a source filter and a recipient filter (mtgsim/cx_static_damage.py)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, card

GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 3, 1)
RELIC = card("Test Relic", "{2}", "Artifact", "")
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class DamageModifiers(unittest.TestCase):
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

    def dealt(self, target, n, source, by=None, combat=False):
        from mtgsim.engine.state import Player as P
        before = target.life if isinstance(target, P) else target.damage
        owner = by or source.controller
        self.game.deal_damage(target, n, owner, source=source, combat=combat)
        after = target.life if isinstance(target, P) else target.damage
        return abs(after - before)

    def test_double_everything(self):
        self.put("Furnace of Rath")
        mine, theirs = self.put(GOBLIN), self.put(BEAR, self.b)
        self.assertEqual(self.dealt(self.b, 2, mine), 4)
        self.assertEqual(self.dealt(self.a, 2, theirs), 4)

    def test_triple_own_sources_only(self):
        self.put("Fiery Emancipation")
        mine, theirs = self.put(GOBLIN), self.put(BEAR, self.b)
        self.assertEqual(self.dealt(self.b, 2, mine), 6)
        self.assertEqual(self.dealt(self.a, 2, theirs), 2)

    def test_creature_sources(self):
        self.put("Gratuitous Violence")
        self.assertEqual(self.dealt(self.b, 2, self.put(GOBLIN)), 4)
        self.assertEqual(self.dealt(self.b, 2, self.put(RELIC)), 2)

    def test_red_instant_spell(self):
        self.put("Fire Servant")                  # red instant or sorcery spells you control: double
        self.assertEqual(self.dealt(self.b, 3, BOLT, by=self.a), 6)
        self.assertEqual(self.dealt(self.b, 3, self.put(GOBLIN)), 3)     # a red permanent isn't a spell

    def test_red_or_artifact_to_opponent_side(self):
        self.put("Mechanized Warfare")            # red or artifact source you control, to an opponent's side: +1
        relic, goblin = self.put(RELIC), self.put(GOBLIN)
        theirs = self.put(BEAR, self.b)
        self.assertEqual(self.dealt(self.b, 2, relic), 3)
        self.assertEqual(self.dealt(theirs, 1, goblin), 2)
        self.assertEqual(self.dealt(self.a, 2, goblin), 2)               # to you: unchanged
        self.assertEqual(self.dealt(self.b, 2, self.put(BEAR)), 2)        # green creature: unchanged

    def test_noncombat_only(self):
        self.put("Tor Wauki the Younger")         # another source you control, noncombat: +1
        goblin = self.put(GOBLIN)
        self.assertEqual(self.dealt(self.b, 2, goblin), 3)
        self.assertEqual(self.dealt(self.b, 2, goblin, combat=True), 2)

    def test_condition(self):
        self.put("Anthem of Rakdos")              # hellbent: double
        goblin = self.put(GOBLIN)
        self.a.hand = [BEAR]
        self.assertEqual(self.dealt(self.b, 2, goblin), 2)
        self.a.hand = []
        self.assertEqual(self.dealt(self.b, 2, goblin), 4)

    def test_affected_player_orders_the_modifiers(self):
        self.put("Torbran, Thane of Red Fell")    # +2, then the opponent picks: double first, then +2
        self.put("Furnace of Rath")
        self.assertEqual(self.dealt(self.b, 2, self.put(GOBLIN)), 6)

    def test_combat_damage_in_a_game(self):
        self.put("Gratuitous Violence")
        goblin = self.put(GOBLIN)
        goblin.sick = False
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 14)         # 3 doubled


if __name__ == "__main__":
    unittest.main()
