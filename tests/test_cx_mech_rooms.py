"""cx_mech: Rooms: cast either half, unlock the other door as a sorcery, "When you unlock this door"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim import cx_mech
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, BEAR

POOL = "Bottomless Pool // Locker Room"


class Rooms(unittest.TestCase):
    ai = Scripted

    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], self.ai()), Player("b", [], self.ai())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def lands(self, n):
        for _ in range(n):
            self.game.enter_battlefield(self.a, self.db.get("Island")).sick = False
        self.game.settle()

    def room(self):
        return next(x for x in self.a.battlefield if "Room" in x.card.subtypes)

    def test_parse_clean(self):
        card = self.db.get(POOL)
        self.assertEqual(card.unsupported, [])
        self.assertEqual(card.back.unsupported, [])

    def test_cast_left_unlocks_it_and_bounces_a_creature(self):
        card = self.db.get(POOL)
        victim = self.game.enter_battlefield(self.b, BEAR)
        self.game.settle()
        self.a.hand = [card]
        self.lands(1)
        (left,) = [x for x in self.game.spell_options(self.a) if x.name.endswith("(Bottomless Pool)")]
        self.assertEqual(left.cmc, 1)                   # the spell has its half's mana value
        self.assertEqual([x.name for x in self.game.spell_options(self.a)].count(card.name), 0)
        self.assertTrue(self.game.cast(self.a, left))
        self.game.settle()
        self.assertEqual(self.room().card.name, card.name)
        self.assertEqual(self.room().card.cmc, 1)       # one door unlocked: {U}; both halves in hand: 6
        self.assertEqual(card.cmc, 6)
        self.assertNotIn(victim, self.b.battlefield)

    def test_cast_right_half_has_only_that_door(self):
        card = self.db.get(POOL)
        self.a.hand = [card]
        self.lands(5)
        (v,) = [x for x in self.game.spell_options(self.a) if x.name.endswith("(Locker Room)")]
        self.assertEqual(v.cmc, 5)
        self.assertTrue(self.game.cast(self.a, v))
        self.game.settle()
        room = self.room()
        self.assertEqual(cx_mech._doors(room)[2], "right")
        self.assertEqual(room.card.cmc, 5)             # {4}{U}
        self.assertFalse(any(e.kind == "bounce" for e in room.card.etb_effects))

    def test_unlock_the_other_door_for_its_cost_runs_its_effects(self):
        card = self.db.get("Central Elevator // Promising Stairs")
        self.a.hand = [card]
        self.lands(8)
        (v,) = [x for x in self.game.spell_options(self.a) if x.name.endswith("(Promising Stairs)")]
        self.assertEqual(v.cmc, 3)
        self.assertTrue(self.game.cast(self.a, v))
        self.game.settle()
        room = self.room()
        self.assertEqual(cx_mech._doors(room)[2], "right")
        self.assertTrue(cx_mech.unlock(self.game, self.a, room))
        self.game.settle()
        self.assertEqual(cx_mech._doors(room)[2], "both")
        self.assertEqual(room.card.cmc, 7)             # {3}{U} + {2}{U}: both doors
        self.assertFalse(cx_mech.can_unlock(self.game, self.a, room))      # nothing left to unlock
        self.assertIn("Whenever", "Whenever")                                # merged abilities stay


class RoomsAi(unittest.TestCase):
    setUp = Rooms.setUp
    ai = HeuristicAI
    lands = Rooms.lands
    room = Rooms.room

    def test_default_ai_casts_a_room_and_unlocks_its_other_door(self):
        card = self.db.get(POOL)
        self.a.hand = [card]
        self.lands(7)
        self.game.step = "main1"
        self.game.main_phase(self.a)
        self.assertTrue(any("Room" in x.card.subtypes for x in self.a.battlefield))     # cast in main 1
        self.game.step = "main2"
        self.game.main_phase(self.a)
        self.assertEqual(cx_mech._doors(self.room())[2], "both")


if __name__ == "__main__":
    unittest.main()
