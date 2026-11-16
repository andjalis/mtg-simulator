"""Referent-bound conditions (#405): "if it's a land card", "if that spell has mana value 5 or greater",
"put a +1/+1 counter on that creature if its power is less than ~'s power" — facts about the referenced
object, read by mtgsim/cx_gcond_ref.py into the shared condition library."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cards import Effect
from mtgsim.cx_condlib import parse
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, MOUNTAIN, SHOCK, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None


class ParseShapes(unittest.TestCase):
    def test_positives(self):
        self.assertEqual(parse("it isn't a creature"), 'lib:["ref_not_is",{"types":["creature"]},"prev"]')
        self.assertEqual(parse("it's not a token"), 'lib:["ref_not_is",{"types":["token"]},"prev"]')
        self.assertEqual(parse("that creature wasn't a token"),
                         'lib:["ref_not_is",{"types":["token"]},"that"]')
        self.assertTrue(parse("it isn't a land card").startswith('lib:["ref_not_is"'))
        self.assertEqual(parse("that spell has mana value 5 or greater"), 'lib:["prev_is",{"mv":[">=",5]}]')
        self.assertEqual(parse("that permanent has mana value 3 or less"),
                         'lib:["ref_stat","mana value","<=",3,"that"]')
        self.assertEqual(parse("it has mana value 3 or less"), 'lib:["ref_stat","mana value","<=",3,"prev"]')
        self.assertEqual(parse("its power is less than ~'s power"),
                         'lib:["ref_stat_vs","power","<","~","power","prev"]')
        self.assertEqual(parse("that creature's power is greater than ~'s power"),
                         'lib:["ref_stat_vs","power",">","~","power","that"]')
        self.assertEqual(parse("it had power greater than ~'s power"),
                         'lib:["ref_stat_vs","power",">","~","power","prev"]')
        self.assertTrue(parse("that creature has greater power or toughness than ~").startswith('lib:["or"'))
        self.assertEqual(parse("its power is exactly 20"), 'lib:["ref_stat","power","==",20,"prev"]')
        self.assertEqual(parse("its power is greater than 0"), 'lib:["ref_stat","power",">",0,"prev"]')
        self.assertEqual(parse("that creature has power 7 or greater"),
                         'lib:["ref_stat","power",">=",7,"that"]')
        self.assertTrue(parse("it was a Locus or Sphere land").startswith('lib:["or"'))
        self.assertEqual(parse("that land was nonbasic"), 'lib:["prev_is",{"basic":false}]')
        self.assertEqual(parse("that card is legendary"), 'lib:["ref_card_is",{"legendary":true}]')
        self.assertEqual(parse("that permanent was blue or black"), 'lib:["prev_is",{"any_color":["U","B"]}]')
        self.assertEqual(parse("that card is exiled"), 'lib:["ref_zone","exiled","card"]')
        self.assertTrue(parse("it is enchanted or equipped").startswith('lib:["or"'))
        self.assertEqual(parse("it's renowned"), 'lib:["ref_flag","renowned","prev"]')
        self.assertEqual(parse("it had a counter on it"), 'lib:["any_counters","it"]')
        self.assertEqual(parse("it has no counters on it"), '!lib:["any_counters","it"]')
        self.assertEqual(parse("that creature is another Hero"),
                         'lib:["and","lib:[\\"prev_is\\",{\\"sub\\":[\\"Hero\\"]}]","lib:[\\"ref_not_src\\",\\"that\\"]"]')

    def test_refusals(self):
        # a predicate the shared noun-phrase reader doesn't know keeps the line ignored, and so do
        # non-facts (votes, "this way", turn counts, self-comparisons)
        for phrase in ("it's an art sticker", "that card has the chosen name", "it has a single target",
                       "it has mutate", "it doesn't have suspend", "that spell is countered this way",
                       "they do", "it's the third time", "it's a fibonacci number", "its mana value is odd",
                       "it had power greater than its toughness", "that card has a counter on it",
                       "that spell has two +1/+1 counters on it"):
            self.assertEqual(parse(phrase), "", phrase)


@unittest.skipUnless(HAVE_DB, "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        for n in ("Shelinda, Yevon Acolyte", "Consul's Lieutenant", "Prismari Apprentice", "Locus Cobra",
                  "Vaultborn Tyrant", "Burn the Impure"):
            self.assertEqual(DB.get(n).unsupported, [], n)


VAMP = card("Test Vampire", "{1}{B}", "Creature — Vampire", "", 2, 2)
PUMP_IF_NOT = card("Test Hex", "{2}{U}", "Instant",
                   "Target creature gets +2/+2 until end of turn. If it isn't a Vampire, it gains haste "
                   "until end of turn.")
MV_TRIGGER = card("Test Apprentice", "{1}{U}{R}", "Creature — Human Wizard",
                  "Whenever you cast an instant or sorcery spell, if that spell has mana value 3 or greater, "
                  "put a +1/+1 counter on ~.", 2, 2)
SORCERY3 = card("Test Ritual", "{2}{R}", "Sorcery", "Test Ritual deals 1 damage to any target.")
STAT_VS = card("Test Acolyte", "{1}{G}", "Creature — Human Cleric",
               "{1}{G}: Put a +1/+1 counter on target creature if its power is less than ~'s power.", 3, 3)
RENOWNED = card("Test Lieutenant", "{1}{W}", "Creature — Human Soldier",
                "Whenever another creature enters the battlefield under your control, if it's renowned, "
                "you gain 5 life.", 2, 2)
LOCUS = card("Test Cobra", "{1}{G}", "Creature — Snake",
             "Whenever a land enters the battlefield under your control, add one mana of any color. "
             "If it was a Locus or Sphere land, put a +1/+1 counter on ~.", 1, 1)
DESERT = card("Test Desert", types="Land — Desert", text="({T}: Add {C}.)")
NONBASIC_PUMP = card("Test Grove", "{1}{G}", "Creature — Treefolk",
                     "Whenever a land enters the battlefield under your control, if that land was nonbasic, "
                     "~ gets +1/+1 until end of turn.", 2, 2)
NO_COUNTERS = card("Test Scavenger", "{2}{B}", "Creature — Zombie",
                   "When ~ enters, if it had no counters on it, draw a card.", 2, 2)
BIG = card("Test Brute", "{3}{R}", "Creature — Giant", "", 3, 3)


class GameBase(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def holds(self, phrase, item=None, prev=None, source=None):
        return self.game.check_cond(self.a, Effect("draw", cond=parse(phrase)), item, prev)


class ReferentGame(GameBase):
    def test_negated_type(self):
        self.assertEqual(PUMP_IF_NOT.unsupported, [])
        for target, haste in ((BEAR, True), (VAMP, False)):
            perm = self.game.enter_battlefield(self.a, target)
            for _ in range(3):
                self.game.enter_battlefield(self.a, ISLAND).sick = False
            self.a.hand = [PUMP_IF_NOT]
            self.assertTrue(self.game.cast(self.a, PUMP_IF_NOT, [perm]))
            self.game.settle()
            self.assertEqual(perm.power, 4)
            self.assertEqual(perm.has("haste"), haste, target.name)

    def test_spell_mana_value(self):
        self.assertEqual(MV_TRIGGER.unsupported, [])
        apprentice = self.game.enter_battlefield(self.a, MV_TRIGGER)
        for _ in range(3):
            self.game.enter_battlefield(self.a, MOUNTAIN).sick = False
        self.game.enter_battlefield(self.a, ISLAND).sick = False
        self.a.hand = [SHOCK]
        self.assertTrue(self.game.cast(self.a, SHOCK, [self.b]))
        self.game.settle()
        self.assertEqual(apprentice.counters.get("+1/+1", 0), 0, "mv 1 spell: no counter")
        self.a.hand = [SORCERY3]
        self.assertTrue(self.game.cast(self.a, SORCERY3, [self.b]))
        self.game.settle()
        self.assertEqual(apprentice.counters.get("+1/+1", 0), 1, "mv 3 spell: one counter")

    def test_power_vs_source(self):
        self.assertEqual(STAT_VS.unsupported, [])
        acolyte = self.game.enter_battlefield(self.a, STAT_VS)
        self.game.enter_battlefield(self.a, FOREST).sick = False
        self.game.enter_battlefield(self.a, FOREST).sick = False
        for target, expected in ((BEAR, 1), (BIG, 0)):
            perm = self.game.enter_battlefield(self.a, target)
            item = StackItem(self.a, list(STAT_VS.activated[0].effects),
                             [None] * len(STAT_VS.activated[0].effects), source=acolyte)
            item.targets[0] = perm
            for eff in item.effects:
                if self.game.check_cond(self.a, eff, item, perm):
                    self.game.resolve(self.a, eff, perm, item, perm)
            self.assertEqual(perm.counters.get("+1/+1", 0), expected, target.name)

    def test_renowned_flag(self):
        self.assertEqual(RENOWNED.unsupported, [])
        self.game.enter_battlefield(self.a, RENOWNED)
        self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        self.assertEqual(self.a.life, 20, "not renowned: no life")
        bear2 = self.game.enter_battlefield(self.a, BEAR)
        bear2.renowned = True          # the trigger checks the creature that just entered
        self.game.settle()
        self.assertEqual(self.a.life, 25, "renowned creature entered: +5 life")

    def test_was_subtype_or_list(self):
        self.assertEqual(LOCUS.unsupported, [])
        cobra = self.game.enter_battlefield(self.a, LOCUS)
        self.game.enter_battlefield(self.a, FOREST)
        self.game.settle()
        self.assertEqual(cobra.counters.get("+1/+1", 0), 0, "Forest is not a Locus or Sphere")
        self.game.enter_battlefield(self.a, DESERT if False else card("Test Locus", types="Land — Locus",
                                                                        text="({T}: Add {G}.)"))
        self.game.settle()
        self.assertEqual(cobra.counters.get("+1/+1", 0), 1, "a Locus land entered")

    def test_nonbasic_land(self):
        self.assertEqual(NONBASIC_PUMP.unsupported, [])
        grove = self.game.enter_battlefield(self.a, NONBASIC_PUMP)
        self.game.enter_battlefield(self.a, ISLAND)          # basic: no pump
        self.game.settle()
        self.assertEqual(grove.power, 2)
        self.game.enter_battlefield(self.a, DESERT)           # nonbasic: pump
        self.game.settle()
        self.assertEqual(grove.power, 3)

    def test_no_counters_on_it(self):
        self.assertEqual(NO_COUNTERS.unsupported, [])
        hand = len(self.a.hand)
        self.game.enter_battlefield(self.a, NO_COUNTERS)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1, "entered with no counters: drew")
        zombie = self.game.enter_battlefield(self.a, NO_COUNTERS)
        zombie.counters["+1/+1"] = 1
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1, "entered with a counter: no draw")

    def test_zone_of_card(self):
        bolt = card("Test Bolt", "{R}", "Instant", "~ deals 3 damage to any target.")
        self.b.exile.append(bolt)
        item = StackItem(self.a, [], [], source=None)
        item.exiled_card = bolt
        self.assertTrue(self.holds("that card is exiled", item=item))
        self.assertFalse(self.holds("that card is in your hand", item=item))
        self.b.exile.remove(bolt)
        self.a.hand = [bolt]
        self.assertTrue(self.holds("that card is in your hand", item=item))
        self.assertFalse(self.holds("that card is exiled", item=item))

    def test_stat_comparisons(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        brute = self.game.enter_battlefield(self.a, BIG)
        item = StackItem(self.a, [], [], source=brute)
        self.assertTrue(self.holds("its power is less than ~'s power", item=item, prev=bear, source=brute))
        self.assertFalse(self.holds("its power is less than ~'s power", item=item, prev=brute, source=bear))
        self.assertTrue(self.holds("that creature has power 2 or greater", item=item, prev=bear))
        self.assertFalse(self.holds("that creature has power 7 or greater", item=item, prev=bear))
        island = self.game.enter_battlefield(self.a, ISLAND)
        self.assertTrue(self.holds("it isn't a creature", item=item, prev=island))
        self.assertFalse(self.holds("it isn't a creature", item=item, prev=bear))


if __name__ == "__main__":
    unittest.main()
