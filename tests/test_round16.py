"""Round 16: mill recipients and filtered recovery of the cards just milled."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, SHOCK, card


ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
FAERIE = card("Test Faerie", "{U}", "Creature — Faerie", "", 1, 1)
SORCERY = card("Test Sorcery", "{1}", "Sorcery", "Draw a card.")


class Round16(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 10
        self.b.library = [BEAR] * 10

    def cast(self, text):
        spell = card("Test Mill", types="Sorcery", text=text)
        self.assertEqual(spell.unsupported, [])
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()
        return spell

    def test_self_mill_wording(self):
        for text in ("Mill ten cards.", "You mill ten cards.", "You may mill ten cards.", "You may mill 10 cards."):
            with self.subTest(text=text):
                self.a.library = [ISLAND] * 10
                self.cast(text)
                self.assertEqual(self.a.milled_last, [ISLAND] * 10)
                self.assertEqual(len(self.b.library), 10)

    def test_target_player(self):
        self.cast("Target player mills six cards.")
        self.assertEqual(len(self.b.library), 4)
        self.assertEqual(len(self.a.library), 10)

    def test_target_opponent_restriction(self):
        spell = card("Opp Mill", types="Sorcery", text="Target opponent mills three cards.")
        eff = spell.spell_effects[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [self.b])
        self.assertFalse(self.game.legal_target(self.a, eff, self.a))
        self.cast(spell.oracle)
        self.assertEqual(len(self.b.library), 7)

    def test_each_opponent_does_not_target(self):
        spell = card("Opp Mill", types="Sorcery", text="Each opponent mills two cards.")
        self.assertEqual(spell.spell_effects[0].target, "each_opponent")
        self.cast(spell.oracle)
        self.assertEqual(len(self.a.library), 10)
        self.assertEqual(len(self.b.library), 8)

    def test_each_player(self):
        self.cast("Each player mills seven cards.")
        self.assertEqual(len(self.a.library), 3)
        self.assertEqual(len(self.b.library), 3)

    def test_that_player_uses_trigger_context(self):
        c = card("Mill Watcher", "{2}", "Creature — Wizard",
                 "Whenever ~ deals combat damage to a player, that player mills ten cards.", 2, 2)
        self.assertEqual(c.unsupported, [])
        src = self.game.enter_battlefield(self.a, c)
        self.game.fire(self.a, "combat_damage_player", src, context=self.b)
        self.game.settle()
        self.assertEqual(self.b.library, [])
        self.assertEqual(len(self.a.library), 10)

    def test_land_pick_excludes_old_graveyard_cards(self):
        self.a.library = [ISLAND, BEAR, SHOCK]
        self.a.graveyard.append(FAERIE)
        self.cast("Mill three cards. Put a land card from among the milled cards into your hand.")
        self.assertEqual(self.a.hand, [ISLAND])
        self.assertIn(FAERIE, self.a.graveyard)
        self.assertIn(BEAR, self.a.graveyard)

    def test_union_of_card_types_and_subtypes(self):
        self.a.library = [BEAR, ISLAND, SHOCK, FAERIE, SORCERY]
        self.cast("Mill five cards. Put all instant, sorcery, or Faerie cards from among the milled cards into your hand.")
        self.assertCountEqual(self.a.hand, [SHOCK, FAERIE, SORCERY])
        self.assertIn(BEAR, self.a.graveyard)
        self.assertIn(ISLAND, self.a.graveyard)

    def test_up_to_two_and_or_with_duplicate_cards(self):
        self.a.library = [BEAR, BEAR, ISLAND, SHOCK]
        self.cast("Mill four cards. You may put up to two creature and/or land cards from among the milled cards into your hand.")
        self.assertEqual(len(self.a.hand), 2)
        self.assertTrue(all(c.is_creature or c.is_land for c in self.a.hand))
        self.assertEqual(len(self.a.graveyard), 3)  # two milled cards and the spell

    def test_each_subtype_with_no_matches(self):
        self.a.library = [BEAR, SHOCK]
        self.cast("Mill two cards. Put each Elf card milled this way into your hand.")
        self.assertEqual(self.a.hand, [])

    def test_permanent_pick_compatibility(self):
        self.a.library = [SHOCK, ISLAND]
        physical_island = self.a.library[-1]
        self.cast("Mill two cards. You may put a permanent card from among the cards milled this way into your hand.")
        self.assertEqual(self.a.hand, [ISLAND])
        self.assertIs(self.a.picked_last, physical_island)

    def test_battlefield_recovery_fires_etb_and_enters_tapped(self):
        creature = card("Test Milled Healer", "{2}", "Creature — Elf",
                        "When ~ enters, you gain 3 life.", 2, 2)
        self.a.library = [creature, SHOCK]
        self.cast("Mill two cards. Put each creature card milled this way onto the battlefield tapped.")
        self.assertEqual([p.card for p in self.a.battlefield], [creature])
        self.assertTrue(self.a.battlefield[0].tapped)
        self.assertEqual(self.a.life, 23)
        self.assertNotIn(creature, self.a.graveyard)

    def test_top_of_library(self):
        self.a.library = [SHOCK, ISLAND, BEAR]
        self.cast("Mill three cards. You may put a creature or land card from among the milled cards on top of your library.")
        self.assertEqual(self.a.library, [ISLAND])
        self.assertEqual(self.a.hand, [])

    def test_empty_mill_resets_last_selection(self):
        self.a.library = []
        self.a.graveyard.append(ELF)
        self.a.milled_last = [ELF]
        self.cast("Mill two cards. Return up to two permanent cards from among them to your hand.")
        self.assertEqual(self.a.hand, [])
        self.assertEqual(self.a.milled_last, [])

    def test_unsupported_selection_stays_visible(self):
        for text in ("Put a noncreature card from among the milled cards into your hand.",
                     "Put a creature card with a finality counter from among the milled cards onto the battlefield.",
                     "Put all cards that have different names from among the milled cards into your hand."):
            with self.subTest(text=text):
                self.assertTrue(card("Unsupported Mill", types="Sorcery", text=text).unsupported)


if __name__ == "__main__":
    unittest.main()
