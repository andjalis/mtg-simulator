"""Activation events (mtgsim/cx_trig_activate.py, #860 item 1): "Whenever <player> activates an ability [of <desc>]
[that isn't a mana ability]", loyalty and exhaust abilities."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cx_events import compile_head
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import BEAR, Scripted
from tests.test_templates import ISLAND, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None
PINGER = card("Test Pinger", "{1}{R}", "Creature — Human Wizard", "{T}: Test Pinger deals 1 damage to any target.", 1, 1)


class Heads(unittest.TestCase):
    def test_parse(self):
        raws, spec = compile_head("Whenever a player activates an ability that isn't a mana ability")
        self.assertEqual((raws, spec["player"], spec["nonmana"], spec["of"]), (("ability_activated",), "any", True, None))
        raws, spec = compile_head("Whenever an opponent activates an ability of an artifact, creature, or land "
                                  "on the battlefield, if it isn't a mana ability")
        self.assertEqual((raws, spec["of"]), (("ability_activated",), [("artifact",), ("creature",), ("land",)]))
        raws, spec = compile_head("Whenever an opponent activates an ability of an artifact they control")
        self.assertEqual((raws, spec["nonmana"]), (("ability_activated",), False))     # mana abilities count too
        self.assertTrue(spec["they_control"])
        self.assertEqual(compile_head("Whenever you activate a loyalty ability")[1]["kw"], "loyalty")
        self.assertEqual(compile_head("Whenever you activate an exhaust ability")[0], ("ability_activated",))

    def test_refusals(self):
        for head in ("Whenever you activate an ability that targets a creature or player",     # Ertha Jo: not read
                     "Whenever you activate an ability of a frobnicated widget",
                     "Whenever you activate a boast ability",                                # no boast keyword tag
                     "Whenever you activate an ability of ~",
                     "Whenever an opponent activates an ability if it isn't a mana ability"):
            self.assertIsNone(compile_head(head), head)


@unittest.skipUnless(HAVE_DB, "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        for n in ("Burning-Tree Shaman", "Immolation Shaman", "Harsh Mentor", "Avalanche of Sector 7", "Wizened Mentor",
                  "Elrond, Moon-Reader", "Ceaseless Searblades", "Crackdown Construct", "Afterburner Expert",
                  "Rings of Brighthearth", "Kurkesh, Onakke Ancient"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_still_partial(self):
        # an intervening "if you removed two or more loyalty counters" is not read
        self.assertTrue(DB.get("Way of the Mind Sculptor").unsupported)


@unittest.skipUnless(HAVE_DB, "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def idx(self, perm, text=None):
        return next(i for i, a in enumerate(perm.activated) if text is None or text in a.text)

    def test_harsh_mentor_nonmana_only(self):
        self.put(self.b, DB.get("Harsh Mentor"))
        pinger = self.put(self.a, PINGER)
        elves = self.put(self.a, DB.get("Llanowar Elves"))
        self.assertIsNotNone(self.game.pay(self.a, {"G": 1}))          # a mana ability: no trigger
        self.assertTrue(elves.tapped)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.assertTrue(self.game.activate_ability(self.a, pinger, self.idx(pinger), [self.b]))
        self.game.settle()
        self.assertEqual(self.a.life, 18)                               # Harsh Mentor: 2 to the activating player
        self.assertEqual(self.b.life, 19)

    def test_harsh_mentor_ignores_its_controller(self):
        self.put(self.a, DB.get("Harsh Mentor"))
        pinger = self.put(self.a, PINGER)
        self.assertTrue(self.game.activate_ability(self.a, pinger, self.idx(pinger), [self.b]))
        self.game.settle()
        self.assertEqual(self.a.life, 20)

    def test_avalanche_counts_mana_abilities_of_artifacts(self):
        self.put(self.b, DB.get("Avalanche of Sector 7"))
        self.put(self.a, DB.get("Mind Stone"))
        self.assertIsNotNone(self.game.pay(self.a, {"generic": 1}))     # Mind Stone's {T}: Add {C}
        self.game.settle()
        self.assertEqual(self.a.life, 19)

    def test_burning_tree_on_equip(self):
        self.put(self.b, DB.get("Burning-Tree Shaman"))
        bear = self.put(self.a, BEAR)
        self.put(self.a, DB.get("Bonesplitter"))
        for _ in range(2):
            self.put(self.a, DB.get("Mountain"))
        gear = next(x for x in self.a.battlefield if x.card.name == "Bonesplitter")
        self.assertTrue(self.game.equip(self.a, gear, bear))
        self.game.settle()
        self.assertEqual(self.a.life, 19)                               # equip, not the Mountain's mana ability

    def test_ajani_loyalty(self):
        self.put(self.a, DB.get("Ajani Unrelenting"))
        jace = self.put(self.a, DB.get("Jace Beleren"))
        before = sum(x.card.is_token for x in self.a.battlefield)
        self.assertTrue(self.game.activate_loyalty(self.a, jace, 0))
        self.game.settle()
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), before + 1)

    def test_afterburner_returns_on_exhaust(self):
        expert = DB.get("Afterburner Expert")
        self.a.graveyard.append(expert)
        para = self.put(self.a, DB.get("Pacesetter Paragon"))
        for _ in range(3):
            self.put(self.a, DB.get("Mountain"))
        self.assertTrue(self.game.activate_ability(self.a, para, self.idx(para, "Exhaust")))
        self.game.settle()
        self.assertTrue(any(x.card.name == "Afterburner Expert" for x in self.a.battlefield))
        self.assertNotIn(expert, list(self.a.graveyard))

    def test_elrond_once_each_turn_and_mana_abilities(self):
        self.put(self.a, DB.get("Elrond, Moon-Reader"))
        self.put(self.a, DB.get("Llanowar Elves"))
        hand = len(self.a.hand)
        self.assertIsNotNone(self.game.pay(self.a, {"G": 1}))          # a creature's mana ability counts
        self.game.settle()
        pinger = self.put(self.a, PINGER)
        self.assertTrue(self.game.activate_ability(self.a, pinger, self.idx(pinger), [self.b]))
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)                    # "triggers only once each turn"

    def test_burning_tree_on_crew_and_cycling(self):
        self.put(self.b, DB.get("Burning-Tree Shaman"))
        bear = self.put(self.a, BEAR)
        cart = self.put(self.a, DB.get("Smuggler's Copter"))
        self.a.ai.choose_crew = lambda game, p, v: [bear]
        self.assertTrue(self.game.activate(self.a, cart, "crew"))
        self.game.settle()
        self.assertEqual(self.a.life, 19)                               # crew is an activated ability
        for _ in range(3):
            self.put(self.a, DB.get("Forest"))
        self.a.hand = [DB.get("Krosan Tusker")]
        self.game.cycle_spare(self.a)
        self.game.settle()
        self.assertEqual(self.a.life, 18)                               # so is cycling, from the hand


if __name__ == "__main__":
    unittest.main()
