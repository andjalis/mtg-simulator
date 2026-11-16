"""Divided damage, split on resolution."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, DRAGON3, ISLAND, card

BOLT = card("Test Forked Bolt", "{R}", "Sorcery", "Test Forked Bolt deals 2 damage divided as you choose among one "
            "or two targets.")
VOLLEY = card("Test Volley", "{2}{R}", "Sorcery", "Test Volley deals 3 damage divided as you choose among one, two, or "
              "three target creatures.")


class DividedDamage(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c):
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_parses(self):
        self.assertEqual((BOLT.unsupported, VOLLEY.unsupported), ([], []))

    def test_kills_a_bear_then_face(self):
        bear = self.perm(BEAR, self.b)
        life = self.b.life
        self.cast(BOLT)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.b.life, life)
        self.cast(BOLT)
        self.assertEqual(self.b.life, life - 2)

    def test_creature_only_scope_never_hits_face(self):
        big = self.perm(DRAGON3, self.b)
        life = self.b.life
        self.cast(VOLLEY)
        self.assertEqual(self.b.life, life)
        self.assertEqual(big.damage, 3)


class DivisionAtCast(DividedDamage):
    def test_division_fixed_when_put_on_stack(self):
        self.assertEqual(BOLT.approximations, [])
        bear = self.perm(BEAR, self.b)
        item = StackItem(self.a, list(BOLT.spell_effects), [None], card=BOLT, name=BOLT.name)
        self.game.stack.append(item)
        planned = item.divided[id(item.effects[0])]
        self.assertEqual([(v, n) for v, n in planned], [(bear, 2)])     # chosen now, not on resolution
        self.perm(DRAGON3, self.b)                                      # a better target appears afterwards
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)

    def test_illegal_target_share_is_lost(self):
        bear = self.perm(BEAR, self.b)
        item = StackItem(self.a, list(BOLT.spell_effects), [None], card=BOLT, name=BOLT.name)
        self.game.stack.append(item)
        life = self.b.life
        self.b.battlefield.remove(bear)                                 # the target is gone before resolution
        self.game.resolve_top()
        self.assertEqual(self.b.life, life)


STRIKE = card("Test Strike", "{1}{R}", "Instant", "Test Strike deals 2 damage to target creature and 2 damage to target "
              "player or planeswalker.\nDraw a card.")


class TwoTargets(DividedDamage):
    def test_two_independent_targets(self):
        self.assertEqual(STRIKE.unsupported, [])
        bear = self.perm(BEAR, self.b)
        life = self.b.life
        self.game.stack.append(StackItem(self.a, list(STRIKE.spell_effects), [bear, self.b, None], card=STRIKE,
                                         name=STRIKE.name))
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.b.life, life - 2)


if __name__ == "__main__":
    unittest.main()


class DividedQualified(DividedDamage):
    """#626 DMG-DIVIDED: X, "up to N", and qualified recipients."""
    def test_parses_real_shapes(self):
        for text in ("deals X damage divided as you choose among any number of target creatures.",
                     "deals 3 damage divided as you choose among one, two, or three target attacking or blocking creatures.",
                     "deals 3 damage divided as you choose among one, two, or three target creatures with flying.",
                     "deals 3 damage divided as you choose among one, two, or three target white and/or blue creatures.",
                     "deals 5 damage divided as you choose among up to five targets.",
                     "deals X damage divided as you choose among any number of target attacking or blocking creatures "
                     "without flying."):
            c = card("Test Spell", "{X}{R}", "Sorcery", "Test Spell " + text)
            self.assertEqual(c.unsupported, [], text)
        c = card("Test Spell", "{2}{R}", "Sorcery", "Test Spell deals 3 damage divided as you choose among up to X targets.")
        self.assertTrue(c.unsupported)

    def test_x_damage_is_divided_by_the_x_paid(self):
        spell = card("Test Fire Covenant", "{X}{R}", "Instant", "Test Fire Covenant deals X damage divided as you choose "
                     "among any number of target creatures.")
        bear = self.perm(BEAR, self.b)
        big = self.perm(DRAGON3, self.b)
        item = StackItem(self.a, list(spell.spell_effects), [None], card=spell, name=spell.name)
        item.x = 2
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(big.damage, 0)

    def test_attacking_or_blocking_only(self):
        spell = card("Test Roil", "{3}{R}", "Instant", "Test Roil deals 5 damage divided as you choose among any number "
                     "of target attacking or blocking creatures.")
        idle = self.perm(BEAR, self.b)
        attacker = self.perm(BEAR, self.b)
        self.game.attackers = [attacker]
        self.cast(spell)
        self.assertIn(idle, self.b.battlefield)
        self.assertNotIn(attacker, self.b.battlefield)


