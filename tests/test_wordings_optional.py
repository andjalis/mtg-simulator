"""Part of #282: wordings with "up to one target" keep the target optional."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, FOREST, ISLAND


def spell(text):
    return card_from_scryfall({"name": "Foo Bar", "mana_cost": "{1}{G}", "cmc": 2, "type_line": "Sorcery",
                               "oracle_text": text})


class OptionalTarget(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_up_to_one_marks_the_target_optional(self):
        for text, kind in (("Put a -1/-1 counter on up to one target creature.", "shrink"),
                           ("Put a +1/+1 counter on up to one target creature.", "p1_counters"),
                           ("Up to one target creature you control connives.", "connive"),
                           ("Up to one target creature you control can't be blocked this turn.", "unblockable")):
            eff = spell(text).spell_effects[0]
            self.assertEqual(eff.kind, kind, text)
            self.assertTrue(eff.data.get("optional_target"), text)

    def test_plain_wordings_stay_mandatory(self):
        for text in ("Put a -1/-1 counter on target creature.", "Target creature you control connives.",
                     "Target creature you control can't be blocked this turn."):
            self.assertFalse(spell(text).spell_effects[0].data.get("optional_target"), text)

    def test_spell_with_no_target_can_still_resolve(self):
        c = spell("Put a -1/-1 counter on up to one target creature.")
        self.assertEqual(self.game.legal_targets(self.a, c.spell_effects[0]), [])
        self.assertTrue(self.game.valid_action_targets(self.a, c.spell_effects, [None], c))

    def test_mandatory_without_target_is_not_castable(self):
        c = spell("Put a -1/-1 counter on target creature.")
        self.assertFalse(self.game.valid_action_targets(self.a, c.spell_effects, [None], c))

    def test_ai_shrinks_the_opponents_creature_with_up_to_one(self):
        """A real turn: HeuristicAI casts the up-to-one shrink spell and aims it at their creature."""
        c = spell("Put a -1/-1 counter on up to one target creature.")
        bear = self.game.enter_battlefield(self.b, BEAR)
        mine = self.game.enter_battlefield(self.a, BEAR)
        for _ in range(2):
            self.game.enter_battlefield(self.a, FOREST).sick = False
        self.a.hand = [c]
        self.game.take_turn(self.a)
        self.assertEqual(bear.counters.get("-1/-1", 0), 1)
        self.assertEqual(mine.counters.get("-1/-1", 0), 0)                # aimed at their side

    def test_shrink_can_target_your_own_creature(self):
        """Fixes #293: the wording has no opponent restriction."""
        eff = spell("Put a -1/-1 counter on target creature.").spell_effects[0]
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.assertIn(mine, self.game.legal_targets(self.a, eff))


if __name__ == "__main__":
    unittest.main()
