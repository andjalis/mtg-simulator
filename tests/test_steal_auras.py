"""Audit 2026-11-16 (opus-cast), round 7: "You control enchanted creature/permanent." Auras (Control Magic,
Mind Control, Confiscate, ...) were not marked hostile, so they could only enchant the caster's own permanents
and never stole anything."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import card, BEAR

STEAL = card("Test Magic", "{2}{U}{U}", "Enchantment — Aura", "Enchant creature\nYou control enchanted creature.")
GIANT = card("Test Giant", "{5}", "Creature — Giant", "", 5, 5)
ISLAND = card("Island", "", "Basic Land — Island", "({T}: Add {U}.)")


def game():
    a = Player("A", [BEAR] * 10, HeuristicAI())
    b = Player("B", [BEAR] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0))
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 10, [ISLAND] * 10
    return g, a, b


class StealAuras(unittest.TestCase):
    def test_parse_hostile(self):
        self.assertTrue(STEAL.aura_hostile)

    def test_castable_on_their_creature_only(self):
        g, a, b = game()
        giant = Permanent(GIANT, b)
        b.battlefield = [giant]
        a.battlefield = [Permanent(ISLAND, a) for _ in range(4)]
        a.hand = [STEAL]
        self.assertTrue(g.can_cast_now(a, STEAL))
        a.battlefield.append(Permanent(BEAR, a))
        from mtgsim import auras
        self.assertEqual(auras.hosts(g, a, STEAL), [giant])

    def test_ai_steals_and_it_returns(self):
        """HeuristicAI casts it on the opponent's best creature; when the Aura leaves, control goes back."""
        g, a, b = game()
        giant = Permanent(GIANT, b)
        b.battlefield = [giant]
        a.battlefield = [Permanent(ISLAND, a) for _ in range(4)] + [Permanent(BEAR, a)]
        a.hand = [STEAL]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertIn(giant, a.battlefield)
        aura = next(p for p in a.battlefield if p.card.name == STEAL.name)
        g.destroy(aura)
        g.settle()
        self.assertIn(giant, b.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Control Magic", "Mind Control", "Treachery", "Confiscate", "Take Possession"):
            self.assertTrue(db.get(name).aura_hostile, name)


if __name__ == "__main__":
    unittest.main()
