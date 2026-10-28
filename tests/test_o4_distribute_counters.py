"""O4 round 2: "Distribute N +1/+1 counters among ... target creatures" (mtgsim.distribute)."""
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import StackItem
from tests.test_templates import BEAR, DRAGON3, MOUNTAIN, Base, card

CHARM = card("Test Charm", "{G}", "Instant", "Distribute two +1/+1 counters among one or two target creatures.")
CHARM3 = card("Test Charm Three", "{G}", "Instant",
              "Distribute three +1/+1 counters among one, two, or three target creatures you control.")
UPTO = card("Test Upto", "{G}", "Sorcery", "Distribute four +1/+1 counters among up to two target creatures you control.")
ANYNUM = card("Test Gearhulk", "{4}{G}", "Artifact Creature — Construct", "When this creature enters, distribute four "
              "+1/+1 counters among any number of target creatures you control.", 4, 4)
RALLY = card("Test Rally", "{G}", "Sorcery", "Distribute four +1/+1 counters among any number of target creatures.")
XSPELL = card("Test Bounty", "{X}{G}", "Sorcery", "Distribute X +1/+1 counters among any number of target creatures "
              "you control.")
UNTARGETED = card("Test Maelstrom", "{G}", "Sorcery", "Distribute three +1/+1 counters among one, two, or three "
                  "creatures you control.")
WALKER = card("Test Ajani", "{3}{W}", "Legendary Planeswalker — Ajani", "+1: Distribute three +1/+1 counters among one, "
              "two, or three target creatures you control.\n-3: Test Ajani deals 1 damage to any target.", cmc=4)
ANNIHILATE = card("Test Shrink", "{G}", "Instant", "Put a -1/-1 counter on target creature.")
# Out of scope: a rider after the distribution, "other", and non-+1/+1 counters.
DOUBLER = card("Test Upgrade", "{G}", "Instant", "Distribute three +1/+1 counters among one, two, or three target "
               "creatures, then double the number of +1/+1 counters on each of those creatures.")
OTHER = card("Test Other", "{G}", "Instant", "Distribute two +1/+1 counters among one or two other target creatures "
             "you control.")
MINUS = card("Test Minus", "{G}", "Instant", "Distribute two -1/-1 counters among one or two target creatures.")


def counters(perm):
    return perm.counters.get("+1/+1", 0)


