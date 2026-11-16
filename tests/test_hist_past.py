"""Turn-history conditions in any past tense the trigger grammar reads (#397 slice 2, mtgsim/cx_hist_past.py):
"if you lost life last turn", "if no creatures died this turn", "if you didn't play a land this turn",
"if you gained or lost life this turn"."""
import os
import random
import unittest

from mtgsim.cx_condlib import parse
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
if HAVE_DB:
    from mtgsim.carddb import CardDB
    DB = CardDB()


class Parse(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(parse("you lost life last turn"), 'lib:["hist","you lose life",1,"last"]')
        self.assertEqual(parse("an opponent lost life last turn"), 'lib:["hist","an opponent loses life",1,"last"]')
        self.assertEqual(parse("no creatures died this turn"), '!lib:["hist","a creature dies",1]')
        self.assertEqual(parse("you didn't play a land this turn"), '!lib:["hist","you play a land",1]')
        self.assertEqual(parse("a player discarded a card this turn"), 'lib:["hist","a player discards a card",1]')
        self.assertEqual(parse("an enchantment was put into your graveyard from the battlefield this turn"),
                         'lib:["hist","an enchantment is put into your graveyard from the battlefield",1]')
        self.assertTrue(parse("you gained or lost life this turn").startswith('lib:["or"'))

    def test_refusals(self):
        for phrase in ("another creature entered the battlefield under your control this turn",   # counts ~
                       "~ was dealt damage this turn", "it was dealt damage this turn",          # per object
                       "that player didn't cast a creature spell this turn",
                       "an opponent lost 3 or more life this turn",                              # a total
                       "an opponent was dealt 3 or more damage this turn",
                       "you frobbed a widget this turn", "no creatures frobbed this turn"):
            self.assertEqual(parse(phrase), "", phrase)


@unittest.skipUnless(HAVE_DB, "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def get(self, name):
        c = DB.get(name)
        self.assertEqual(c.unsupported, [], name)
        return c

    def turn(self, p):
        self.game.turn += 1
        self.game.active_idx = self.game.players.index(p)

    def tokens(self, p):
        return sum(1 for x in p.battlefield if x.card.is_token)

    def test_first_response_last_turn(self):
        self.game.enter_battlefield(self.a, self.get("First Response"))
        self.game.change_life(self.a, -2, None)            # turn 2: lost life
        self.turn(self.b)                                  # turn 3: "last turn" is turn 2
        self.game.fire(self.b, "upkeep")
        self.game.settle()
        self.assertEqual(self.tokens(self.a), 1)
        self.turn(self.a)                                  # turn 4: nothing lost on turn 3
        self.game.fire(self.a, "upkeep")
        self.game.settle()
        self.assertEqual(self.tokens(self.a), 1)

    def test_titan_hunter_no_creatures_died(self):
        self.game.enter_battlefield(self.a, self.get("Titan Hunter"))
        self.game.fire(self.b, "end_step")                 # nothing died: 4 damage to that player
        self.game.settle()
        self.assertEqual(self.b.life, 16)
        self.turn(self.a)
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.destroy(bear)
        self.game.settle()
        self.game.fire(self.a, "end_step")                 # a creature died this turn: nothing
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 16))

    def test_mercadian_atlas_didnt_play_a_land(self):
        self.game.enter_battlefield(self.a, self.get("Mercadian Atlas"))
        hand = len(self.a.hand)
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1, "no land played: drew")
        self.turn(self.a)
        self.a.hand.append(FOREST)
        self.game.play_land(self.a, FOREST)
        hand = len(self.a.hand)
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand, "played a land: no draw")

    def test_starlit_soothsayer_gained_or_lost_life(self):
        self.game.enter_battlefield(self.a, self.get("Starlit Soothsayer"))

        def fired():
            return sum("Starlit Soothsayer trigger resolves" in e for e in self.game.events)
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual(fired(), 0, "no life change: no surveil")
        for delta in (3, -1):                              # gained, then (next turn) lost
            self.turn(self.a)
            self.game.change_life(self.a, delta, None)
            self.game.fire(self.a, "end_step")
            self.game.settle()
        self.assertEqual(fired(), 2)

    def test_raven_man_a_player_discarded(self):
        self.game.enter_battlefield(self.a, self.get("The Raven Man"))
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual(self.tokens(self.a), 0)
        self.turn(self.b)
        self.b.hand = [ISLAND]
        self.game.discard_card(self.b, ISLAND)            # an opponent's discard counts too
        self.game.fire(self.b, "end_step")
        self.game.settle()
        self.assertEqual(self.tokens(self.a), 1)

    def test_charging_cinderhorn_no_creatures_attacked(self):
        horn = self.game.enter_battlefield(self.a, self.get("Charging Cinderhorn"))
        bear = self.game.enter_battlefield(self.a, BEAR)
        bear.sick = horn.sick = False
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual(horn.counters.get("fury", 0), 1, "no attacks: a fury counter")
        self.turn(self.a)
        self.a.ai.attack = (bear,)
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual(horn.counters.get("fury", 0), 1, "a creature attacked: none")


if __name__ == "__main__":
    unittest.main()
