"""Triggers an effect creates for the rest of the turn: "Whenever <event> this turn, <effects>" (#399)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem

from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")


def turn_triggers(text):
    effects, bad = _parse_effects(text)
    if bad:
        return None
    return [[(t.event, [(e.kind, e.target) for e in t.effects]) for t in e.data["triggers"]]
            for e in effects if e.kind == "cx_turn_trigger"]


class Parsing(unittest.TestCase):
    def test_heads_and_bodies(self):
        self.assertEqual(turn_triggers("Whenever a creature attacks this turn, put a +1/+1 counter on it."),
                         [[("ev:attacks", [("p1_counters", "prev")])]])
        self.assertEqual(turn_triggers("Whenever you cast a creature spell this turn, draw a card."),
                         [[("ev:any_cast", [("draw", "none")])]])
        self.assertEqual(turn_triggers("Whenever a creature blocks this turn, its controller loses 1 life."),
                         [[("ev:blocks", [("lose_life", "that_controller")])]])
        self.assertEqual(turn_triggers("Whenever a creature dies this turn, you gain 1 life."),
                         [[("ev:dies", [("gain_life", "none")])]])

    def test_a_later_sentence_about_its_objects_belongs_to_the_trigger(self):
        got = turn_triggers("Whenever a creature you control attacks alone this turn, put three +1/+1 counters on "
                            "it. It gains trample, lifelink, and indestructible until end of turn.")
        self.assertEqual(len(got), 1)
        self.assertEqual([k for k, _ in got[0][0][1]], ["p1_counters", "grant", "grant", "grant"])
        # an independent sentence stays the spell's own
        effects, bad = _parse_effects("Whenever a creature dies this turn, you gain 1 life. Draw a card.")
        self.assertEqual(([e.kind for e in effects], bad), (["cx_turn_trigger", "draw"], []))

    def test_refusals(self):
        for text in ("Whenever that creature deals combat damage to a player this turn, draw a card.",   # earlier object
                     "Whenever a creature dealt damage this way dies this turn, add {R}.",
                     "Whenever a creature dies this turn, ~ deals 1 damage to any target.",           # ~ is no permanent
                     'Whenever a nontoken creature you control dies this turn, create a 1/1 black Rat creature '
                     'token with "~ can\'t block."',
                     "Whenever a creature attacks this turn, it gains flanking and frobs until end of turn.",
                     # the follow-up sentence about "it" doesn't parse: it must not run when the spell resolves
                     "Whenever a creature attacks this turn, put a +1/+1 counter on it. It frobs."):
            with self.subTest(text):
                self.assertIsNone(turn_triggers(text))


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def create(self, text, who=None):
        who = who or self.a
        spell = card("Test Spell", "{1}", "Instant", text)
        item = StackItem(who, [], [])
        item.card = spell
        for eff in spell.spell_effects:
            self.game.resolve(who, eff, None, item, None)
        self.game.settle()

    def test_blocks_dies_and_its_controller(self):
        self.create("Whenever a creature blocks this turn, its controller loses 1 life.")
        self.create("Whenever a creature dies this turn, you gain 1 life.")
        theirs = self.game.enter_battlefield(self.b, card("Theirs", "{1}", "Creature — Bear", "", 2, 2))
        self.game.fire(self.b, "blocks", theirs)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 19))      # the blocker's controller
        self.game.destroy(theirs)
        self.game.settle()
        self.assertEqual(self.a.life, 21)

    def test_it_is_the_event_object_and_the_trigger_ends_with_the_turn(self):
        self.create("Whenever a creature attacks this turn, put a +1/+1 counter on it.")
        bear = self.game.enter_battlefield(self.a, card("Bear", "{1}", "Creature — Bear", "", 2, 2))
        self.game.fire(self.a, "attacks", bear)
        self.game.settle()
        self.assertEqual(bear.counters.get("+1/+1"), 1)
        self.game.turn += 1
        self.game.fire(self.a, "attacks", bear)
        self.game.settle()
        self.assertEqual(bear.counters.get("+1/+1"), 1)
        self.assertEqual(self.game.cx_turn_watchers, [])

    def test_controller_relative_heads(self):
        self.create("Whenever a creature you control enters this turn, put a +1/+1 counter on it.")
        theirs = self.game.enter_battlefield(self.b, card("Theirs", "{1}", "Creature — Bear", "", 2, 2))
        mine = self.game.enter_battlefield(self.a, card("Mine", "{1}", "Creature — Bear", "", 2, 2))
        self.game.settle()
        self.assertEqual((mine.counters.get("+1/+1"), theirs.counters.get("+1/+1")), (1, None))

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        self.assertEqual([e.kind for e in db.get("The Naked Time").chapters[1]], ["cx_turn_trigger"])   # "II — ..."
        dup = db.get("Theoretical Duplication")
        item = StackItem(self.a, [], [])
        item.card = dup
        for eff in dup.spell_effects:
            self.game.resolve(self.a, eff, None, item, None)
        self.game.enter_battlefield(self.b, card("Ogre", "{3}", "Creature — Ogre", "", 3, 3))
        self.game.settle()
        self.assertEqual([x.card.name for x in self.a.battlefield], ["Ogre"])       # a copy, on our side
        guildmage = db.get("Vizkopa Guildmage")                                    # "... loses that much life"
        eff = next(e for act in guildmage.activated for e in act.effects or () if e.kind == "cx_turn_trigger")
        self.game.resolve(self.a, eff, None, item, None)
        from mtgsim.cards.model import Effect
        self.game.resolve(self.a, Effect("gain_life", 3), None, item, None)
        self.game.settle()
        self.assertEqual(self.b.life, 17)


class AI(unittest.TestCase):
    def game(self, extra):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        forest = db.get("Forest")
        a, b = Player("a", [], HeuristicAI()), Player("b", [], Scripted())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 2, "main1"
        a.library = b.library = [forest] * 10
        for _ in range(4):
            g.enter_battlefield(a, forest).sick = False
        glimpse = db.get("Glimpse of Nature")
        a.hand = [glimpse] + extra
        return g, a, glimpse

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_casts_it_before_the_creatures_it_draws_for(self):
        elf = card("Elf", "{G}", "Creature — Elf", "", 1, 1)
        g, a, glimpse = self.game([elf, elf, elf])
        g.main_phase(a)
        g.settle()
        self.assertNotIn(glimpse, a.hand)
        self.assertEqual(sum(x.card.name == "Elf" for x in a.battlefield), 3)
        self.assertGreaterEqual(len(a.hand) + sum(x.card.name == "Forest" for x in a.battlefield), 3 + 4)   # drew 3

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_holds_it_when_nothing_would_trigger(self):
        g, a, glimpse = self.game([])
        g.main_phase(a)
        g.settle()
        self.assertIn(glimpse, a.hand)


if __name__ == "__main__":
    unittest.main()
