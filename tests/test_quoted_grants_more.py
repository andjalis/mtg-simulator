"""Quoted trigger grants left after #338 (#540): no-duration grants to a permanent, tokens created with a quoted
ability ("They have "..."", "The tokens have "...""), and "face-up" in the noun-phrase selector."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from mtgsim.permanent_templates import selector

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")


class Parsing(unittest.TestCase):
    def test_no_duration_grant_to_a_permanent(self):
        got = parse_sentence('Target creature gains "When this creature dies, draw a card."')
        self.assertEqual([(e.kind, e.data.get("permanent")) for e in got], [("grant_triggers", True)])
        got = parse_sentence('Until end of turn, target creature gains "When this creature dies, draw a card."')
        self.assertEqual([(e.kind, e.data.get("permanent")) for e in got], [("grant_triggers", None)])

    def test_refusals(self):
        # "~ gains" with no duration: in a cast trigger ~ is a spell, nothing carries it onto the permanent
        self.assertIsNone(parse_sentence('~ gains "When ~ leaves the battlefield, target opponent draws a card."'))
        # a group without a duration
        self.assertIsNone(parse_sentence('Creatures you control gain "When this creature dies, draw a card."'))
        # a predefined token has no card of its own to extend
        effects, bad = _parse_effects('Create a Food token. It has "When this token dies, draw a card."')
        self.assertTrue(bad)

    def test_token_created_with_the_ability(self):
        effects, bad = _parse_effects('Create two 1/1 black Rat creature tokens. They have "When this token dies, '
                                      'you gain 1 life."')
        self.assertEqual(bad, [])
        self.assertEqual([t.event for t in effects[-1].data["card"].triggers], ["dies"])

    def test_face_up_selector(self):
        self.assertEqual(selector("face-up nontoken creatures you control", plural=True)["traits"],
                         ["face-up", "nontoken"])


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 5, HeuristicAI())
        self.b = Player("b", [BEAR] * 5, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def resolve(self, text, target=None):
        spell = card("Test Spell", "{1}", "Sorcery", text)
        item = StackItem(self.a, [], [])
        item.card = spell
        for eff in spell.spell_effects:
            self.game.resolve(self.a, eff, target, item, None)
        self.game.settle()

    def test_permanent_grant_outlasts_the_turn_but_not_the_object(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.resolve('Target creature gains "When this creature dies, you gain 3 life."', bear)
        self.game.turn += 1                        # cleanup clears temp_triggers, not this
        for perm in self.a.battlefield:
            perm.temp_triggers.clear()
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(self.a.life, 23)

    def test_tokens_have_the_ability(self):
        self.resolve('Create two 1/1 black Rat creature tokens. They have "When this token dies, you gain 1 life."')
        rats = [x for x in self.a.battlefield if "Rat" in x.card.subtypes]
        self.assertEqual(len(rats), 2)
        self.game.destroy(rats[0])
        self.game.settle()
        self.assertEqual(self.a.life, 21)

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_whisperwood_skips_face_down_creatures(self):
        from mtgsim import manifest
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Whisperwood Elemental", "Ribtruss Roaster", "Return of the Mole Man", "Ascendant Spirit"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)
        wood = self.game.enter_battlefield(self.a, db.get("Whisperwood Elemental"))
        bear = self.game.enter_battlefield(self.a, BEAR)
        hidden = manifest.manifest_one(self.game, self.a)
        self.game.settle()
        self.assertTrue(self.game.activate(self.a, wood, "ability:0"))
        self.game.settle()
        self.assertEqual([t.event for t in bear.temp_triggers], ["dies"])
        self.assertEqual(hidden.temp_triggers, [])
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(sum(x.hidden is not None for x in self.a.battlefield), 2)    # manifested one more


if __name__ == "__main__":
    unittest.main()
