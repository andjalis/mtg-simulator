"""Attack / damage / targeting / counter heads (mtgsim/cx_trig_heads.py) and "When you control no <np>" state
triggers (mtgsim/cx_trig_state.py), #404 slice 3."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cards import Effect
from mtgsim.cx_events import compile_head
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import BEAR, Scripted
from tests.test_templates import ISLAND, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None
GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
DINO = card("Test Dino", "{G}", "Creature — Dinosaur", "", 1, 5)
ROGUE = card("Test Rogue", "{B}", "Creature — Faerie Rogue", "", 1, 1)


class Heads(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(compile_head("Whenever equipped creature attacks alone")[1]["flags"], {"attacks": "alone"})
        self.assertEqual(compile_head("Whenever a Rogue you control attacks and isn't blocked")[0], ("unblocked",))
        self.assertEqual(compile_head("Whenever ~ deals damage to a Goblin or Orc")[1]["dmgd"],
                         [("Goblin",), ("Orc",)])
        self.assertEqual(compile_head("Whenever ~ deals 6 or more damage to an opponent")[1]["dmg_n"], 6)
        self.assertEqual(compile_head("Whenever a source an opponent controls deals damage to you")[1]["player"],
                         "src_opp")
        self.assertEqual(compile_head("Whenever one or more +1/+1 counters are put on another creature you control")
                         [0], ("p1_added",))

    def test_refusals(self):
        for head in ("Whenever a source an opponent controls draws a card",
                     "Whenever ~ deals damage to a frobnicated thing",
                     "Whenever one or more +1/+1 counters are put on one or more creatures",
                     "Whenever a creature attacks enchanted frob"):
            self.assertIsNone(compile_head(head), head)


@unittest.skipUnless(HAVE_DB, "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        for n in ("Reaper's Talisman", "Sigil of Valor", "Stinkdrinker Bandit", "Curse of Predation",
                  "Curse of Stalked Prey", "Stormchaser Drake", "Dinosaur Hunter", "East-Mark Cavalier",
                  "Briarbridge Patrol", "Deus of Calamity", "Farsight Mask", "Shalai and Hallar",
                  "Enduring Scalelord", "Covetous Dragon", "Emperor Crocodile", "Tethered Griffin", "Synod Centurion"):
            self.assertEqual(DB.get(n).unsupported, [], n)


@unittest.skipUnless(HAVE_DB, "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def attack(self, *attackers, blocks=None):
        self.a.ai.attack = list(attackers)
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_attacks_alone(self):
        bear, goblin = self.put(self.a, BEAR), self.put(self.a, GOBLIN)
        sigil = self.put(self.a, DB.get("Sigil of Valor"))
        sigil.attached_to = bear
        bear.equipment.append(sigil) if sigil not in bear.equipment else None
        self.attack(bear, goblin)                               # two attackers: no trigger
        self.assertEqual(self.b.life, 20 - 2 - 1)
        self.game.turn += 1
        bear.tapped = goblin.tapped = False
        self.attack(bear)                                       # alone: +1/+1 for the other creature (the Goblin)
        self.assertEqual(self.b.life, 17 - 3)

    def test_attacks_and_isnt_blocked(self):
        self.put(self.a, DB.get("Stinkdrinker Bandit"))
        rogue, other = self.put(self.a, ROGUE), self.put(self.a, GOBLIN)
        wall = self.put(self.b, card("Test Wall", "{W}", "Creature — Wall", "Defender", 0, 4))
        self.attack(rogue, other, blocks={other: [wall]})
        self.assertEqual(self.b.life, 20 - 3)                   # the unblocked Rogue gets +2/+1

    def test_curse_of_predation(self):
        curse = self.put(self.b, DB.get("Curse of Predation"))
        curse.curse_target = self.b                             # b's own curse on b: a's attacker grows
        bear = self.put(self.a, BEAR)
        self.attack(bear)
        self.assertEqual(bear.counters.get("+1/+1", 0), 1)
        curse.curse_target = self.a
        self.game.turn += 1
        bear.tapped = False
        self.attack(bear)
        self.assertEqual(bear.counters.get("+1/+1", 0), 1)      # attacking b, curse on a: no counter

    def test_damage_to_a_dinosaur_destroys_it(self):
        hunter = self.put(self.a, DB.get("Dinosaur Hunter"))
        goblin, dino = self.put(self.b, GOBLIN), self.put(self.b, DINO)
        self.game.deal_damage(goblin, 0 + 1, by=self.a, cause="x", source=hunter)
        self.game.settle()
        self.game.deal_damage(dino, 1, by=self.a, cause="x", source=hunter)
        self.game.settle()
        self.assertNotIn(dino, self.b.battlefield)

    def test_n_or_more_damage(self):
        deus = self.put(self.a, DB.get("Deus of Calamity"))
        land = self.put(self.b, ISLAND)
        self.game.deal_damage(self.b, 5, by=self.a, cause="x", source=deus)
        self.game.settle()
        self.assertIn(land, self.b.battlefield)
        self.game.deal_damage(self.b, 6, by=self.a, cause="x", source=deus)
        self.game.settle()
        self.assertNotIn(land, self.b.battlefield)

    def test_source_an_opponent_controls_damages_you(self):
        self.put(self.a, DB.get("Farsight Mask"))
        self.a.ai = type("Yes", (Scripted,), {"choose_yes": lambda *a, **k: True})()
        mine, theirs = self.put(self.a, GOBLIN), self.put(self.b, GOBLIN)
        hand = len(self.a.hand)
        self.game.deal_damage(self.a, 1, by=self.a, cause="x", source=mine)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)
        self.game.deal_damage(self.a, 1, by=self.b, cause="x", source=theirs)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_that_player_is_the_sources_controller(self):
        self.put(self.a, DB.get("Michiko Konda, Truth Seeker"))
        theirs = self.put(self.b, GOBLIN)
        mine = len(self.a.battlefield)
        self.game.deal_damage(self.a, 1, by=self.b, cause="x", source=theirs)
        self.game.settle()
        self.assertEqual(len(self.a.battlefield), mine)
        self.assertNotIn(theirs, self.b.battlefield)            # b sacrificed its only permanent

    def test_counters_on_your_creature_that_much(self):
        self.put(self.a, DB.get("Shalai and Hallar"))
        bear = self.put(self.a, BEAR)
        theirs = self.put(self.b, GOBLIN)
        self.game.resolve(self.a, Effect("p1_counters", 2, target="permanent"), theirs)
        self.game.settle()
        self.assertEqual(self.b.life, 20)
        self.game.resolve(self.a, Effect("p1_counters", 2, target="permanent"), bear)
        self.game.settle()
        self.assertEqual(self.b.life, 18)

    def test_becomes_target_of_your_spell(self):
        drake = self.put(self.a, DB.get("Stormchaser Drake"))
        hand = len(self.a.hand)
        theirs = StackItem(self.b, [Effect("pump", 1, 1, target="creature")], [drake], card=GOBLIN, kind="spell")
        self.game.check_ward(theirs)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)
        mine = StackItem(self.a, [Effect("pump", 1, 1, target="creature")], [drake], card=GOBLIN, kind="spell")
        self.game.check_ward(mine)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_control_no_other_creatures(self):
        bear = self.put(self.a, BEAR)
        croc = self.put(self.a, DB.get("Emperor Crocodile"))
        self.game.state_based_actions()
        self.assertIn(croc, self.a.battlefield)
        self.game.destroy(bear)
        self.game.settle()
        self.game.state_based_actions()
        self.assertNotIn(croc, self.a.battlefield)

    def test_control_no_artifacts(self):
        dragon = self.put(self.a, DB.get("Covetous Dragon"))
        self.game.state_based_actions()
        self.assertNotIn(dragon, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()
