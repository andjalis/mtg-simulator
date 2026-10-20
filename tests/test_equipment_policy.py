"""Automatic Equip value choices; manual activation keeps the full legal choices."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.cards import make_token
from mtgsim.engine import Game, Permanent, Player, choose_equip_cost, equip_all
from tests.test_templates import BEAR, DRAGON3, MOUNTAIN, SHOCK, card


def blade(text="Equip—Sacrifice a creature.", bonus="Equipped creature gets +2/+2."):
    return card("Policy Blade", "{1}", "Artifact — Equipment", f"{bonus}\n{text}")


class EquipmentPolicyTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [MOUNTAIN] * 30, HeuristicAI())
        self.b = Player("b", [MOUNTAIN] * 30, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(17))
        self.game.turn, self.game.step = 1, "main1"

    def perm(self, c):
        p = Permanent(c, self.a)
        p.sick = False
        self.a.battlefield.append(p)
        return p

    def board(self, eq=None, victim=None):
        return (self.perm(eq or blade()), self.perm(DRAGON3),
                self.perm(victim or make_token("Soldier", 1, 1)))

    def choose(self, eq, host, reserve=0):
        return choose_equip_cost(self.game, self.a, eq, host, reserve)

    def test_declines_losing_valuable_body_for_small_bonus(self):
        eq, host, victim = self.board(victim=BEAR)
        equip_all(self.game, self.a)
        self.assertIsNone(eq.attached_to)
        self.assertIn(victim, self.a.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 0)

    def test_accepts_small_token_for_larger_attachment(self):
        eq, host, victim = self.board()
        equip_all(self.game, self.a)
        self.assertIs(eq.attached_to, host)
        self.assertNotIn(victim, self.a.battlefield)

    def test_large_token_is_not_cheap_fodder(self):
        eq, host, victim = self.board(victim=make_token("Beast", 5, 5))
        self.assertIsNone(self.choose(eq, host))

    def test_evaluates_all_victims_instead_of_first_legacy_candidate(self):
        eq, host, big = self.board(victim=make_token("Beast", 5, 5))
        small = self.perm(make_token("Soldier", 1, 1))
        self.assertEqual(self.choose(eq, host), (0, small))
        self.assertIn(big, self.a.battlefield)

    def test_counters_and_existing_attachments_increase_victim_cost(self):
        eq, host, victim = self.board()
        victim.counters["+1/+1"] = 5
        self.assertIsNone(self.choose(eq, host))
        victim.counters.clear()
        gear = self.perm(blade("Equip {0}", "Equipped creature gets +4/+4."))
        gear.attached_to = victim
        self.assertIsNone(self.choose(eq, host))

    def test_prefers_cheap_mana_to_losing_token(self):
        eq, host, victim = self.board(blade("Equip {1}\nEquip—Sacrifice a creature."))
        self.perm(MOUNTAIN)
        self.assertEqual(self.choose(eq, host), (0, None))

    def test_prefers_small_token_to_expensive_mana(self):
        eq, host, victim = self.board(blade("Equip {6}\nEquip—Sacrifice a creature."))
        lands = [self.perm(MOUNTAIN) for _ in range(6)]
        equip_all(self.game, self.a)
        self.assertIs(eq.attached_to, host)
        self.assertNotIn(victim, self.a.battlefield)
        self.assertFalse(any(p.tapped for p in lands))

    def test_mana_is_more_valuable_with_spells_in_hand(self):
        eq, host, victim = self.board(blade("Equip {3}\nEquip—Sacrifice a creature."))
        for _ in range(4):
            self.perm(MOUNTAIN)
        self.assertEqual(self.choose(eq, host), (0, None))
        self.a.hand = [SHOCK]
        self.assertEqual(self.choose(eq, host, reserve=1), (1, victim))

    def test_discount_applied_before_comparing_mana(self):
        eq, host, victim = self.board(blade("Equip {6}\nEquip—Sacrifice a creature."))
        host.card = card("Discount Host", "{2}{R}", text="Equip abilities you activate that target ~ cost {6} less to activate.",
                         power=3, toughness=3)
        self.assertEqual(self.choose(eq, host), (0, None))

    def test_mixed_cost_and_reserve(self):
        eq, host, victim = self.board(blade("Equip—{1}{R}, Sacrifice a creature.",
                                             "Equipped creature gets +3/+3."))
        for _ in range(2):
            self.perm(MOUNTAIN)
        self.assertIsNone(self.choose(eq, host, reserve=1))
        self.assertEqual(self.choose(eq, host), (0, victim))

    def test_sole_target_is_kept_even_for_huge_bonus(self):
        eq = self.perm(blade(bonus="Equipped creature gets +20/+20."))
        host = self.perm(BEAR)
        self.assertIsNone(self.choose(eq, host))
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=host))
        self.assertNotIn(host, self.a.battlefield)

    def test_manual_poor_trade_and_explicit_ability_remain_legal(self):
        eq, host, victim = self.board(blade("Equip {1}\nEquip—Sacrifice a creature."), BEAR)
        land = self.perm(MOUNTAIN)
        self.assertEqual(self.choose(eq, host), (0, None))
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=victim, ability=1))
        self.assertFalse(land.tapped)
        self.assertNotIn(victim, self.a.battlefield)

    def test_new_keywords_can_justify_trade(self):
        eq, host, victim = self.board(blade(bonus="Equipped creature gets +2/+2 and has deathtouch and lifelink."), BEAR)
        self.assertEqual(self.choose(eq, host), (0, victim))

    def test_redundant_keywords_do_not_justify_trade(self):
        eq, host, victim = self.board(blade(bonus="Equipped creature gets +2/+2 and has deathtouch and lifelink."), BEAR)
        host.perm_kw.update({"deathtouch", "lifelink"})
        self.assertIsNone(self.choose(eq, host))

    def test_no_benefit_and_equal_value_trades_declined(self):
        eq, host, victim = self.board(blade(bonus="Equipped creature gets +0/+0."))
        self.assertIsNone(self.choose(eq, host))
        eq.card = blade(bonus="Equipped creature gets +1/+1.")
        self.assertIsNone(self.choose(eq, host))

    def test_deterministic_equal_cost_choice(self):
        eq, host, victim = self.board(blade("Equip {1}\nEquip {1}"))
        self.perm(MOUNTAIN)
        for _ in range(3):
            self.assertEqual(self.choose(eq, host), (0, None))
        eq.card = blade()
        other = self.perm(make_token("Soldier", 1, 1))
        self.assertEqual(self.choose(eq, host), (0, victim))
        self.assertIn(other, self.a.battlefield)

    def test_policy_hook_can_decline_and_board_is_not_mutated_by_scoring(self):
        eq, host, victim = self.board()
        state = (list(self.a.battlefield), list(self.a.hand), list(self.a.graveyard), host.power, host.toughness)
        with patch.object(self.game, "pay", side_effect=AssertionError("scoring must not pay")):
            self.assertEqual(self.choose(eq, host), (0, victim))
        self.assertEqual(state, (list(self.a.battlefield), list(self.a.hand), list(self.a.graveyard), host.power, host.toughness))
        self.assertIsNone(eq.attached_to)
        self.a.ai.choose_equip_cost = lambda *args: None
        equip_all(self.game, self.a)
        self.assertIsNone(eq.attached_to)


if __name__ == "__main__":
    unittest.main()
