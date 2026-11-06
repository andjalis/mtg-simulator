"""The land-type verb family (mtgsim.cx_grammar_landtype)."""
import unittest

from mtgsim.cx_grammar import parse_sentence

from tests.test_cx_grammar import Base
from tests.test_templates import FOREST, ISLAND, card

DUAL = card("Test Dual", "", "Land", "{T}: Add {G} or {U}.")


class Resolving(Base):
    def test_becomes_an_island_until_end_of_turn(self):
        forest = self.perm(FOREST, self.b)
        self.cast(self.spell("Target land becomes an Island until end of turn."), [forest])
        self.assertEqual(set(forest.card.produces), {"U"})
        self.assertIn("Island", forest.card.subtypes)
        self.assertNotIn("Forest", forest.card.subtypes)
        self.game.turn += 1
        self.game.state_based_actions()
        self.assertEqual(set(forest.card.produces), {"G"})

    def test_nonbasic_loses_its_own_mana_for_good(self):
        dual = self.perm(DUAL, self.b)
        self.cast(self.spell("Target nonbasic land becomes a Mountain."), [dual])
        self.game.turn += 3
        self.game.state_based_actions()
        self.assertEqual(set(dual.card.produces), {"R"})

    def test_group_in_addition(self):
        island = self.perm(ISLAND, self.a)
        self.cast(self.spell("Lands you control become Swamps in addition to their other types until end of turn."))
        self.assertEqual(set(island.card.produces), {"U", "B"})

    def test_rejects(self):
        for s in ("Target permanent becomes a Forest.", "Target land becomes Islands until end of turn.",
                  "Target land becomes an Island this turn."):
            self.assertIsNone(parse_sentence(s), s)


class AIUse(Base):
    def test_ai_aims_it_at_their_land(self):
        self.perm(ISLAND, self.a)
        forest = self.perm(FOREST, self.b)
        spell = self.spell("Target land becomes an Island until end of turn.")
        with self.game.targeting(spell):
            self.assertIs(self.a.ai.choose_target(self.game, self.a, spell.spell_effects[0], spell), forest)


if __name__ == "__main__":
    unittest.main()
