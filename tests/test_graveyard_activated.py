"""Graveyard returns are abilities, with costs at activation and a source at resolution."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card


def revenant(text):
    return card("Test Revenant", "{2}", "Creature — Spirit", text, 2, 2)


class GraveyardActivated(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def prepare(self, text, mana=3):
        c = revenant(text)
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.activated, [])
        self.assertEqual(len(c.gy_activated), 1)
        self.a.graveyard.append(c)
        for _ in range(mana):
            self.game.enter_battlefield(self.a, ISLAND)
        return self.a.graveyard[-1]

    def test_return_enters_tapped_with_finality(self):
        c = self.prepare("{3}: Return this card from your graveyard to the battlefield tapped with a finality counter on it.")
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        returned = self.a.creatures[0]
        self.assertIs(returned.card, c)
        self.assertTrue(returned.tapped)
        self.assertEqual(returned.counters.get("finality"), 1)
        self.game.destroy(returned)
        self.assertIn(c, self.a.exile)

    def test_automatic_main_phase_policy_uses_ability(self):
        c = self.prepare("{2}: Return ~ from your graveyard to the battlefield tapped.")
        self.game.graveyard_abilities(self.a)
        self.assertEqual([p.card for p in self.a.creatures], [c])

    def test_insufficient_mana_keeps_source_in_graveyard(self):
        c = self.prepare("{4}: Return this card from your graveyard to the battlefield.")
        self.assertFalse(self.game.activate_graveyard(self.a, c))
        self.assertIn(c, self.a.graveyard)
        self.assertTrue(all(not p.tapped for p in self.a.battlefield))

    def test_zone_and_index_validation(self):
        c = self.prepare("{1}: Return this card from your graveyard to the battlefield.")
        self.assertFalse(self.game.can_activate_graveyard(self.b, c))
        self.assertFalse(self.game.can_activate_graveyard(self.a, c, -1))
        self.assertFalse(self.game.can_activate_graveyard(self.a, c, 1))
        self.a.graveyard.remove(c)
        self.a.hand.append(c)
        self.assertFalse(self.game.activate_graveyard(self.a, c))

    def test_sorcery_restrictions(self):
        c = self.prepare("{1}: Return this card from your graveyard to the battlefield. Activate only as a sorcery.")
        self.game.step = "end_step"
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))
        self.game.step = "main1"
        self.game.active_idx = 1
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))
        self.game.active_idx = 0
        self.assertTrue(self.game.can_activate_graveyard(self.a, c))
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.activate_graveyard(self.a, c))
            self.assertFalse(self.game.can_activate_graveyard(self.a, c))

    def test_instant_speed_return_on_opponents_turn(self):
        c = self.prepare("{1}: Return this card from your graveyard to the battlefield.")
        self.game.active_idx = 1
        self.game.step = "end_step"
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.assertIs(self.a.creatures[0].card, c)

    def test_discard_and_life_are_paid_at_activation(self):
        c = self.prepare("{1}, Discard a card, Pay 2 life: Return this card from your graveyard to the battlefield.")
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))
        self.a.hand = [BEAR]
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.assertIn(c, self.a.graveyard)
        self.assertIn(BEAR, self.a.graveyard)
        self.assertEqual(self.a.hand, [])
        self.assertEqual(self.a.life, 18)
        self.assertFalse(self.game.stack[0].is_spell)
        self.game.settle()
        self.assertIs(self.a.creatures[0].card, c)

    def test_response_can_exile_source(self):
        c = self.prepare("{1}: Return this card from your graveyard to the battlefield.")
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.a.graveyard.remove(c)
        self.a.exile.append(c)
        self.game.settle()
        self.assertEqual(self.a.creatures, [])
        self.assertIn(c, self.a.exile)

    def test_countering_ability_does_not_remove_source(self):
        c = self.prepare("{1}: Return this card from your graveyard to the battlefield.")
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.game.counter(self.b, Effect("counter"), self.game.stack[-1])
        self.assertIn(c, self.a.graveyard)
        self.assertFalse(self.game.stack)

    def test_delirium_gate_counts_distinct_types(self):
        c = self.prepare("Delirium — {1}: Return this card from your graveyard to the battlefield with a finality counter on it. Activate only if there are four or more card types among cards in your graveyard and only as a sorcery.")
        self.a.graveyard += [BEAR] * 4
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))
        self.a.graveyard += [ISLAND, card("Relic", types="Artifact"), card("Ritual", types="Sorcery")]
        self.assertTrue(self.game.activate_graveyard(self.a, c))

    def test_descend_eight_counts_permanents_not_spells(self):
        c = self.prepare("Descend 8 — {1}: Return this card from your graveyard to the battlefield with a finality counter on it. Activate only if there are eight or more permanent cards in your graveyard and only as a sorcery.")
        self.a.graveyard += [card("Ritual", types="Sorcery")] * 8
        self.assertFalse(self.game.can_activate_graveyard(self.a, c))
        self.a.graveyard += [BEAR] * 7
        self.assertTrue(self.game.activate_graveyard(self.a, c))

    def test_return_fires_entry_trigger(self):
        c = self.prepare("When ~ enters, you gain 2 life.\n{1}: Return this card from your graveyard to the battlefield.")
        self.assertTrue(self.game.activate_graveyard(self.a, c))
        self.assertEqual(self.a.life, 22)

    def test_unsupported_cost_or_restriction_stays_visible(self):
        for text in ("{1}, Exile another creature card from your graveyard: Return this card from your graveyard to the battlefield.",
                     "{T}: Return this card from your graveyard to the battlefield.",
                     "{1}: Return this card from your graveyard to the battlefield. Activate only if you've scried or surveilled this turn."):
            with self.subTest(text=text):
                c = revenant(text)
                self.assertTrue(c.unsupported)
                self.assertEqual(c.gy_activated, [])
                self.assertEqual(c.activated, [])


if __name__ == "__main__":
    unittest.main()
