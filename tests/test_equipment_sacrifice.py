"""Equip costs, chosen-object identity, responses and attachment cleanup."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.cards import make_token
from mtgsim.engine import Game, Permanent, Player, equip_all
from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card


TOOLS = card("Dissection Tools", "{5}", "Artifact — Equipment",
             "When Dissection Tools enters, manifest dread, then attach Dissection Tools to that creature.\n"
             "Equipped creature has +2/+2 and has deathtouch and lifelink.\nEquip—Sacrifice a creature.")
HAUBERK = card("Demonmail Hauberk", "{4}", "Artifact — Equipment",
               "Equipped creature gets +4/+2.\nEquip—Sacrifice a creature.")
BLADE = card("Test Mana Blade", "{1}", "Artifact — Equipment",
             "Equipped creature gets +1/+1.\nEquip {2}")
VICTIM = card("Test Sacrifice", "", "Creature — Human",
              "Indestructible\nWhen Test Sacrifice dies, draw a card.", 1, 1)
WATCHER = card("Test Watcher", "", "Creature — Human",
               "Whenever you sacrifice a creature, you gain 1 life.", 1, 1)
BOUNCE = card("Test Bounce", "{U}", "Instant", "Return target creature to its owner's hand.")


class EquipmentSacrificeTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 30, HeuristicAI())
        self.b = Player("b", [ISLAND] * 30, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 30
        self.b.library = [ISLAND] * 30

    def perm(self, c, p=None):
        p = self.a if p is None else p
        x = Permanent(c, p)
        x.sick = False
        p.battlefield.append(x)
        return x

    def board(self):
        return self.perm(TOOLS), self.perm(DRAGON3), self.perm(BEAR)

    def test_general_templates(self):
        for c in (TOOLS, HAUBERK):
            self.assertEqual(c.unsupported, [])
            self.assertEqual(c.equip_cost, {})
            self.assertTrue(c.equip_sacrifice)
        self.assertEqual(TOOLS.equip_bonus, (2, 2))
        self.assertEqual(TOOLS.equip_keywords, frozenset({"deathtouch", "lifelink"}))
        self.assertFalse(BLADE.equip_sacrifice)

    def test_unknown_costs_and_bonus_restrictions_stay_visible(self):
        for text in ("Equip—Sacrifice an artifact.", "Equip—Sacrifice two creatures.",
                     "Equip—Sacrifice a creature with power 3 or greater.",
                     "Equip—{2}, Sacrifice a creature with flying.", "Equip—Sacrifice a creature. Activate only once each turn.",
                     "Equipped creature has +2/+2 as long as you control a token.",
                     "Equipped creature has +2/+2 and has protection from blue as long as you control a token."):
            with self.subTest(text=text):
                c = card("Restricted Equipment", "", "Artifact — Equipment", text)
                self.assertTrue(c.unsupported)
                self.assertIsNone(c.equip_cost)
                self.assertEqual(c.equip_bonus, (0, 0))

    def test_pay_sacrifice_without_mana_and_apply_bonus(self):
        eq, host, victim = self.board()
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertIs(eq.attached_to, host)
        self.assertNotIn(victim, self.a.battlefield)
        self.assertIn(BEAR, self.a.graveyard)
        self.assertEqual(self.a.sacrificed_turn, 1)
        self.assertEqual((host.power, host.toughness), (5, 5))
        self.assertTrue(host.has("deathtouch") and host.has("lifelink"))
        self.assertEqual(self.game.stack, [])

    def test_cost_is_paid_before_responses_and_triggers_go_above_equip(self):
        eq, host, _ = self.board()
        victim = self.perm(VICTIM)
        self.perm(WATCHER)
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=victim))
        self.assertNotIn(victim, self.a.battlefield)  # indestructible doesn't stop sacrifice
        self.assertIn(VICTIM, self.a.graveyard)
        self.assertIsNone(eq.attached_to)
        self.assertIs(self.game.stack[0].targets[0], host)
        self.game.flush_triggers()
        self.assertEqual(self.game.stack[0].effects[0].kind, "equip")
        self.assertEqual(len(self.game.stack), 3)
        self.game.settle()
        self.assertIs(eq.attached_to, host)
        self.assertEqual(self.a.hand, [ISLAND])
        self.assertEqual(self.a.life, 21)

    def test_may_sacrifice_target_and_does_not_retarget(self):
        eq, host, other = self.board()
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=host))
        self.assertIsNone(eq.attached_to)
        self.assertIn(other, self.a.battlefield)
        self.assertIn(DRAGON3, self.a.graveyard)

    def test_cannot_sacrifice_opponents_creature_or_noncreature(self):
        eq, host, victim = self.board()
        for invalid in (self.perm(BEAR, self.b), eq, self.perm(ISLAND)):
            self.assertFalse(self.game.equip(self.a, eq, host, sacrifice=invalid))
            self.assertIn(victim, self.a.battlefield)
            self.assertIsNone(eq.attached_to)
        self.assertEqual(self.a.sacrificed_turn, 0)

    def test_invalid_target_does_not_pay_cost(self):
        eq, host, victim = self.board()
        for invalid in (self.perm(DRAGON3, self.b), self.perm(ISLAND)):
            self.assertFalse(self.game.equip(self.a, eq, invalid))
            self.assertIn(victim, self.a.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 0)

    def test_only_target_is_a_legal_cost_but_automatic_policy_keeps_it(self):
        eq, host = self.perm(TOOLS), self.perm(BEAR)
        equip_all(self.game, self.a)
        self.assertIn(host, self.a.battlefield)
        self.assertIsNone(eq.attached_to)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertNotIn(host, self.a.battlefield)
        self.assertIsNone(eq.attached_to)

    def test_default_policy_uses_another_creature_and_activate_dispatches(self):
        eq, host, victim = self.board()
        equip_all(self.game, self.a)
        self.assertIs(eq.attached_to, host)
        self.assertNotIn(victim, self.a.battlefield)
        victim = self.perm(BEAR)
        self.assertTrue(self.game.activate(self.a, eq, "equip", host))
        self.assertNotIn(victim, self.a.battlefield)
        self.assertIs(eq.attached_to, host)  # targeting an already equipped creature is legal

    def test_sorcery_timing_and_activation_lock_do_not_pay(self):
        eq, host, victim = self.board()
        for step in ("declare_attackers", "end_step"):
            self.game.step = step
            self.assertFalse(self.game.equip(self.a, eq, host))
        self.game.step = "main1"
        self.game.active_idx = 1
        self.assertFalse(self.game.equip(self.a, eq, host))
        self.game.active_idx = 0
        with patch.object(self.game, "activations_stopped", return_value=True):
            self.assertFalse(self.game.equip(self.a, eq, host))
        self.assertIn(victim, self.a.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 0)

    def test_pending_equip_blocks_another_sorcery_activation(self):
        eq, host, victim = self.board()
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.equip(self.a, eq, host))
            self.assertFalse(self.game.equip(self.a, eq, host, sacrifice=host))
        self.assertEqual(self.a.sacrificed_turn, 1)

    def test_token_payment_vanishes_and_host_death_detaches(self):
        eq, host = self.perm(TOOLS), self.perm(DRAGON3)
        token = self.perm(make_token("Soldier", 1, 1))
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=token))
        self.assertEqual(self.a.graveyard, [])
        self.game.destroy(host)
        self.assertIsNone(eq.attached_to)
        self.assertIn(eq, self.a.battlefield)

    def test_removing_equipment_removes_stats_and_keywords(self):
        eq, host, _ = self.board()
        self.game.equip(self.a, eq, host)
        self.game.leave_battlefield(eq, "hand")
        self.assertIsNone(eq.attached_to)
        self.assertEqual((host.power, host.toughness), (3, 3))
        self.assertFalse(host.has("lifelink") or host.has("deathtouch"))

    def test_target_leaving_and_same_card_returning_does_not_retarget(self):
        eq, host, _ = self.board()
        with patch.object(self.game, "settle"):
            self.game.equip(self.a, eq, host)
        self.game.leave_battlefield(host, "hand")
        self.a.hand.remove(DRAGON3)
        returned = self.game.enter_battlefield(self.a, DRAGON3)
        self.game.settle()
        self.assertIsNot(host, returned)
        self.assertIsNone(eq.attached_to)

    def test_equipment_leaving_and_returning_is_a_new_source(self):
        eq, host, _ = self.board()
        with patch.object(self.game, "settle"):
            self.game.equip(self.a, eq, host)
        self.game.leave_battlefield(eq, "hand")
        self.a.hand.remove(TOOLS)
        returned = self.perm(TOOLS)
        self.game.settle()
        self.assertIsNone(returned.attached_to)
        self.assertIsNone(eq.attached_to)

    def test_failed_reequip_keeps_original_host_and_success_moves_bonus(self):
        eq, old, victim = self.board()
        self.game.equip(self.a, eq, old, sacrifice=victim)
        target, payment = self.perm(BEAR), self.perm(BEAR)
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.equip(self.a, eq, target, sacrifice=payment))
        self.assertIs(eq.attached_to, old)
        self.assertEqual(old.power, 5)
        self.game.destroy(target)
        self.game.settle()
        self.assertIs(eq.attached_to, old)
        target, payment = self.perm(BEAR), self.perm(BEAR)
        self.assertTrue(self.game.equip(self.a, eq, target, sacrifice=payment))
        self.assertIs(eq.attached_to, target)
        self.assertEqual((old.power, target.power), (3, 4))

    def test_reequip_can_sacrifice_previous_host(self):
        eq, old, victim = self.board()
        self.game.equip(self.a, eq, old, sacrifice=victim)
        target = self.perm(BEAR)
        self.assertTrue(self.game.equip(self.a, eq, target, sacrifice=old))
        self.assertIs(eq.attached_to, target)
        self.assertNotIn(old, self.a.battlefield)

    def test_friendly_hexproof_is_legal_and_source_disappearance_keeps_cost_paid(self):
        eq, host, victim = self.board()
        host.temp_kw.add("hexproof")
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.equip(self.a, eq, host))
        self.game.destroy(eq)
        self.game.settle()
        self.assertIsNone(eq.attached_to)
        self.assertIn(victim.card, self.a.graveyard)
        self.assertIn(host, self.a.battlefield)

    def test_control_or_type_change_invalidates_chosen_target(self):
        for change in ("controller", "type"):
            with self.subTest(change=change):
                self.setUp()
                eq, host, _ = self.board()
                with patch.object(self.game, "settle"):
                    self.game.equip(self.a, eq, host)
                if change == "controller":
                    self.a.battlefield.remove(host)
                    host.controller = self.b
                    self.b.battlefield.append(host)
                else:
                    host.card = ISLAND
                self.game.settle()
                self.assertIsNone(eq.attached_to)

    def test_source_control_change_keeps_attachment_bonus_and_cleanup(self):
        eq, host, _ = self.board()
        with patch.object(self.game, "settle"):
            self.game.equip(self.a, eq, host)
        self.a.battlefield.remove(eq)
        eq.controller = self.b
        self.b.battlefield.append(eq)
        self.game.settle()
        self.assertIs(eq.attached_to, host)
        self.assertEqual((host.power, host.toughness), (5, 5))
        self.assertTrue(host.has("lifelink"))
        self.assertIn(eq, host.equipment)
        self.game.destroy(host)
        self.assertIsNone(eq.attached_to)

    def test_attached_equipment_survives_stolen_host_but_detaches_if_host_stops_being_creature(self):
        eq, host, _ = self.board()
        self.game.equip(self.a, eq, host)
        self.a.battlefield.remove(host)
        host.controller = self.b
        self.b.battlefield.append(host)
        self.game.state_based_actions()
        self.assertIs(eq.attached_to, host)
        self.assertEqual((host.power, host.toughness), (5, 5))
        self.assertTrue(host.has("deathtouch"))
        host.card = ISLAND
        self.game.state_based_actions()
        self.assertIsNone(eq.attached_to)

    def test_real_priority_response_bounces_target_after_payment(self):
        eq, host, victim = self.board()
        self.perm(ISLAND, self.b)
        self.b.hand = [BOUNCE]

        class BounceAI(HeuristicAI):
            def respond(inner, game, me):
                if BOUNCE in me.hand and any(e.kind == "equip" for i in game.stack for e in i.effects):
                    self.assertNotIn(victim, self.a.battlefield)
                    self.assertIsNone(eq.attached_to)
                    return BOUNCE, [host]
                return None

        self.b.ai = BounceAI()
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertIn(DRAGON3, self.a.hand)
        self.assertIsNone(eq.attached_to)
        self.assertIn(BEAR, self.a.graveyard)

    def test_ordinary_mana_equip_still_pays_and_waits_for_resolution(self):
        eq, host = self.perm(BLADE), self.perm(BEAR)
        self.assertFalse(self.game.equip(self.a, eq, host))
        lands = [self.perm(MOUNTAIN) for _ in range(2)]
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertTrue(all(x.tapped for x in lands))
        self.assertIsNone(eq.attached_to)
        self.assertEqual(self.a.sacrificed_turn, 0)
        self.game.settle()
        self.assertIs(eq.attached_to, host)

    def test_animated_equipment_cannot_attach_or_stay_attached(self):
        eq, host, _ = self.board()
        self.game.equip(self.a, eq, host)
        eq.card = dataclasses.replace(TOOLS, types=frozenset({"Artifact", "Creature"}), power=2, toughness=2)
        self.game.state_based_actions()
        self.assertIsNone(eq.attached_to)
        self.game.equip(self.a, eq, host)
        self.assertIsNone(eq.attached_to)

    def test_manifest_attaches_to_new_creature_with_full_tools_bonus(self):
        strong = self.perm(DRAGON3)
        self.a.library = [BEAR]
        eq = self.game.enter_battlefield(self.a, TOOLS)
        self.game.settle()
        self.assertIsNot(eq.attached_to, strong)
        self.assertIs(eq.attached_to.front, BEAR)
        self.assertEqual((eq.attached_to.power, eq.attached_to.toughness), (4, 4))
        self.assertTrue(eq.attached_to.has("deathtouch") and eq.attached_to.has("lifelink"))


if __name__ == "__main__":
    unittest.main()
