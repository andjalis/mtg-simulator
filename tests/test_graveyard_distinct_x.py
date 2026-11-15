"""Distinct graveyard target mana values and X are chosen before payment."""
from mtgsim.counter_mechanics import protect_graveyard_targets
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base
from tests.test_templates import card


class DistinctX(Base):
    def prepare(self, land_count=5):
        spell = self.spell("Return from your graveyard to the battlefield any number of target creature cards "
                           "that each have a different mana value X or less.", types="Sorcery")
        spell.mana_cost = {"X": 1, "B": 3, "generic": 0}
        self.a.hand.append(spell)
        swamp = card("Swamp", "", "Basic Land — Swamp", "({T}: Add {B}.)")
        for _ in range(land_count):
            self.perm(swamp, self.a)
        self.a.graveyard.extend([card("Zero", "{0}", "Creature — Human", "", 1, 1),
                                 card("One A", "{1}", "Creature — Human", "", 1, 1),
                                 card("One B", "{1}", "Creature — Human", "", 1, 1),
                                 card("Two", "{2}", "Creature — Human", "", 2, 2),
                                 card("Three", "{3}", "Creature — Human", "", 3, 3)])
        return spell, list(self.a.graveyard)

    def test_cast_selects_x_before_targets_and_pays_it(self):
        spell, cards = self.prepare()
        self.assertTrue(self.game.cast(self.a, spell))
        self.game.settle()
        values = sorted(p.card.cmc for p in self.a.creatures)
        self.assertEqual(values, [0, 1, 2])
        self.assertTrue(all(p.tapped for p in self.a.battlefield if p.card.is_land))

    def test_duplicate_values_and_over_x_are_rejected_before_payment(self):
        for indices in ((1, 2), (4,)):
            with self.subTest(indices=indices):
                self.setUp()
                spell, cards = self.prepare()
                self.assertFalse(self.game.cast(self.a, spell, [tuple(cards[i] for i in indices)]))
                self.assertIn(spell, self.a.hand)
                self.assertTrue(all(not p.tapped for p in self.a.battlefield))

    def test_x_zero_allows_zero_mana_value(self):
        spell, cards = self.prepare(3)
        self.assertTrue(self.game.cast(self.a, spell, [(cards[0],)]))
        self.game.settle()
        self.assertEqual([p.card.name for p in self.a.creatures], ["Zero"])

    def test_heuristic_selects_distinct_targets_for_planned_x(self):
        spell, _ = self.prepare()
        selected = self.a.ai.choose_target(self.game, self.a, spell.spell_effects[0], spell)
        self.assertEqual(sorted(c.cmc for c in selected), [0, 1, 2])
        self.assertTrue(self.game.cast(self.a, spell, [selected]))

    def test_cast_without_paying_mana_cost_uses_x_zero(self):
        from mtgsim.cards import AltCost
        from mtgsim.graveyard_returns import max_target_x
        spell, cards = self.prepare()
        free = self.game._variant(spell, "free", AltCost("free", {}))
        self.assertEqual(max_target_x(self.game, self.a, free), 0)
        self.assertEqual([c.cmc for c in self.a.ai.choose_target(self.game, self.a, free.spell_effects[0], free)], [0])
        self.assertTrue(self.game.cast(self.a, free, [(cards[0],)]))
        self.game.settle()
        self.assertEqual([p.card.name for p in self.a.creatures], ["Zero"])

    def test_partial_target_invalidation_preserves_other_target(self):
        import dataclasses
        spell, cards = self.prepare()
        eff = spell.spell_effects[0]
        eff = dataclasses.replace(eff, data=dict(eff.data, x_limit=2))
        targets = [(cards[1], cards[3])]
        effects = protect_graveyard_targets(self.game, [eff], targets)
        item = StackItem(self.a, effects, targets, card=spell, kind="spell")
        self.game.stack.append(item)
        self.game.move_card(cards[1], self.a.graveyard, self.a.hand)
        self.game.move_card(cards[1], self.a.hand, self.a.graveyard)
        self.game.resolve_top()
        self.assertTrue(item.resolved)
        self.assertEqual([p.card.name for p in self.a.creatures], ["Two"])
