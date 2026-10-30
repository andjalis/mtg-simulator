"""smol-chonk-4 batch 5, part 2: cross-event compound triggers and the "token" enters description.

"Whenever you cast a <color> spell or a <Type> you control enters" (Staff of the Magus family,
Necklace of Girion) and "Whenever another <type> you control enters or dies" (Daxos, Blessed by
the Sun) are one sentence with two triggers that carry different filters. The permanent_enters
description vocabulary now also accepts "token" (Wildwood Mentor, Leonardo); "outlaw",
"snow" and similar words card_matches can't express stay unsupported.
"""
import dataclasses
import random
import unittest

from mtgsim.cards.parse import _parse_trigger
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, MOUNTAIN, SHOCK, ISLAND, card

STAFF = card("Test Flame Magus", "{3}", "Artifact",
             "Whenever you cast a red spell or a Mountain you control enters, you gain 1 life.")
DAXOS = card("Test Daxos", "{1}{W}", "Creature — Human Soldier",
             "Whenever another creature you control enters or dies, you gain 1 life.", 2, 2)
MENTOR = card("Test Mentor", "{2}{G}", "Creature — Human Shaman",
              "Whenever a token you control enters, put a +1/+1 counter on ~.", 1, 1)
SPAWNER = card("Test Spawner", "{1}{G}", "Creature — Elf",
               "When ~ enters, create a 1/1 green Saproling creature token.", 1, 1)
SQUIRREL = dataclasses.replace(card("Saproling", types="Creature — Saproling", text="", cmc=0),
             is_token=True)


class CompoundParse(unittest.TestCase):
    def test_staff_line_makes_two_triggers(self):
        trigs, bad, _ = _parse_trigger("Whenever you cast a red spell or a Mountain you control "
                                    "enters, you gain 1 life.")
        self.assertEqual(bad, [])
        self.assertEqual([(t.event, t.filter) for t in trigs],
                         [("cast_spell", "spell:red"), ("permanent_enters", "noself|any|Mountain")])

    def test_and_whenever_wording_matches_the_same_shape(self):
        trigs, bad, _ = _parse_trigger("Whenever you cast a green spell and whenever a Forest you "
                                    "control enters, put a +1/+1 counter on target creature you control.")
        self.assertEqual(bad, [])
        self.assertEqual([(t.event, t.filter) for t in trigs],
                         [("cast_spell", "spell:green"), ("permanent_enters", "noself|any|Forest")])

    def test_enters_or_dies_makes_two_triggers(self):
        trigs, bad, _ = _parse_trigger("Whenever another creature you control enters or dies, "
                                    "you gain 1 life.")
        self.assertEqual(bad, [])
        self.assertEqual([(t.event, t.filter) for t in trigs],
                         [("permanent_enters", "noself|other|creature"),
                          ("ally_dies", "other||creature")])

    def test_token_description(self):
        self.assertEqual(MENTOR.unsupported, [], "mentor")
        (trig,) = MENTOR.triggers
        self.assertEqual((trig.event, trig.filter), ("permanent_enters", "noself|any|token"))
        trigs, bad, _ = _parse_trigger("Whenever another creature token you control enters, untap ~.")
        self.assertEqual(bad, [])
        self.assertEqual(trigs[0].filter, "noself|other|creature token")

    def test_words_the_engine_cant_match_stay_unsupported(self):
        for text in ("Whenever another outlaw you control enters, ~ deals 1 damage to target opponent.",
                     "Whenever another snow permanent you control enters, scry 1.",
                     "Whenever another nontoken historic permanent you control enters, you gain 1 life."):
            self.assertIsNone(_parse_trigger(text), text)


class CompoundEngine(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.ai.attack, p.ai.block = (), {}

    def test_staff_fires_on_cast_and_on_land(self):
        self.game.enter_battlefield(self.a, STAFF)
        self.game.enter_battlefield(self.a, MOUNTAIN)
        self.a.hand.append(SHOCK)
        self.game.cast(self.a, SHOCK, [self.b])
        self.game.settle()
        self.assertEqual(self.a.life, 22)          # 20 + red spell + Mountain
        self.game.enter_battlefield(self.a, MOUNTAIN)
        self.game.settle()
        self.assertEqual(self.a.life, 23)
        self.game.enter_battlefield(self.a, ISLAND)          # not a Mountain
        self.a.hand.append(SHOCK)
        self.game.cast(self.a, SHOCK, [self.b])              # still only red spells trigger it
        self.game.settle()
        self.assertEqual(self.a.life, 24)

    def test_daxos_fires_on_other_creatures_only(self):
        daxos = self.game.enter_battlefield(self.a, DAXOS)
        self.game.settle()
        self.assertEqual(self.a.life, 20)          # its own entry is not "another"
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        self.assertEqual(self.a.life, 21)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(self.a.life, 22)
        self.game.destroy(daxos)                   # its own death is not "another"
        self.game.settle()
        self.assertEqual(self.a.life, 22)

    def test_mentor_fires_for_tokens_only(self):
        mentor = self.game.enter_battlefield(self.a, MENTOR)
        self.game.settle()
        self.game.enter_battlefield(self.a, BEAR)             # not a token
        self.game.settle()
        self.assertEqual(mentor.counters.get("+1/+1"), None)
        self.game.enter_battlefield(self.a, SQUIRREL)
        self.game.settle()
        self.assertEqual(mentor.counters.get("+1/+1"), 1)


if __name__ == "__main__":
    unittest.main()
