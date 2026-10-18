"""Discounts for spells that have Adventures use the characteristics of the cast face."""
import dataclasses
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_adventure_milling import adventurer
from tests.test_templates import BEAR, ISLAND, card


class AdventureDiscounts(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.front = adventurer()
        self.front.adventure = dataclasses.replace(self.front.adventure, mana_cost={"generic": 2, "U": 1}, cmc=3)

    def discount(self, text="Permanent spells you cast that have an Adventure cost {1} less to cast.", who=None):
        source = card("Test Adventure Discount", types="Enchantment", text=text)
        self.assertEqual(source.unsupported, [])
        return self.game.enter_battlefield(who or self.a, source)

    def test_front_face_is_discounted_but_adventure_is_not(self):
        self.discount()
        half = self.game._variant(self.front, "adventure")
        self.assertEqual(self.game.cost_of(self.a, self.front), {"generic": 1})
        self.assertEqual(self.game.cost_of(self.a, half), {"generic": 2, "U": 1})
        self.assertEqual(self.game.cost_of(self.a, BEAR), BEAR.mana_cost)

    def test_discount_changes_actual_payability_and_casting(self):
        self.discount()
        self.game.enter_battlefield(self.a, ISLAND)
        self.a.hand.append(self.front)
        self.assertTrue(self.game.can_cast_now(self.a, self.front))
        self.assertFalse(self.game.can_cast_now(self.a, self.game._variant(self.front, "adventure")))
        self.assertTrue(self.game.cast(self.a, self.front, []))
        self.game.settle()
        self.assertEqual([p.card for p in self.a.creatures], [self.front])

    def test_discount_works_after_adventure_from_exile(self):
        self.discount()
        self.a.on_adventure.append(self.front)
        option = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == "from_adventure")
        self.assertEqual(self.game.cost_of(self.a, option), {"generic": 1})

    def test_discount_is_only_from_controllers_battlefield(self):
        self.discount(who=self.b)
        self.assertEqual(self.game.cost_of(self.a, self.front), {"generic": 2})
        source = self.discount()
        self.game.leave_battlefield(source, "graveyard")
        self.assertEqual(self.game.cost_of(self.a, self.front), {"generic": 2})

    def test_stacks_and_never_reduces_colored_pips(self):
        self.front.mana_cost = {"generic": 1, "G": 1}
        self.discount()
        self.discount()
        self.assertEqual(self.game.cost_of(self.a, self.front), {"generic": 0, "G": 1})

    def test_combines_with_existing_creature_discount(self):
        self.discount()
        self.discount("Creature spells you cast cost {1} less to cast.")
        self.assertEqual(self.game.cost_of(self.a, self.front), {"generic": 0})

    def test_type_scopes(self):
        relic = adventurer("Test Relic Adventure", "Artifact")
        self.discount("Creature spells you cast that have an Adventure cost {1} less to cast.")
        self.assertEqual(self.game.cost_of(self.a, relic), {"generic": 2})
        self.discount("Artifact spells you cast that have an Adventure cost {1} less to cast.")
        self.assertEqual(self.game.cost_of(self.a, relic), {"generic": 1})

    def test_unqualified_spells_scope(self):
        self.discount("Spells you cast that have an Adventure cost {1} less to cast.")
        self.assertEqual(self.game.cost_of(self.a, self.front), {"generic": 1})
        self.assertEqual(self.game.cost_of(self.a, self.game._variant(self.front, "adventure")), {"generic": 2, "U": 1})

    def test_adventure_spell_discount_still_applies_to_adventure_half(self):
        self.discount("Adventure spells you cast cost {1} less to cast.")
        self.assertEqual(self.game.cost_of(self.a, self.game._variant(self.front, "adventure")), {"generic": 1, "U": 1})
        self.assertEqual(self.game.cost_of(self.a, self.front), {"generic": 2})

    def test_unsupported_discount_stays_visible(self):
        c = card("Test Conditional Discount", types="Enchantment", text="Permanent spells you cast that have an Adventure cost {1} less to cast if you control a Giant.")
        self.assertTrue(c.unsupported)


if __name__ == "__main__":
    unittest.main()
