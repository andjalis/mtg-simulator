"""Trigger-event library (mtgsim/cx_events.py): subject + event heads, and the engine observer."""
import random
import unittest

from mtgsim.cx_events import compile_head
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SHOCK, card

GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
CHIEF = card("Test Chief", "{2}{R}", "Creature — Goblin",
             "Whenever a nontoken Goblin you control attacks, that creature gets +1/+0 until end of turn.", 2, 2)
WARD = card("Test Watchtower", "{2}{W}", "Enchantment",
            "Whenever a creature attacks you, you gain 1 life.")
GRAVE = card("Test Grave", "{2}{B}", "Enchantment",
             "Whenever a creature an opponent controls with power 2 or greater dies, draw a card.")
SPITE = card("Test Spite", "{1}{R}", "Enchantment",
             "Whenever an opponent casts a white or blue instant or sorcery spell, ~ deals 2 damage to that player.")
LANDS = card("Test Lands", "{1}{G}", "Enchantment", "Whenever a land enters under an opponent's control, you gain 2 life.")
FANGS = card("Test Fangs", "{1}{B}", "Creature — Vampire",
             "Whenever a Vampire you control deals combat damage to a player, that player loses 1 life.", 1, 1)
ALTAR = card("Test Altar", "{1}{B}", "Artifact", "Whenever a player sacrifices a creature, you gain 1 life.\n"
                                                 "Sacrifice a creature: Add {B}.")
DREAD = card("Test Dread", "{1}{B}", "Creature — Specter",
             "Whenever ~ blocks or becomes blocked by a nonblack creature, destroy that creature at end of combat.", 1, 4)
LORE = card("Test Lore", "{U}", "Enchantment", "Whenever a player plays a land, you gain 1 life.")


class Heads(unittest.TestCase):
    def test_grammar(self):
        self.assertEqual(compile_head("Whenever an Insect, Leech, Slug, or Worm you control attacks")[1]["alts"],
                         [("Insect",), ("Leech",), ("Slug",), ("Worm",)])
        self.assertEqual(compile_head("When ~ enters or is turned face up")[0], ("etb", "turned_face_up"))
        self.assertEqual(compile_head("Whenever ~ deals combat damage to a player or battle")[0],
                         ("combat_damage_player",))
        spell = compile_head("Whenever you cast your first instant or sorcery spell each turn")[1]["spell"]
        self.assertEqual((spell["nth"], spell["alts"]), (1, [("instant",), ("sorcery",)]))
        self.assertEqual(compile_head("Whenever a player sacrifices a creature")[0], ("sacrificed",))

    def test_unknown_words_fail_closed(self):
        for head in ("Whenever a creature of the chosen type enters", "Whenever a creature dies this turn",
                     "Whenever your commander attacks", "Whenever a frobnicated creature attacks"):
            self.assertIsNone(compile_head(head), head)

    def test_parse(self):
        for c in (CHIEF, WARD, GRAVE, SPITE, LANDS, FANGS, ALTAR, LORE, DREAD):
            self.assertEqual(c.unsupported, [], c.name)
            if c is not GRAVE:      # deaths and entries with a plain selector stay with backlog_templates
                self.assertTrue(c.triggers[0].event.startswith("ev:"), c.name)


class Observer(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_typed_attack_pumps_that_creature(self):
        self.put(self.a, CHIEF)
        goblin, bear = self.put(self.a, GOBLIN), self.put(self.a, BEAR)
        self.put(self.b, WARD)
        self.a.ai.attack = [goblin, bear]
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 20 - 2 - 2 + 2)       # Goblin 2/1, Bear 2/2; Watchtower +1 each attacker

    def test_opponent_creature_dies_with_power(self):
        self.put(self.a, GRAVE)
        bear = self.put(self.b, BEAR)
        goblin = self.put(self.b, GOBLIN)
        hand = len(self.a.hand)
        self.game.dies(goblin)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)             # power 1: no card
        self.game.dies(bear)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_cast_filter_and_that_player(self):
        self.put(self.a, SPITE)
        self.game.enter_battlefield(self.b, MOUNTAIN).tapped = False
        self.b.hand = [SHOCK]
        self.game.active_idx = 1
        self.assertTrue(self.game.cast(self.b, SHOCK, [self.a]))
        self.game.settle()
        self.assertEqual(self.b.life, 20)                    # red instant: no trigger
        blue = card("Test Blue", "{U}", "Instant", "Draw a card.")
        self.game.enter_battlefield(self.b, ISLAND).tapped = False
        self.b.hand = [blue]
        self.assertTrue(self.game.cast(self.b, blue, []))
        self.game.settle()
        self.assertEqual(self.b.life, 18)

    def test_land_enters_under_opponent(self):
        self.put(self.a, LANDS)
        self.put(self.a, ISLAND)
        self.assertEqual(self.a.life, 20)
        self.put(self.b, ISLAND)
        self.assertEqual(self.a.life, 22)

    def test_combat_damage_that_player(self):
        fangs = self.put(self.a, FANGS)
        self.a.ai.attack = [fangs]
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 18)

    def test_blocked_by_filter(self):
        dread, bear = self.put(self.a, DREAD), self.put(self.b, BEAR)
        black = self.put(self.b, card("Test Black Bear", "{1}{B}", "Creature — Bear", "", 0, 5))
        self.a.ai.attack, self.b.ai.block = [dread], {dread: [black]}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertIn(black, self.b.battlefield)             # black blocker: no trigger
        self.b.ai.block = {dread: [bear]}
        dread.tapped = False
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)

    def test_sacrifice_and_land_played(self):
        self.put(self.a, ALTAR)
        self.put(self.a, LORE)
        bear = self.put(self.b, BEAR)
        self.game.sacrifice(bear)
        self.game.settle()
        self.assertEqual(self.a.life, 21)
        self.a.hand = [ISLAND]
        self.game.active_idx = 0
        self.game.play_land(self.a, ISLAND)
        self.game.settle()
        self.assertEqual(self.a.life, 22)


if __name__ == "__main__":
    unittest.main()
