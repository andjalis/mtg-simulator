""""That player" in a spell or ability without an event player is the previous object's player (#609)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")


class ThatPlayer(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 5, HeuristicAI())
        self.b = Player("b", [BEAR] * 5, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.hand = [ISLAND] * 2

    def run_spell(self, spell, target):
        effects = list(spell.spell_effects)
        self.game.stack.append(StackItem(self.a, effects, [target] + [None] * (len(effects) - 1), card=spell,
                                         name=spell.name))
        self.game.resolve_top()
        self.game.settle()

    def spell(self, text):
        return card("Test Spell", "{1}{U}", "Instant", text)

    def test_bounce_then_that_player_discards(self):
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.run_spell(self.spell("Return target permanent to its owner's hand. Then that player discards a card."),
                       bear)
        self.assertEqual(len(self.b.hand), 2)             # 2 + the Bear - 1 (before #609: 3)

    def test_bounce_of_a_stolen_permanent_is_its_owner(self):
        stolen = self.game.enter_battlefield(self.a, BEAR)
        stolen.owner = self.b
        self.run_spell(self.spell("Return target permanent to its owner's hand. Then that player discards a card."),
                       stolen)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (2, 2))

    def test_other_actions_mean_its_controller(self):
        for text in ("Exile target creature an opponent controls. That player draws a card.",   # cx_players
                     "Destroy target creature. That player draws a card."):
            with self.subTest(text):
                self.setUp()
                bear = self.game.enter_battlefield(self.b, BEAR)
                self.run_spell(self.spell(text), bear)
                self.assertEqual((len(self.a.hand), len(self.b.hand)), (2, 3))

    def test_a_target_player_still_wins(self):
        spell = self.spell("Target player reveals their hand. That player discards a card.")
        self.run_spell(spell, self.b)
        self.assertEqual(len(self.b.hand), 1)

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.run_spell(db.get("Recoil"), bear)
        self.assertEqual(len(self.b.hand), 2)
        # Frightful Delusion: the countered spell's controller discards
        theirs = card("Their Spell", "{1}", "Sorcery", "Draw a card.")
        item = StackItem(self.b, list(theirs.spell_effects), [None], card=theirs, name=theirs.name)
        self.game.stack.append(item)
        delusion = db.get("Frightful Delusion")
        effects = list(delusion.spell_effects)
        self.game.stack.append(StackItem(self.a, effects, [item] + [None] * (len(effects) - 1), card=delusion,
                                         name=delusion.name))
        self.game.resolve_top()
        self.game.settle()
        self.assertEqual(len(self.b.hand), 1)


if __name__ == "__main__":
    unittest.main()
