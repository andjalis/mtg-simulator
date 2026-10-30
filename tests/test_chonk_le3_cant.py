"""le-chonk-3 batch 4: can't-restriction eval side (engine only; parser strips are cross-area).

- "Creature spells can't be cast" (Aether Storm): a permanent with ``advanced_rules["no_cast"]``
  (a tuple of spell kinds, judged with the existing batch1 ``spell_kind_ok``) stops everyone
  from casting those spells, until it leaves or its abilities are suppressed.
- "Creatures your opponents control can't block this turn" (Cosmotronic Wave, Hazardous Blast):
  ``cant_block_all`` with ``data["theirs"]`` restricts the restriction to the caster's
  opponents. The one-line parser pattern for the wording is a cards-side change (see the
  batch report); the effect kind is exercised directly here.
"""
import dataclasses
import random
import unittest

from mtgsim.cards import Effect
from mtgsim.engine import Game, Permanent, Player, can_block
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

STORM = dataclasses.replace(                    # Aether Storm wording
    card("Test Storm", "{2}{U}", "Enchantment", ""),
    advanced_rules={"no_cast": ("creature",)})
REDBEAR = card("Test Bear", "{1}{R}", "Creature — Bear", "", 2, 2)
WAVE = dataclasses.replace(                      # Cosmotronic Wave wording
    card("Test Wave", "{3}{R}", "Sorcery", ""),
    spell_effects=[Effect("cant_block_all", target="none", data={"theirs": True})])
BOTH = dataclasses.replace(                      # plain "Creatures can't block this turn"
    card("Test Stun", "{3}{R}", "Sorcery", ""),
    spell_effects=[Effect("cant_block_all", target="none")])


class CantRestrictions(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], None)
        self.b = Player("b", [], None)
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def land(self, p, n, c=MOUNTAIN):
        for _ in range(n):
            land = Permanent(c, p)
            land.sick = False
            p.battlefield.append(land)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_no_cast_bans_that_spell_kind(self):
        storm = self.perm(STORM, self.a)
        self.a.hand = [REDBEAR, WAVE]
        self.land(self.a, 6)
        self.assertFalse(self.game.can_cast_now(self.a, REDBEAR))   # creature spell banned
        self.assertTrue(self.game.can_cast_now(self.a, WAVE))      # sorceries still fine
        self.a.battlefield.remove(storm)
        self.assertTrue(self.game.can_cast_now(self.a, REDBEAR))

    def test_no_cast_is_suppressed_with_the_permanent(self):
        storm = self.perm(STORM, self.b)
        self.a.hand = [REDBEAR]
        self.land(self.a, 6)
        self.assertFalse(self.game.can_cast_now(self.a, REDBEAR))
        storm.silenced_by = self.perm(card("Test Silence", "{1}", "Creature", "", 1, 1), self.a)
        self.assertTrue(self.game.can_cast_now(self.a, REDBEAR))

    def test_theirs_only_restriction(self):
        mine = self.perm(BEAR, self.a)
        theirs = self.perm(BEAR, self.b)
        self.a.hand = [WAVE]
        self.land(self.a, 6)
        self.assertTrue(self.game.cast(self.a, WAVE))
        self.assertFalse(can_block(theirs, mine))                   # only the opponent's can't block
        self.assertTrue(can_block(mine, theirs))
        self.assertTrue(mine.can_attack())

    def test_plain_cant_block_all_regression(self):
        mine = self.perm(BEAR, self.a)
        theirs = self.perm(BEAR, self.b)
        self.a.hand = [BOTH]
        self.land(self.a, 6)
        self.assertTrue(self.game.cast(self.a, BOTH))
        self.assertFalse(can_block(theirs, mine))
        self.assertFalse(can_block(mine, theirs))


if __name__ == "__main__":
    unittest.main()
