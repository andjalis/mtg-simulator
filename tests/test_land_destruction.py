"""Land removal uses land targets and preserves restrictions, ward and follow-up effects."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card


class LandDestruction(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def spell(self, text="Destroy target land."):
        c = card("Test Land Removal", types="Sorcery", text=text)
        self.assertEqual(c.unsupported, [])
        self.a.hand.append(c)
        return c

    def test_legal_targets_exclude_nonlands_and_players(self):
        mine = self.game.enter_battlefield(self.a, ISLAND)
        theirs = self.game.enter_battlefield(self.b, MOUNTAIN)
        bear = self.game.enter_battlefield(self.b, BEAR)
        effect = self.spell().spell_effects[0]
        self.assertEqual(self.game.legal_targets(self.a, effect), [mine, theirs])
        self.assertFalse(self.game.legal_target(self.a, effect, bear))
        self.assertFalse(self.game.legal_target(self.a, effect, self.b))

    def test_ai_plans_and_casts_land_destruction(self):
        land = self.game.enter_battlefield(self.b, ISLAND)
        self.game.enter_battlefield(self.b, BEAR)
        spell = self.spell()
        plan = self.a.ai.plan_spell(self.game, self.a, spell)
        self.assertIsNotNone(plan)
        self.assertEqual(plan[1], [land])
        self.assertTrue(self.game.cast(self.a, spell, plan[1]))
        self.game.settle()
        self.assertNotIn(land, self.b.battlefield)
        self.assertIn(ISLAND, self.b.graveyard)
        self.assertFalse(self.game.creature_died_turn)

    def test_basic_nonbasic_and_controller_filters(self):
        mine = self.game.enter_battlefield(self.a, card("My Dual", types="Land — Island Swamp"))
        theirs = self.game.enter_battlefield(self.b, card("Their Dual", types="Land — Island Swamp"))
        basic = self.game.enter_battlefield(self.b, ISLAND)
        snow = self.game.enter_battlefield(self.b, card("Snow-Covered Swamp", types="Basic Snow Land — Swamp"))
        effect = self.spell("Destroy target nonbasic land an opponent controls.").spell_effects[0]
        self.assertEqual(self.game.legal_targets(self.a, effect), [theirs])
        for target in (mine, basic, snow):
            self.assertFalse(self.game.legal_target(self.a, effect, target))

    def test_hexproof_indestructible_and_ward(self):
        protected = self.game.enter_battlefield(self.b, card("Protected Land", types="Land", text="Hexproof"))
        sturdy = self.game.enter_battlefield(self.b, card("Sturdy Land", types="Land", text="Indestructible"))
        warded = self.game.enter_battlefield(self.b, card("Warded Land", types="Land", text="Ward {2}"))
        spell = self.spell()
        self.assertNotIn(protected, self.game.legal_targets(self.a, spell.spell_effects[0]))
        self.assertTrue(self.game.cast(self.a, spell, [sturdy]))
        self.game.settle()
        self.assertIn(sturdy, self.b.battlefield)
        spell = self.spell()
        self.assertTrue(self.game.cast(self.a, spell, [warded]))
        self.game.settle()
        self.assertIn(warded, self.b.battlefield)  # no mana to pay ward

    def test_removed_land_fizzles_before_draw(self):
        land = self.game.enter_battlefield(self.b, ISLAND)
        spell = self.spell("Destroy target land. Draw a card.")
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.cast(self.a, spell, [land]))
        self.game.leave_battlefield(land, "hand")
        self.game.settle()
        self.assertEqual(self.a.hand, [])

    def test_basic_land_search_uses_the_destroyed_lands_controller(self):
        land = self.game.enter_battlefield(self.b, MOUNTAIN)
        self.b.library = [ISLAND]
        spell = self.spell("Destroy target land. Its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle. Draw a card.")
        self.assertTrue(self.game.cast(self.a, spell, [land]))
        self.game.settle()
        self.assertIn(MOUNTAIN, self.b.graveyard)
        self.assertEqual([p.card for p in self.b.battlefield], [ISLAND])
        self.assertTrue(self.b.battlefield[0].tapped)
        self.assertEqual(self.a.hand, [ISLAND])

    def test_unsupported_land_variants_stay_visible(self):
        c = card("Test Limited Removal", types="Sorcery", text="Destroy target land with mana value 3 or greater.")
        self.assertTrue(c.unsupported)


if __name__ == "__main__":
    unittest.main()
