"""Day and night: real game state, flip by spells cast, daybound/nightbound transform."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND

NAME = "Avabruck Caretaker // Hollowhenge Huntmaster"


class DayNight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = CardDB(offline=True).get(NAME)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_parse_is_full(self):
        self.assertTrue(self.card.daybound and self.card.back.nightbound)
        self.assertFalse(self.card.approximations)
        self.assertFalse(self.card.back.approximations)

    def test_enter_makes_day_and_cycle(self):
        perm = self.game.enter_battlefield(self.a, self.card)
        self.assertEqual(self.game.day_night, "day")
        self.assertEqual(perm.card.name, self.card.name)
        self.game.last_turn_spells = {}
        self.game.take_turn(self.b)               # opponent's turn after a turn with no spells
        self.assertEqual(self.game.day_night, "night")
        self.assertEqual(perm.card.name, self.card.back.name)
        self.game.last_turn_spells = {self.b.name: 2}
        self.game.take_turn(self.a)
        self.assertEqual(self.game.day_night, "day")
        self.assertEqual(perm.card.name, self.card.name)

    def test_enters_transformed_at_night(self):
        self.game.day_night = "night"
        perm = self.game.enter_battlefield(self.a, self.card)
        self.assertEqual(perm.card.name, self.card.back.name)


    def test_enters_transformed_so_the_front_enters_trigger_never_fires(self):
        """Fixes #249: a front-face enters trigger must not fire when the card enters transformed at night."""
        from mtgsim.cards import card_from_scryfall
        front = {"name": "Dawn Watcher", "mana_cost": "{2}{W}", "cmc": 3, "type_line": "Creature — Human Werewolf",
                 "oracle_text": "When this creature enters, you gain 3 life.\nDaybound", "power": "2", "toughness": "2"}
        back = {"name": "Dusk Howler", "mana_cost": "", "cmc": 0, "type_line": "Creature — Werewolf",
                "oracle_text": "Nightbound", "power": "4", "toughness": "4"}
        card = card_from_scryfall({"name": "Dawn Watcher // Dusk Howler", "layout": "transform", "cmc": 3,
                                   "card_faces": [front, back]})
        self.game.day_night = "night"
        life = self.a.life
        perm = self.game.enter_battlefield(self.a, card)
        self.game.settle()
        self.assertEqual(perm.card.name, "Dusk Howler")
        self.assertEqual(self.a.life, life)                             # no front-face trigger at night
        self.game.day_night = "day"
        self.game.enter_battlefield(self.a, card)
        self.game.settle()
        self.assertEqual(self.a.life, life + 3)                         # by day it fires


    def test_nightbound_entering_with_neither_makes_it_night(self):
        night = self.card.back
        self.assertIsNone(getattr(self.game, "day_night", None))
        self.game.enter_battlefield(self.a, night)
        self.assertEqual(self.game.day_night, "night")

    def test_previous_player_after_an_extra_turn(self):
        perm = self.game.enter_battlefield(self.a, self.card)
        self.game.last_turn_spells = {}
        self.game.take_turn(self.a)                    # a's turn after b's (previous = b by default)
        self.assertEqual(self.game.day_night, "night")
        self.game.last_turn_spells = {self.a.name: 2, self.b.name: 0}
        self.game.take_turn(self.a)                    # an extra turn: the previous turn was a's own, who cast 2
        self.assertEqual(self.game.day_night, "day")
        self.assertEqual(perm.card.name, self.card.name)


if __name__ == "__main__":
    unittest.main()
