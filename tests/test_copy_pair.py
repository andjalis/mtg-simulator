"""#340 slice 7: conditional entry counters on clones (Spark Double, Undercover Operative, Dominion Saboteur) and
two-target copies 'target X becomes a copy of another target Y until end of turn' (Shuri, Saheeli)."""
import os
import random
import unittest

from mtgsim import copies
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

LEGEND = card("Test Legend", "{3}{G}", "Legendary Creature — Elf Warrior", "Trample", 5, 4)
BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
WALKER = card_from_scryfall({"name": "Test Walker", "mana_cost": "{3}{U}", "cmc": 4, "loyalty": "3",
                             "type_line": "Legendary Planeswalker — Testy", "oracle_text": "+1: You gain 1 life."})
ROCK = card("Test Rock", "{1}", "Artifact", "", cmc=1)
GOLEM = card("Test Golem", "{5}", "Legendary Artifact Creature — Golem", "", 5, 5)


class Parse(unittest.TestCase):
    def test_conditional_counters(self):
        mods = copies.parse_except("it enters with an additional +1/+1 counter on it if it's a creature, it enters "
                                   "with an additional loyalty counter on it if it's a planeswalker, and it isn't "
                                   "legendary")
        self.assertEqual(mods, {"counters_if": (("+1/+1", 1, "creature"), ("loyalty", 1, "planeswalker")),
                                "legendary": False})
        self.assertEqual(copies.parse_except("it enters with a shield counter on it if you control that creature"),
                         {"counters_if": (("shield", 1, "mine"),)})
        self.assertIsNone(copies.parse_except("it enters with a shield counter on it if it's a Wizard"))

    def test_pair(self):
        c = card("Pair Test", "{1}", "Artifact", "{1}, {T}: Target artifact you control becomes a copy of another "
                 "target artifact or creature you control until end of turn, except it's an artifact in addition to "
                 "its other types.")
        self.assertEqual(c.unsupported, [])
        marker, eff = c.activated[-1].effects
        self.assertEqual((marker.kind, eff.kind, eff.data["pair"]), ("die_roll", "become_copy", True))
        bad = card("Pair Test", "{1}", "Artifact", "{T}: Target artifact you control becomes a copy of another "
                   "target artifact you control, except it's an artifact.")         # no duration
        self.assertTrue(bad.unsupported)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def clone(self, name):
        c = self.db.get(name)
        self.assertEqual(c.unsupported, [], name)
        perm = self.g.enter_battlefield(self.a, c)
        self.g.settle()
        return perm

    def test_spark_double_creature_and_planeswalker(self):
        self.g.enter_battlefield(self.a, LEGEND)
        double = self.clone("Spark Double")
        self.assertEqual((double.card.name, double.card.legendary, double.counters.get("+1/+1")),
                         ("Test Legend", False, 1))
        self.assertEqual((double.power, double.toughness), (6, 5))
        self.g.leave_battlefield(next(x for x in self.a.battlefield if x.card.name == "Test Legend"
                                      and x is not double), "graveyard")
        self.g.leave_battlefield(double, "graveyard")
        walker = self.g.enter_battlefield(self.a, WALKER)
        double = self.clone("Spark Double")
        self.assertEqual((double.card.name, double.counters.get("loyalty"), double.counters.get("+1/+1", 0)),
                         ("Test Walker", 4, 0))
        self.assertIn(walker, self.a.battlefield)            # not legendary: no legend rule

    def test_undercover_operative_shield_only_for_your_creature(self):
        self.g.enter_battlefield(self.b, LEGEND)
        op = self.clone("Undercover Operative")
        self.assertEqual((op.card.name, op.counters.get("shield", 0)), ("Test Legend", 0))
        self.g.leave_battlefield(op, "graveyard")
        self.g.enter_battlefield(self.a, card("Test Titan", "{7}", "Creature — Giant", "", 7, 7))
        op = self.clone("Undercover Operative")
        self.assertEqual((op.card.name, op.counters.get("shield", 0)), ("Test Titan", 1))

    def test_dominion_saboteur_copies_counters(self):
        bear = self.g.enter_battlefield(self.b, card("Test Titan", "{7}", "Creature — Giant", "", 7, 7))
        bear.counters["+1/+1"] = 2
        bear.counters["stun"] = 1
        sab = self.clone("Dominion Saboteur")
        self.assertEqual((sab.card.name, sab.counters.get("+1/+1"), sab.counters.get("stun")), ("Test Titan", 2, 1))

    def test_shuri_pair_copy_until_end_of_turn(self):
        shuri = self.g.enter_battlefield(self.a, self.db.get("Shuri, Wakandan Inventor"))
        shuri.sick = False
        self.assertEqual(shuri.card.unsupported, [])
        rock = self.g.enter_battlefield(self.a, ROCK)
        golem = self.g.enter_battlefield(self.a, GOLEM)
        self.g.enter_battlefield(self.a, ISLAND).sick = False
        idx = next(i for i, act in enumerate(shuri.activated) if any(e.data.get("pair") for e in act.effects))
        self.assertTrue(self.g.activate_ability(self.a, shuri, idx, [rock, golem]))
        self.g.settle()
        self.assertEqual((rock.card.name, rock.card.legendary, rock.power), ("Test Golem", False, 5))
        self.assertTrue(golem.card.legendary and golem in self.a.battlefield)
        copies.revert(rock)
        self.assertEqual(rock.card.name, "Test Rock")

    def test_ai_names_the_weak_one_as_subject(self):
        self.a.ai = HeuristicAI()
        shuri = self.g.enter_battlefield(self.a, self.db.get("Shuri, Wakandan Inventor"))
        shuri.sick = False
        rock = self.g.enter_battlefield(self.a, ROCK)
        golem = self.g.enter_battlefield(self.a, GOLEM)
        self.g.enter_battlefield(self.a, ISLAND).sick = False
        from mtgsim.engine.policy import choose_ability
        action = choose_ability(self.g, self.a, instant=False)
        self.assertIsNotNone(action)
        self.assertTrue(self.g.do_action(self.a, action))
        self.g.settle()
        self.assertEqual((rock.card.name, golem.card.name), ("Test Golem", "Test Golem"))
