"""Pilot and Spirit token statics (#375): crew/saddle power bonus, "can't block or be blocked by non-X"."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.engine.policy import choose_crew, saddle_creatures
from mtgsim.engine.state import can_block

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")
PILOT = card("Test Pilot", "{W}", "Creature — Pilot",
             "This creature saddles Mounts and crews Vehicles as though its power were 2 greater.", power=1, toughness=1)
VEHICLE = card("Test Wagon", "{2}", "Artifact — Vehicle", "Crew 3", power=4, toughness=4)
MOUNT = card("Test Steed", "{2}", "Creature — Horse Mount", "Saddle 3", power=3, toughness=3)
SPIRIT_MAKER = card("Test Spirits", "{1}{B}", "Sorcery", "Create a 1/1 colorless Spirit creature token with "
                    "\"This token can't block or be blocked by non-Spirit creatures.\"")
SPIRIT = card("Test Spirit", "{1}", "Creature — Spirit", "", power=2, toughness=2)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20


class Crew(Base):
    def test_parses(self):
        self.assertEqual(PILOT.unsupported, [])
        self.assertEqual((PILOT.advanced_rules["crew_bonus"], PILOT.advanced_rules["saddle_bonus"]), (2, 2))
        only = card("Test Crewman", "{W}", "Creature — Pilot",
                    "This creature crews Vehicles as though its power were 2 greater.", power=1, toughness=1)
        self.assertNotIn("saddle_bonus", only.advanced_rules)

    def test_one_pilot_crews_and_saddles_three(self):
        pilot = self.game.enter_battlefield(self.a, PILOT)
        wagon = self.game.enter_battlefield(self.a, VEHICLE)
        wagon.sick = False
        self.assertEqual(choose_crew(self.game, self.a, wagon), [pilot])
        self.assertTrue(self.game.activate(self.a, wagon, "crew"))
        self.assertTrue(wagon.is_creature and pilot.tapped)
        self.assertEqual(pilot.power, 1)                      # not a P/T change
        pilot.tapped = False
        steed = self.game.enter_battlefield(self.a, MOUNT)
        self.assertEqual(saddle_creatures(self.game, self.a, steed), [pilot])

    def test_suppressed_pilot_counts_its_power(self):
        pilot = self.game.enter_battlefield(self.a, PILOT)
        wagon = self.game.enter_battlefield(self.a, VEHICLE)
        wagon.sick = False
        pilot.silenced_by = self.game.enter_battlefield(self.b, BEAR)
        self.assertIsNone(choose_crew(self.game, self.a, wagon))


class Evasion(Base):
    def test_spirit_token(self):
        self.assertEqual(SPIRIT_MAKER.unsupported, [])
        from mtgsim.engine.state import StackItem
        self.game.stack.append(StackItem(self.a, list(SPIRIT_MAKER.spell_effects), [None], card=SPIRIT_MAKER,
                                         name=SPIRIT_MAKER.name))
        self.game.resolve_top()
        token = next(x for x in self.a.battlefield if x.card.is_token)
        bear, spirit = self.game.enter_battlefield(self.b, BEAR), self.game.enter_battlefield(self.b, SPIRIT)
        self.assertFalse(can_block(bear, token))              # non-Spirits can't block it
        self.assertTrue(can_block(spirit, token))
        self.assertFalse(can_block(token, bear))              # and it can't block them
        self.assertTrue(can_block(token, spirit))

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards_are_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Baboon Spirit", "Lost in the Spirit World", "Dragonfly Pilot", "Deathless Pilot",
                     "Back on Track", "Shorikai, Genesis Engine", "Sneaky Homunculus"):
            with self.subTest(name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")


if __name__ == "__main__":
    unittest.main()
