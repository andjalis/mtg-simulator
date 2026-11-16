"""Fixes from the opus-refs behaviour audit, round 6 (2026-11-16): "If this spell was kicked, that player discards
three cards instead" (Hypnotic Cloud) replaced the targeted discard with one aimed at nobody."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
SWAMP = card("Swamp", "", "Basic Land — Swamp", "({T}: Add {B}.)")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 20, [ISLAND] * 20
    a.my_turn, b.my_turn = True, False
    return g, a, b


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class KickedThatPlayer(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def _cast(self, kicked):
        g, a, b = game()
        for _ in range(6):
            g.enter_battlefield(a, SWAMP)
        b.hand = [BEAR] * 5
        a.hand = [self.db.get("Hypnotic Cloud")]
        spell = next(o for o in g.spell_options(a) if (g._origin(o)[1] == "kicker") == kicked)
        self.assertTrue(g.cast(a, spell, [b]))
        g.settle()
        return a, b

    def test_kicked_target_player_discards_three(self):
        a, b = self._cast(True)
        self.assertEqual(len(b.hand), 2)
        self.assertEqual(a.hand, [])

    def test_unkicked_discards_one(self):
        a, b = self._cast(False)
        self.assertEqual(len(b.hand), 4)

    def test_kicked_version_keeps_the_player_target(self):
        card_ = self.db.get("Hypnotic Cloud")
        kick = next(ac for ac in card_.alt_costs if ac.kind == "kicker")
        self.assertEqual([(e.kind, e.target, e.amount) for e in kick.effects], [("discard", "player", 3)])

    def test_that_player_after_a_creature_target_is_not_rebound(self):
        """Only a player target carries over: "that player" after "target creature" is its controller."""
        from mtgsim.cards.parse import _kicker_instead
        from mtgsim.cards.model import Effect
        base = [Effect("destroy", target="creature")]
        _kicker_instead(base, "that player discards three cards instead.")
        self.assertNotEqual(base[0].target, "creature")


if __name__ == "__main__":
    unittest.main()
