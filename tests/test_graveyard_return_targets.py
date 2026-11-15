"""Entry attachments and mana-value-constrained graveyard targets (#508)."""
from mtgsim.counter_mechanics import protect_graveyard_targets
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base
from tests.test_templates import card


class GraveyardReturnTargets(Base):
    def equipment_trigger(self):
        source = card("Snuffler", "{2}", "Creature — Beast",
                      "When ~ enters, return target Equipment card from your graveyard to the battlefield attached to ~.", 2, 2)
        self.assertFalse(source.unsupported)
        equipment = card("Sword", "{1}", "Artifact — Equipment", "")
        self.a.graveyard.append(equipment)
        permanent = self.game.enter_battlefield(self.a, source)
        self.game.flush_triggers()
        return permanent, self.game.stack[-1]

    def test_equipment_is_attached_before_entry_event(self):
        source, item = self.equipment_trigger()
        seen = []
        emit = self.game.rule_events.emit
        def observe(event):
            if event.destination == "battlefield" and getattr(event.source.card, "name", "") == "Sword":
                seen.append(event.source.attached_to)
            return emit(event)
        self.game.rule_events.emit = observe
        self.game.resolve_top()
        self.assertEqual(seen, [source])
        self.assertIs(next(x for x in self.a.battlefield if x.card.name == "Sword").attached_to, source)

    def test_equipment_enters_unattached_if_source_left(self):
        source, _ = self.equipment_trigger()
        self.game.destroy(source)
        self.game.resolve_top()
        self.assertIsNone(next(x for x in self.a.battlefield if x.card.name == "Sword").attached_to)

    def test_equipment_cannot_attach_through_protection(self):
        source, _ = self.equipment_trigger()
        source.temp_kw.add("protection from artifacts")
        self.game.resolve_top()
        self.assertIsNone(next(x for x in self.a.battlefield if x.card.name == "Sword").attached_to)

    def test_equipment_target_is_not_changeling_creature(self):
        shifter = card("Shifter", "{9}", "Creature — Shapeshifter", "Changeling", 1, 1)
        self.a.graveyard.append(shifter)
        _, item = self.equipment_trigger()
        self.assertEqual(item.targets[0].name, "Sword")

    def budget_spell(self):
        return self.spell("Return up to three target creature cards with total mana value 3 or less "
                          "from your graveyard to the battlefield.", types="Sorcery")

    def test_budget_and_card_limit_are_casting_constraints(self):
        eff = self.budget_spell().spell_effects[0]
        self.a.graveyard.extend([card("One", "{1}", "Creature — Human", "", 1, 1),
                                 card("Two", "{2}", "Creature — Human", "", 1, 1),
                                 card("Three", "{3}", "Creature — Human", "", 1, 1),
                                 card("Zero", "{0}", "Creature — Human", "", 1, 1)])
        a, b, c, d = self.a.graveyard
        self.assertTrue(self.game.legal_target(self.a, eff, (a, b)))
        self.assertFalse(self.game.legal_target(self.a, eff, (a, c)))
        self.assertFalse(self.game.legal_target(self.a, eff, (a, b, d, c)))
        self.assertFalse(self.game.legal_target(self.a, eff, (a, a)))
        self.assertFalse(self.game.legal_target(self.a, eff, (object(),)))

    def test_left_and_returned_card_is_illegal_but_other_target_returns(self):
        spell = self.budget_spell()
        self.a.graveyard.extend([card("One", "{1}", "Creature — Human", "", 1, 1),
                                 card("Two", "{2}", "Creature — Human", "", 2, 2)])
        one, two = self.a.graveyard
        targets = [(one, two)]
        effects = protect_graveyard_targets(self.game, spell.spell_effects, targets)
        item = StackItem(self.a, effects, targets, card=spell, kind="spell")
        self.game.stack.append(item)
        self.game.move_card(one, self.a.graveyard, self.a.hand)
        self.game.move_card(one, self.a.hand, self.a.graveyard)
        self.game.resolve_top()
        self.assertTrue(item.resolved)
        self.assertEqual([p.card.name for p in self.a.creatures], ["Two"])
        self.assertIn(one, self.a.graveyard)

    def test_empty_target_list_resolves(self):
        spell = self.budget_spell()
        item = StackItem(self.a, spell.spell_effects, [()], card=spell, kind="spell")
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertTrue(item.resolved)

    def test_all_invalid_targets_fizzle(self):
        spell = self.budget_spell()
        self.a.graveyard.append(card("One", "{1}", "Creature — Human", "", 1, 1))
        one = self.a.graveyard[0]
        targets = [(one,)]
        effects = protect_graveyard_targets(self.game, spell.spell_effects, targets)
        item = StackItem(self.a, effects, targets, card=spell, kind="spell")
        self.game.stack.append(item)
        self.game.move_card(one, self.a.graveyard, self.a.exile)
        self.game.resolve_top()
        self.assertFalse(item.resolved)

    def test_ally_constraint_and_changeling(self):
        spell = self.spell("Return any number of target Ally creature cards with total mana value 8 or less "
                           "from your graveyard to the battlefield.", types="Sorcery")
        self.a.graveyard.extend([card("Ally", "{1}", "Creature — Ally", "", 1, 1),
                                 card("Shifter", "{2}", "Creature — Shapeshifter", "Changeling", 1, 1),
                                 card("Human", "{1}", "Creature — Human", "", 1, 1)])
        ally, shifter, human = self.a.graveyard
        eff = spell.spell_effects[0]
        self.assertTrue(self.game.legal_target(self.a, eff, (ally, shifter)))
        self.assertFalse(self.game.legal_target(self.a, eff, (human,)))
