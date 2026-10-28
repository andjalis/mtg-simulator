"""Shared +1/+1 counter costs, mana conflicts and transactional activation."""
import dataclasses
import random
import unittest

from mtgsim.ai import BaselineAI
from mtgsim.cards import _parse_ability_cost
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, PLAINS, card


INITIATE = card("Hopeful Initiate", "{W}", "Creature — Human Warlock",
                "Training\n{2}{W}, Remove two +1/+1 counters from among creatures you control: "
                "Destroy target artifact or enchantment.", 1, 2)


class SharedCounterCosts(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], BaselineAI()), Player("b", [], BaselineAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game._priority_depth = 2, "main1", 1
        self.source = self.put(INITIATE)
        self.target = self.put(card("Test Artifact", "{1}", "Artifact"), self.b)
        self.lands = [self.put(PLAINS) for _ in range(3)]

    def put(self, definition=BEAR, who=None, counters=0):
        perm = self.game.enter_battlefield(who or self.a, definition, counters={"+1/+1": counters})
        return perm

    def activate(self, target=None):
        return self.game.activate_ability(self.a, self.source, 0, [target or self.target])

    def draw_source(self, cost="{W}", extras=""):
        text = cost + ", Remove two +1/+1 counters from among creatures you control"
        self.source = self.put(card("Test Counter User", "{1}", "Creature — Human",
                                    text + extras + ": Draw a card.", 1, 2))
        self.a.library = [BEAR] * 5
        return self.source

    def test_oracle_template_is_fully_recognized(self):
        self.assertEqual(INITIATE.unsupported, [])
        self.assertEqual(INITIATE.activated[0].extra_costs, {"remove_creature_counters": 2})

    def test_same_creature_pays_both_counters_before_resolution(self):
        donor = self.put(counters=3)
        self.assertTrue(self.activate())
        self.assertEqual(donor.p1, 1)
        self.assertTrue(all(p.tapped for p in self.lands))
        self.assertIn(self.target, self.b.battlefield)
        self.assertEqual(len(self.game.stack), 1)
        self.game.resolve_top()
        self.assertNotIn(self.target, self.b.battlefield)

    def test_counters_can_be_split_between_source_and_another_creature(self):
        self.source.counters["+1/+1"] = 1
        donor = self.put(counters=1)
        self.assertTrue(self.activate())
        self.assertEqual((self.source.p1, donor.p1), (0, 0))

    def test_source_can_pay_all_the_counters(self):
        self.source.counters["+1/+1"] = 2
        self.assertTrue(self.activate())
        self.assertEqual(self.source.p1, 0)

    def test_not_enough_counters_leaves_mana_and_state_unchanged(self):
        donor = self.put(counters=1)
        events = list(self.game.events)
        self.assertFalse(self.game.can_activate(self.a, self.source, 0))
        self.assertFalse(self.activate())
        self.assertEqual(donor.p1, 1)
        self.assertTrue(all(not p.tapped for p in self.lands))
        self.assertEqual(self.game.events, events)
        self.assertFalse(self.game.stack)

    def test_opponents_and_noncreatures_cannot_donate(self):
        enemy = self.put(who=self.b, counters=2)
        artifact = self.put(card("Counter Artifact", types="Artifact"), counters=2)
        self.assertFalse(self.activate())
        self.assertEqual((enemy.p1, artifact.p1), (2, 2))

    def test_other_counter_types_do_not_pay(self):
        self.source.counters.update({"charge": 2, "vigilance": 2, "-1/-1": 1})
        self.assertFalse(self.activate())
        self.assertEqual(self.source.counters["charge"], 2)

    def test_failed_mana_payment_does_not_remove_counters(self):
        donor = self.put(counters=2)
        self.lands[0].tapped = True
        self.assertFalse(self.activate())
        self.assertEqual(donor.p1, 2)
        self.assertEqual([p.tapped for p in self.lands], [True, False, False])

    def test_illegal_target_does_not_pay_costs(self):
        donor = self.put(counters=2)
        creature = self.put(who=self.b)
        self.assertFalse(self.activate(creature))
        self.assertEqual(donor.p1, 2)
        self.assertTrue(all(not p.tapped for p in self.lands))
        self.assertFalse(self.game.stack)

    def test_probe_does_not_spend_resources(self):
        donor = self.put(counters=2)
        events = list(self.game.events)
        action = ("activate", self.source, "ability:0", [self.target])
        self.assertTrue(self.game.can_perform(self.a, action))
        self.assertEqual(donor.p1, 2)
        self.assertTrue(all(not p.tapped for p in self.lands))
        self.assertFalse(self.game.stack)
        self.assertEqual(self.game.events, events)

    def test_costs_stay_paid_if_target_leaves_before_resolution(self):
        donor = self.put(counters=2)
        self.assertTrue(self.activate())
        self.game.leave_battlefield(self.target, "graveyard")
        self.game.resolve_top()
        self.assertEqual(donor.p1, 0)
        self.assertTrue(all(p.tapped for p in self.lands))
        self.assertFalse(self.game.stack)

    def test_donor_dying_to_counter_loss_does_not_cancel_ability(self):
        donor = self.put(card("Counter Body", types="Creature", power=0, toughness=0), counters=2)
        self.assertTrue(self.activate())
        self.game.state_based_actions()
        self.assertNotIn(donor, self.a.battlefield)
        self.game.resolve_top()
        self.assertNotIn(self.target, self.b.battlefield)

    def test_mana_creature_can_tap_and_donate_counters(self):
        self.draw_source()
        for p in self.lands:
            p.tapped = True
        donor = self.put(card("Counter Druid", types="Creature", text="{T}: Add {W}.", power=1, toughness=2), counters=2)
        donor.sick = False
        self.assertTrue(self.game.activate_ability(self.a, self.source, 0, []))
        self.assertTrue(donor.tapped)
        self.assertEqual(donor.p1, 0)

    def treasure_creature(self, power=1):
        definition = dataclasses.replace(card("Counter Treasure", types="Artifact Creature", power=power, toughness=3),
                                         token_kind="treasure", produces=frozenset({"W"}))
        donor = self.put(definition, counters=2)
        donor.sick = False
        return donor

    def test_mana_sacrifice_cannot_also_supply_counter_cost(self):
        self.draw_source()
        for p in self.lands:
            p.tapped = True
        donor = self.treasure_creature()
        self.assertFalse(self.game.activate_ability(self.a, self.source, 0, []))
        self.assertEqual(donor.p1, 2)
        self.assertIn(donor, self.a.battlefield)

    def test_planner_tries_another_donor_to_leave_mana_available(self):
        self.draw_source()
        for p in self.lands:
            p.tapped = True
        white = self.treasure_creature()
        other = self.treasure_creature(5)
        other.card = dataclasses.replace(other.card, produces=frozenset({"C"}))
        self.assertTrue(self.game.activate_ability(self.a, self.source, 0, []))
        self.assertNotIn(white, self.a.battlefield)
        self.assertEqual(other.p1, 0)
        self.assertIn(other, self.a.battlefield)

    def test_donor_losing_creature_type_during_mana_payment_rolls_back(self):
        self.draw_source()
        for p in self.lands:
            p.tapped = True
        mana = self.treasure_creature()
        donor = self.put(card("Animated Counter Artifact", types="Artifact"), counters=2)
        self.game.add_continuous_effect(donor, "add_types", types={"Creature"}, source=mana)
        self.game.add_continuous_effect(donor, "set_base", power=2, toughness=2, source=mana)
        # The only counter donor relies on the mana source for its creature type.
        mana.counters["+1/+1"] = 0
        self.assertFalse(self.game.activate_ability(self.a, self.source, 0, []))
        self.assertIn(mana, self.a.battlefield)
        self.assertFalse(mana.tapped)
        self.assertEqual(donor.p1, 2)
        self.assertTrue(donor.is_creature)
        self.assertFalse(self.game.stack)

    def test_donor_can_be_sacrificed_as_a_later_cost(self):
        self.draw_source(extras=", Sacrifice another creature")
        donor = self.put(counters=2)
        # Leave only this donor eligible for the sacrifice.
        self.game.leave_battlefield(self.a.creatures[0], "graveyard")
        self.assertTrue(self.game.activate_ability(self.a, self.source, 0, []))
        self.assertNotIn(donor, self.a.battlefield)
        self.assertEqual(donor.p1, 0)

    def test_self_and_shared_counter_costs_do_not_double_spend(self):
        self.draw_source(extras=", Remove a +1/+1 counter from ~")
        self.source.counters["+1/+1"] = 2
        self.assertFalse(self.game.can_activate(self.a, self.source, 0))
        self.source.counters["+1/+1"] = 3
        self.assertTrue(self.game.activate_ability(self.a, self.source, 0, []))
        self.assertEqual(self.source.p1, 0)

    def test_unsupported_unbounded_and_specific_counter_costs_stay_visible(self):
        for cost in ("Remove any number of +1/+1 counters", "Remove three charge counters", "Remove X charge counters"):
            with self.subTest(cost=cost):
                definition = card("Unsupported Cost", types="Creature", power=1, toughness=1,
                                  text="{1}, " + cost + " from among creatures you control: Draw a card.")
                self.assertTrue(definition.unsupported)
                self.assertFalse(definition.activated)

    def test_numbered_and_repeated_fixed_costs(self):
        _, costs = _parse_ability_cost("Remove 3 +1/+1 counters from among creatures you control, "
                                       "Remove a +1/+1 counter from among creatures you control")
        self.assertEqual(costs["remove_creature_counters"], 4)
        self.assertIsNone(_parse_ability_cost("Remove 0 +1/+1 counters from among creatures you control"))


if __name__ == "__main__":
    unittest.main()