class DistributeCounters(Base):
    def resolve(self, c, targets, x=0):
        item = StackItem(self.a, c.spell_effects, targets, card=c)
        item.x = x
        for eff, tgt in zip(c.spell_effects, targets):
            self.game.resolve(self.a, eff, tgt, item)

    def test_templates(self):
        for c in (CHARM, CHARM3, UPTO, ANYNUM, RALLY, XSPELL, UNTARGETED, WALKER):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual([(e.amount, e.data["slots"]) for e in (
            CHARM.spell_effects[0], CHARM3.spell_effects[0], UPTO.spell_effects[0], XSPELL.spell_effects[0])],
            [(2, 2), (3, 3), (4, 2), (0, 99)])
        self.assertTrue(XSPELL.spell_effects[0].data["x"])
        self.assertEqual(UNTARGETED.spell_effects[0].target, "none")

    def test_out_of_scope_lines_stay_unsupported(self):
        for c in (DOUBLER, OTHER, MINUS):
            with self.subTest(card=c.name):
                self.assertEqual(len(c.unsupported), 1)
                self.assertFalse(any(e.kind == "distribute_counters" for e in c.spell_effects))

    def test_real_cards(self):
        db = CardDB(offline=True)
        if db.lookup("Elusive Otter") is None:
            self.skipTest("card database not built")
        otter = db.get("Elusive Otter")
        self.assertEqual(otter.unsupported, [])
        self.assertEqual(otter.adventure.unsupported, [])
        self.assertEqual(otter.adventure.spell_effects[0].kind, "distribute_counters")
        self.assertEqual(len(db.get("Biogenic Upgrade").unsupported), 1)

    def test_dies_trigger_with_where_x_moves_the_counters(self):
        db = CardDB(offline=True)
        if db.lookup("Quirion Beastcaller") is None:
            self.skipTest("card database not built")
        caller = self.perm(db.get("Quirion Beastcaller"), self.a)
        caller.counters["+1/+1"] = 3
        bear = self.perm(BEAR, self.a)
        caller.damage = 99
        self.game.state_based_actions()
        self.game.settle()
        self.assertNotIn(caller, self.a.battlefield)
        self.assertEqual(counters(bear), 3)

    def test_three_counters_spread_over_the_best_creatures(self):
        big, small = self.perm(DRAGON3, self.a), self.perm(BEAR, self.a)
        self.resolve(CHARM3, [big])
        self.assertEqual((counters(big), counters(small)), (2, 1))
        self.assertEqual((big.power, small.power), (5, 3))

    def test_one_target_gets_every_counter(self):
        only = self.perm(BEAR, self.a)
        self.resolve(CHARM3, [only])
        self.assertEqual(counters(only), 3)

    def test_slot_limit_and_one_counter_per_target(self):
        mine = [self.perm(BEAR, self.a) for _ in range(4)]
        self.resolve(CHARM, [mine[0]])                 # "one or two": two targets at most
        self.assertEqual(sorted(counters(c) for c in mine), [0, 0, 1, 1])
        self.resolve(XSPELL, [mine[0]], x=2)
        self.assertEqual(sum(counters(c) for c in mine), 4)    # two counters, never more targets than counters
        self.resolve(RALLY, [mine[0]])
        self.assertEqual(sum(counters(c) for c in mine), 8)
        self.assertEqual(sum(bool(counters(c)) for c in mine), 4)     # four counters reach four creatures

    def test_x_zero_places_nothing(self):
        bear = self.perm(BEAR, self.a)
        self.resolve(XSPELL, [bear], x=0)
        self.assertEqual(counters(bear), 0)

    def test_never_targets_the_opponent(self):
        theirs = self.perm(DRAGON3, self.b)
        mine = self.perm(BEAR, self.a)
        for c in (CHARM, CHARM3, UPTO, RALLY, XSPELL):
            with self.subTest(card=c.name):
                self.assertEqual(self.game.legal_targets(self.a, c.spell_effects[0]), [mine])
        self.resolve(CHARM3, [mine])
        self.assertEqual((counters(theirs), counters(mine)), (0, 3))

    def test_untargeted_uses_only_my_creatures(self):
        theirs = self.perm(DRAGON3, self.b)
        mine = [self.perm(BEAR, self.a) for _ in range(2)]
        self.resolve(UNTARGETED, [None])
        self.assertEqual(sorted(counters(c) for c in mine), [1, 2])
        self.assertEqual(counters(theirs), 0)

    def test_no_creature_means_no_cast_and_no_counters(self):
        self.perm(DRAGON3, self.b)          # the opponent has a creature, I have none
        self.a.hand = [CHARM3]
        self.perm(MOUNTAIN, self.a)
        self.assertFalse(self.game.cast(self.a, CHARM3))
        self.assertEqual(self.a.hand, [CHARM3])
        self.resolve(UNTARGETED, [None])    # nothing to put them on: no crash
        self.resolve(CHARM3, [None])
        self.assertEqual(counters(self.b.battlefield[0]), 0)

    def test_cast_x_spell_puts_the_paid_x_on_my_creatures(self):
        bear = self.perm(BEAR, self.a)
        for _ in range(4):
            self.perm(card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)"), self.a)
        self.a.hand = [XSPELL]
        self.assertTrue(self.game.cast(self.a, XSPELL))
        self.game.settle()
        self.assertEqual(counters(bear), 3)

    def test_planeswalker_ability_and_enters_trigger(self):
        bear = self.perm(BEAR, self.a)
        walker = self.perm(WALKER, self.a)
        walker.counters["loyalty"] = 4
        self.assertTrue(self.game.activate_loyalty(self.a, walker, 0))
        self.game.settle()
        self.assertEqual((counters(bear), walker.loyalty), (3, 5))
        self.game.enter_battlefield(self.a, ANYNUM)
        self.game.settle()
        self.assertEqual(sum(counters(c) for c in self.a.creatures), 7)

    def test_enters_trigger_with_no_other_creature_is_harmless(self):
        self.game.enter_battlefield(self.a, ANYNUM)
        self.game.settle()
        self.assertEqual(counters(self.a.creatures[0]), 4)     # itself is a creature you control

    def test_counters_survive_combat_damage(self):
        big, small = self.perm(DRAGON3, self.a), self.perm(BEAR, self.a)
        self.resolve(CHARM3, [big])
        small.damage = 2                      # a 3/3 now: 2 damage doesn't kill it
        self.game.state_based_actions()
        self.assertIn(small, self.a.battlefield)
        big.damage = 5                        # 5/5 with the counters, so 5 kills it
        self.game.state_based_actions()
        self.assertNotIn(big, self.a.battlefield)

    def test_minus_counter_annihilates_a_distributed_one(self):
        bear = self.perm(BEAR, self.a)
        self.resolve(CHARM, [bear])
        self.assertEqual(counters(bear), 2)
        self.game.resolve(self.a, ANNIHILATE.spell_effects[0], bear, StackItem(self.a, [], [], card=ANNIHILATE))
        self.assertEqual((counters(bear), bear.power), (1, 3))


if __name__ == "__main__":
    unittest.main()
