"""Activation restrictions: "Activate only during your turn, before attackers are declared", "only if ~ is
attacking", graveyard / permanent-count gates, and the "and only once" combinations."""
import random
import unittest

from mtgsim.cx_activation import strip
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

SORCERER = card("Test Sorcerer", "{1}{R}", "Creature — Human Wizard",
                "{T}: ~ deals 1 damage to any target. Activate only during your turn, before attackers are declared.",
                1, 1)
RING = card("Test Ring", "", "Land",
            "{R}, {T}, Sacrifice ~: It deals 2 damage to any target. "
            "Activate only if there are seven or more cards in your graveyard.")
TOME = card("Test Tome", "{3}", "Artifact", "{2}, {T}: Draw a card. Activate only if you have no cards in hand.")
VETERAN = card("Test Veteran", "{1}{W}", "Creature — Human",
               "{2}: Draw a card. Activate only as a sorcery and only once each turn.", 1, 1)


class Parse(unittest.TestCase):
    def test_strip_codes(self):
        body, codes, sorcery, once, once_game = strip(
            "Draw a card. Activate only if you control three or more artifacts and only once each turn.")
        self.assertEqual((body, codes, sorcery, once, once_game),
                         ("Draw a card.", ("control>=3:artifacts",), False, True, False))
        self.assertEqual(strip("Draw a card. Activate only as a sorcery and only once.")[2:], (True, False, True))
        self.assertIsNone(strip("Draw a card. Activate only if the moon is full."))
        self.assertIsNone(strip("Draw a card."))

    def test_abilities_parse_fully(self):
        for c in (SORCERER, RING, TOME, VETERAN):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(SORCERER.activated[0].restrictions, ("pre_attack:mine",))
        self.assertEqual(RING.activated[0].restrictions, ("gy>=7",))
        self.assertTrue(VETERAN.activated[0].sorcery and VETERAN.activated[0].once)


class Gates(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 2, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, c, who=None):
        perm = self.game.enter_battlefield(who or self.a, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_before_attackers_on_your_turn(self):
        perm = self.put(SORCERER)
        self.assertTrue(self.game.can_activate(self.a, perm, 0))
        self.game.step = "declare_attackers"
        self.assertFalse(self.game.can_activate(self.a, perm, 0))
        self.game.step, self.game.active_idx = "main1", 1
        self.assertFalse(self.game.can_activate(self.a, perm, 0))

    def test_graveyard_gate(self):
        land = self.put(RING)
        land.tapped = False
        self.put(MOUNTAIN).tapped = False
        self.assertFalse(self.game.can_activate(self.a, land, 0))
        self.a.graveyard.extend([BEAR] * 7)
        self.assertTrue(self.game.can_activate(self.a, land, 0))

    def test_empty_hand_gate(self):
        tome = self.put(TOME)
        for _ in range(2):
            self.put(ISLAND).tapped = False
        self.a.hand = [BEAR]
        self.assertFalse(self.game.can_activate(self.a, tome, 0))
        self.a.hand = []
        self.assertTrue(self.game.can_activate(self.a, tome, 0))


if __name__ == "__main__":
    unittest.main()


ARTIST = card("Test Artist", "{1}{B}", "Creature — Vampire",
              "Whenever ~ or another creature dies, target player loses 1 life and you gain 1 life.", 0, 1)


class OrAnotherDies(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 2, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_parses(self):
        self.assertEqual(ARTIST.unsupported, [])
        self.assertEqual(sorted(t.event for t in ARTIST.triggers), ["creature_dies", "dies"])

    def drain_after_death(self, who):
        artist = self.game.enter_battlefield(self.a, ARTIST)
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.settle()
        before = self.a.life
        self.game.destroy(artist if who == "self" else bear)
        self.game.settle()
        return self.a.life - before

    def test_other_creature_dies(self):
        self.assertEqual(self.drain_after_death("other"), 1)

    def test_self_dies_once(self):
        self.assertEqual(self.drain_after_death("self"), 1)