class DividedComputed(DividedDamage):
    """#626 DMG-DIVIDED residue: "where X is Q as you cast ~", "X plus 1", "damage equal to Q divided"."""
    MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
    JAWS = card("Test Jaws", "{5}{R}{R}", "Sorcery", "Test Jaws deals X damage divided as you choose among any number "
                "of targets, where X is the number of Mountains you control as you cast this spell.")
    WIND = card("Test Wind", "{4}{R}", "Sorcery", "Test Wind deals X damage divided as you choose among any number of "
                "target creatures, where X is the number of creatures on the battlefield as you cast this spell.")
    SHOWER = card("Test Shower", "{X}{X}{R}", "Sorcery", "Test Shower deals X plus 1 damage divided as you choose among "
                  "any number of targets.")
    ORCA = card("Test Orca", "{5}{U}{B}{R}", "Creature — Demon", "When Test Orca dies, it deals damage equal to its "
                "power divided as you choose among any number of targets.", 7, 6)

    def test_parses(self):
        for c in (self.JAWS, self.WIND, self.SHOWER, self.ORCA):
            self.assertEqual(c.unsupported, [], c.name)
        for text in ("deals X damage divided as you choose among any number of targets, where X is the number of "
                     "cards in that player's hand as you cast this spell.",
                     "deals 3 plus 1 damage divided as you choose among any number of targets.",
                     "deals X damage divided evenly, rounded down, among any number of targets."):
            self.assertTrue(card("Test Spell", "{X}{R}", "Sorcery", "Test Spell " + text).unsupported, text)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB()
        for name in ("Jaws of Stone", "Volcanic Wind", "Monstrous Onslaught", "Meteor Shower", "Orca, Siege Demon"):
            c = db.get(name)
            self.assertEqual((c.unsupported, c.approximations), ([], []), name)

    def test_as_you_cast_counts_when_put_on_the_stack(self):
        for _ in range(3):
            self.perm(self.MOUNTAIN, self.a)
        ogre = self.perm(DRAGON3, self.b)
        item = StackItem(self.a, list(self.JAWS.spell_effects), [None], card=self.JAWS, name=self.JAWS.name)
        self.game.stack.append(item)                 # cast with three Mountains
        self.perm(self.MOUNTAIN, self.a)             # a fourth one before it resolves doesn't count
        self.game.resolve_top()
        self.assertNotIn(ogre, self.b.battlefield)
        self.assertEqual(self.b.life, 20)

    def test_wind_counts_every_creature_and_hits_only_theirs(self):
        mine = self.perm(BEAR, self.a)
        bears = [self.perm(BEAR, self.b) for _ in range(2)]
        life = self.b.life
        self.cast(self.WIND)                         # three creatures: 3 damage, never at a player
        self.assertEqual(sum(b not in self.b.battlefield for b in bears), 1)
        self.assertIn(mine, self.a.battlefield)
        self.assertEqual(self.b.life, life)

    def test_x_plus_one(self):
        bear = self.perm(BEAR, self.b)
        item = StackItem(self.a, list(self.SHOWER.spell_effects), [None], card=self.SHOWER, name=self.SHOWER.name)
        item.x = 2
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.b.life, 19)            # 3 damage: 2 to the bear, 1 to the face

    def test_orca_dies_and_divides_its_power(self):
        orca = self.perm(self.ORCA, self.a)
        orca.counters["+1/+1"] = 1                   # 8 power
        bear, big = self.perm(BEAR, self.b), self.perm(DRAGON3, self.b)
        life = self.b.life
        self.game.destroy(orca)
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertNotIn(big, self.b.battlefield)
        self.assertEqual(self.b.life, life - (8 - 2 - DRAGON3.toughness))

    def test_ai_casts_jaws_at_their_creatures(self):
        for _ in range(7):
            self.perm(self.MOUNTAIN, self.a)
        bear, big = self.perm(BEAR, self.b), self.perm(DRAGON3, self.b)
        mine = self.perm(BEAR, self.a)
        self.a.hand = [self.JAWS]
        spell = self.a.ai.choose_spell(self.game, self.a, precombat=True)
        self.assertIsNotNone(spell)
        self.assertEqual(spell[0].name, self.JAWS.name)
        self.assertTrue(self.game.cast(self.a, self.JAWS))
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertNotIn(big, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)

    def test_ai_casts_a_plain_divided_spell_and_holds_it_with_no_target(self):
        """Before #626's AI value the default AI never cast a divided-damage spell at all (its plan was worth 0)."""
        for _ in range(3):
            self.perm(self.MOUNTAIN, self.a)
        self.a.hand = [VOLLEY]
        self.assertIsNone(self.a.ai.choose_spell(self.game, self.a, precombat=True))     # no creature of theirs
        self.perm(BEAR, self.b)
        spell = self.a.ai.choose_spell(self.game, self.a, precombat=True)
        self.assertIsNotNone(spell)
        self.assertEqual(spell[0].name, VOLLEY.name)

    def test_where_x_division_is_not_counted_twice(self):
        """Game.resolve applies the "where X is" count and hands the handler a copy: the division planned at cast
        is used as is (on main it was planned again with the count squared)."""
        spell = card("Test Ureni", "{2}{R}", "Sorcery", "Test Ureni deals X damage divided as you choose among any "
                     "number of targets, where X is the number of Mountains you control.")
        for _ in range(2):
            self.perm(self.MOUNTAIN, self.a)
        life = self.b.life
        self.cast(spell)
        self.assertEqual(self.b.life, life - 2)
