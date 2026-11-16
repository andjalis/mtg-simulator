"""#646 slice 12: "Affinity for Equipment" (CR 702.41a: costs {1} less for each Equipment you control)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, MOUNTAIN, card

FINISHER = card("Test Finisher", "{6}{R}", "Creature — Ogre Warrior", "Affinity for Equipment\nTrample", 5, 5)
SWORD = card("Test Sword", "{2}", "Artifact — Equipment", "Equipped creature gets +1/+1.\nEquip {2}")
ROCK = card("Test Rock", "{1}", "Artifact", "")


class Parsing(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(FINISHER.unsupported, [])
        self.assertEqual(FINISHER.cost_reduction, "affinity:Equipment")


class Engine(Base):
    def test_each_equipment_reduces_the_cost(self):
        """CR 702.41a: {1} less for each Equipment you control; other artifacts don't count."""
        before = self.game.cost_of(self.a, FINISHER).get("generic")
        self.perm(SWORD, self.a)
        self.perm(SWORD, self.a)
        self.perm(ROCK, self.a)
        self.perm(SWORD, self.b)                              # not yours
        self.assertEqual(self.game.cost_of(self.a, FINISHER).get("generic"), before - 2)


class HeuristicUse(Base):
    def test_ai_casts_it_with_the_discount(self):
        self.game.step = "main1"
        self.a.hand = [FINISHER]
        self.a.battlefield = [Permanent(MOUNTAIN, self.a) for _ in range(4)] + \
            [Permanent(SWORD, self.a) for _ in range(3)] + [Permanent(BEAR, self.a)]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn("Test Finisher", [x.card.name for x in self.a.battlefield])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Oxidda Finisher", "Rebel Salvo"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()
