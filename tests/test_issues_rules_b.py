"""Issue fixes, rules lane b."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND


class DayNightTransformOnly(unittest.TestCase):
    """#264 (3): daybound/nightbound permanents transform only through day/night."""

    def setUp(self):
        self.card = CardDB(offline=True).get("Avabruck Caretaker // Hollowhenge Huntmaster")
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_other_transform_effects_are_blocked(self):
        perm = self.game.enter_battlefield(self.a, self.card)
        self.game.transform(perm)
        self.assertEqual(perm.card.name, self.card.name)
        self.game.day_night = "night"
        from mtgsim.day_night import set_state
        set_state(self.game, "night")
        self.assertEqual(perm.card.name, self.card.back.name)
        self.game.transform(perm)                       # a night face can't be flipped by another effect either
        self.assertEqual(perm.card.name, self.card.back.name)

    def test_non_daybound_still_transforms(self):
        from mtgsim.cards import card_from_scryfall
        f = {"name": "F", "mana_cost": "{1}", "cmc": 1, "type_line": "Creature — Human", "oracle_text": "", "power": "1", "toughness": "1"}
        b = {"name": "B", "mana_cost": "", "cmc": 0, "type_line": "Creature — Werewolf", "oracle_text": "", "power": "2", "toughness": "2"}
        card = card_from_scryfall({"name": "F // B", "layout": "transform", "cmc": 1, "card_faces": [f, b]})
        perm = self.game.enter_battlefield(self.a, card)
        self.game.transform(perm)
        self.assertEqual(perm.card.name, "B")


class ReflexiveTargetAfterAction(unittest.TestCase):
    """#250: a reflexive "When you do" payoff picks its target after the action, not at cast."""

    def setUp(self):
        from tests.test_combat_triggers import Scripted
        self.card = CardDB().get("Faebloom Trick")
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_payoff_is_untargeted_at_cast(self):
        from mtgsim.engine import TARGETED
        self.assertEqual(self.card.unsupported, [])
        self.assertFalse([e for e in self.card.spell_effects if e.target in TARGETED])
        self.assertTrue(any(e.kind == "reflex_late" for e in self.card.spell_effects))

    def test_target_chosen_after_the_action(self):
        victim = self.game.enter_battlefield(self.b, BEAR)
        victim.tapped = False
        self.game.cast_free(self.a, self.card)
        self.game.settle()
        self.assertTrue(victim.tapped)
        self.assertEqual(sum(1 for x in self.a.battlefield if x.card.is_token), 2)

    def test_no_legal_target_still_does_the_action(self):
        self.game.cast_free(self.a, self.card)               # no creature to tap: the payoff just does nothing
        self.game.settle()
        self.assertEqual(sum(1 for x in self.a.battlefield if x.card.is_token), 2)



if __name__ == "__main__":
    unittest.main()
