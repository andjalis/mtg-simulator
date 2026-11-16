"""#721: "if it's your turn" / "if it's not your turn" in spell effects are checked against the active player."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB().get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class YourTurn(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def turn_of(self, p):
        self.game.active_idx = self.game.players.index(p)
        for q in self.game.players:
            q.my_turn = q is p

    def resolve(self, name, targets=()):
        card = db(name)
        effects = list(card.spell_effects)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        self.game.stack.append(StackItem(self.a, effects, targets, card=card, name=card.name))
        self.game.resolve_top()
        self.game.settle()

    def test_zealous_display_untaps_on_their_turn(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        bear.tapped = True
        self.turn_of(self.b)
        self.resolve("Zealous Display")
        self.assertEqual(bear.power, 4)
        self.assertFalse(bear.tapped)

    def test_zealous_display_does_not_untap_on_my_turn(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        bear.tapped = True
        self.turn_of(self.a)
        self.resolve("Zealous Display")
        self.assertEqual(bear.power, 4)
        self.assertTrue(bear.tapped)

    def test_days_undoing_ends_only_my_turn(self):
        self.turn_of(self.b)
        self.resolve("Day's Undoing")
        self.assertFalse(getattr(self.game, "turn_ended", False))
        self.turn_of(self.a)
        self.resolve("Day's Undoing")
        self.assertTrue(self.game.turn_ended)

    def test_fated_conflagration_scries_only_on_my_turn(self):
        from mtgsim.cards import Effect
        game = self.game
        scry = Effect("scry", 2, cond="your_turn")
        self.turn_of(self.b)
        self.assertFalse(game.check_cond(self.a, scry, None, None))
        self.assertTrue(game.check_cond(self.b, scry, None, None))
        self.assertEqual([e.cond for e in db("Fated Conflagration").spell_effects], ["", "your_turn"])


if __name__ == "__main__":
    unittest.main()
