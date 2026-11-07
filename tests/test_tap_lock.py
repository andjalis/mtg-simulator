"""Tap-locks: "doesn't untap during its controller's untap step for as long as ..." is a persistent link."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, StackItem

from tests.test_templates import BEAR, ISLAND


class TapLock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_parse_is_full(self):
        for name in ("Merchant Raiders", "Mana Leech", "Amber Prison", "Icefall Regent", "Time of Ice"):
            self.assertFalse([n for n in self.db.get(name).approximations if "tap-lock" in n], name)

    def test_controlled_lock_holds_until_the_source_leaves(self):
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.enter_battlefield(self.a, self.db.get("Merchant Raiders"))
        self.game.settle()
        self.assertTrue(bear.tapped)
        self.game.untap_step(self.b)
        self.assertTrue(bear.tapped)                      # not just one skipped untap step
        self.game.untap_step(self.b)
        self.assertTrue(bear.tapped)
        raiders = next(x for x in self.a.battlefield if x.card.name == "Merchant Raiders")
        self.game.leave_battlefield(raiders, "graveyard")
        self.game.untap_step(self.b)
        self.assertFalse(bear.tapped)

    def test_tapped_lock_holds_while_the_source_stays_tapped(self):
        leech = self.game.enter_battlefield(self.a, self.db.get("Mana Leech"))
        land = self.game.enter_battlefield(self.b, self.db.get("Island"))
        ability = leech.card.activated[0]
        leech.tapped = True                               # the {T} cost
        self.game.stack.append(StackItem(self.a, list(ability.effects), [land], source=leech, name="Mana Leech ability"))
        self.game.resolve_top()
        self.assertTrue(land.tapped)
        for _ in range(2):
            self.game.untap_step(self.b)
            self.assertTrue(land.tapped)
        leech.tapped = False
        self.game.untap_step(self.b)
        self.assertFalse(land.tapped)

    def test_ai_locks_the_opponents_creature_for_good(self):
        """A real turn: HeuristicAI casts Merchant Raiders and its trigger locks the opponent's creature down."""
        bear = self.game.enter_battlefield(self.b, BEAR)
        for _ in range(4):
            self.game.enter_battlefield(self.a, self.db.get("Island")).sick = False
        self.a.hand = [self.db.get("Merchant Raiders")]
        self.a.library = [self.db.get("Giant Growth")] * 20
        self.game.take_turn(self.a)
        self.assertTrue(any(x.card.name == "Merchant Raiders" for x in self.a.battlefield))
        self.assertTrue(bear.tapped)
        self.game.take_turn(self.b)                       # their untap step doesn't free it
        self.assertTrue(bear.tapped)


if __name__ == "__main__":
    unittest.main()
