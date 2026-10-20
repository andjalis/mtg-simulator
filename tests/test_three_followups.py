"""Object identity and event timing for manifest/attach and delayed end steps."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim import copies
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card
from tests.test_copies import KIKI


MACHETE = card("Test Manifest Equipment", "{R}", "Artifact — Equipment",
               "When this Equipment enters, manifest dread, then attach Test Manifest Equipment to that creature.\n"
               "Equipped creature gets +1/+1.\nEquip {2}")
MANIFEST = card("Test Manifest", "{R}", "Sorcery", "Manifest dread.")
BLINK_TEXT = ("Exile target creature. Return it to the battlefield under its owner's control "
              "at the beginning of the next end step.")
BLINK = card("Test Blink", "{R}", "Instant", BLINK_TEXT)
BLINKER = card("Test Blinker", "{R}", "Creature — Bird",
               "{R}: Exile another target creature you control. Return that card to the battlefield "
               "under its owner's control at the beginning of the next end step.", 1, 1)
FLY_BLINK = card("Test Flying Blink", "{R}", "Instant",
                 "Exile target creature you control without flying. Return it to the battlefield under its "
                 "owner's control with a flying counter on it at the beginning of the next end step.")
TOKENS_TEXT = ("Create two 1/1 red Warrior creature tokens. They gain haste until end of turn. "
               "Sacrifice them at the beginning of the next end step.")
TOKENS = card("Test Brief Tokens", "{R}", "Instant", TOKENS_TEXT)
MY_TOKENS = card("Test My Brief Tokens", "{R}", "Instant",
                 TOKENS_TEXT.replace("the next end step", "your next end step"))
QUOTED_COPY = card("Test Quoted Copy", "{R}", "Sorcery",
                   'Create a token that\'s a copy of target creature you control, except it has haste and '
                   '"At the beginning of the end step, sacrifice ~."')


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 30, HeuristicAI())
        self.b = Player("b", [ISLAND] * 30, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(2), log=True)
        self.game.turn = 1
        for p in (self.a, self.b):
            p.library = [ISLAND] * 30
        for _ in range(8):
            land = self.game.enter_battlefield(self.a, MOUNTAIN)
            land.tapped = False

    def cast(self, c, targets=None):
        self.a.hand.append(c)
        self.assertTrue(self.game.cast(self.a, c, targets))

    def end(self, p):
        self.game.active_idx = self.game.players.index(p)
        self.game.step = "end_step"
        self.game.fire(p, "end_step")
        self.game.settle()

    def copy_token(self):
        src = self.game.enter_battlefield(self.a, KIKI)
        self.game.enter_battlefield(self.a, DRAGON3)
        eff = KIKI.activated[0].effects[0]
        copies.resolve(self.game, self.a, eff, None, StackItem(self.a, [eff], [None], source=src))
        return src, next(x for x in self.a.creatures if x.card.is_token)

    def test_templates(self):
        for c in (MACHETE, MANIFEST, BLINK, BLINKER, FLY_BLINK, TOKENS, MY_TOKENS, QUOTED_COPY):
            self.assertEqual(c.unsupported, [], c.name)

    def test_manifest_attaches_exact_new_creature_with_two_cards(self):
        strong = self.game.enter_battlefield(self.a, DRAGON3)
        self.a.library = [DRAGON3, ISLAND]
        self.cast(MACHETE)
        eq = next(x for x in self.a.battlefield if x.card is MACHETE)
        host = eq.attached_to
        self.assertIsNot(host, strong)
        self.assertIs(host.front, ISLAND)
        self.assertEqual((host.power, host.toughness), (3, 3))
        self.assertIn(DRAGON3, self.a.graveyard)
        self.assertEqual(self.a.library, [])

    def test_manifest_one_card_and_empty_library(self):
        for library in ([], [BEAR]):
            with self.subTest(cards=len(library)):
                self.setUp()
                self.game.enter_battlefield(self.a, DRAGON3)
                self.a.library = list(library)
                self.cast(MACHETE)
                eq = next(x for x in self.a.battlefield if x.card is MACHETE)
                self.assertEqual(self.a.graveyard, [])
                if library:
                    self.assertIs(eq.attached_to.front, BEAR)
                else:
                    self.assertIsNone(eq.attached_to)

    def test_manifest_still_happens_when_equipment_source_left(self):
        self.a.library = [BEAR]
        eq = self.game.enter_battlefield(self.a, MACHETE)
        self.game.destroy(eq)
        self.game.settle()
        manifests = [x for x in self.a.creatures if x.face_down_kind == "manifest_dread"]
        self.assertEqual(len(manifests), 1)
        self.assertIsNone(eq.attached_to)

    def test_simple_manifest_keeps_simplified_two_two_and_front_card(self):
        self.a.library = [DRAGON3, BEAR]
        self.cast(MANIFEST)
        manifest = self.a.creatures[0]
        self.assertEqual((manifest.power, manifest.toughness), (2, 2))
        self.assertIs(manifest.front, BEAR)
        self.game.leave_battlefield(manifest, "hand")
        self.assertIn(BEAR, self.a.hand)

    def test_manifest_attachment_cleans_up_after_host_changes_controller(self):
        self.a.library = [BEAR]
        self.cast(MACHETE)
        eq = next(x for x in self.a.battlefield if x.card is MACHETE)
        host = eq.attached_to
        self.a.battlefield.remove(host)
        host.controller = self.b
        self.b.battlefield.append(host)
        self.game.leave_battlefield(host, "hand")
        self.assertIsNone(eq.attached_to)
        self.assertIn(BEAR, self.a.hand)

    def test_copy_sacrifices_at_either_players_next_end_step(self):
        for active in (0, 1):
            with self.subTest(active=active):
                self.setUp()
                self.game.active_idx = active
                _, token = self.copy_token()
                self.end(self.game.active)
                self.assertNotIn(token, self.a.battlefield)
                self.assertEqual(self.game.delayed, [])

    def test_creation_in_end_step_waits_for_next_event(self):
        self.end(self.a)
        _, token = self.copy_token()
        self.game.settle()
        self.assertIn(token, self.a.battlefield)
        self.end(self.b)
        self.assertNotIn(token, self.a.battlefield)

    def test_creation_by_end_step_trigger_waits_for_next_event(self):
        maker = card("Test End Maker", "{R}", "Enchantment",
                     "At the beginning of your end step, " + TOKENS_TEXT[0].lower() + TOKENS_TEXT[1:])
        self.assertEqual(maker.unsupported, [])
        self.game.enter_battlefield(self.a, maker)
        self.end(self.a)
        tokens = list(self.a.creatures)
        self.assertEqual(len(tokens), 2)
        self.end(self.b)
        self.assertTrue(all(t not in self.a.battlefield for t in tokens))

    def test_delayed_sacrifice_survives_source_departure_and_runs_once(self):
        src, token = self.copy_token()
        self.game.destroy(src)
        self.game.fire(self.b, "end_step")
        self.game.flush_triggers()
        self.assertEqual(len(self.game.stack), 1)
        self.assertEqual(self.game.delayed, [])
        self.game.resolve_top()
        self.assertNotIn(token, self.a.battlefield)
        self.end(self.a)
        self.assertEqual(self.game.stack, [])

    def test_delayed_sacrifice_does_not_follow_new_permanent(self):
        _, token = self.copy_token()
        self.game.leave_battlefield(token, "hand")
        new = self.game.enter_battlefield(self.a, token.card)
        self.end(self.b)
        self.assertIn(new, self.a.battlefield)

    def test_stolen_token_cannot_be_sacrificed_by_delayed_controller(self):
        _, token = self.copy_token()
        self.a.battlefield.remove(token)
        token.controller = self.b
        self.b.battlefield.append(token)
        self.end(self.b)
        self.assertIn(token, self.b.battlefield)
        self.assertEqual(self.game.delayed, [])
        self.b.battlefield.remove(token)
        token.controller = self.a
        self.a.battlefield.append(token)
        self.end(self.a)
        self.assertIn(token, self.a.battlefield)

    def test_token_continuations_bind_haste_and_sac_to_all_created_tokens(self):
        existing = self.game.enter_battlefield(self.a, BEAR)
        self.cast(TOKENS)
        tokens = [x for x in self.a.creatures if x is not existing]
        self.assertEqual(len(tokens), 2)
        self.assertTrue(all(x.has("haste") for x in tokens))
        self.assertFalse(existing.has("haste"))
        self.end(self.b)
        self.assertEqual(self.a.creatures, [existing])

    def test_your_next_end_step_skips_opponents_event(self):
        self.cast(MY_TOKENS)
        self.end(self.b)
        self.assertEqual(len(self.a.creatures), 2)
        self.end(self.a)
        self.assertEqual(self.a.creatures, [])

    def test_granted_end_step_ability_is_not_a_delayed_trigger(self):
        self.game.enter_battlefield(self.a, BEAR)
        self.cast(QUOTED_COPY)
        token = next(x for x in self.a.creatures if x.card.is_token)
        self.assertEqual(self.game.delayed, [])
        self.a.battlefield.remove(token)
        token.controller = self.b
        self.b.battlefield.append(token)
        self.end(self.a)
        self.assertNotIn(token, self.b.battlefield)

    def test_blink_returns_on_opponents_turn_as_new_object(self):
        target = self.game.enter_battlefield(self.a, BEAR)
        target.counters["+1/+1"] = 3
        self.game.active_idx = 1
        self.cast(BLINK, [target])
        self.assertNotIn(target, self.a.battlefield)
        self.assertEqual(len(self.a.exile), 1)
        self.end(self.b)
        returned = self.a.creatures[0]
        self.assertIsNot(returned, target)
        self.assertEqual(returned.counters, {})
        self.assertTrue(returned.sick)
        self.assertEqual(self.a.exile, [])
        self.end(self.a)
        self.assertEqual(self.a.creatures, [returned])

    def test_blink_during_end_step_waits_and_survives_source_departure(self):
        src = self.game.enter_battlefield(self.a, BLINKER)
        target = self.game.enter_battlefield(self.a, BEAR)
        self.end(self.a)
        self.assertTrue(self.game.activate_ability(self.a, src, 0, [target]))
        self.game.destroy(src)
        self.assertEqual(self.a.creatures, [])
        self.end(self.b)
        self.assertEqual([x.card.name for x in self.a.creatures], [BEAR.name])

    def test_blink_returns_stolen_creature_under_owner_control(self):
        target = self.game.enter_battlefield(self.b, BEAR)
        self.b.battlefield.remove(target)
        target.controller = self.a
        self.a.battlefield.append(target)
        self.cast(BLINK, [target])
        self.assertEqual(len(self.b.exile), 1)
        self.assertEqual(self.a.exile, [])
        self.end(self.a)
        self.assertEqual([x.card.name for x in self.b.creatures], [BEAR.name])
        self.assertEqual(self.a.creatures, [])

    def test_blink_return_does_not_find_equal_card_or_reexiled_object(self):
        for reexile in (False, True):
            with self.subTest(reexile=reexile):
                self.setUp()
                target = self.game.enter_battlefield(self.a, BEAR)
                self.a.exile.append(BEAR)  # identical definition already in exile
                self.cast(BLINK, [target])
                bound = self.game.delayed[0].context[1]
                self.a.exile.remove(bound)
                if reexile:
                    self.a.exile.append(bound)  # same Python card, a new zone object
                else:
                    self.a.hand.append(bound)
                self.end(self.b)
                self.assertEqual(self.a.creatures, [])
                self.assertIn(BEAR, self.a.exile)

    def test_exiled_token_does_not_return(self):
        target = self.game.enter_battlefield(self.a, dataclasses.replace(BEAR, is_token=True))
        self.cast(BLINK, [target])
        self.end(self.b)
        self.assertEqual(self.a.creatures, [])
        self.assertEqual(self.a.exile, [])

    def test_blink_rechecks_control_and_hexproof(self):
        for change in ("control", "hexproof"):
            with self.subTest(change=change):
                self.setUp()
                target = self.game.enter_battlefield(self.a, BEAR)
                self.game._priority_depth += 1
                c = FLY_BLINK if change == "control" else BLINK
                self.cast(c, [target])
                self.game._priority_depth -= 1
                self.a.battlefield.remove(target)
                target.controller = self.b
                self.b.battlefield.append(target)
                if change == "hexproof":
                    target.temp_kw.add("hexproof")
                self.game.resolve_top()
                self.assertIn(target, self.b.battlefield)
                self.assertEqual(self.game.delayed, [])

    def test_flying_counter_changes_future_legality(self):
        target = self.game.enter_battlefield(self.a, BEAR)
        self.cast(FLY_BLINK, [target])
        self.end(self.b)
        returned = self.a.creatures[0]
        self.assertTrue(returned.has("flying"))
        self.assertEqual(returned.counters.get("flying"), 1)
        self.assertNotIn(returned, self.game.legal_targets(self.a, FLY_BLINK.spell_effects[0]))

    def test_unrecognized_or_unbound_continuations_stay_visible(self):
        for text in (
            "Sacrifice it at the beginning of the next end step.",
            "Return it to the battlefield under its owner's control at the beginning of the next end step.",
            "Create a 1/1 red Warrior creature token. If you paid life this turn, draw a card. "
            "Sacrifice it at the beginning of the next end step.",
            BLINK_TEXT.replace("Return it", "If you do, return it"),
            TOKENS_TEXT.replace("Sacrifice them", "If you control a Bird, sacrifice them"),
        ):
            c = card("Test Unknown", "{R}", "Instant", text)
            self.assertTrue(c.unsupported, text)

    def test_actual_turn_end_executes_scheduler(self):
        # Exercise take_turn, not only synthetic fire() events.
        target = self.game.enter_battlefield(self.a, BEAR)
        self.cast(BLINK, [target])
        with patch.object(self.a.ai, "main_phase"), patch.object(self.b.ai, "main_phase"), \
                patch.object(self.b.ai, "choose_attackers", return_value=[]):
            self.game.take_turn(self.b)
        self.assertEqual([x.card.name for x in self.a.creatures], [BEAR.name])

    def test_optional_blink_does_not_save_opposing_creature_from_sweeper(self):
        sweep = card("Test Blink Sweeper", "{R}", "Sorcery",
                     "Exile up to one target artifact or creature. Return it to the battlefield under its "
                     "owner's control at the beginning of the next end step. "
                     "Test Blink Sweeper deals 4 damage to each creature.")
        target = self.game.enter_battlefield(self.b, BEAR)
        self.cast(sweep)
        self.assertNotIn(target, self.b.battlefield)
        self.assertIn(BEAR, self.b.graveyard)
        self.assertEqual(self.game.delayed, [])

    def test_blink_other_and_invalid_player_target_do_nothing(self):
        src = self.game.enter_battlefield(self.a, BLINKER)
        # "another target creature": with no other creature, activation is illegal (target legality is checked up front)
        self.assertFalse(self.game.activate_ability(self.a, src, 0, [src]))
        self.assertIn(src, self.a.battlefield)
        self.assertEqual(self.game.delayed, [])
        self.assertFalse(self.game.cast(self.a, BLINK, [self.a]))   # a player is not a legal creature target
        self.assertEqual(self.game.delayed, [])


class DatabaseFollowups(unittest.TestCase):
    def test_real_card_templates_and_remaining_limits(self):
        db = CardDB(offline=True)
        if db._all is None:
            self.skipTest("card DB absent")
        try:
            for name in ("Conductive Machete", "Cursed Windbreaker", "Killer's Mask", "Abuelo, Ancestral Echo",
                         "Explosive Getaway", "Skyskipper Duo", "Salvation Swan", "Harried Dronesmith",
                         "Molten Duplication", "Salt Road Skirmish", "War Effort"):
                self.assertEqual(db.get(name).unsupported, [], name)
            for name in ("Come Back Wrong", "Nine-Lives Familiar", "Parting Gust"):
                self.assertTrue(db.get(name).unsupported, name)
        finally:
            db._all.close()
