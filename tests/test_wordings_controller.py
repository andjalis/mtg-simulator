"""Wordings that say "an opponent controls" keep the restriction: the target can't be one of your own permanents."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND


def spell(text):
    return card_from_scryfall({"name": "Foo Bar", "mana_cost": "{2}{U}", "cmc": 3, "type_line": "Sorcery",
                               "oracle_text": text})


class Controller(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        self.mine = self.game.enter_battlefield(self.a, BEAR)
        self.theirs = self.game.enter_battlefield(self.b, BEAR)

    def test_restricted_wordings_only_target_the_opponent(self):
        for text, kind in (("Tap target creature an opponent controls.", "tap"),
                           ("Tap target nonland permanent an opponent controls.", "tap"),
                           ("Tap target creature you don't control.", "tap"),
                           ("Target creature an opponent controls can't block this turn.", "cant_block_turn"),
                           ("Destroy target creature an opponent controls.", "destroy"),
                           ("Destroy target nonland permanent an opponent controls.", "destroy"),
                           ("Return target nonland permanent an opponent controls to its owner's hand.", "bounce"),
                           ("~ deals 3 damage to target creature an opponent controls.", "damage")):
            c = spell(text)
            self.assertEqual(c.unsupported, [], text)
            eff = c.spell_effects[0]
            self.assertEqual(eff.kind, kind, text)
            legal = self.game.legal_targets(self.a, eff)
            self.assertIn(self.theirs, legal, text)
            self.assertNotIn(self.mine, legal, text)

    def test_unrestricted_wordings_still_allow_either(self):
        eff = spell("Tap target creature.").spell_effects[0]
        legal = self.game.legal_targets(self.a, eff)
        self.assertIn(self.mine, legal)
        self.assertIn(self.theirs, legal)

    def test_nonland_permanent_is_not_a_creature(self):
        self.assertEqual(spell("Tap target nonland permanent.").spell_effects[0].target, "nonland_perm")

    def test_ai_frost_lynx_taps_the_opponents_creature(self):
        """HeuristicAI casts Frost Lynx and its enters trigger taps the opponent's creature, not its own."""
        db = CardDB(offline=True)
        lynx = db.get("Frost Lynx")
        self.a.battlefield.remove(self.mine)
        self.mine = self.game.enter_battlefield(self.a, db.get("Wall of Omens"))      # a defender: never attacks
        for _ in range(3):
            self.game.enter_battlefield(self.a, CardDB(offline=True).get("Island")).sick = False
        self.a.hand = [lynx]
        self.theirs.tapped = False
        self.game.take_turn(self.a)
        self.assertTrue(any(x.card.name == "Frost Lynx" for x in self.a.battlefield))
        self.assertTrue(self.theirs.tapped)
        self.assertFalse(self.mine.tapped)


if __name__ == "__main__":
    unittest.main()
