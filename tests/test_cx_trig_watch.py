"""'When that creature dies this turn' (cx_trig_watch), on real cards from the database."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")


@unittest.skipUnless(HAVE_DB, "card database not built")
class WatchTests(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parse(self):
        for n in ("A Good Day to Die", "Blessed Defiance"):
            self.assertEqual(self.db.get(n).unsupported, [], n)

    def test_draws_when_the_creature_dies(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.cast_free(self.a, self.db.get("A Good Day to Die"))
        self.game.settle()
        self.assertEqual(len(self.game.cx_watchers), 1)
        hand = len(self.a.hand)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)
        self.assertEqual(self.game.cx_watchers, [])

    def test_no_trigger_if_a_different_creature_dies(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        other = self.game.enter_battlefield(self.a, BEAR)
        self.game.cast_free(self.a, self.db.get("A Good Day to Die"))
        self.game.settle()
        target = self.game.cx_watchers[0][1]
        spare = other if target is bear else bear
        hand = len(self.a.hand)
        self.game.destroy(spare)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)

    def test_expires_at_end_of_turn(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.cast_free(self.a, self.db.get("A Good Day to Die"))
        self.game.settle()
        self.game.turn += 1
        hand = len(self.a.hand)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)

    def test_spirit_token_for_blessed_defiance(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.cast_free(self.a, self.db.get("Blessed Defiance"))
        self.game.settle()
        self.game.destroy(bear)
        self.game.settle()
        self.assertTrue(any(x.card.is_token and "Spirit" in x.card.name for x in self.a.battlefield))


@unittest.skipUnless(HAVE_DB, "card database not built")
class WatchAI(unittest.TestCase):
    """The default AI really casts the spell, aims it at its own creature, and the payoff follows."""

    def run_turn(self, name):
        from mtgsim.ai import HeuristicAI
        from tests.test_templates import PLAINS, SWAMP
        db = CardDB()
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 2, "main1"
        game.active_idx = 0
        for p in (a, b):
            p.library = [ISLAND] * 20
        card = db.get(name)
        a.hand = [card]
        for land_card in (PLAINS, PLAINS, SWAMP, SWAMP):
            land = game.enter_battlefield(a, land_card)
            land.tapped = False
        bear = game.enter_battlefield(a, BEAR)
        bear.sick = False
        game.settle()
        return game, a, b, bear, card

    def test_ai_casts_the_trick_on_its_attacker_and_the_payoff_follows(self):
        from tests.test_templates import card
        for name in ("A Good Day to Die", "Blessed Defiance"):
            with self.subTest(card=name):
                game, a, b, bear, spell = self.run_turn(name)
                wall = game.enter_battlefield(b, card("Test Wall", "{2}", "Creature — Wall", "", 1, 4))
                game.settle()
                game.step = "declare_blockers"
                a.ai.after_blocks(game, a, [bear], {bear: [wall]})            # HeuristicAI picks the spell and the target
                game.settle()
                self.assertNotIn(spell, a.hand)                                # it cast the trick
                self.assertEqual([w[1] for w in game.cx_watchers], [bear])     # aimed at its own attacker
                hand, tokens = len(a.hand), sum(1 for x in a.battlefield if x.card.is_token)
                game.destroy(bear)
                game.settle()
                if name == "A Good Day to Die":
                    self.assertEqual(len(a.hand), hand + 1)
                else:
                    self.assertEqual(sum(1 for x in a.battlefield if x.card.is_token), tokens + 1)
