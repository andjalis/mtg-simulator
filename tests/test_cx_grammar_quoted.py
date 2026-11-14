"""Temporary grants of quoted triggered abilities (#338 slice 2)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.policy import default_choose_target
from mtgsim.engine.state import StackItem

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")
ENDURANCE = card("Test Endurance", "{1}{B}", "Instant", "Until end of turn, target creature gets +2/+0 and gains "
                 "\"When this creature dies, return it to the battlefield tapped under its owner's control.\"")
LESSON = card("Test Lesson", "{G}", "Instant", "Until end of turn, up to two target creatures you control each gain "
              "\"Whenever this creature deals combat damage to a player, draw a card.\"")
RALLY = card("Test Rally", "{1}{W}", "Instant", "Until end of turn, Bears you control gain \"Whenever this creature "
             "attacks, you gain 1 life.\"")


def kinds(text):
    effects, bad = _parse_effects(text)
    return None if bad else [e.kind for e in effects]


class Parsing(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(kinds(ENDURANCE.oracle), ["pump", "grant_triggers"])
        self.assertEqual(kinds(LESSON.oracle), ["grant_triggers", "grant_triggers"])
        self.assertEqual(kinds(RALLY.oracle), ["cx_group"])
        self.assertEqual(kinds("Until end of turn, creatures you control get +2/+2 and gain \"Whenever this creature "
                               "deals combat damage to a player, draw a card.\""), ["cx_group"])

    def test_refusals(self):
        for text in (
                # a drawback the AI would hand to its own creature
                "Until end of turn, target creature gets +1/+1 and gains \"At the beginning of your upkeep, you lose "
                "1 life.\"",
                # not a one-turn grant
                "Target creature gets +1/+1 and gains \"When this creature dies, draw a card.\"",
                # the return rider "it deals 1 damage to each opponent" has no faithful reading here
                "Until end of turn, target creature you control gains \"When this creature dies, return it to the "
                "battlefield tapped under its owner's control. It deals 1 damage to each opponent.\"",
                # the quoted body itself isn't matched
                "Until end of turn, target creature gains \"Whenever this creature attacks, frobnicate.\""):
            with self.subTest(text):
                self.assertIsNone(kinds(text))

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards_are_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Abnormal Endurance", "Warriors' Lesson", "Undying Malice", "Feign Death", "Fake Your Own Death",
                     "Presumed Dead", "Not Dead After All", "Commander Mustard", "Supernatural Stamina"):
            with self.subTest(name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def cast(self, c, targets, by=None):
        effects = list(c.spell_effects)
        self.game.stack.append(StackItem(by or self.a, effects, targets, card=c, name=c.name))
        self.game.resolve_top()
        self.game.settle()

    def bears(self, p):
        return [x for x in p.battlefield if x.card.name == BEAR.name]

    def test_dies_return_tracks_the_card_and_its_owner(self):
        theirs = self.game.enter_battlefield(self.b, BEAR)
        self.cast(ENDURANCE, [theirs, None])
        self.assertEqual(theirs.power, 4)
        self.assertEqual(len(theirs.temp_triggers), 1)          # cleared at cleanup like other one-turn grants
        self.game.destroy(theirs)
        self.game.settle()
        back = self.bears(self.b)
        self.assertEqual(len(back), 1)                           # under its owner's control, not the caster's
        self.assertIsNot(back[0], theirs)
        self.assertTrue(back[0].tapped)
        self.assertEqual((back[0].power, back[0].temp_triggers), (2, []))   # a new object: no pump, no ability
        self.assertNotIn(BEAR, self.b.graveyard)

    def test_card_moved_in_response_is_not_returned(self):
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.cast(ENDURANCE, [mine, None])
        self.game.destroy(mine)                                  # the trigger waits in pending
        card = mine.front
        self.a.graveyard.remove(card)
        self.a.exile.append(card)
        self.game.settle()
        self.assertEqual(self.bears(self.a), [])
        self.assertIn(card, self.a.exile)

    def test_riders_act_on_the_returned_permanent(self):
        fake = card("Test Fake", "{1}{B}", "Instant", "Until end of turn, target creature gets +2/+0 and gains \"When "
                    "this creature dies, return it to the battlefield tapped under its owner's control and create a "
                    "Treasure token.\"")
        presumed = card("Test Presumed", "{1}{B}", "Instant", "Until end of turn, target creature gets +2/+0 and gains "
                        "\"When this creature dies, return it to the battlefield under its owner's control and "
                        "suspect it.\"")
        for spell, check in ((fake, lambda back: any(x.card.name == "Treasure" for x in self.a.battlefield)),
                             (presumed, lambda back: back.has("menace"))):
            with self.subTest(spell.name):
                bear = self.game.enter_battlefield(self.a, BEAR)
                self.cast(spell, [bear, None])
                self.game.destroy(bear)
                self.game.settle()
                back = [x for x in self.bears(self.a) if x is not bear]
                self.assertEqual(len(back), 1)
                self.assertTrue(check(back[0]))
                self.game.leave_battlefield(back[0], "exile")

    def test_group_grant_is_fixed_on_resolution(self):
        old = self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, BEAR)
        self.cast(RALLY, [None])
        late = self.game.enter_battlefield(self.a, BEAR)
        self.assertEqual((len(old.temp_triggers), len(theirs.temp_triggers), len(late.temp_triggers)), (1, 0, 0))
        life = self.a.life
        self.game.fire(self.a, "attacks", old)
        self.game.settle()
        self.assertEqual(self.a.life, life + 1)

    def test_combat_damage_draw_for_the_recipients_controller(self):
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.cast(LESSON, [mine, None])
        hand = len(self.a.hand)
        self.game.fire(self.a, "combat_damage_player", mine, context=self.b)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_ai_aims_the_grant_at_its_own_creatures(self):
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.game.enter_battlefield(self.b, BEAR)
        for eff in LESSON.spell_effects + ENDURANCE.spell_effects[:1]:
            self.assertIs(default_choose_target(self.game, self.a, eff), mine)


if __name__ == "__main__":
    unittest.main()
