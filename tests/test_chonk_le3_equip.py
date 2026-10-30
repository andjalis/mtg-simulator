"""le-chonk-3 batch 4: restricted Equip wordings ("Equip Wizard {1}", "Equip legendary creature {1}").

The cards-side line template for these equip costs is cross-area (face_lines parses only
"Equip {cost}"); the engine contract is ``advanced_rules["equip_restriction"]`` — a subtype, a
"Warlock or Wizard" style list, or "legendary" — checked both by the AI's equip-target choice
and by the equip legality check. Ace's Baseball Bat ("Equip legendary creature {1}") and the
~11 "Equip <type> {N}" cards in the database unblock once the parser fills it.
"""
import dataclasses
import random
import unittest

from mtgsim.engine import Game, Permanent, Player
from mtgsim.engine.policy import choose_equip_target, equip_matches
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

SWORD = dataclasses.replace(
    card("Test Sword", "{1}", "Artifact — Equipment", "Equipped creature gets +1/+1.\nEquip {1}"),
    advanced_rules={"equip_restriction": "Knight"})
BAT = dataclasses.replace(
    card("Test Bat", "{2}", "Artifact — Equipment", "Equipped creature gets +3/+0.\nEquip {2}"),
    advanced_rules={"equip_restriction": "legendary"})
KNIGHT = card("Test Knight", "{1}{W}", "Creature — Human Knight", "", 2, 2)
CHANGELING = card("Test Changeling", "{1}", "Creature — Shapeshifter", "Changeling", 1, 1)
LEGEND = card("Test Legend", "{1}{W}", "Legendary Creature — Human Knight", "", 2, 2)


class EquipRestriction(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], None)
        self.b = Player("b", [], None)
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for _ in range(4):
            land = Permanent(MOUNTAIN, self.a)
            land.sick = False
            self.a.battlefield.append(land)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_matches(self):
        knight = self.perm(KNIGHT, self.a)
        bear = self.perm(BEAR, self.a)
        changeling = self.perm(CHANGELING, self.a)
        legend = self.perm(LEGEND, self.a)
        self.assertTrue(equip_matches(knight, "Knight"))
        self.assertTrue(equip_matches(changeling, "Knight"))
        self.assertTrue(equip_matches(legend, "Knight"))
        self.assertFalse(equip_matches(bear, "Knight"))
        self.assertTrue(equip_matches(knight, "Shaman or Warlock or Knight"))
        self.assertFalse(equip_matches(bear, "Shaman or Warlock or Knight"))
        self.assertTrue(equip_matches(legend, "legendary"))
        self.assertFalse(equip_matches(knight, "legendary"))

    def test_equip_legality(self):
        sword = self.perm(SWORD, self.a)
        knight = self.perm(KNIGHT, self.a)
        bear = self.perm(BEAR, self.a)
        self.assertTrue(self.game.equip(self.a, sword, knight))
        self.assertFalse(self.game.equip(self.a, sword, bear))

    def test_ai_skips_disallowed_hosts(self):
        sword = self.perm(SWORD, self.a)
        self.perm(BEAR, self.a)                          # the better creature, but not a Knight
        knight = self.perm(KNIGHT, self.a)
        self.assertIs(choose_equip_target(self.game, self.a, sword), knight)
        self.assertTrue(self.game.equip(self.a, sword))
        self.assertIs(sword.attached_to, knight)

    def test_legendary_restriction(self):
        bat = self.perm(BAT, self.a)
        knight = self.perm(KNIGHT, self.a)
        legend = self.perm(LEGEND, self.a)
        self.assertIs(choose_equip_target(self.game, self.a, bat), legend)
        self.assertFalse(self.game.equip(self.a, bat, knight))
        self.assertTrue(self.game.equip(self.a, bat, legend))


if __name__ == "__main__":
    unittest.main()
