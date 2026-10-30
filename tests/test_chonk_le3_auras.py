"""le-chonk-3 batch 4: new Aura restriction wordings and "can't be blocked this turn" effects.

The 2026-10-29 census auras/enchant family (828 potential full matches): the engine models an
Aura's restriction as a keyword granted to the host while the Aura is attached (the same
``equip_keywords`` path Equipment uses), or as ``aura_flags`` where a consumer already exists.
Covered here: "can't be blocked", "can't block", "attacks each combat if able" (exact),
"can't attack" (recorded simplification: played as defender), "can't attack or block / doesn't
untap ... and its activated abilities can't be activated" on any enchanted permanent, and the
spell-side "can't be blocked this turn" patterns.
"""
import random
import unittest

from mtgsim import auras
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, can_block

from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card

TUNNEL = card("Test Tunnel", "{1}{U}", "Enchantment — Aura",
              "Enchant creature\nEnchanted creature gets +1/+0 and can't be blocked.")
VEIL = card("Test Veil", "{U}", "Enchantment — Aura", "Enchant creature\nEnchanted creature can't be blocked.")
BLIGHT = card("Test Blight", "{B}", "Enchantment — Aura",
              "Enchant creature\nEnchanted creature gets -1/-1 and can't block.")
FRENZY = card("Test Frenzy", "{2}{R}", "Enchantment — Aura",
              "Enchant creature\nEnchanted creature gets +2/+2 and attacks each combat if able.")
ARREST = card("Test Arrest", "{1}{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature can't attack.")
BINDS = card("Test Binds", "{2}{W}", "Enchantment — Aura", "Enchant permanent\n"
             "Enchanted permanent can't attack or block, and its activated abilities can't be activated.")
RUST = card("Test Rust", "{1}{U}", "Enchantment — Aura", "Enchant artifact or creature\n"
            "Enchanted permanent doesn't untap during its controller's untap step and its activated "
            "abilities can't be activated.")
STRIKE = card("Test Strike", "{1}{R}", "Sorcery",
              "Target creature gets +1/+0 until end of turn and can't be blocked this turn.")
SLIP = card("Test Slip", "{R}", "Sorcery", "Target creature can't be blocked this turn.")
PROWLERISH = card("Test Prowlerish", "{1}{U}", "Creature — Fish", "Flying\n"
                  "{2}{U}: ~ can't be blocked this turn.", 2, 1)
WELL = card("Test Well", "{2}", "Artifact", "{2}, {T}: Draw a card.")


class AuraRestrictionTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        for _ in range(4):
            self.perm(MOUNTAIN, self.a)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def cast_on(self, aura, host):
        auras.attach(self.game, aura, host)
        return aura

    def test_templates_match(self):
        for c in (TUNNEL, VEIL, BLIGHT, FRENZY, ARREST, BINDS, RUST, STRIKE, SLIP, PROWLERISH):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(TUNNEL.equip_bonus, (1, 0))
        self.assertEqual(TUNNEL.equip_keywords, frozenset({"unblockable"}))
        self.assertEqual(BLIGHT.equip_keywords, frozenset({"cant_block_now"}))
        self.assertEqual(FRENZY.equip_keywords, frozenset({"must_attack_now"}))
        self.assertEqual(ARREST.equip_keywords, frozenset({"defender"}))
        self.assertIn("defender", ARREST.approximations[0])
        self.assertEqual(BINDS.aura_flags, frozenset({"cant_attack_block", "cant_activate"}))
        self.assertEqual(RUST.aura_flags, frozenset({"no_untap", "cant_activate"}))

    def test_hostility(self):
        for c in (VEIL, FRENZY):                       # friendly: own creature wants them
            with self.subTest(card=c.name):
                self.assertFalse(c.aura_hostile)
        for c in (BLIGHT, ARREST, BINDS, RUST):
            with self.subTest(card=c.name):
                self.assertTrue(c.aura_hostile)

    def test_cant_be_blocked(self):
        mine = self.perm(BEAR, self.a)
        aura = self.perm(TUNNEL, self.a)
        self.cast_on(aura, mine)
        theirs = self.perm(DRAGON3, self.b)
        self.assertTrue(theirs.can_attack())
        self.assertFalse(can_block(theirs, mine))
        self.assertTrue(mine.can_attack())             # it can still attack

    def test_cant_block(self):
        theirs = self.perm(BEAR, self.b)
        aura = self.perm(BLIGHT, self.a)
        self.cast_on(aura, theirs)
        mine = self.perm(DRAGON3, self.a)
        self.assertTrue(theirs.can_attack())            # can't block only, not attack
        self.assertFalse(can_block(theirs, mine))
        self.assertTrue(can_block(mine, theirs))

    def test_attacks_each_combat(self):
        theirs = self.perm(BEAR, self.b)
        aura = self.perm(FRENZY, self.b)               # caster b puts it on their own
        self.cast_on(aura, theirs)
        self.assertTrue(theirs.has("must_attack_now"))
        self.game.take_turn(self.b)
        self.assertIn(theirs, self.game.attackers)     # forced into combat

    def test_cant_attack_plays_as_defender(self):
        theirs = self.perm(DRAGON3, self.b)
        aura = self.perm(ARREST, self.a)
        self.cast_on(aura, theirs)
        mine = self.perm(BEAR, self.a)
        self.assertFalse(theirs.can_attack())
        self.assertTrue(can_block(theirs, mine))       # still blocks (the approximation is exact here)

    def test_cant_attack_block_and_activate(self):
        theirs = self.perm(DRAGON3, self.b)
        aura = self.perm(BINDS, self.a)
        self.cast_on(aura, theirs)
        mine = self.perm(BEAR, self.a)
        self.assertFalse(theirs.can_attack())
        self.assertFalse(can_block(theirs, mine))
        well = self.perm(WELL, self.b)
        self.assertFalse(self.game.can_activate(self.b, well, 0))

    def test_no_untap_and_cant_activate_on_artifact(self):
        well = self.perm(WELL, self.b)
        aura = self.perm(RUST, self.a)
        self.cast_on(aura, well)
        well.tapped = True
        self.game.take_turn(self.b)
        self.assertTrue(well.tapped)                   # didn't untap
        self.assertFalse(self.game.can_activate(self.b, well, 0))

    def test_spell_pump_and_unblockable(self):
        mine = self.perm(BEAR, self.a)
        theirs = self.perm(DRAGON3, self.b)
        self.a.hand = [STRIKE]
        self.game.cast(self.a, STRIKE)
        self.assertEqual((mine.power, mine.toughness), (3, 2))
        self.assertFalse(can_block(theirs, mine))
        self.game.take_turn(self.a)                      # cleanup wears it off
        self.assertTrue(can_block(theirs, mine))

    def test_spell_unblockable_and_self(self):
        self.assertEqual(SLIP.spell_effects[0].kind, "unblockable")
        self.assertEqual(PROWLERISH.activated[0].effects[0].kind, "unblockable")
        mine = self.perm(BEAR, self.a)
        theirs = self.perm(DRAGON3, self.b)
        self.a.hand = [SLIP]
        self.game.cast(self.a, SLIP)
        self.assertFalse(can_block(theirs, mine))
