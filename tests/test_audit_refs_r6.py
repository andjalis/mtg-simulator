"""Fixes from the opus-refs behaviour audit, round 6 (2026-11-16): a fight mode chosen after another mode of a
modal spell (Brigid's Command) found no fighter and did nothing."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
PLAINS = card("Plains", "", "Basic Land — Plains", "({T}: Add {W}.)")
FOREST = card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 20, [ISLAND] * 20
    a.my_turn, b.my_turn = True, False
    return g, a, b


def ready(g, p, c):
    perm = g.enter_battlefield(p, c)
    perm.sick = False
    g.settle()
    return perm


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class FightAfterAnotherMode(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def _board(self):
        g, a, b = game()
        for land in (FOREST, PLAINS, FOREST):
            ready(g, a, land)
        kith = ready(g, a, self.db.get("Kinsbaile Skirmisher"))
        bear = ready(g, b, BEAR)
        return g, a, b, kith, bear

    def test_copy_then_fight_resolves_the_fight(self):
        g, a, b, kith, bear = self._board()
        cmd = self.db.get("Brigid's Command")
        a.ai.choose_modes = lambda game, me, modes, n, strict: [0, 3]    # copy + "fights target creature"
        a.hand = [cmd]
        self.assertTrue(g.cast(a, cmd, [None, kith, bear]))
        g.settle()
        self.assertTrue(any("chooses modes 1, 4" in e for e in g.events))
        self.assertNotIn(bear, b.battlefield)
        self.assertEqual(kith.damage, 2)
        self.assertTrue(any("fights Grizzly Bears" in e for e in g.events))

    def test_ai_casts_it_and_the_fight_hits_the_opponent(self):
        g, a, b, kith, bear = self._board()
        a.hand = [self.db.get("Brigid's Command")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertNotIn(bear, b.battlefield)
        self.assertIn(kith, a.battlefield)
        self.assertTrue(any("fights Grizzly Bears" in e for e in g.events))

    def test_plain_fight_spell_still_uses_its_first_target(self):
        g, a, b, kith, bear = self._board()
        prey = self.db.get("Prey Upon")
        a.hand = [prey]
        self.assertTrue(g.cast(a, prey, [kith, bear]))
        g.settle()
        self.assertNotIn(bear, b.battlefield)

    def test_counter_then_that_creature_fights_still_works(self):
        """No fight mark: the fighter stays the first target ("Put a +1/+1 counter on target creature you
        control. Then that creature fights target creature you don't control.")."""
        g, a, b, kith, bear = self._board()
        ready(g, a, FOREST)
        spell = self.db.get("Hunt the Weak")
        a.hand = [spell]
        self.assertTrue(g.cast(a, spell, [kith, bear]))
        g.settle()
        self.assertNotIn(bear, b.battlefield)
        self.assertEqual(kith.counters.get("+1/+1"), 1)


if __name__ == "__main__":
    unittest.main()
