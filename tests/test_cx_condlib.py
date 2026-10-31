"""The shared condition library: "If <condition>, X", intervening-if triggers and "as long as" statics."""
import random
import unittest

from mtgsim.cards import Effect
from mtgsim.cx_condlib import parse
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, card

KICKED = card("Test Kicked Sprout", "{G}", "Creature — Elf",
              "Kicker {2}\nWhen ~ enters, if it was kicked, you gain 5 life.", 1, 1)
MONARCH = card("Test Court Page", "{1}{W}", "Creature — Human",
               "At the beginning of your upkeep, if you're the monarch, draw a card.", 1, 1)
GATES = card("Test Gatekeeper", "{3}", "Creature — Human",
             "When ~ enters, if you control two or more Gates, you gain 3 life.", 2, 2)
LIBRARIAN = card("Test Librarian", "{2}{U}", "Creature — Human Wizard",
                 "When ~ enters, if there are three or more instant and/or sorcery cards in your graveyard, "
                 "draw a card.", 2, 2)
STATIC = card("Test Underdog", "{1}{R}", "Creature — Goblin",
              "~ gets +2/+2 as long as an opponent controls more creatures than you.", 1, 1)
GATE = card("Test Gate", types="Land — Gate", text="({T}: Add {C}.)")
BOLT = card("Test Bolt", "{R}", "Instant", "~ deals 3 damage to any target.")


class ConditionParse(unittest.TestCase):
    def test_parse_codes(self):
        self.assertEqual(parse("it was kicked"), 'lib:["kicked"]')
        self.assertEqual(parse("a permanent you controlled left the battlefield this turn"), "perm_left")
        self.assertTrue(parse("you control no untapped lands").startswith("lib:"))
        self.assertTrue(parse("you control an artifact and an enchantment").startswith('lib:["and"'))
        self.assertTrue(parse("you control a Desert or there is a Desert card in your graveyard").startswith('lib:["or"'))
        self.assertEqual(parse("you control your commander"), "")
        self.assertEqual(parse("you win the flip"), "")

    def test_cards_parse(self):
        for c in (KICKED, MONARCH, GATES, LIBRARIAN, STATIC):
            self.assertEqual(c.unsupported, [], c.name)


class ConditionEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def holds(self, phrase, source=None):
        item = StackItem(self.a, [], [], source=source)
        return self.game.check_cond(self.a, Effect("draw", cond=parse(phrase)), item, None)

    def test_counts(self):
        self.assertFalse(self.holds("you control two or more Gates"))
        self.game.enter_battlefield(self.a, GATE)
        self.game.enter_battlefield(self.a, GATE)
        self.assertTrue(self.holds("you control two or more Gates"))
        self.assertFalse(self.holds("you control no untapped lands"))
        self.assertTrue(self.holds("you control no creatures"))
        self.game.enter_battlefield(self.b, BEAR)
        self.assertTrue(self.holds("an opponent controls more creatures than you"))
        self.a.graveyard.extend([BOLT, BOLT])
        self.assertFalse(self.holds("there are three or more instant and/or sorcery cards in your graveyard"))
        self.a.graveyard.append(BOLT)
        self.assertTrue(self.holds("there are three or more instant and/or sorcery cards in your graveyard"))
        self.assertTrue(self.holds("you control a Gate or there is a Gate card in your graveyard"))

    def test_player_state(self):
        self.assertFalse(self.holds("you're the monarch"))
        self.game.monarch = self.a
        self.assertTrue(self.holds("you're the monarch"))
        self.b.life = 5
        self.assertTrue(self.holds("an opponent has 5 or less life"))
        self.assertTrue(self.holds("you have more life than an opponent"))
        self.b.counters["poison"] = 3
        self.assertTrue(self.holds("an opponent has three or more poison counters"))

    def test_kicked_trigger(self):
        perm = self.game.enter_battlefield(self.a, KICKED)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        perm.kicked = True
        self.assertTrue(self.holds("it was kicked", source=perm))

    def test_kicked_cast(self):
        for _ in range(3):
            self.game.enter_battlefield(self.a, FOREST).sick = False
        self.a.hand = [KICKED]
        variants = [v for v in self.game.spell_options(self.a) if getattr(v, "origin", (None, ""))[1] == "kicker"]
        self.assertTrue(variants)
        self.assertTrue(self.game.cast(self.a, variants[0], []))
        self.game.settle()
        self.assertEqual(self.a.life, 25)

    def test_intervening_if_graveyard(self):
        self.a.graveyard.extend([BOLT] * 3)
        hand = len(self.a.hand)
        self.game.enter_battlefield(self.a, LIBRARIAN)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_static(self):
        dog = self.game.enter_battlefield(self.a, STATIC)
        self.assertEqual(dog.power, 1)
        self.game.enter_battlefield(self.b, BEAR)
        self.game.enter_battlefield(self.b, BEAR)
        self.assertEqual(dog.power, 3)


if __name__ == "__main__":
    unittest.main()


class TurnHistory(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def holds(self, phrase):
        code = parse(phrase)
        self.assertTrue(code, phrase)
        return self.game.check_cond(self.a, Effect("draw", cond=code), StackItem(self.a, [], []), None)

    def test_entered_and_died(self):
        self.assertFalse(self.holds("a creature entered the battlefield under your control this turn"))
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        self.assertTrue(self.holds("a creature entered the battlefield under your control this turn"))
        self.assertFalse(self.holds("two or more creatures died this turn"))
        self.game.destroy(bear)
        self.game.enter_battlefield(self.b, BEAR)
        self.game.destroy(self.b.battlefield[-1])
        self.game.settle()
        self.assertTrue(self.holds("two or more creatures died this turn"))
        self.game.turn += 1
        self.assertFalse(self.holds("a creature entered the battlefield under your control this turn"))
