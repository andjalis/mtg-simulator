"""Counter riders must apply before entry checks; finality replaces dying."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card


class ReturnCounters(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def cast(self, text):
        spell = card("Test Return", types="Sorcery", text=text)
        self.assertEqual(spell.unsupported, [])
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()

    def test_additional_counters_preserve_native_counters(self):
        native = card("Test Native", "{1}", "Creature — Ooze", "~ enters with two +1/+1 counters on it.", 0, 0)
        self.a.graveyard.append(native)
        self.cast("Return target creature card from your graveyard to the battlefield with two additional +1/+1 counters on it.")
        self.assertEqual(self.a.battlefield[0].p1, 4)
        self.assertEqual(self.a.battlefield[0].toughness, 4)

    def test_counter_prevents_zero_toughness_death(self):
        zero = card("Test Zero", "{1}", "Creature — Ooze", "", 0, 0)
        self.a.graveyard.append(zero)
        self.cast("Return target creature card from your graveyard to the battlefield with an additional +1/+1 counter on it.")
        self.assertEqual([p.card for p in self.a.creatures], [zero])

    def test_x_rider_uses_the_mana_paid(self):
        spell = card("Test X Return", "{X}", "Sorcery", "Return target creature card from your graveyard to the battlefield with X additional +1/+1 counters on it.")
        self.assertEqual(spell.unsupported, [])
        for _ in range(3):
            self.game.enter_battlefield(self.a, ISLAND)
        self.a.graveyard.append(BEAR)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()
        self.assertEqual(self.a.creatures[0].p1, 3)

    def test_multiple_returns_each_receive_counters_and_enter_tapped(self):
        self.a.graveyard += [BEAR, BEAR]
        self.cast("Return up to two target creature cards from your graveyard to the battlefield tapped with three additional +1/+1 counters on them.")
        self.assertEqual(len(self.a.creatures), 2)
        self.assertTrue(all(p.p1 == 3 and p.tapped for p in self.a.creatures))

    def test_mana_value_and_opponents_graveyard(self):
        giant = card("Test Giant", "{5}", "Creature — Giant", "", 5, 5)
        self.b.graveyard += [BEAR, giant]
        self.cast("Put target creature card with mana value 4 or less from a graveyard onto the battlefield under your control with a finality counter on it.")
        self.assertEqual(self.a.creatures[0].card, BEAR)
        self.assertEqual(self.a.creatures[0].counters.get("finality"), 1)
        self.assertIn(giant, self.b.graveyard)

    def test_finality_exiles_without_death_events(self):
        creature = card("Test Doomed", "{2}", "Creature — Spirit", "When ~ dies, you gain 3 life.", 2, 2)
        self.a.graveyard.append(creature)
        self.cast("Return target creature card from your graveyard to the battlefield with a finality counter on it.")
        self.game.destroy(self.a.creatures[0])
        self.game.settle()
        self.assertIn(creature, self.a.exile)
        self.assertNotIn(creature, self.a.graveyard)
        self.assertEqual(self.a.life, 20)
        self.assertFalse(self.game.creature_died_turn)
        self.assertFalse(self.a.creature_died_turn)

    def test_finality_on_noncreature_permanent(self):
        relic = card("Test Relic", "{2}", "Artifact")
        self.a.graveyard.append(relic)
        self.cast("Return target artifact card from your graveyard to the battlefield with a finality counter on it.")
        self.game.sacrifice(self.a.battlefield[0])
        self.assertIn(relic, self.a.exile)
        self.assertNotIn(relic, self.a.graveyard)

    def test_bounce_clears_finality_on_reentry(self):
        self.a.graveyard.append(BEAR)
        self.cast("Return target creature card from your graveyard to the battlefield with a finality counter on it.")
        self.game.leave_battlefield(self.a.creatures[0], "hand")
        self.a.hand.remove(BEAR)
        fresh = self.game.enter_battlefield(self.a, BEAR)
        self.assertFalse(fresh.counters.get("finality"))
        self.game.destroy(fresh)
        self.assertIn(BEAR, self.a.graveyard)

    def test_removing_finality_allows_death(self):
        self.a.graveyard.append(BEAR)
        self.cast("Return target creature card from your graveyard to the battlefield with a finality counter on it.")
        perm = self.a.creatures[0]
        perm.counters.pop("finality")
        self.game.destroy(perm)
        self.assertIn(BEAR, self.a.graveyard)

    def test_milled_return_with_counter(self):
        self.a.library = [BEAR]
        self.cast("Mill a card. Put a creature card milled this way onto the battlefield with a finality counter on it.")
        self.assertEqual(self.a.creatures[0].counters.get("finality"), 1)

    def test_unknown_rider_remains_unsupported(self):
        spell = card("Test Unknown", types="Sorcery", text="Return target creature card from your graveyard to the battlefield with a shield counter on it.")
        self.assertTrue(spell.unsupported)


if __name__ == "__main__":
    unittest.main()
