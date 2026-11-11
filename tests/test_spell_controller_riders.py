"""Spell targets and counterspell riders must keep the referenced spell's identity."""
import dataclasses
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, ISLAND, card

FEEDBACK = card("Parallectric Feedback", "{3}{R}", "Instant",
                "Parallectric Feedback deals damage to target spell's controller equal to that spell's mana value.")
BACKLASH = card("Essence Backlash", "{2}{U}{R}", "Instant",
               "Counter target creature spell. Essence Backlash deals damage equal to that spell's power to its controller.")


class SpellControllerRiderTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], None), Player("b", [], None)
        self.game = Game(self.a, self.b, random.Random(0))
        self.a.library = self.b.library = [ISLAND] * 20

    def spell(self, c=BEAR, controller=None, kind="spell"):
        it = StackItem(controller or self.b, [], [], card=c, kind=kind)
        self.game.stack.append(it)
        return it

    def resolve(self, c, target):
        it = StackItem(self.a, c.spell_effects, [target] + [None] * (len(c.spell_effects) - 1), card=c)
        self.game.stack.append(it)
        self.game.resolve_top()
        return it

    def test_controller_templates(self):
        self.assertEqual(FEEDBACK.unsupported, [])
        self.assertEqual(BACKLASH.unsupported, [])

    def test_feedback_targets_spell_and_leaves_it_on_stack(self):
        spell = self.spell()
        eff = FEEDBACK.spell_effects[0]
        self.assertEqual(self.game.auto_targets(self.a, [eff]), [spell])
        self.resolve(FEEDBACK, spell)
        self.assertEqual((self.a.life, self.b.life), (20, 18))
        self.assertIn(spell, self.game.stack)

    def test_feedback_can_be_cast_without_a_counter_effect(self):
        from mtgsim.engine import Permanent
        from tests.test_templates import MOUNTAIN
        self.game.turn, self.game.step = 1, "main1"
        for _ in range(4):
            self.a.battlefield.append(Permanent(MOUNTAIN, self.a))
        self.a.hand = [FEEDBACK]
        self.assertFalse(self.game.can_cast_now(self.a, FEEDBACK))
        spell = self.spell()
        self.assertTrue(self.game.can_cast_now(self.a, FEEDBACK))
        self.assertTrue(self.game.cast(self.a, FEEDBACK, [spell]))
        self.assertEqual(self.b.life, 18)

    def test_feedback_can_target_own_spell_and_copy_but_not_ability(self):
        own = self.spell(controller=self.a)
        copy = self.spell(kind="copy")
        ability = StackItem(self.b, [], [], kind="trigger")
        self.game.stack.append(ability)
        self.assertEqual(self.game.legal_targets(self.a, FEEDBACK.spell_effects[0]), [own, copy])
        self.resolve(FEEDBACK, own)
        self.assertEqual((self.a.life, self.b.life), (18, 20))

    def test_feedback_fizzles_when_spell_has_left(self):
        spell = self.spell()
        self.game.stack.remove(spell)
        it = self.resolve(FEEDBACK, spell)
        self.assertFalse(it.resolved)
        self.assertEqual(self.b.life, 20)

    def test_feedback_uses_x_on_stack(self):
        spell = self.spell(card("X spell", "{X}{X}{U}", "Instant", cmc=1))
        spell.x = 3
        self.resolve(FEEDBACK, spell)
        self.assertEqual(self.b.life, 13)

    def test_backlash_uses_power_after_spell_leaves_stack(self):
        creature = card("Giant", "{6}{R}", "Creature — Giant", "", 4, 4)
        spell = self.spell(creature)
        self.resolve(BACKLASH, spell)
        self.assertNotIn(spell, self.game.stack)
        self.assertIn(creature, self.b.graveyard)
        self.assertEqual(self.b.life, 16)

    def test_backlash_still_damages_when_spell_cannot_be_countered(self):
        spell = self.spell(dataclasses.replace(BEAR, uncounterable=True))
        self.resolve(BACKLASH, spell)
        self.assertIn(spell, self.game.stack)
        self.assertEqual(self.b.life, 18)

    def test_ambiguous_controller_stays_unmatched_without_counter(self):
        c = card("Ambiguous", "{R}", "Instant",
                 "Ambiguous deals damage equal to that spell's power to its controller.")
        self.assertTrue(c.unsupported)

    def test_controller_reference_survives_another_target(self):
        # The countered spell stays the referent after a later permanent target.
        from mtgsim.engine import Permanent
        mine = Permanent(BEAR, self.a)
        self.a.battlefield.append(mine)
        spell = self.spell()
        c = card("Rider", "{U}", "Instant", "Counter target spell. Target creature gets +1/+1 until end of turn. "
                 "Rider deals 2 damage to that spell's controller.")
        it = StackItem(self.a, c.spell_effects, [spell, mine, None], card=c)
        self.game.stack.append(it)
        self.game.resolve_top()
        self.assertEqual(self.b.life, 18)

    def test_real_oracle_entries(self):
        db = CardDB(offline=True)
        if db._all is None:
            self.skipTest("offline card database is missing")
        for name in ("Parallectric Feedback", "Refuse // Cooperate", "Essence Backlash"):
            with self.subTest(card=name):
                self.assertEqual(db.get(name).unsupported, [])


if __name__ == "__main__":
    unittest.main()
