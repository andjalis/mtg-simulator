"""Restricted token grants choose before costs and keep the same target through responses."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, PLAINS, card


GRANT = "Target attacking creature token gains indestructible until end of turn."
HOB = card("Test Protector", "{4}{R}", "Creature — Cat Mutant Rebel",
           "At the beginning of combat on your turn, create a 2/2 red Mutant creature token. "
           "It gains haste until end of turn. Destroy it at the beginning of the next end step.\n"
           "{1}{W}: " + GRANT, 4, 4)
TOKEN = dataclasses.replace(BEAR, is_token=True)
BOUNCE = card("Test Retreat", "{0}", "Instant", "Return target creature to its owner's hand.")
MIXED = card("Test Protection and Draw", "{0}", "Instant", GRANT + " Draw a card.")


class AttackingTokenGrants(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 30, HeuristicAI())
        self.b = Player("b", [ISLAND] * 30, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "declare_attackers"
        self.src = self.game.enter_battlefield(self.a, HOB)
        for _ in range(4):
            self.game.enter_battlefield(self.a, PLAINS)
        self.seen = []

    def token(self, owner=None, attacking=True):
        token = self.game.enter_battlefield(owner or self.a, TOKEN)
        if attacking:
            self.game.attackers.append(token)
        return token

    def respond(self, action=None):
        def response(game, me):
            if game.stack and not self.seen:
                item = game.stack[-1]
                self.seen.append((item, list(item.targets)))
                return action(item) if action else None
            return None
        self.b.ai.respond = response

    def activate(self, target=None):
        return self.game.activate_ability(self.a, self.src, 0, None if target is None else [target])

    def test_general_template_and_real_card(self):
        self.assertEqual(HOB.unsupported, [])
        effect = HOB.activated[0].effects[0]
        self.assertEqual((effect.kind, effect.target, effect.filter, effect.data),
                         ("grant", "creature", "attacking_token", {"keyword": "indestructible"}))
        db = CardDB(offline=True)
        if db._all is None:
            self.skipTest("card DB absent")
        try:
            hob = db.get("Old Hob, Alleycat Blues")
            self.assertEqual(hob.unsupported, [])
            self.assertEqual(hob.activated[0].effects[0], effect)
        finally:
            db._all.close()

    def test_unknown_restrictions_remain_visible(self):
        for text in (GRANT.replace("token", "token with power 2 or less"),
                     GRANT.replace("end of turn", "your next turn")):
            self.assertTrue(card("Test Unknown", "{W}", "Enchantment", "{W}: " + text).unsupported)

    def test_no_attacker_means_no_activation_or_payment(self):
        self.token(attacking=False)
        self.game.attackers.append(self.src)  # an attacking nontoken is not enough
        self.assertFalse(self.game.can_activate(self.a, self.src, 0))
        self.assertFalse(self.activate())
        self.assertFalse(any(x.tapped for x in self.a.battlefield))
        self.assertEqual(self.src.ability_turns, {})

    def test_explicit_illegal_targets_rejected_without_payment(self):
        good = self.token()
        idle = self.token(attacking=False)
        artifact = self.game.enter_battlefield(self.a, dataclasses.replace(
            TOKEN, types=frozenset({"Artifact"}), power=None, toughness=None))
        self.game.attackers.append(artifact)
        for bad in (self.src, idle, artifact, self.a):
            with self.subTest(target=bad):
                self.assertFalse(self.activate(bad))
                self.assertFalse(any(x.tapped for x in self.a.battlefield))
                self.assertFalse(good.has("indestructible"))

    def test_autoselection_and_stack_target_are_legal(self):
        good = self.token()
        self.token(attacking=False)
        self.respond()
        self.assertTrue(self.activate())
        self.assertEqual(self.seen[0][1], [good])
        self.assertTrue(good.has("indestructible"))
        self.assertEqual(sum(x.tapped for x in self.a.battlefield), 2)

    def test_target_is_chosen_before_mana_payment(self):
        good = self.token()
        seen = []
        def choose(game, me, eff):
            seen.append(sum(x.tapped for x in me.battlefield))
            return good
        self.a.ai.choose_target = choose
        self.assertTrue(self.activate())
        self.assertEqual(seen, [0])

    def test_failed_payment_keeps_target_and_costs_intact(self):
        target = self.token()
        for land in self.a.battlefield:
            if land.card.is_land:
                land.tapped = True
        self.assertFalse(self.activate(target))
        self.assertFalse(target.has("indestructible"))
        self.assertEqual(self.src.ability_turns, {})

    def test_optional_control_restriction(self):
        mine = card("Test My Tokens", "{W}", "Enchantment",
                    "{0}: " + GRANT.replace("token gains", "token you control gains"))
        source = self.game.enter_battlefield(self.b, mine)
        attacker = self.token()
        self.assertFalse(self.game.activate_ability(self.b, source, 0, [attacker]))
        self.assertFalse(attacker.has("indestructible"))
        source = self.game.enter_battlefield(self.a, mine)
        self.assertTrue(self.game.activate_ability(self.a, source, 0, [attacker]))
        self.assertTrue(attacker.has("indestructible"))

    def test_can_explicitly_protect_an_opposing_attacker(self):
        source = self.game.enter_battlefield(self.b, card(
            "Test Other Protector", "{W}", "Enchantment", "{0}: " + GRANT))
        attacker = self.token()
        self.assertTrue(self.game.activate_ability(self.b, source, 0, [attacker]))
        self.assertTrue(attacker.has("indestructible"))

    def test_gaining_hexproof_in_response_fizzles_enemy_grant(self):
        source = self.game.enter_battlefield(self.b, card(
            "Test Other Protector", "{W}", "Enchantment", "{0}: " + GRANT))
        attacker = self.token()
        self.respond(lambda item: attacker.temp_kw.add("hexproof"))
        self.assertTrue(self.game.activate_ability(self.b, source, 0, [attacker]))
        self.assertFalse(attacker.has("indestructible"))

    def test_own_hexproof_and_untapped_vigilant_attackers_are_legal(self):
        attacker = self.token()
        attacker.temp_kw.update({"hexproof", "vigilance"})
        self.assertFalse(attacker.tapped)
        self.assertTrue(self.activate(attacker))
        self.assertTrue(attacker.has("indestructible"))

    def test_bounce_response_keeps_paid_costs_and_does_not_retarget(self):
        target, spare = self.token(), self.token()
        def bounce(item):
            self.b.hand.append(BOUNCE)
            return BOUNCE, [target]
        self.respond(bounce)
        self.assertTrue(self.activate(target))
        self.assertEqual(self.seen[0][1], [target])
        self.assertNotIn(target, self.a.battlefield)
        self.assertFalse(spare.has("indestructible"))
        self.assertEqual(sum(x.tapped for x in self.a.battlefield), 2)
        self.assertTrue(any("fizzles" in event for event in self.game.events))

    def test_same_card_reentering_is_a_different_target(self):
        target, spare = self.token(), self.token()
        replacement = []
        def replace(item):
            self.game.leave_battlefield(target, "exile")
            replacement.append(self.token())
        self.respond(replace)
        self.assertTrue(self.activate(target))
        self.assertFalse(replacement[0].has("indestructible"))
        self.assertFalse(spare.has("indestructible"))

    def test_removal_from_combat_in_response_fizzles(self):
        target, spare = self.token(), self.token()
        self.respond(lambda item: self.game.attackers.remove(target))
        self.assertTrue(self.activate(target))
        self.assertFalse(target.has("indestructible"))
        self.assertFalse(spare.has("indestructible"))

    def test_type_change_in_response_fizzles_even_if_restored(self):
        for restore in (False, True):
            with self.subTest(restore=restore):
                self.setUp()
                target = self.token()
                def change(item):
                    target.card = dataclasses.replace(TOKEN, types=frozenset({"Artifact"}))
                    self.game.state_based_actions()
                    if restore:
                        target.card = TOKEN
                self.respond(change)
                self.assertTrue(self.activate(target))
                self.assertFalse(target.has("indestructible"))
                self.assertNotIn(target, self.game.attackers)

    def test_control_change_in_response_fizzles_even_if_restored(self):
        for restore in (False, True):
            with self.subTest(restore=restore):
                self.setUp()
                target = self.token()
                def move(to):
                    target.controller.battlefield.remove(target)
                    target.controller = to
                    to.battlefield.append(target)
                def change(item):
                    move(self.b)
                    self.game.state_based_actions()
                    if restore:
                        move(self.a)
                self.respond(change)
                self.assertTrue(self.activate(target))
                self.assertFalse(target.has("indestructible"))
                self.assertNotIn(target, self.game.attackers)

    def test_source_leaving_or_changing_controller_does_not_stop_grant(self):
        for remove in (False, True):
            with self.subTest(remove=remove):
                self.setUp()
                target = self.token()
                def change(item):
                    if remove:
                        self.game.leave_battlefield(self.src, "exile")
                    else:
                        self.a.battlefield.remove(self.src)
                        self.src.controller = self.b
                        self.b.battlefield.append(self.src)
                self.respond(change)
                self.assertTrue(self.activate(target))
                self.assertTrue(target.has("indestructible"))

    def test_sacrificed_target_is_not_replaced_after_payment(self):
        source = self.game.enter_battlefield(self.a, card(
            "Test Sacrifice Protector", "{W}", "Enchantment", "Sacrifice a creature: " + GRANT))
        target, spare = self.token(), self.token()
        self.respond()
        self.assertTrue(self.game.activate_ability(self.a, source, 0, [target]))
        self.assertNotIn(target, self.a.battlefield)
        self.assertEqual(self.seen[0][1], [target])
        self.assertFalse(spare.has("indestructible"))

    def test_noncombat_stale_attacker_list_is_not_legal(self):
        self.token()
        for step in ("begin_combat", "main2", "end_step", "cleanup"):
            self.game.step = step
            self.assertFalse(self.activate(), step)
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_spell_and_modal_ability_reject_missing_targets_before_payment(self):
        self.a.hand.append(MIXED)
        self.assertFalse(self.game.cast(self.a, MIXED))
        self.assertIn(MIXED, self.a.hand)
        source = self.game.enter_battlefield(self.a, card(
            "Test Modal Protector", "{W}", "Enchantment", "{W}: Choose one —\n• " + GRANT + "\n• Draw a card."))
        self.a.ai.choose_modes = lambda game, me, modes, n, up_to: [0]
        self.assertFalse(self.game.activate_ability(self.a, source, 0))
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_other_legal_target_resolves_when_attacker_becomes_illegal(self):
        target = self.token()
        mixed = card("Test Mixed Grant", "{0}", "Instant", GRANT + " Test Mixed Grant deals 1 damage to any target.")
        self.a.hand.append(mixed)
        self.respond(lambda item: self.game.attackers.remove(target))
        self.assertTrue(self.game.cast(self.a, mixed, [target, self.b]))
        self.assertEqual(self.b.life, 19)
        self.assertFalse(target.has("indestructible"))

    def test_grant_survives_end_of_combat_and_stops_delayed_destroy(self):
        self.game.fire(self.a, "begin_combat")
        self.game.settle()
        target = next(x for x in self.a.creatures if x.front.is_token)
        self.game.attackers.append(target)
        self.assertTrue(self.activate(target))
        self.game.attackers.clear()
        self.game.step = "end_step"
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertIn(target, self.a.battlefield)
        self.assertTrue(target.has("indestructible"))
        self.assertEqual(self.game.delayed, [])
        target.temp_kw.clear()  # the expired delayed trigger cannot retry next turn
        self.game.fire(self.b, "end_step")
        self.game.settle()
        self.assertIn(target, self.a.battlefield)

    def test_real_turn_keeps_protected_hob_token_and_cleans_up_keyword(self):
        protected = []
        blocker = self.game.enter_battlefield(self.b, dataclasses.replace(BEAR, power=3, toughness=3))
        def choose_blocks(game, me, opp, attackers):
            return {next(x for x in attackers if x.front.is_token): [blocker]}
        def after_blocks(game, me, attackers, blocks):
            target = next(x for x in attackers if x.front.is_token)
            protected.append(target)
            self.assertTrue(game.activate_ability(me, self.src, 0, [target]))
        with patch.object(self.a.ai, "main_phase"), \
                patch.object(self.a.ai, "choose_attackers", side_effect=lambda game, me, opp: me.creatures), \
                patch.object(self.b.ai, "choose_blocks", side_effect=choose_blocks), \
                patch.object(self.a.ai, "after_blocks", side_effect=after_blocks):
            self.game.take_turn(self.a)
        self.assertEqual(len(protected), 1)
        self.assertIn(protected[0], self.a.battlefield)
        self.assertFalse(protected[0].has("indestructible"))
        self.assertEqual(protected[0].damage, 0)
        self.assertEqual(self.game.delayed, [])


if __name__ == "__main__":
    unittest.main()
