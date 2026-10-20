"""Aura spells target their host: legal hosts, cast-time choice, responses and fizzles (mtgsim.auras + engine).

Card text is written out so no card DB is needed."""
import dataclasses
import random
import unittest

from mtgsim import auras, copies
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_auras import BLADE, BOOST, PACIFY
from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, SHOCK, card

HEXBEAR = card("Hexproof Bear", "{1}{G}", "Creature — Bear", "Hexproof", 2, 2)
WARDBEAR = card("Warded Bear", "{1}{G}", "Creature — Bear", "Ward {2}", 4, 4)
ROBOT = card("Test Robot", "{2}", "Artifact Creature — Robot", "", 1, 1)
ROCK = card("Test Rock", "{2}", "Artifact", "{T}: Add {C}.")
CIRCUIT = card("Test Circuit", "{R}", "Enchantment — Aura",
               "Enchant artifact creature\nEnchanted creature gets +1/+1.")
GIFT = card("Test Gift", "{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1.")
UNSUMMON = card("Test Unsummon", "{U}", "Instant", "Return target creature to its owner's hand.")
ROYAL = card("Test Royal", "{R}", "Sorcery", "Create a Royal Role token attached to target creature you control.")


class AnswerTheAura(HeuristicAI):
    """Opponent AI that answers an Aura spell by casting its held instant at the Aura's target."""

    def __init__(self, answer):
        super().__init__()
        self.answer = answer
        self.answered = []

    def respond(self, game, me):
        top = game.stack[-1] if game.stack else None
        if (top is not None and top.is_spell and top.card is not None and top.card.aura and top.targets
                and self.answer in me.hand and game.can_cast_now(me, self.answer)):
            self.answered.append(top.targets[0])
            return self.answer, [top.targets[0]]
        return None


class AuraTargetingTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        self.lands = [self.perm(MOUNTAIN, self.a) for _ in range(4)]

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def hold(self, c, targets=None):
        """Cast c but keep it on the stack (as if inside a priority loop) so the test can respond."""
        self.a.hand.append(c)
        self.game._priority_depth += 1
        try:
            ok = self.game.cast(self.a, c, targets)
        finally:
            self.game._priority_depth -= 1
        return ok

    def resolve(self):
        self.game.resolve_top()
        self.game.state_based_actions()

    def untapped(self):
        return sum(not x.tapped for x in self.lands)

    # ------------------------------------------------------------------ legality (auras module)

    def test_artifact_creature_needs_both_types(self):
        robot, rock, bear = self.perm(ROBOT, self.a), self.perm(ROCK, self.a), self.perm(BEAR, self.a)
        self.assertTrue(auras.is_legal_host(self.game, self.a, CIRCUIT, robot))
        self.assertFalse(auras.is_legal_host(self.game, self.a, CIRCUIT, rock))
        self.assertFalse(auras.is_legal_host(self.game, self.a, CIRCUIT, bear))

    def test_hexproof_only_matters_when_targeting(self):
        theirs = self.perm(HEXBEAR, self.b)
        mine = self.perm(HEXBEAR, self.a)
        self.assertFalse(auras.is_legal_host(self.game, self.a, PACIFY, theirs))
        self.assertTrue(auras.is_legal_host(self.game, self.a, PACIFY, theirs, targeted=False))
        self.assertTrue(auras.is_legal_host(self.game, self.a, BOOST, mine))      # own hexproof creature

    def test_you_control_restriction_and_battlefield(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.assertTrue(auras.is_legal_host(self.game, self.a, BOOST, mine))
        self.assertFalse(auras.is_legal_host(self.game, self.a, BOOST, theirs))
        self.game.destroy(mine)
        self.assertFalse(auras.is_legal_host(self.game, self.a, BOOST, mine))

    def test_hosts_lists_both_sides_policy_picks_one(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(DRAGON3, self.b)
        self.assertEqual(set(auras.hosts(self.game, self.a, GIFT)), {mine, theirs})
        self.assertEqual(auras.wanted_hosts(self.game, self.a, GIFT), [mine])
        self.assertEqual(auras.wanted_hosts(self.game, self.a, PACIFY), [theirs])
        self.assertIs(auras.choose_host(self.game, self.a, PACIFY), theirs)

    # ------------------------------------------------------------------ casting

    def test_aura_spell_targets_its_host_on_the_stack(self):
        theirs = self.perm(DRAGON3, self.b)
        self.assertTrue(self.hold(PACIFY))
        self.assertEqual(self.game.stack[-1].targets, [theirs])
        self.resolve()
        self.assertEqual([a.card.name for a in theirs.auras], ["Test Pacify"])

    def test_explicit_host_is_used(self):
        self.perm(DRAGON3, self.a)
        weak = self.perm(BEAR, self.a)
        self.assertTrue(self.hold(BOOST, [weak]))
        self.resolve()
        self.assertEqual([a.card.name for a in weak.auras], ["Test Boost"])

    def test_unchosen_target_slot_uses_the_policy_host(self):
        best = self.perm(DRAGON3, self.a)
        self.perm(BEAR, self.a)
        self.assertTrue(self.hold(BOOST, [None]))
        self.assertEqual(self.game.stack[-1].targets, [best])

    def test_copy_of_an_aura_spell_targets_a_host_too(self):
        theirs = self.perm(DRAGON3, self.b)
        self.assertTrue(self.hold(PACIFY))
        copies.copy_spell(self.game, self.a, self.game.stack[-1])
        self.assertEqual(len(self.game.stack), 2)
        self.assertEqual(self.game.stack[-1].targets, [theirs])
        self.resolve()
        self.resolve()
        self.assertEqual([a.card.name for a in theirs.auras], ["Test Pacify", "Test Pacify"])
        self.assertTrue(any(a.card.is_token for a in theirs.auras))

    def test_copy_of_an_aura_spell_fails_if_its_host_is_gone(self):
        theirs = self.perm(DRAGON3, self.b)
        self.assertTrue(self.hold(PACIFY))
        copies.copy_spell(self.game, self.a, self.game.stack[-1])
        self.game.leave_battlefield(theirs, "hand")
        self.resolve()
        self.resolve()
        self.assertEqual(self.game.stack, [])
        self.assertFalse(any(x.card.aura for x in self.a.battlefield))
        self.assertEqual(self.a.graveyard.count(PACIFY), 1)      # the copy ceases to exist

    def test_illegal_explicit_host_is_rejected_before_paying(self):
        theirs = self.perm(BEAR, self.b)
        hexed = self.perm(HEXBEAR, self.b)
        self.perm(BEAR, self.a)
        for c, bad in ((BOOST, theirs), (PACIFY, hexed)):
            with self.subTest(card=c.name):
                self.assertFalse(self.hold(c, [bad]))
                self.assertIn(c, self.a.hand)
                self.assertEqual(self.untapped(), 4)
                self.assertEqual(self.game.stack, [])
                self.a.hand.remove(c)

    def test_hostile_aura_skips_hexproof_and_needs_an_opposing_target(self):
        self.perm(BEAR, self.a)
        self.perm(HEXBEAR, self.b)
        self.a.hand = [PACIFY]
        self.assertFalse(self.game.can_cast_now(self.a, PACIFY))     # only own creature + hexproof opponent
        theirs = self.perm(BEAR, self.b)
        self.assertTrue(self.game.can_cast_now(self.a, PACIFY))
        self.game.cast(self.a, PACIFY)
        self.assertEqual([a.card.name for a in theirs.auras], ["Test Pacify"])

    def test_ward_on_the_host_triggers(self):
        warded = self.perm(WARDBEAR, self.b)
        for x in self.lands[1:]:
            x.tapped = True                    # can pay {R} for Pacify but not ward {2}
        self.a.hand = [PACIFY]
        self.game.cast(self.a, PACIFY)
        self.assertEqual(warded.auras, [])
        self.assertIn(PACIFY, self.a.graveyard)

    # ------------------------------------------------------------------ responses and resolution

    def test_host_bounced_in_response_aura_fails_without_retargeting(self):
        self.perm(BEAR, self.b)
        big = self.perm(DRAGON3, self.b)
        self.assertTrue(self.hold(PACIFY))
        self.assertEqual(self.game.stack[-1].targets, [big])
        self.game.leave_battlefield(big, "hand")
        self.resolve()
        self.assertEqual(self.game.stack, [])
        self.assertIn(PACIFY, self.a.graveyard)
        self.assertFalse(any(x.auras for x in self.b.battlefield))
        self.assertFalse(any(x.card is PACIFY for x in self.a.battlefield))

    def test_host_destroyed_in_response_friendly_aura_fails(self):
        mine = self.perm(DRAGON3, self.a)
        other = self.perm(BEAR, self.a)
        self.assertTrue(self.hold(BOOST))
        self.game.destroy(mine)
        self.resolve()
        self.assertIn(BOOST, self.a.graveyard)
        self.assertEqual(other.auras, [])

    def test_host_gains_hexproof_in_response(self):
        theirs = self.perm(DRAGON3, self.b)
        self.assertTrue(self.hold(PACIFY))
        theirs.temp_kw.add("hexproof")
        self.resolve()
        self.assertEqual(theirs.auras, [])
        self.assertIn(PACIFY, self.a.graveyard)

    def test_host_changes_control_in_response_you_control_aura_fails(self):
        mine = self.perm(DRAGON3, self.a)
        self.assertTrue(self.hold(BOOST))
        self.a.battlefield.remove(mine)
        mine.controller = self.b
        self.b.battlefield.append(mine)
        self.resolve()
        self.assertEqual(mine.auras, [])
        self.assertIn(BOOST, self.a.graveyard)

    def test_host_leaves_and_returns_in_response_is_a_new_object(self):
        theirs = self.perm(DRAGON3, self.b)
        self.assertTrue(self.hold(PACIFY))
        self.game.leave_battlefield(theirs, "hand")
        self.b.hand.remove(DRAGON3)
        again = self.game.enter_battlefield(self.b, DRAGON3)
        self.resolve()
        self.assertEqual(again.auras, [])
        self.assertIn(PACIFY, self.a.graveyard)

    def test_host_stops_being_a_creature_in_response(self):
        theirs = self.perm(DRAGON3, self.b)
        self.assertTrue(self.hold(PACIFY))
        theirs.card = dataclasses.replace(DRAGON3, types=frozenset({"Artifact"}))   # e.g. a type-changing effect
        self.resolve()
        self.assertEqual(theirs.auras, [])
        self.assertIn(PACIFY, self.a.graveyard)

    # ------------------------------------------------------------------ end-to-end priority responses

    def opponent_answers(self, answer, land):
        self.b.ai = AnswerTheAura(answer)
        self.b.hand = [answer]
        self.perm(land, self.b)
        return self.b.ai

    def test_opponent_bounces_the_target_in_response(self):
        ai = self.opponent_answers(UNSUMMON, ISLAND)
        theirs = self.perm(DRAGON3, self.b)
        other = self.perm(BEAR, self.b)
        self.a.hand = [PACIFY]
        self.assertTrue(self.game.cast(self.a, PACIFY))      # outside a priority loop: b may respond
        self.assertEqual(ai.answered, [theirs])
        self.assertEqual(self.game.stack, [])
        self.assertIn(DRAGON3, self.b.hand)
        self.assertIn(UNSUMMON, self.b.graveyard)
        self.assertIn(PACIFY, self.a.graveyard)
        self.assertEqual(other.auras, [])                     # no retarget to the remaining creature
        self.assertFalse(any(x.card is PACIFY for x in self.a.battlefield))

    def test_opponent_kills_the_host_of_a_friendly_aura_in_response(self):
        ai = self.opponent_answers(SHOCK, MOUNTAIN)
        mine = self.perm(BEAR, self.a)
        self.a.hand = [BOOST]
        self.assertTrue(self.game.cast(self.a, BOOST))
        self.assertEqual(ai.answered, [mine])
        self.assertNotIn(mine, self.a.battlefield)
        self.assertEqual(sorted(c.name for c in self.a.graveyard), ["Grizzly Bears", "Test Boost"])
        self.assertFalse(any(x.card is BOOST for x in self.a.battlefield))

    # ------------------------------------------------------------------ attached Auras (not targeting)

    def test_attached_aura_stays_when_host_gains_hexproof(self):
        theirs = self.perm(DRAGON3, self.b)
        self.a.hand = [PACIFY]
        self.game.cast(self.a, PACIFY)
        theirs.temp_kw.add("hexproof")
        self.game.state_based_actions()
        self.assertEqual([a.card.name for a in theirs.auras], ["Test Pacify"])

    def test_attached_aura_falls_off_when_host_becomes_illegal(self):
        mine = self.perm(DRAGON3, self.a)
        self.a.hand = [BOOST]
        self.game.cast(self.a, BOOST)
        self.assertEqual(len(mine.auras), 1)
        self.a.battlefield.remove(mine)               # stolen: no longer "creature you control"
        mine.controller = self.b
        self.b.battlefield.append(mine)
        self.game.state_based_actions()
        self.assertEqual(mine.auras, [])
        self.assertIn(BOOST, self.a.graveyard)
        self.assertFalse(any(x.card is BOOST for x in self.a.battlefield))

    def test_host_leaving_cleans_up(self):
        theirs = self.perm(DRAGON3, self.b)
        self.a.hand = [PACIFY]
        self.game.cast(self.a, PACIFY)
        aura = next(x for x in self.a.battlefield if x.card is PACIFY)
        self.game.leave_battlefield(theirs, "hand")
        self.assertIsNone(aura.aura_host)
        self.assertNotIn(aura, self.a.battlefield)
        self.assertIn(PACIFY, self.a.graveyard)

    # ------------------------------------------------------------------ non-spell attachments still work

    def test_role_token_still_attaches(self):
        mine = self.perm(BEAR, self.a)
        self.a.hand = [ROYAL]
        self.game.cast(self.a, ROYAL, [mine])
        self.assertEqual([a.card.name for a in mine.auras], ["Royal Role"])

    def test_self_attaching_equipment_still_attaches(self):
        mine = self.perm(BEAR, self.a)
        self.a.hand = [BLADE]
        self.game.cast(self.a, BLADE)
        blade = next(x for x in self.a.battlefield if x.card is BLADE)
        self.assertIs(blade.attached_to, mine)


if __name__ == "__main__":
    unittest.main()
