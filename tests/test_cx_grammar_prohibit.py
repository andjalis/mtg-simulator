"""The prohibition verb family (mtgsim.cx_grammar_prohibit): players can't cast ..."""
import unittest

from mtgsim.advanced_templates import cast_allowed
from mtgsim.cx_grammar import parse_sentence

from tests.test_cx_grammar import Base
from tests.test_templates import BEAR, card

BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")


class Statics(Base):
    def test_you_cant_cast_creature_spells(self):
        self.perm(card("Test Ban", "{1}", "Enchantment", "You can't cast creature spells."), self.a)
        self.assertFalse(cast_allowed(self.game, self.a, BEAR))
        self.assertTrue(cast_allowed(self.game, self.a, BOLT))
        self.assertTrue(cast_allowed(self.game, self.b, BEAR))

    def test_your_opponents_cant_cast_instants_or_sorceries(self):
        self.perm(card("Test Ban", "{1}", "Enchantment", "Your opponents can't cast instant or sorcery spells."), self.a)
        self.assertFalse(cast_allowed(self.game, self.b, BOLT))
        self.assertTrue(cast_allowed(self.game, self.a, BOLT))
        self.assertTrue(cast_allowed(self.game, self.b, BEAR))

    def test_rejects(self):
        for s in ("Your opponents can't cast spells with the chosen name.", "You can't cast creature spells unless you pay {2}.",
                  "Your opponents can't cast spells during combat."):
            self.assertIsNone(parse_sentence(s), s)


class ThisTurn(Base):
    def test_target_player_this_turn(self):
        self.cast(self.spell("Target player can't cast creature spells this turn."), [self.b])
        self.assertFalse(cast_allowed(self.game, self.b, BEAR))
        self.assertTrue(cast_allowed(self.game, self.a, BEAR))
        self.game.turn += 1
        self.assertTrue(cast_allowed(self.game, self.b, BEAR))


class AIUse(Base):
    def test_ai_aims_it_at_the_opponent(self):
        spell = self.spell("Target player can't cast creature spells this turn.")
        with self.game.targeting(spell):
            self.assertIs(self.a.ai.choose_target(self.game, self.a, spell.spell_effects[0], spell), self.b)

    def test_ai_casts_a_lock_on_the_opponent(self):
        spell = card("Test Silence", "{W}", "Sorcery", "Your opponents can't cast spells this turn.")
        self.assertEqual(spell.unsupported, [])
        self.b.hand = [BOLT, BOLT, BEAR]
        plan = self.a.ai.plan_spell(self.game, self.a, spell, precombat=True)
        self.assertIsNotNone(plan)
        self.assertGreater(plan[0], 0)


if __name__ == "__main__":
    unittest.main()
