"""Real-card tests for alternative casting costs and object-bound keyword triggers."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB, ALL_CARDS
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player
from mtgsim import kw_altcast
from tests.test_templates import card


@unittest.skipUnless(ALL_CARDS.exists(), "build the card database")
class AlternativeCastingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        island = self.db.get("Island")
        self.a = Player("a", [island] * 40, HeuristicAI())
        self.b = Player("b", [island] * 40, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(19), log=True)
        self.a.library = [island] * 40
        self.b.library = [island] * 40
        self.g.turn = 3
        self.g.step = "main1"
        self.g.active_idx = 0

    def mana(self, name, n):
        return [self.g.enter_battlefield(self.a, self.db.get(name)) for _ in range(n)]

    def option(self, kind):
        return next(c for c in self.g.spell_options(self.a) if self.g._origin(c)[1] == kind)

    def upkeep(self):
        self.g.step = "upkeep"
        self.g.fire(self.a, "upkeep")
        self.g.settle()

    def end(self, p=None):
        self.g.step = "end_step"
        self.g.fire(p or self.a, "end_step")
        self.g.settle()

    def test_real_card_parsing(self):
        for name in ("Fiery Temper", "Dregscape Zombie", "Mogg War Marshal", "Gurmag Angler",
                     "Foundry Assembler", "Flame Jab", "Rift Bolt", "Durkwood Baloth", "Ancestral Vision",
                     "Vaultbreaker", "Sprout Swarm", "Avalanche Riders", "Mwonvuli Ooze", "Sustaining Spirit",
                     "Survival Cache"):
            with self.subTest(card=name):
                c = self.db.get(name)
                self.assertFalse(any(s.startswith(("Madness", "Unearth", "Echo", "Delve", "Improvise", "Retrace",
                                                  "Suspend", "Dash", "Buyback", "Rebound", "Cumulative upkeep"))
                                     for s in c.unsupported), c.unsupported)

    def test_madness_cast_on_discard_at_opponents_turn(self):
        temper = self.db.get("Fiery Temper")
        self.a.hand = [temper]
        self.mana("Mountain", 1)
        self.g.active_idx = 1
        self.g.discard_card(self.a, temper)
        self.assertIn(temper, self.a.exile)
        self.assertEqual(self.a.discarded_cards, [temper])
        self.g.settle()
        self.assertEqual(self.b.life, 17)
        self.assertIn(temper, self.a.graveyard)
        self.assertNotIn(temper, self.a.exile)

    def test_madness_unpayable_goes_to_graveyard(self):
        c = self.db.get("Reckless Wurm")
        self.a.hand = [c]
        self.g.discard_card(self.a, c)
        self.g.settle()
        self.assertIn(c, self.a.graveyard)
        self.assertNotIn(c, self.a.exile)

    def test_madness_free_creature(self):
        c = self.db.get("Basking Rootwalla")
        self.a.hand = [c]
        self.g.discard_card(self.a, c)
        self.g.settle()
        self.assertTrue(any(x.card.name == c.name for x in self.a.battlefield))

    def test_madness_cannot_use_stale_exile_permission(self):
        c = self.db.get("Basking Rootwalla")
        self.a.hand = [c]
        self.g.discard_card(self.a, c)
        self.a.exile.remove(c)
        self.a.exile.append(c)
        self.g.settle()
        self.assertIn(c, self.a.exile)
        self.assertFalse(self.a.creatures)

    def test_unearth_haste_and_next_end_step(self):
        c = self.db.get("Dregscape Zombie")
        self.a.graveyard.append(c)
        self.mana("Swamp", 1)
        opt = self.option("unearth")
        self.assertTrue(opt.is_ability)
        self.assertTrue(self.g.can_cast_now(self.a, opt))
        self.assertTrue(self.g.cast(self.a, opt))
        perm = self.a.creatures[0]
        self.assertTrue(perm.has("haste"))
        self.assertFalse(perm.was_cast)
        self.end(self.b)
        self.assertIn(c, self.a.exile)
        self.assertNotIn(perm, self.a.battlefield)

    def test_unearth_replaces_bounce_and_death(self):
        for destination in ("hand", "graveyard"):
            with self.subTest(destination=destination):
                c = self.db.get("Dregscape Zombie")
                perm = self.g.enter_battlefield(self.a, c)
                kw_altcast.entered(self.g, perm, "unearth")
                if destination == "graveyard":
                    self.g.dies(perm)
                    self.assertFalse(self.g.creature_died_turn)
                else:
                    self.g.leave_battlefield(perm, destination)
                self.assertIn(c, self.a.exile)
                self.assertNotIn(c, self.a.hand)
                self.assertNotIn(c, self.a.graveyard)

    def test_unearth_is_exact_graveyard_ability_and_sorcery_speed(self):
        c = self.db.get("Dregscape Zombie")
        self.a.graveyard.append(c)
        self.mana("Swamp", 1)
        opt = self.option("unearth")
        self.g.active_idx = 1
        self.assertFalse(self.g.can_cast_now(self.a, opt))
        self.g.active_idx = 0
        self.g._priority_depth = 1
        self.assertTrue(self.g.cast(self.a, opt))
        self.assertIn(c, self.a.graveyard)
        self.a.graveyard.remove(c)
        self.a.graveyard.append(c)
        self.g.resolve_top()
        self.assertFalse(self.a.creatures)

    def test_echo_paid_once(self):
        c = self.db.get("Mogg War Marshal")
        perm = self.g.enter_battlefield(self.a, c)
        lands = self.mana("Mountain", 2)
        self.upkeep()
        self.assertIn(perm, self.a.battlefield)
        self.assertTrue(all(x.tapped for x in lands))
        self.upkeep()
        self.assertIn(perm, self.a.battlefield)

    def test_echo_unpaid_sacrifices_and_triggers_dies(self):
        c = self.db.get("Mogg War Marshal")
        perm = self.g.enter_battlefield(self.a, c)
        self.g.settle()
        self.assertEqual(len(self.a.creatures), 2)
        self.upkeep()
        self.assertNotIn(perm, self.a.battlefield)
        self.assertEqual(len(self.a.creatures), 2)
        self.assertIn(c, self.a.graveyard)

    def test_buyback_returns_only_on_success(self):
        c = self.db.get("Whispers of the Muse")
        self.a.hand = [c]
        self.mana("Island", 6)
        self.assertTrue(self.g.cast(self.a, self.option("buyback")))
        self.assertIn(c, self.a.hand)
        self.assertNotIn(c, self.a.graveyard)

    def test_buyback_countered_does_not_return(self):
        c = self.db.get("Whispers of the Muse")
        self.a.hand = [c]
        self.mana("Island", 6)
        self.g._priority_depth = 1
        self.assertTrue(self.g.cast(self.a, self.option("buyback")))
        self.g.counter(self.b, Effect("counter"), self.g.stack[-1])
        self.assertNotIn(c, self.a.hand)
        self.assertIn(c, self.a.graveyard)

    def test_buyback_illegal_target_does_not_return(self):
        c = self.db.get("Elvish Fury")
        bear = self.g.enter_battlefield(self.a, self.db.get("Grizzly Bears"))
        self.a.hand = [c]
        self.mana("Forest", 5)
        self.g._priority_depth = 1
        self.assertTrue(self.g.cast(self.a, self.option("buyback"), [bear]))
        self.g.leave_battlefield(bear, "exile")
        self.g.resolve_top()
        self.assertIn(c, self.a.graveyard)
        self.assertNotIn(c, self.a.hand)

    def test_dash_returns_next_end_step_and_does_not_track_reentry(self):
        c = self.db.get("Mardu Scout")
        self.a.hand = [c]
        self.mana("Mountain", 2)
        self.assertTrue(self.g.cast(self.a, self.option("dash")))
        perm = self.a.creatures[0]
        self.assertTrue(perm.has("haste"))
        self.end(self.b)
        self.assertIn(c, self.a.hand)
        self.assertNotIn(perm, self.a.battlefield)

    def test_rebound_from_hand_only(self):
        c = self.db.get("Survival Cache")
        self.a.hand = [c]
        self.mana("Plains", 3)
        self.assertTrue(self.g.cast(self.a, c))
        self.assertEqual(self.a.life, 22)
        self.assertIn(c, self.a.exile)
        self.upkeep()
        self.assertEqual(self.a.life, 24)
        self.assertIn(c, self.a.graveyard)
        self.assertNotIn(c, self.a.exile)
        self.upkeep()
        self.assertEqual(self.a.life, 24)

    def test_rebound_countered(self):
        c = self.db.get("Survival Cache")
        self.a.hand = [c]
        self.mana("Plains", 3)
        self.g._priority_depth = 1
        self.g.cast(self.a, c)
        self.g.counter(self.b, Effect("counter"), self.g.stack[-1])
        self.assertIn(c, self.a.graveyard)
        self.assertFalse(getattr(self.a, "rebounding", []))

    def test_suspend_counts_own_upkeeps_and_casts(self):
        c = self.db.get("Rift Bolt")
        self.a.hand = [c]
        self.mana("Mountain", 1)
        self.assertTrue(self.g.cast(self.a, self.option("suspend")))
        self.assertFalse(self.g.stack)
        self.assertIn(c, self.a.exile)
        self.g.fire(self.b, "upkeep")
        self.g.settle()
        self.assertEqual(self.b.life, 20)
        self.upkeep()
        self.assertEqual(self.b.life, 17)
        self.assertIn(c, self.a.graveyard)

    def test_suspend_no_mana_cost_and_haste(self):
        vision = self.db.get("Ancestral Vision")
        self.a.hand = [vision]
        self.mana("Island", 1)
        self.assertFalse(self.g.can_cast_now(self.a, vision))
        self.assertFalse(self.g.cast(self.a, vision))
        self.g.cast(self.a, self.option("suspend"))
        for _ in range(3):
            self.upkeep()
            self.assertIn(vision, self.a.exile)
        self.upkeep()
        self.assertIn(vision, self.a.graveyard)
        c = self.db.get("Durkwood Baloth")
        self.a.hand = [c]
        self.mana("Forest", 1)
        self.g.step = "main1"
        self.g.cast(self.a, self.option("suspend"))
        for _ in range(5):
            self.upkeep()
        perm = next(x for x in self.a.creatures if x.card.name == c.name)
        self.assertTrue(perm.has("haste"))
        perm.temp_kw.clear()
        self.assertTrue(perm.has("haste"))

    def test_cumulative_upkeep_mana_increases_then_sacrifices(self):
        c = self.db.get("Sustaining Spirit")
        perm = self.g.enter_battlefield(self.a, c)
        self.mana("Plains", 2)
        self.upkeep()
        self.assertEqual(perm.counters["age"], 1)
        self.assertIn(perm, self.a.battlefield)
        self.upkeep()
        self.assertNotIn(perm, self.a.battlefield)
        self.assertEqual(perm.counters["age"], 2)

    def test_cumulative_upkeep_life_and_unsupported_cost(self):
        c = self.db.get("Glacial Chasm")
        self.assertEqual(c.altcast["cumulative"], ("life", 2))
        perm = self.g.enter_battlefield(self.a, card("Life upkeep", "{1}", "Enchantment", "Cumulative upkeep—Pay 2 life."))
        self.upkeep()
        self.assertEqual(self.a.life, 18)
        self.upkeep()
        self.assertEqual(self.a.life, 14)
        other = card("Unknown upkeep", "{1}", "Enchantment", "Cumulative upkeep—Discard a card.")
        self.assertTrue(other.unsupported)

    def test_delve_exiles_only_generic_and_not_self(self):
        c = self.db.get("Gurmag Angler")
        self.a.hand = [c]
        self.a.graveyard.extend([self.db.get("Island")] * 8)
        self.assertFalse(self.g.can_cast_now(self.a, c))
        self.assertEqual(len(self.a.graveyard), 8)
        self.mana("Swamp", 1)
        self.assertTrue(self.g.can_cast_now(self.a, c))
        self.assertTrue(self.g.cast(self.a, c))
        self.assertEqual(len(self.a.exile), 6)
        self.assertEqual(len(self.a.graveyard), 2)
        self.assertTrue(any(x.card is c for x in self.a.creatures))

    def test_improvise_taps_artifacts_without_sacrificing(self):
        c = self.db.get("Foundry Assembler")
        self.a.hand = [c]
        artifacts = [self.g.enter_battlefield(self.a, self.db.get("Ornithopter")) for _ in range(5)]
        self.assertTrue(self.g.can_cast_now(self.a, c))
        self.assertTrue(self.g.cast(self.a, c))
        self.assertTrue(all(x.tapped for x in artifacts))
        self.assertTrue(all(x in self.a.battlefield for x in artifacts))

    def test_improvise_does_not_double_spend_colored_mana(self):
        c = self.db.get("Bastion Inventor")
        self.a.hand = [c]
        self.g.enter_battlefield(self.a, self.db.get("Sky Diamond")).tapped = False
        artifacts = [self.g.enter_battlefield(self.a, self.db.get("Ornithopter")) for _ in range(5)]
        self.assertTrue(self.g.can_cast_now(self.a, c))
        self.assertTrue(self.g.cast(self.a, c))
        self.assertTrue(all(x.tapped for x in artifacts))

    def test_retrace_discards_land_and_can_be_used_again(self):
        c = self.db.get("Flame Jab")
        self.a.graveyard.append(c)
        self.a.hand = [self.db.get("Mountain"), self.db.get("Mountain")]
        self.mana("Mountain", 2)
        self.assertTrue(self.g.cast(self.a, self.option("retrace"), [self.b]))
        self.assertEqual(self.b.life, 19)
        self.assertEqual(len(self.a.hand), 1)
        self.assertIn(c, self.a.graveyard)
        self.assertTrue(self.g.cast(self.a, self.option("retrace"), [self.b]))
        self.assertEqual(self.b.life, 18)
        self.assertFalse(any(self.g._origin(x)[1] == "retrace" for x in self.g.spell_options(self.a)))

    def test_minimal_policy_uses_suspend_and_unearth(self):
        c = self.db.get("Dregscape Zombie")
        self.a.graveyard.append(c)
        self.mana("Swamp", 1)
        kw_altcast.use_abilities(self.g, self.a)
        self.assertTrue(any(x.card is c for x in self.a.creatures))
        bolt = self.db.get("Rift Bolt")
        self.a.hand = [bolt]
        self.mana("Mountain", 1)
        kw_altcast.use_abilities(self.g, self.a)
        self.assertIn(bolt, self.a.exile)

    def test_two_identical_suspended_copies_remain_independent(self):
        c = self.db.get("Rift Bolt")
        self.a.hand = [c, c]
        self.mana("Mountain", 2)
        self.g.cast(self.a, self.option("suspend"))
        self.g.cast(self.a, self.option("suspend"))
        self.assertEqual(len(self.a.exile), 2)
        self.upkeep()
        self.assertEqual(self.b.life, 14)
        self.assertEqual(self.a.graveyard.count(c), 2)
        self.assertFalse(self.a.exile)

    def test_rebound_from_graveyard_does_not_rebound_again(self):
        from mtgsim.cards import AltCost
        from mtgsim.engine import GraveyardTarget
        c = self.db.get("Staggershock")
        self.a.graveyard.append(c)
        self.mana("Mountain", 3)
        ref = GraveyardTarget(self.a, c, self.a.graveyard.entries[0])
        opt = self.g._graveyard_variant(ref, "flashback", AltCost("flashback", c.mana_cost))
        self.assertTrue(self.g.cast(self.a, opt, [self.b]))
        self.assertIn(c, self.a.exile)
        self.assertFalse(getattr(self.a, "rebounding", []))
        self.upkeep()
        self.assertEqual(self.b.life, 18)

    def test_rebound_illegal_target_does_not_exile(self):
        c = self.db.get("Staggershock")
        victim = self.g.enter_battlefield(self.b, self.db.get("Grizzly Bears"))
        self.a.hand = [c]
        self.mana("Mountain", 3)
        self.g._priority_depth = 1
        self.g.cast(self.a, c, [victim])
        self.g.leave_battlefield(victim, "exile")
        self.g.resolve_top()
        self.assertIn(c, self.a.graveyard)
        self.assertNotIn(c, self.a.exile)

    def test_dash_delayed_return_does_not_follow_reentry(self):
        c = self.db.get("Mardu Scout")
        self.a.hand = [c]
        self.mana("Mountain", 2)
        self.g.cast(self.a, self.option("dash"))
        old = self.a.creatures[0]
        self.g.leave_battlefield(old, "exile")
        self.a.exile.remove(c)
        new = self.g.enter_battlefield(self.a, c)
        self.end()
        self.assertIn(new, self.a.battlefield)
        self.assertNotIn(c, self.a.hand)
        self.assertFalse(new.has("haste"))

    def test_unearth_countered_ability_keeps_card_in_graveyard(self):
        c = self.db.get("Dregscape Zombie")
        self.a.graveyard.append(c)
        self.mana("Swamp", 1)
        self.g._priority_depth = 1
        self.g.cast(self.a, self.option("unearth"))
        self.g.counter(self.b, Effect("counter", data={"ability": True}), self.g.stack[-1])
        self.assertIn(c, self.a.graveyard)
        self.assertFalse(self.a.creatures)

    def test_delve_graveyard_cast_does_not_exile_its_own_entry(self):
        from mtgsim.cards import AltCost
        from mtgsim.engine import GraveyardTarget
        c = self.db.get("Gurmag Angler")
        self.a.graveyard.extend([c] + [self.db.get("Island")] * 6)
        self.mana("Swamp", 1)
        ref = GraveyardTarget(self.a, c, self.a.graveyard.entries[0])
        opt = self.g._graveyard_variant(ref, "flashback", AltCost("flashback", c.mana_cost))
        self.assertTrue(self.g.cast(self.a, opt))
        self.assertTrue(any(x.card is c for x in self.a.creatures))
        self.assertEqual(len(self.a.exile), 6)
        self.assertFalse(self.a.graveyard)

    def test_improvise_failed_payment_rolls_back_taps(self):
        c = self.db.get("Bastion Inventor")
        self.a.hand = [c]
        artifacts = [self.g.enter_battlefield(self.a, self.db.get("Ornithopter")) for _ in range(5)]
        self.assertFalse(self.g.cast(self.a, c))
        self.assertFalse(any(x.tapped for x in artifacts))
        self.assertIn(c, self.a.hand)

    def test_suspend_haste_ends_on_control_change(self):
        c = self.db.get("Durkwood Baloth")
        perm = self.g.enter_battlefield(self.a, c)
        kw_altcast.entered(self.g, perm, "suspend_cast")
        self.assertTrue(perm.has("haste"))
        kw_altcast.control_changed(perm)
        self.assertFalse(perm.has("haste"))

    def test_suspend_cost_is_not_a_spell_cost(self):
        c = self.db.get("Errant Ephemeron")
        self.a.hand = [c]
        discount = card("Discount", "{1}", "Enchantment", "Creature spells you cast cost {1} less to cast.")
        self.g.enter_battlefield(self.a, discount)
        opt = self.option("suspend")
        self.assertEqual(self.g.cost_of(self.a, opt), {"generic": 1, "U": 1})
        self.assertFalse(self.g.can_cast_now(self.a, opt))

    def test_discover_cast_does_not_enable_rebound(self):
        c = self.db.get("Survival Cache")
        self.assertTrue(self.g.cast_free(self.a, c))
        self.assertIn(c, self.a.graveyard)
        self.assertNotIn(c, self.a.exile)
        self.assertFalse(getattr(self.a, "rebounding", []))

    def test_improvise_pays_for_x(self):
        c = self.db.get("Universal Surveillance")
        self.a.hand = [c]
        self.mana("Island", 3)
        artifacts = [self.g.enter_battlefield(self.a, self.db.get("Ornithopter")) for _ in range(4)]
        self.g._priority_depth = 1
        self.assertTrue(self.g.cast(self.a, c))
        self.assertEqual(self.g.stack[-1].x, 4)
        self.assertTrue(all(a.tapped for a in artifacts))
        self.g.resolve_top()
        self.assertEqual(len(self.a.hand), 4)

    def test_delve_pays_for_x(self):
        from mtgsim.engine import StackItem
        c = self.db.get("Logic Knot")
        self.a.hand = [c]
        self.mana("Island", 2)
        self.a.graveyard.extend([self.db.get("Island")] * 4)
        target = StackItem(self.b, [], [], card=self.db.get("Grizzly Bears"), kind="spell")
        self.g.stack.append(target)
        self.g._priority_depth = 1
        self.assertTrue(self.g.cast(self.a, c, [target]))
        self.assertEqual(self.g.stack[-1].x, 4)
        self.assertEqual(len(self.a.exile), 4)
        self.g.resolve_top()
        self.assertNotIn(target, self.g.stack)


if __name__ == "__main__":
    unittest.main()
