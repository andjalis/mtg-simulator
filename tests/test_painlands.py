"""Audit 2026-11-16 (opus-cast), round 5 (decks): painlands' "{T}: Add {W} or {U}. This land deals 1 damage to you."
dropped the damage, so painlands, Talismans and threshold lands made coloured mana for free (34 full cards, #801)."""
import unittest

from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import card

PAIN = card("Test Wastes", "", "Land", "{T}: Add {C}.\n{T}: Add {W} or {U}. ~ deals 1 damage to you.")
PIT = card("Test Pit", "", "Land", "{T}: Add {B}. ~ deals 1 damage to you.")
BLUE = card("Test Blue", "{U}", "Instant", "Draw a card.")
ONE = card("Test Colorless", "{1}", "Artifact", "")
BLACK_ONE = card("Test Generic", "{1}", "Instant", "Draw a card.")


class Painlands(Base):
    def cast(self, land, spell):
        self.game.turn, self.game.step = 1, "main1"
        self.a.battlefield = [Permanent(land, self.a)]
        self.a.hand = [spell]
        self.assertTrue(self.game.cast(self.a, spell, None))
        self.game.settle()
        return self.a.life

    def test_coloured_mana_deals_one(self):
        self.assertEqual(PAIN.mana_damage, 1)
        self.assertEqual(self.cast(PAIN, BLUE), 19)

    def test_colourless_is_free(self):
        """The {C} ability has no damage: a generic cost is paid with it."""
        self.assertEqual(self.cast(PAIN, ONE), 20)

    def test_a_single_damaging_ability_always_hurts(self):
        """Cabal Pit-style: its only mana ability deals the damage, even for a generic cost."""
        self.assertEqual(self.cast(PIT, BLACK_ONE), 19)

    def test_ai_mana_check_spares_its_last_life(self):
        """Like a pay-life source: the AI's payability check doesn't count it at 1 life."""
        self.game.turn, self.game.step = 1, "main1"
        self.a.battlefield = [Permanent(PAIN, self.a)]
        self.a.life = 1
        self.assertFalse(self.game.can_pay(self.a, {"U": 1, "generic": 0}))
        self.assertTrue(self.game.can_pay(self.a, {"generic": 1}))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_adarkar_wastes_and_sulfurous_springs(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name, spell in (("Adarkar Wastes", BLUE), ("Sulfurous Springs", card("Test Red", "{R}", "Instant",
                                                                                   "Draw a card."))):
            self.setUp()
            self.game.turn, self.game.step = 1, "main1"
            self.a.battlefield = [Permanent(db.get(name), self.a)]
            self.a.hand = [spell]
            self.assertTrue(self.game.cast(self.a, spell, None))
            self.game.settle()
            self.assertEqual(self.a.life, 19, name)


if __name__ == "__main__":
    unittest.main()
