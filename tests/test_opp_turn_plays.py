"""#853: the AI plays land denial in the opponent's upkeep and answers a big spell with "damage to target spell's
controller" (Solfatara, Turf Wound, Pardic Miner, Parallectric Feedback)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
MOUNTAIN = card("Mountain", "", "Basic Land — Mountain", "({T}: Add {R}.)")
FOREST = card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 20, [ISLAND] * 20
    return g, a, b


def put(g, p, c, n=1):
    for _ in range(n):
        perm = g.enter_battlefield(p, c)
        perm.sick = False
    g.settle()
    return perm


def lands(p):
    return sum(x.card.is_land for x in p.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class LandDenialInTheirUpkeep(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def _their_turn(self, mine=None, hand=None, their_lands=1):
        g, a, b = game()
        a.my_turn, b.my_turn = False, True
        put(g, a, MOUNTAIN, 3)
        if mine:
            put(g, a, self.db.get(mine))
        a.hand = [self.db.get(hand)] if hand else []
        put(g, b, ISLAND, their_lands)
        b.hand = [ISLAND, BEAR]
        g.take_turn(b)
        return g, a, b

    def test_solfatara_in_their_upkeep(self):
        g, a, b = self._their_turn(hand="Solfatara")
        self.assertEqual(lands(b), 1)                 # the land drop was denied
        self.assertTrue(any("casts Solfatara -> [b" in e for e in g.events))

    def test_pardic_miner_early(self):
        g, a, b = self._their_turn(mine="Pardic Miner")
        self.assertEqual(lands(b), 1)
        self.assertFalse(any(x.card.name == "Pardic Miner" for x in a.battlefield))

    def test_pardic_miner_kept_once_they_have_mana(self):
        g, a, b = self._their_turn(mine="Pardic Miner", their_lands=4)
        self.assertEqual(lands(b), 5)
        self.assertTrue(any(x.card.name == "Pardic Miner" for x in a.battlefield))

    def test_not_on_my_own_turn(self):
        g, a, b = game()
        a.my_turn, b.my_turn = True, False
        put(g, a, MOUNTAIN, 3)
        a.hand = [self.db.get("Solfatara"), ISLAND]
        g.take_turn(a)
        self.assertIn("Solfatara", [c.name for c in a.hand])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class DamageToTheSpellsController(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def _cast_into(self, spell, n_lands, life=20):
        g, a, b = game()
        a.my_turn, b.my_turn = True, False
        put(g, b, MOUNTAIN, 4)
        put(g, a, FOREST, n_lands)
        a.life = life
        b.hand = [self.db.get("Parallectric Feedback")]
        c = self.db.get(spell)
        a.hand = [c]
        self.assertTrue(g.cast(a, c, None))
        g.settle()
        return g, a, b

    def test_big_spell_is_punished(self):
        g, a, b = self._cast_into("Craw Wurm", 6)
        self.assertEqual(a.life, 14)
        self.assertEqual(b.hand, [])

    def test_small_spell_is_not(self):
        g, a, b = self._cast_into("Grizzly Bears", 2)
        self.assertEqual(a.life, 20)
        self.assertEqual(len(b.hand), 1)

    def test_small_spell_when_lethal(self):
        g, a, b = self._cast_into("Grizzly Bears", 2, life=2)
        self.assertTrue(g.over or a.life <= 0)


if __name__ == "__main__":
    unittest.main()
