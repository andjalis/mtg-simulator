"""'If you've scried or surveilled this turn' and 'if you've surveilled this turn': per-player flags set by
scry and surveil, cleared each turn, and read by cx_condlib."""
import random
import unittest

from mtgsim import cx_condlib
from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND

EITHER, SURVEIL = 'lib:["scried_surveilled"]', 'lib:["surveilled"]'


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10


class ScrySurveilTurn(Base):
    def holds(self, code, p=None):
        return cx_condlib.check(self.game, p or self.a, code)

    def test_phrases_map_to_the_codes(self):
        self.assertEqual(cx_condlib._ALIASES["you've scried or surveilled this turn"], EITHER)
        self.assertEqual(cx_condlib._ALIASES["you've surveilled this turn"], SURVEIL)

    def test_scry_counts_for_either_but_not_for_surveilled(self):
        self.game.resolve(self.a, Effect("scry", 1), None)
        self.assertTrue(self.holds(EITHER))
        self.assertFalse(self.holds(SURVEIL))

    def test_surveil_counts_for_both(self):
        self.game.resolve(self.a, Effect("surveil", 2), None)
        self.assertTrue(self.holds(EITHER))
        self.assertTrue(self.holds(SURVEIL))

    def test_only_the_player_who_scried(self):
        self.game.resolve(self.b, Effect("surveil", 1), None)
        self.assertFalse(self.holds(EITHER))
        self.assertTrue(self.holds(EITHER, self.b))

    def test_scry_zero_and_surveil_zero_are_not_events(self):
        # 701.22b / 701.25c: instructed to scry 0 or surveil 0, no scry or surveil event occurs.
        self.game.resolve(self.a, Effect("scry", 0), None)
        self.game.resolve(self.a, Effect("surveil", 0), None)
        self.assertFalse(self.holds(EITHER))

    def test_flags_clear_at_the_next_turn(self):
        self.game.resolve(self.a, Effect("scry", 1), None)
        self.game.resolve(self.a, Effect("surveil", 1), None)
        self.game.take_turn(self.b)
        self.assertFalse(self.holds(EITHER))
        self.assertFalse(self.holds(SURVEIL))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB()

    def test_surveillance_phantasm_attacks_only_after_scry_or_surveil(self):
        self.game.enter_battlefield(self.a, self.db.get("Surveillance Phantasm"))
        phantasm = self.a.creatures[0]
        phantasm.sick = False
        self.assertFalse(phantasm.can_attack())
        self.game.resolve(self.a, Effect("scry", 1), None)
        self.assertTrue(phantasm.can_attack())

    def futurescribe_combat_trigger(self):
        card = self.db.get("Desperate Futurescribe")
        self.game.enter_battlefield(self.a, card)
        self.game.enter_battlefield(self.a, BEAR)
        source, bear = self.a.creatures
        effects = list(card.triggers[0].effects)
        self.game.stack.append(StackItem(self.a, effects, self.game.auto_targets(self.a, effects, source), source=source,
                                         kind="ability"))
        self.game.settle()
        return bear

    def test_desperate_futurescribe_pumps_without_scry(self):
        bear = self.futurescribe_combat_trigger()
        self.assertEqual((bear.power, bear.toughness), (3, 3))
        self.assertEqual(bear.counters.get("+1/+1", 0), 0)

    def test_desperate_futurescribe_puts_a_counter_instead_after_surveil(self):
        self.game.resolve(self.a, Effect("surveil", 1), None)
        bear = self.futurescribe_combat_trigger()
        self.assertEqual((bear.power, bear.toughness), (3, 3))
        self.assertEqual(bear.counters.get("+1/+1"), 1)


if __name__ == "__main__":
    unittest.main()
