"""#508: one dies trigger, source exile, then targeted/random/top returns."""
import dataclasses
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.coverage import card_coverage
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

BIRD = card("Return Bird", "{1}", "Creature — Bird", "", 1, 1)
CLERIC = card("Return Cleric", "{3}", "Creature — Cleric", "When ~ enters, you gain 3 life.", 3, 3)
ROCK = card("Return Rock", "{8}", "Artifact", "")


class DiesReturns(Base):
    def source(self, body, owner=None):
        definition = card("Return Source", "{5}", "Creature — Bird Cleric", "When ~ dies, " + body, 4, 4)
        self.assertEqual(definition.unsupported, [])
        return self.game.enter_battlefield(owner or self.a, definition)

    def stack_death(self, source):
        self.game.destroy(source)
        self.game.flush_triggers()
        self.assertTrue(self.game.stack)
        return self.game.stack[-1]

    def retarget(self, item, targets):
        from mtgsim.counter_mechanics import protect_graveyard_targets
        effects = [dataclasses.replace(e, data={k: v for k, v in e.data.items()
                                                if k not in ("graveyard_ref", "graveyard_zone")}) for e in item.effects]
        item.targets = targets
        item.effects = protect_graveyard_targets(self.game, effects, targets)

    def test_targeted_return_has_targets_before_resolution_and_exiles_first(self):
        source = self.source("exile it and return target creature card from your graveyard to the battlefield.")
        self.a.graveyard.append(CLERIC)
        target = self.a.graveyard[0]
        item = self.stack_death(source)
        self.assertEqual([e.target for e in item.effects], ["none", "graveyard_card", "none"])
        self.retarget(item, [None, target, None])
        observed = []
        enter = self.game.enter_battlefield
        def check(*args, **kwargs):
            observed.append(source.front in self.a.exile)
            return enter(*args, **kwargs)
        self.game.enter_battlefield = check
        self.game.resolve_top()
        self.game.settle()
        self.assertTrue(item.resolved)
        self.assertEqual(observed, [True])
        self.assertEqual([c.card.name for c in self.a.creatures], [CLERIC.name])
        self.assertEqual(self.a.life, 23)

    def test_all_targets_illegal_fizzles_before_source_exile(self):
        source = self.source("exile it and return target creature card from your graveyard to the battlefield.")
        self.a.graveyard.append(BEAR)
        target = self.a.graveyard[0]
        item = self.stack_death(source)
        self.retarget(item, [None, target, None])
        self.game.move_card(target, self.a.graveyard, self.a.exile)
        self.game.resolve_top()
        self.assertFalse(item.resolved)
        self.assertIn(source.front, self.a.graveyard)
        self.assertNotIn(source.front, self.a.exile)

    def test_another_excludes_source_but_allows_same_named_copy(self):
        source = self.source("exile it, then return another target creature card from your graveyard to your hand.")
        self.a.graveyard.append(source.card)
        other = self.a.graveyard[0]
        item = self.stack_death(source)
        with self.game.targeting(item):
            self.assertEqual(self.game.legal_targets(self.a, item.effects[1]), [other])
        self.game.resolve_top()
        self.assertEqual(self.a.hand, [other])
        self.assertIn(source.front, self.a.exile)

    def test_targeting_source_itself_exiles_it_without_reanimating(self):
        source = self.source("exile it and return target creature card from your graveyard to the battlefield.")
        item = self.stack_death(source)
        self.assertIs(item.targets[1], source.front)
        self.game.resolve_top()
        self.assertTrue(item.resolved)
        self.assertIn(source.front, self.a.exile)
        self.assertEqual(self.a.creatures, [])

    def test_source_missing_does_not_gate_return(self):
        source = self.source("exile it, then return another target creature card from your graveyard to your hand.")
        self.a.graveyard.append(BEAR)
        target = self.a.graveyard[0]
        self.stack_death(source)
        self.game.move_card(source.front, self.a.graveyard, self.a.hand)
        self.game.resolve_top()
        self.assertIn(target, self.a.hand)
        self.assertIn(source.front, self.a.hand)
        self.assertEqual(self.a.exile, [])

    def test_source_that_leaves_and_returns_is_not_exiled_even_before_flush(self):
        for before_flush in (True, False):
            with self.subTest(before_flush=before_flush):
                self.setUp()
                source = self.source("exile it, then return the top creature card of your graveyard to the battlefield.")
                self.a.graveyard.append(BEAR)
                self.game.destroy(source)
                if not before_flush:
                    self.game.flush_triggers()
                self.game.move_card(source.front, self.a.graveyard, self.a.hand)
                self.game.move_card(source.front, self.a.hand, self.a.graveyard)
                if before_flush:
                    self.game.flush_triggers()
                self.game.resolve_top()
                self.assertEqual(self.a.exile, [])
                # Its new graveyard object is now the top creature, so the return may choose it.
                self.assertIn(source.front.name, [c.card.name for c in self.a.creatures])

    def test_target_zone_generation_protected(self):
        source = self.source("exile it, then return another target creature card from your graveyard to your hand.")
        self.a.graveyard.append(BEAR)
        target = self.a.graveyard[0]
        item = self.stack_death(source)
        self.game.move_card(target, self.a.graveyard, self.a.hand)
        self.game.move_card(target, self.a.hand, self.a.graveyard)
        self.game.resolve_top()
        self.assertFalse(item.resolved)
        self.assertIn(source.front, self.a.graveyard)
        self.assertEqual(self.a.hand, [])

    def test_stolen_source_uses_owner_exile_and_controller_graveyard(self):
        source = self.source("exile it, then return the top creature card of your graveyard to the battlefield.", self.b)
        self.b.battlefield.remove(source)
        source.controller = self.a
        self.a.battlefield.append(source)
        self.a.graveyard.append(BEAR)
        self.b.graveyard.append(CLERIC)
        self.stack_death(source)
        self.game.resolve_top()
        self.assertIn(source.front, self.b.exile)
        self.assertEqual(self.a.exile, [])
        self.assertEqual([c.card.name for c in self.a.creatures], [BEAR.name])
        self.assertEqual([c.name for c in self.b.graveyard], [CLERIC.name])

    def test_top_creature_uses_graveyard_order_after_exile(self):
        source = self.source("exile it, then return the top creature card of your graveyard to the battlefield.")
        self.a.graveyard.extend([CLERIC, BEAR, ROCK])
        top = self.a.graveyard[1]
        self.stack_death(source)
        self.game.resolve_top()
        self.assertIs(self.a.creatures[0].front, top)
        self.assertIn(CLERIC, self.a.graveyard)
        self.assertIn(ROCK, self.a.graveyard)

    def test_random_return_samples_distinct_physical_cards_from_own_graveyard(self):
        source = self.source("exile it, then return two creature cards at random from your graveyard to the battlefield.")
        self.a.graveyard.extend([BEAR, BEAR, CLERIC, BIRD, ROCK])
        self.b.graveyard.append(CLERIC)
        pool = list(self.a.graveyard[:4])
        self.stack_death(source)
        self.game.rng = random.Random(7)
        expected = random.Random(7).sample(pool, 2)
        self.game.resolve_top()
        self.assertEqual([x.front for x in self.a.creatures], expected)
        self.assertEqual(len({x.front.physical_id for x in self.a.creatures}), 2)
        self.assertIn(ROCK, self.a.graveyard)
        self.assertIn(CLERIC, self.b.graveyard)
        self.assertIn(source.front, self.a.exile)

    def test_random_return_handles_empty_and_small_pools(self):
        for pool in ([], [BEAR], [BEAR, BEAR]):
            with self.subTest(n=len(pool)):
                self.setUp()
                source = self.source("exile it, then return two creature cards at random from your graveyard to the battlefield.")
                self.a.graveyard.extend(pool)
                self.stack_death(source)
                self.game.resolve_top()
                self.assertEqual(len(self.a.creatures), len(pool))
                self.assertIn(source.front, self.a.exile)

    def test_subtype_targets_are_optional_distinct_and_not_limited_to_creatures(self):
        source = self.source("exile it, then return up to two target Bird and/or Cleric permanent cards from your graveyard to the battlefield.")
        tribal = card("Bird Relic", "{2}", "Kindred Artifact — Bird", "")
        changeling = dataclasses.replace(BEAR, changeling=True)
        self.a.graveyard.extend([BIRD, CLERIC, tribal, BEAR, changeling])
        item = self.stack_death(source)
        with self.game.targeting(item):
            legal = self.game.legal_targets(self.a, item.effects[1])
        self.assertIn(self.a.graveyard[2], legal)
        self.assertIn(self.a.graveyard[4], legal)
        self.assertNotIn(self.a.graveyard[3], legal)
        self.assertIsNotNone(item.targets[1])
        self.assertIsNotNone(item.targets[2])
        self.assertIsNot(item.targets[1], item.targets[2])
        self.assertTrue(all(e.data["optional_target"] for e in item.effects[1:3]))

    def test_one_illegal_target_does_not_stop_other_return(self):
        source = self.source("exile it, then return up to two target Bird and/or Cleric permanent cards from your graveyard to the battlefield.")
        self.a.graveyard.extend([BIRD, CLERIC])
        first, second = self.a.graveyard
        item = self.stack_death(source)
        self.retarget(item, [None, first, second, None])
        self.game.move_card(second, self.a.graveyard, self.a.hand)
        self.game.resolve_top()
        self.assertTrue(item.resolved)
        self.assertEqual([x.front for x in self.a.creatures], [first])
        self.assertIn(source.front, self.a.exile)

    def test_zero_optional_targets_still_exiles_source(self):
        source = self.source("exile it, then return up to two target Bird and/or Cleric permanent cards from your graveyard to the battlefield.")
        item = self.stack_death(source)
        item.targets = [None] * len(item.effects)
        self.game.resolve_top()
        self.assertTrue(item.resolved)
        self.assertIn(source.front, self.a.exile)
        self.assertEqual(self.a.creatures, [])

    def test_multiple_targets_leave_graveyard_before_any_enters(self):
        source = self.source("exile it, then return up to two target Bird and/or Cleric permanent cards from your graveyard to the battlefield.")
        self.a.graveyard.extend([BIRD, CLERIC])
        first, second = self.a.graveyard
        item = self.stack_death(source)
        self.retarget(item, [None, first, second, None])
        observed = []
        enter = self.game.enter_battlefield
        def check(*args, **kwargs):
            observed.append(list(self.a.graveyard))
            return enter(*args, **kwargs)
        self.game.enter_battlefield = check
        self.game.resolve_top()
        self.assertEqual(observed, [[], []])
        self.assertEqual([x.front for x in self.a.creatures], [first, second])

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_entry_lock_preserves_returned_card(self):
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        source = self.source("exile it, then return the top creature card of your graveyard to the battlefield.")
        self.a.graveyard.append(BEAR)
        target = self.a.graveyard[0]
        generation = target.generation
        self.game.enter_battlefield(self.b, db.get("Grafdigger's Cage"))
        self.stack_death(source)
        self.game.resolve_top()
        self.assertEqual(self.a.graveyard, [target])
        self.assertEqual(target.generation, generation)
        self.assertEqual(self.a.creatures, [])
        self.assertIn(source.front, self.a.exile)


class Parsing(unittest.TestCase):
    def test_unknown_riders_and_non_death_antecedents_remain_visible(self):
        for line in (
            "When ~ enters, exile it, then return two creature cards at random from your graveyard to the battlefield.",
            "When ~ dies, exile it, then return target creature card from your graveyard to the battlefield attached to ~.",
            "When ~ dies, exile it, then return up to two target Unknown permanent cards from your graveyard to the battlefield.",
            "When ~ dies, exile it, then return target creature card of the chosen type from your graveyard to the battlefield.",
            "When ~ dies, exile it, then return two creature cards at random from your graveyard to the battlefield tapped.",
            "When ~ dies, exile it, then return target creature card from an opponent's graveyard to the battlefield.",
        ):
            with self.subTest(line=line):
                self.assertTrue(card("Refusal", "{3}", "Creature", line, 3, 3).unsupported)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_five_real_cards_full(self):
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in ("Moldgraf Monstrosity", "Celestial Gatekeeper", "Mistmoon Griffin", "Sylvan Hierophant", "Body Snatcher"):
            with self.subTest(name=name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")


if __name__ == "__main__":
    unittest.main()
