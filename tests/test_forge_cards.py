"""Demolition Field, Esper Origins and Uldaros Theorix (Forge comparison decks)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player

DB = CardDB(offline=True)


def perm(name, p):
    x = Permanent(DB.get(name), p)
    x.sick = False
    p.battlefield.append(x)
    return x


class ForgeCards(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [DB.get("Forest")] * 20

    def test_templates(self):
        for n in ("Demolition Field", "Esper Origins", "Uldaros Theorix"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_demolition_field_swaps_lands_for_both(self):
        field = perm("Demolition Field", self.a)
        victim = perm("Demolition Field", self.b)
        for _ in range(2):
            perm("Forest", self.a)
        self.assertTrue(self.game.activate_ability(self.a, field, 0))
        self.game.settle()
        self.assertNotIn(field, self.a.battlefield)
        self.assertNotIn(victim, self.b.battlefield)
        self.assertEqual(sum(x.card.name == "Forest" for x in self.b.battlefield), 1)
        self.assertEqual(sum(x.card.name == "Forest" for x in self.a.battlefield), 3)

    def test_esper_origins_flashback_returns_as_saga(self):
        origins = DB.get("Esper Origins")
        for _ in range(4):
            perm("Forest", self.a)
        self.a.graveyard = [origins]
        fb = next(c for c in self.game.spell_options(self.a) if "flashback" in c.name)
        self.game.cast(self.a, fb)
        self.game.settle()
        saga = next(x for x in self.a.battlefield if x.card.name == "Summon: Esper Maduin")
        self.assertEqual(saga.counters.get("finality"), 1)
        self.assertNotIn(origins, self.a.exile)

    def test_theorix_casts_free_spells_up_to_six(self):
        bolt, bear, giant = DB.get("Lightning Bolt"), DB.get("Grizzly Bears"), DB.get("Hill Giant")
        self.a.graveyard = [bolt, bear, giant]
        self.game.resolve(self.a, DB.get("Uldaros Theorix").etb_effects[0], None)
        self.game.settle()
        self.assertTrue(any(x.card.name == "Hill Giant" for x in self.a.battlefield))
        self.assertIn(bear, self.a.graveyard)     # only the best card of each type is exiled
        self.assertLess(self.b.life, 20)          # Lightning Bolt was cast for free


if __name__ == "__main__":
    unittest.main()
