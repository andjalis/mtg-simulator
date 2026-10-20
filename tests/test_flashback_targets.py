"""Granted flashback: graveyard targets chosen on cast/activation, rechecked on resolution, exact copies."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import ISLAND, MOUNTAIN, card

GRANT = "Target instant or sorcery card in your graveyard gains flashback until end of turn. " \
        "The flashback cost is equal to its mana cost."
REPLAY = card("Test Replay", "{R}", "Instant", GRANT)
MAGE = card("Test Replay Mage", "{R}", "Creature — Wizard", "When this creature enters, " + GRANT, 1, 1)
LICH = card("Test Replay Lich", "{R}", "Creature — Zombie", "{T}: " + GRANT, 1, 1)
WALKER = card("Test Replay Walker", "{R}", "Legendary Planeswalker — Test", "+1: " + GRANT)
WALKER.loyalty = 3
CHOICE = card("Test Replay Choice", "{R}", "Sorcery", "Choose one —\n• Draw a card.\n• " + GRANT)
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
BLAST = card("Test Blast", "{2}{R}", "Sorcery", "Test Blast deals 5 damage to any target.")
REDO = card("Test Redo", "{R}", "Instant", "Test Redo deals 1 damage to any target.\nFlashback {4}{R}")
BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
GRAVE_EXILE = card("Test Grave Robber", "{0}", "Instant", "Exile target card from an opponent's graveyard.")
NEGATE = card("Test Denial", "{0}", "Instant", "Counter target spell.")
TEAM = card("Test Replay Team", "{R}", "Instant", "Teamwork 2 (As an additional cost to cast this spell, you may tap "
            "any number of creatures you control with total power 2 or more.)\nChoose one. If this spell was cast "
            "using teamwork, choose both instead.\n• Draw a card.\n• " + GRANT)
OGRE = card("Test Ogre", "{1}{R}", "Creature — Ogre", "", 2, 2)
DORK = card("Test Dork", "{G}", "Creature — Elf", "{T}: Add {R}.", 2, 2)
SHOT = card("Test Replay Shot", "{R}", "Instant", "Test Replay Shot deals 2 damage to any target. " + GRANT)
MIXED = card("Test Replay Draw", "{R}", "Instant", GRANT + " Draw a card.")
DISCARDER = card("Test Replay Discarder", "{R}", "Creature — Human", "Discard a card: " + GRANT, 1, 1)
UNSPELL = card("Test Unspell", "{0}", "Instant", "Return target spell you don't control to its owner's hand.")


def card_of(t):
    return getattr(t, "card", t)


class FlashbackTargets(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 20, HeuristicAI())
        self.b = Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for pl in (self.a, self.b):
            pl.library = [ISLAND] * 20
        self.seen = []

    def lands(self, n=1):
        for _ in range(n):
            self.a.battlefield.append(Permanent(MOUNTAIN, self.a))

    def options(self, c):
        return [o for o in self.game.spell_options(self.a) if o.name.startswith(c.name + " (")]

    @staticmethod
    def bolts(zone):
        return [c for c in zone if c is BOLT]

    def respond_once(self, response=None, when=None):
        """b answers the first stack item matching ``when`` with ``response(item)`` (an action or None)."""
        def respond(game, me):
            if game.stack and not self.seen and (when is None or when(game.stack[-1])):
                item = game.stack[-1]
                self.seen.append((item, list(item.targets)))
                return response(item) if response else None
            return None
        self.b.ai.respond = respond

    def exile_response(self, item):
        self.b.hand.append(GRAVE_EXILE)
        return GRAVE_EXILE, []

    # ---------------------------------------------------------------- cast time
    def test_templates_target_the_graveyard(self):
        for c in (REPLAY, MAGE, LICH, WALKER, CHOICE):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(REPLAY.spell_effects[0].target, "graveyard_spell")

    def test_target_is_chosen_and_stored_when_cast(self):
        self.a.graveyard.extend([BOLT, BLAST])
        self.lands()
        self.a.hand = [REPLAY]
        self.respond_once(when=lambda item: item.card is REPLAY)
        self.assertTrue(self.game.cast(self.a, REPLAY, [BOLT]))
        item, targets = self.seen[0]
        self.assertIs(card_of(targets[0]), BOLT)       # on the stack before resolution, not picked later
        self.assertEqual(len(self.options(BOLT)), 1)
        self.assertEqual(self.options(BLAST), [])      # the old resolution-time pick took the highest mana value

    def test_no_legal_target_means_no_cast_and_no_payment(self):
        self.a.graveyard.extend([BEAR, ISLAND])
        self.lands()
        self.a.hand = [REPLAY]
        self.assertFalse(self.game.can_cast_now(self.a, REPLAY))
        self.assertFalse(self.game.cast(self.a, REPLAY))
        self.assertEqual(self.a.hand, [REPLAY])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))
        self.assertEqual(self.a.granted_fb, [])

    def test_explicit_illegal_target_is_rejected_before_costs(self):
        self.a.graveyard.append(BEAR)
        self.lands()
        self.a.hand = [REPLAY]
        self.assertFalse(self.game.cast(self.a, REPLAY, [BEAR]))
        self.assertFalse(self.game.cast(self.a, REPLAY, [BOLT]))   # not in the graveyard at all
        self.assertEqual(self.a.hand, [REPLAY])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_opponents_graveyard_is_not_a_legal_target(self):
        self.b.graveyard.append(BOLT)
        self.lands()
        self.a.hand = [REPLAY]
        self.assertFalse(self.game.cast(self.a, REPLAY))
        self.assertEqual(self.game.legal_targets(self.a, REPLAY.spell_effects[0]), [])

    def test_trigger_targets_when_put_on_the_stack(self):
        self.a.graveyard.append(BOLT)
        self.respond_once(when=lambda item: not item.is_spell)
        self.game.enter_battlefield(self.a, MAGE)
        self.game.settle()
        self.assertTrue(self.seen)
        self.assertIs(card_of(self.seen[0][1][0]), BOLT)
        self.assertEqual(len(self.options(BOLT)), 1)

    def test_trigger_without_a_target_is_skipped(self):
        self.a.graveyard.append(BEAR)
        self.respond_once(when=lambda item: not item.is_spell)
        self.game.enter_battlefield(self.a, MAGE)
        self.game.settle()
        self.assertEqual(self.seen, [])
        self.assertFalse(any("fizzles" in line for line in self.game.events))
        self.assertEqual(self.a.granted_fb, [])

    def test_activated_ability_needs_a_target_before_tapping(self):
        lich = Permanent(LICH, self.a)
        lich.sick = False
        self.a.battlefield.append(lich)
        self.assertFalse(self.game.activate_ability(self.a, lich, 0))
        self.assertFalse(lich.tapped)
        self.a.graveyard.extend([BOLT, BLAST])
        self.respond_once(when=lambda item: not item.is_spell)
        self.assertTrue(self.game.activate_ability(self.a, lich, 0, [BOLT]))
        self.assertTrue(lich.tapped)
        self.assertIs(card_of(self.seen[0][1][0]), BOLT)
        self.assertEqual((len(self.options(BOLT)), self.options(BLAST)), (1, []))

    def test_loyalty_ability_needs_a_target_before_loyalty_changes(self):
        pw = self.game.enter_battlefield(self.a, WALKER)
        before = pw.loyalty
        self.assertFalse(self.game.activate_loyalty(self.a, pw, 0))
        self.assertEqual((pw.loyalty, pw.loyalty_used), (before, False))
        self.a.graveyard.append(BOLT)
        self.assertTrue(self.game.activate_loyalty(self.a, pw, 0))
        self.assertEqual(pw.loyalty, before + 1)
        self.assertEqual(len(self.options(BOLT)), 1)

    def test_modal_grant_mode_targets_on_cast(self):
        self.a.graveyard.append(BOLT)
        self.lands()
        self.a.hand = [CHOICE]
        self.respond_once(when=lambda item: item.card is CHOICE)
        self.a.ai.choose_modes = lambda game, me, modes, n, up_to: [
            i for i, m in enumerate(modes) if any(e.kind == "grant_flashback" for e in m)][:n]
        self.assertTrue(self.game.cast(self.a, CHOICE))
        item, targets = self.seen[0]
        grant = [t for e, t in zip(item.effects, targets) if e.kind == "grant_flashback"]
        self.assertEqual([card_of(t) for t in grant], [BOLT])
        self.assertEqual(len(self.options(BOLT)), 1)

    def test_modal_without_a_graveyard_target_picks_another_mode(self):
        self.a.graveyard.append(BEAR)
        self.lands()
        self.a.hand = [CHOICE]
        self.assertTrue(self.game.cast(self.a, CHOICE))
        self.assertEqual(len(self.a.hand), 1)                       # drew instead
        self.assertEqual(self.a.granted_fb, [])

    def test_modal_grant_mode_without_a_target_is_rejected_before_costs(self):
        self.a.graveyard.append(BEAR)
        self.lands()
        crew = Permanent(OGRE, self.a)                              # sick: free to tap for teamwork
        self.a.battlefield.append(crew)
        self.a.hand = [TEAM]
        self.a.ai.choose_modes = lambda game, me, modes, n, up_to: [
            i for i, m in enumerate(modes) if any(e.kind == "grant_flashback" for e in m)][:n]
        self.assertFalse(self.game.cast(self.a, TEAM))
        self.assertEqual(self.a.hand, [TEAM])
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_teamwork_grant_mode_targets_before_tapping(self):
        self.assertEqual((TEAM.teamwork, TEAM.unsupported), (2, []))
        self.a.graveyard.append(BOLT)
        self.lands()
        crew = Permanent(OGRE, self.a)
        self.a.battlefield.append(crew)
        self.a.hand = [TEAM]
        self.respond_once(when=lambda item: item.card is TEAM)
        self.assertTrue(self.game.cast(self.a, TEAM))
        item, targets = self.seen[0]
        self.assertEqual(sorted(e.kind for e in item.effects), ["draw", "grant_flashback"])
        self.assertTrue(crew.tapped)
        self.assertEqual((len(self.a.hand), len(self.options(BOLT))), (1, 1))

    def test_teamwork_is_skipped_when_the_crew_is_the_mana(self):
        self.a.graveyard.append(BOLT)
        self.game.step = "main2"                                    # untapped non-sick creatures may crew
        dork = Permanent(DORK, self.a)
        dork.sick = False
        self.a.battlefield.append(dork)
        self.a.hand = [TEAM]
        self.respond_once(when=lambda item: item.card is TEAM)
        self.assertTrue(self.game.cast(self.a, TEAM))
        item, _ = self.seen[0]
        self.assertEqual(len(item.effects), 1)                      # one mode: the dork paid the mana
        self.assertTrue(dork.tapped)

    # ------------------------------------------------------- recheck on resolution
    def test_target_leaving_in_response_fizzles_without_retargeting(self):
        self.a.graveyard.extend([BOLT, BLAST])
        self.lands()
        self.a.hand = [REPLAY]
        self.respond_once(self.exile_response, when=lambda item: item.card is REPLAY)
        self.assertTrue(self.game.cast(self.a, REPLAY, [BLAST]))    # the exile takes the highest mana value
        self.assertNotIn(BLAST, self.a.graveyard)
        self.assertIn(BOLT, self.a.graveyard)
        self.assertEqual(self.a.granted_fb, [])
        self.assertEqual(self.options(BOLT), [])                    # no new target picked on resolution

    def test_abilities_lose_their_target_in_response_but_costs_stay_paid(self):
        for kind in ("tap", "loyalty"):
            with self.subTest(kind=kind):
                self.setUp()
                self.a.graveyard.extend([BOLT, BLAST])
                self.respond_once(self.exile_response, when=lambda item: not item.is_spell)
                if kind == "tap":
                    src = Permanent(LICH, self.a)
                    src.sick = False
                    self.a.battlefield.append(src)
                    self.assertTrue(self.game.activate_ability(self.a, src, 0, [BLAST]))
                    self.assertTrue(src.tapped)
                else:
                    src = self.game.enter_battlefield(self.a, WALKER)
                    before = src.loyalty
                    self.assertTrue(self.game.activate_loyalty(self.a, src, 0, [BLAST]))
                    self.assertEqual((src.loyalty, src.loyalty_used), (before + 1, True))
                self.assertTrue(self.seen)
                self.assertEqual(self.a.granted_fb, [])
                self.assertEqual(self.options(BOLT), [])                # no retarget to the remaining Bolt

    def test_trigger_resolves_after_its_source_leaves(self):
        self.a.graveyard.append(BOLT)

        def remove_source(item):
            self.game.leave_battlefield(item.source, "exile")
            return None
        self.respond_once(remove_source, when=lambda item: not item.is_spell)
        self.game.enter_battlefield(self.a, MAGE)
        self.game.settle()
        self.assertTrue(self.seen)
        self.assertFalse(any(x.card is MAGE for x in self.a.battlefield))
        self.assertEqual(len(self.options(BOLT)), 1)

    def test_lost_graveyard_target_does_not_stop_the_other_target(self):
        self.a.graveyard.append(BLAST)
        self.lands()
        self.a.hand = [SHOT]
        self.respond_once(self.exile_response, when=lambda item: item.card is SHOT)
        self.assertTrue(self.game.cast(self.a, SHOT, [self.b, BLAST]))
        self.assertEqual(self.b.life, 18)                           # the damage still resolves
        self.assertEqual((self.a.granted_fb, self.options(BLAST)), ([], []))

    def test_untouched_target_survives_a_response(self):
        self.a.graveyard.extend([BOLT, BLAST])
        self.lands()
        self.a.hand = [REPLAY]
        self.respond_once(self.exile_response, when=lambda item: item.card is REPLAY)
        self.assertTrue(self.game.cast(self.a, REPLAY, [BOLT]))
        self.assertEqual(len(self.options(BOLT)), 1)

    def test_same_name_copy_entering_is_a_new_object(self):
        self.a.graveyard.append(BOLT)
        self.lands()
        self.a.hand = [REPLAY]

        def swap(item):    # the targeted Bolt leaves and the same CardDef comes back as a new card
            self.exile_response(item)
            return GRAVE_EXILE, []
        self.respond_once(swap, when=lambda item: item.card is REPLAY)
        orig = self.game.resolve_top

        def resolve_top():
            if self.game.stack and self.game.stack[-1].card is GRAVE_EXILE:
                orig()
                self.a.graveyard.append(BOLT)
                return
            orig()
        self.game.resolve_top = resolve_top
        self.assertTrue(self.game.cast(self.a, REPLAY, [BOLT]))
        self.assertEqual(self.bolts(self.a.graveyard), [BOLT])
        self.assertEqual(self.options(BOLT), [])

    def test_duplicate_copies_track_the_exact_targeted_slot(self):
        effect = REPLAY.spell_effects[0]
        for slot, survives in ((0, False), (1, True)):
            with self.subTest(slot=slot):
                self.setUp()
                self.a.graveyard.extend([BOLT, BOLT])              # the same shared CardDef twice
                self.lands()
                self.a.hand = [REPLAY]
                target = self.game.legal_targets(self.a, effect)[slot]
                self.assertIs(target.card, BOLT)
                self.respond_once(self.exile_response, when=lambda item: item.card is REPLAY)
                self.assertTrue(self.game.cast(self.a, REPLAY, [target]))   # the exile removes the first copy
                self.assertEqual(self.bolts(self.a.graveyard), [BOLT])
                self.assertEqual(len(self.options(BOLT)), int(survives))

    def test_granted_copy_is_the_one_that_leaves(self):
        effect = REPLAY.spell_effects[0]
        self.a.graveyard.extend([BOLT, BOLT])
        self.lands(2)
        self.a.hand = [REPLAY]
        second = self.game.legal_targets(self.a, effect)[1]
        self.assertTrue(self.game.cast(self.a, REPLAY, [second]))
        option = self.options(BOLT)[0]
        self.assertTrue(self.game.cast(self.a, option, [self.b]))
        self.assertEqual((self.b.life, self.bolts(self.a.graveyard), list(self.a.exile)), (17, [BOLT], [BOLT]))
        remaining = [t for t in self.game.legal_targets(self.a, effect) if t.card is BOLT]
        self.assertEqual(len(remaining), 1)
        self.assertIsNot(remaining[0].entry, second.entry)
        self.assertEqual(self.options(BOLT), [])                  # the untouched copy never had flashback

    def test_grant_ends_when_the_card_leaves_and_returns(self):
        self.a.graveyard.append(BOLT)
        self.lands()
        self.a.hand = [REPLAY]
        self.assertTrue(self.game.cast(self.a, REPLAY))
        self.assertEqual(len(self.options(BOLT)), 1)
        self.a.graveyard.remove(BOLT)
        self.a.graveyard.append(BOLT)
        self.assertEqual(self.options(BOLT), [])

    def test_mixed_spell_with_its_only_target_gone_does_nothing(self):
        self.a.graveyard.append(BOLT)
        self.lands()
        self.a.hand = [MIXED]
        self.respond_once(self.exile_response, when=lambda item: item.card is MIXED)
        self.assertTrue(self.game.cast(self.a, MIXED))
        self.assertEqual(self.a.hand, [])                          # no draw: every target was illegal
        self.assertTrue(any("fizzles" in line for line in self.game.events))

    def test_discard_cost_card_cannot_be_the_target(self):
        perm = Permanent(DISCARDER, self.a)
        perm.sick = False
        self.a.battlefield.append(perm)
        self.a.hand = [BOLT]
        self.assertFalse(self.game.activate_ability(self.a, perm, 0))    # targets come before the discard
        self.assertEqual((self.a.hand, list(self.a.graveyard)), ([BOLT], []))
        self.a.graveyard.append(BLAST)
        self.respond_once(when=lambda item: not item.is_spell)
        self.assertTrue(self.game.activate_ability(self.a, perm, 0))
        self.assertIs(card_of(self.seen[0][1][0]), BLAST)
        self.assertEqual((len(self.options(BLAST)), self.options(BOLT)), (1, []))

    def test_every_graveyard_mutation_ends_the_grant(self):
        def pop(gy): gy.pop(0)
        def delete(gy): del gy[0]
        def delete_slice(gy): del gy[:]
        def clear(gy): gy.clear()
        def setitem(gy): gy[0] = BOLT
        def set_slice(gy): gy[:] = [BOLT]
        def remove_add(gy): gy.remove(BOLT); gy.append(BOLT)
        def remove_iadd(gy): gy.remove(BOLT); gy += [BOLT]
        def remove_extend(gy): gy.remove(BOLT); gy.extend([BOLT])
        def remove_insert(gy): gy.remove(BOLT); gy.insert(0, BOLT)
        def reassign(gy): self.a.graveyard = [BOLT]
        for change in (pop, delete, delete_slice, clear, setitem, set_slice, remove_add, remove_iadd,
                       remove_extend, remove_insert, reassign):
            with self.subTest(change=change.__name__):
                self.setUp()
                self.a.graveyard.append(BOLT)
                self.lands()
                self.a.hand = [REPLAY]
                self.assertTrue(self.game.cast(self.a, REPLAY))
                stale = self.options(BOLT)
                self.assertEqual(len(stale), 1)
                change(self.a.graveyard)
                self.assertEqual(self.options(BOLT), [])
                self.lands()
                self.assertFalse(self.game.cast(self.a, stale[0], [self.b]))   # the old option can't be reused
                self.assertEqual(self.b.life, 20)

    def granted_replay(self, copies):
        self.a.graveyard.extend([REPLAY] * copies)
        self.game.enter_battlefield(self.a, MAGE)
        self.game.settle()
        self.assertEqual(len(self.a.granted_fb), 1)
        self.lands()
        return self.options(REPLAY)[0]

    def test_flashback_grant_spell_cannot_target_its_own_entry(self):
        option = self.granted_replay(1)
        self.assertFalse(self.game.can_cast_now(self.a, option))
        self.assertFalse(self.game.cast(self.a, option))
        self.assertEqual((list(self.a.graveyard), list(self.a.exile)), ([REPLAY], []))
        self.assertFalse(any(x.tapped for x in self.a.battlefield))

    def test_flashback_grant_spell_targets_a_same_name_copy(self):
        option = self.granted_replay(2)
        own = self.a.granted_fb[0]
        self.assertFalse(self.game.cast(self.a, option, [own]))      # explicit own entry is rejected unpaid
        self.assertFalse(any(x.tapped for x in self.a.battlefield))
        self.respond_once(when=lambda item: item.card is option)
        self.assertTrue(self.game.cast(self.a, option))
        bound = self.seen[0][1][0]
        self.assertIs(bound.card, REPLAY)
        self.assertIsNot(bound.entry, own.entry)
        self.assertEqual((list(self.a.graveyard), list(self.a.exile)), ([REPLAY], [REPLAY]))
        self.assertEqual(len(self.options(REPLAY)), 1)                 # the other copy now has flashback

    def test_reordering_keeps_the_grant_on_its_card(self):
        for change in (lambda gy: gy.reverse(), lambda gy: gy.sort(key=lambda c: -c.cmc)):
            with self.subTest():
                self.setUp()
                self.a.graveyard.extend([BOLT, BLAST])
                self.lands()
                self.a.hand = [REPLAY]
                self.assertTrue(self.game.cast(self.a, REPLAY, [BOLT]))
                change(self.a.graveyard)
                self.assertEqual((len(self.options(BOLT)), self.options(BLAST)), (1, []))

    def test_stale_option_after_cleanup(self):
        self.a.graveyard.append(BOLT)
        self.lands()
        self.a.hand = [REPLAY]
        self.assertTrue(self.game.cast(self.a, REPLAY))
        stale = self.options(BOLT)[0]
        with patch.object(self.a.ai, "main_phase"), patch.object(self.b.ai, "main_phase"):
            self.game.take_turn(self.b)
        self.game.step = "main1"
        self.game.active_idx = self.game.players.index(self.a)
        self.lands()
        self.assertFalse(self.game.can_cast_now(self.a, stale))
        self.assertFalse(self.game.cast(self.a, stale, [self.b]))
        self.assertIn(BOLT, self.a.graveyard)

    # ------------------------------------------------------------ cost and cleanup
    def test_granted_cost_is_the_mana_cost_and_native_flashback_stays(self):
        self.a.graveyard.append(REDO)
        self.lands()
        self.a.hand = [REPLAY]
        self.assertTrue(self.game.cast(self.a, REPLAY))
        costs = sorted(sorted(o.mana_cost.items()) for o in self.options(REDO))
        self.assertEqual(costs, sorted([sorted(REDO.mana_cost.items()),
                                        sorted({"generic": 4, "R": 1}.items())]))
        native = next(o for o in self.options(REDO) if o.mana_cost.get("generic"))
        self.lands(2)
        self.assertFalse(self.game.cast(self.a, native, [self.b]))      # {4}{R} is not the granted {R}
        self.assertIn(REDO, self.a.graveyard)

    def test_failed_payment_keeps_the_card_and_the_grant(self):
        self.a.graveyard.append(BLAST)
        self.lands()
        self.a.hand = [REPLAY]
        self.assertTrue(self.game.cast(self.a, REPLAY))
        option = self.options(BLAST)[0]
        self.lands(2)                                   # one short of {2}{R}
        self.assertFalse(self.game.cast(self.a, option, [self.b]))
        self.assertIn(BLAST, self.a.graveyard)
        self.assertEqual(len(self.options(BLAST)), 1)
        self.lands()
        self.assertTrue(self.game.cast(self.a, self.options(BLAST)[0], [self.b]))
        self.assertEqual((self.b.life, list(self.a.exile)), (15, [BLAST]))

    def test_granted_spell_is_exiled_when_countered_or_bounced(self):
        for answer in (NEGATE, UNSPELL):
            with self.subTest(answer=answer.name):
                self.setUp()
                self.a.graveyard.append(BOLT)
                self.lands(2)
                self.a.hand = [REPLAY]
                self.assertTrue(self.game.cast(self.a, REPLAY))
                self.b.hand.append(answer)
                self.respond_once(lambda item: (answer, [item]),
                                  when=lambda item: item.card is not None and item.card.name.startswith("Test Bolt"))
                self.assertTrue(self.game.cast(self.a, self.options(BOLT)[0], [self.b]))
                self.assertTrue(self.seen)
                self.assertEqual(self.b.life, 20)
                self.assertEqual((self.bolts(self.a.graveyard), list(self.a.hand), list(self.a.exile)), ([], [], [BOLT]))

    def test_grant_expires_at_cleanup(self):
        self.a.graveyard.append(BOLT)
        self.lands()
        self.a.hand = [REPLAY]
        self.assertTrue(self.game.cast(self.a, REPLAY))
        self.assertEqual(len(self.a.granted_fb), 1)
        with patch.object(self.a.ai, "main_phase"), patch.object(self.b.ai, "main_phase"):
            self.game.take_turn(self.b)
        self.assertEqual(self.a.granted_fb, [])
        self.assertEqual(self.options(BOLT), [])


if __name__ == "__main__":
    unittest.main()
