"""Counted target lists lifted onto any effect (#312): "up to one", "up to N", "N target ..."."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")


def parsed(text):
    effects, bad = _parse_effects(text)
    return None if bad else effects


class Parsing(unittest.TestCase):
    def test_counts(self):
        tap = parsed("Tap up to two target artifacts and/or creatures.")
        self.assertEqual([e.kind for e in tap], ["tap", "tap"])
        self.assertTrue(all(e.data["optional_target"] and e.data["distinct"] for e in tap))
        self.assertEqual(len({e.data["group"] for e in tap}), 1)
        tuck = parsed("Put two target lands on top of their owners' libraries.")
        self.assertEqual(len(tuck), 2)
        self.assertFalse(any(e.data.get("optional_target") for e in tuck))     # exactly two
        blink = parsed("Exile up to three target lands you control, then return them to the battlefield tapped "
                       "under their owner's control.")
        self.assertEqual(len(blink), 3)
        one = parsed("Remove all counters from up to one target permanent.")
        self.assertEqual(len(one), 1)
        self.assertTrue(one[0].data["optional_target"])
        self.assertNotIn("distinct", one[0].data)

    def test_parse_is_deterministic(self):
        a = parsed("Tap up to two target artifacts and/or creatures.")
        b = parsed("Tap up to two target artifacts and/or creatures.")
        self.assertEqual(a, b)

    def test_refusals(self):
        for text in ("Choose up to one target creature an opponent controls.",     # a referent, not an effect
                     "Destroy up to two target creatures and they can't be regenerated.",   # "they" stays plural
                     "Tap up to two target creatures and frobnicate them.",      # rest unparsed
                     "Destroy target artifact and up to two target creatures."):  # two target phrases
            with self.subTest(text):
                self.assertIsNone(parsed(text))

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards_are_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Double Negative", "Hex", "Plow Under", "Gandalf, Shadow's Foe", "Redeem",
                     "Council of Echoes", "Veteran Ice Climber", "Whirlwind Technique"):
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

    def spell(self, text):
        c = card("Test Spell", "{1}", "Instant", text)
        self.assertEqual(c.unsupported, [], text)
        return c

    def resolve(self, c, targets):
        item = StackItem(self.a, list(c.spell_effects), targets, card=c, name=c.name)
        self.game.stack.append(item)
        self.game.resolve_top()
        return item

    def test_ai_picks_distinct_targets_and_may_pick_fewer(self):
        bounce = self.spell("Return up to two target nonland permanents to their owners' hands.")
        theirs = [self.game.enter_battlefield(self.b, BEAR)]
        targets = self.game.auto_targets(self.a, bounce.spell_effects)
        self.assertEqual(targets, [theirs[0], None])            # one legal target: the second slot stays empty
        theirs.append(self.game.enter_battlefield(self.b, BEAR))
        targets = self.game.auto_targets(self.a, bounce.spell_effects)
        self.assertEqual({id(t) for t in targets}, {id(t) for t in theirs})
        self.assertTrue(self.game.valid_action_targets(self.a, bounce.spell_effects, targets))
        self.assertFalse(self.game.valid_action_targets(self.a, bounce.spell_effects, [theirs[0], theirs[0]]))
        self.resolve(bounce, targets)
        self.assertEqual(self.b.battlefield, [])

    def test_exact_count_needs_that_many_targets(self):
        tuck = self.spell("Put two target creatures on top of their owners' libraries.")
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.assertFalse(self.game.valid_action_targets(self.a, tuck.spell_effects, [bear, None]))

    def test_fizzles_only_when_every_chosen_target_is_illegal(self):
        bounce = self.spell("Return up to two target nonland permanents to their owners' hands.")
        x, y = self.game.enter_battlefield(self.b, BEAR), self.game.enter_battlefield(self.b, BEAR)
        self.game.leave_battlefield(x, "exile")                  # gone before resolution
        item = self.resolve(bounce, [x, y])
        self.assertTrue(item.resolved)
        self.assertNotIn(y, self.b.battlefield)
        z = self.game.enter_battlefield(self.b, BEAR)
        self.game.leave_battlefield(z, "exile")
        item = self.resolve(bounce, [z, None])
        self.assertFalse(item.resolved)                          # its only target is gone

    def test_no_target_chosen_resolves(self):
        tap = self.spell("Tap up to two target creatures you don't control. You gain 1 life.")
        life = self.a.life
        item = self.resolve(tap, [None, None, None])
        self.assertTrue(item.resolved)
        self.assertEqual(self.a.life, life + 1)


if __name__ == "__main__":
    unittest.main()
