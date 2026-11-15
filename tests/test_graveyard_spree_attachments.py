"""Targeted spree graveyard returns and attachment during entry (#508)."""
import unittest

from mtgsim.carddb import CardDB
from mtgsim.counter_mechanics import protect_graveyard_targets
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import card


class SpreeReturns(Base):
    @unittest.skipUnless(DB_FILE.exists(), "offline card database missing")
    def test_all_modes_are_targeted(self):
        c = CardDB(DB_FILE).get("One Last Job")
        self.assertFalse(c.unsupported)
        self.assertEqual(len(c.spree), 3)
        self.assertEqual([e.target for _, effects in c.spree for e in effects], ["graveyard_card"] * 3)
        self.assertEqual([e.kind for _, effects in c.spree for e in effects],
                         ["cx_card_move", "cx_card_move", "gy_return_attachment_choice"])

    @unittest.skipUnless(DB_FILE.exists(), "offline card database missing")
    def test_cast_selected_modes_through_spree_variant(self):
        c = CardDB(DB_FILE).get("One Last Job")
        self.a.hand.append(c)
        plains = card("Plains", "", "Basic Land — Plains", "({T}: Add {W}.)")
        for _ in range(6):
            self.perm(plains, self.a)
        self.a.graveyard.extend([card("Human", "{1}", "Creature — Human", "", 1, 1),
                                 card("Vehicle", "{2}", "Artifact — Vehicle", "", 3, 3)])
        options = self.game.spell_options(self.a)
        selected = next(v for v in options if getattr(v, "origin", (None, ""))[1] == "spree_3")
        self.assertEqual([e.target for e in selected.spell_effects], ["graveyard_card", "graveyard_card"])
        self.assertTrue(self.game.cast(self.a, selected, list(self.a.graveyard)))
        self.game.settle()
        self.assertEqual({p.card.name for p in self.a.battlefield} & {"Human", "Vehicle"}, {"Human", "Vehicle"})

    def mode(self, body):
        from mtgsim.graveyard_returns import spree_return_mode
        effects = spree_return_mode(body + ".")
        self.assertIsNotNone(effects)
        return effects[0]

    def resolve_mode(self, eff, target):
        effects = protect_graveyard_targets(self.game, [eff], [target])
        item = StackItem(self.a, effects, [target], card=card("Spell", "{1}", "Sorcery", ""))
        self.game.stack.append(item)
        self.game.resolve_top()
        return item

    def test_mount_vehicle_and_changeling_targets(self):
        eff = self.mode("Return target Mount or Vehicle card from your graveyard to the battlefield")
        self.a.graveyard.extend([card("Mount", "{1}", "Creature — Horse Mount", "", 1, 1),
                                 card("Vehicle", "{2}", "Artifact — Vehicle", "", 3, 3),
                                 card("Shifter", "{1}", "Creature — Shapeshifter", "Changeling", 1, 1),
                                 card("Human", "{1}", "Creature — Human", "", 1, 1)])
        self.assertEqual([c.name for c in self.game.legal_targets(self.a, eff)], ["Mount", "Vehicle", "Shifter"])

    def test_aura_enters_attached_before_zone_event_even_to_shroud(self):
        eff = self.mode("Return target Aura or Equipment card from your graveyard to the battlefield "
                        "attached to a creature you control")
        host = self.perm(card("Host", "{1}", "Creature — Human", "Shroud", 2, 2), self.a)
        aura = card("Aura", "{1}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1.")
        self.a.graveyard.append(aura)
        observed, emit = [], self.game.rule_events.emit
        def record(event):
            if event.destination == "battlefield" and getattr(event.source.card, "name", "") == "Aura":
                observed.append(event.source.aura_host)
            return emit(event)
        self.game.rule_events.emit = record
        self.resolve_mode(eff, self.a.graveyard[0])
        self.assertEqual(observed, [host])
        self.assertIs(next(x for x in self.a.battlefield if x.card.name == "Aura").aura_host, host)

    def test_no_legal_aura_host_leaves_card_in_graveyard(self):
        eff = self.mode("Return target Aura or Equipment card from your graveyard to the battlefield "
                        "attached to a creature you control")
        aura = card("Aura", "{1}", "Enchantment — Aura", "Enchant creature")
        self.a.graveyard.append(aura)
        target = self.a.graveyard[0]
        self.resolve_mode(eff, target)
        self.assertIn(target, self.a.graveyard)

    def test_equipment_enters_unattached_without_a_creature(self):
        eff = self.mode("Return target Aura or Equipment card from your graveyard to the battlefield "
                        "attached to a creature you control")
        self.a.graveyard.append(card("Sword", "{1}", "Artifact — Equipment", ""))
        self.resolve_mode(eff, self.a.graveyard[0])
        self.assertIsNone(next(x for x in self.a.battlefield if x.card.name == "Sword").attached_to)

    def test_a_target_leaving_and_returning_fizzles(self):
        eff = self.mode("Return target creature card from your graveyard to the battlefield")
        self.a.graveyard.append(card("Creature", "{1}", "Creature — Human", "", 1, 1))
        target = self.a.graveyard[0]
        effects = protect_graveyard_targets(self.game, [eff], [target])
        item = StackItem(self.a, effects, [target], card=card("Spell", "{1}", "Sorcery", ""))
        self.game.stack.append(item)
        self.game.move_card(target, self.a.graveyard, self.a.hand)
        self.game.move_card(target, self.a.hand, self.a.graveyard)
        self.game.resolve_top()
        self.assertFalse(item.resolved)

    def test_partial_legality_of_multiple_modes(self):
        first = self.mode("Return target creature card from your graveyard to the battlefield")
        second = self.mode("Return target Mount or Vehicle card from your graveyard to the battlefield")
        self.a.graveyard.extend([card("Human", "{1}", "Creature — Human", "", 1, 1),
                                 card("Vehicle", "{2}", "Artifact — Vehicle", "", 3, 3)])
        a, b = self.a.graveyard
        effects = protect_graveyard_targets(self.game, [first, second], [a, b])
        item = StackItem(self.a, effects, [a, b], card=card("Spell", "{1}", "Sorcery", ""))
        self.game.stack.append(item)
        self.game.move_card(a, self.a.graveyard, self.a.exile)
        self.game.resolve_top()
        self.assertTrue(item.resolved)
        self.assertTrue(any(x.card.name == "Vehicle" for x in self.a.battlefield))

    def test_same_card_can_target_distinct_modes(self):
        first = self.mode("Return target creature card from your graveyard to the battlefield")
        second = self.mode("Return target Mount or Vehicle card from your graveyard to the battlefield")
        self.a.graveyard.append(card("Mount", "{1}", "Creature — Horse Mount", "", 1, 1))
        target = self.a.graveyard[0]
        self.assertTrue(self.game.valid_action_targets(self.a, [first, second], [target, target]))


class ReturnedCreatureAttachments(Base):
    def spell_and_cards(self, toughness=2):
        text = ("Return target creature card from your graveyard to the battlefield, then return up to two target "
                "Aura and/or Equipment cards from your graveyard to the battlefield attached to that creature.")
        spell = self.spell(text, types="Sorcery")
        creature = card("Host", "{1}", "Creature — Human", "", 2, toughness)
        aura = card("Aura", "{1}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1.")
        equipment = card("Sword", "{1}", "Artifact — Equipment", "")
        self.a.graveyard.extend([creature, aura, equipment])
        return spell, list(self.a.graveyard)

    def resolve_targets(self, spell, targets, before=None):
        effects = protect_graveyard_targets(self.game, spell.spell_effects, targets)
        item = StackItem(self.a, effects, targets, card=spell, kind="spell")
        self.game.stack.append(item)
        if before:
            before()
        self.game.resolve_top()
        return item

    def test_returns_attachments_to_the_actual_returned_creature(self):
        spell, (host_card, aura_card, sword_card) = self.spell_and_cards()
        other = self.perm(card("Other", "{5}", "Creature — Human", "", 5, 5), self.a)
        self.resolve_targets(spell, [host_card, aura_card, sword_card, None])
        host = next(p for p in self.a.creatures if p.card.name == "Host")
        aura = next(p for p in self.a.battlefield if p.card.name == "Aura")
        sword = next(p for p in self.a.battlefield if p.card.name == "Sword")
        self.assertIs(aura.aura_host, host)
        self.assertIs(sword.attached_to, host)
        self.assertIsNot(host, other)

    def test_aura_can_save_zero_toughness_host_before_state_actions(self):
        spell, (host_card, aura_card, _) = self.spell_and_cards(toughness=0)
        self.resolve_targets(spell, [host_card, aura_card, None, None])
        host = next(p for p in self.a.battlefield if p.card.name == "Host")
        self.assertEqual(host.toughness, 1)

    def test_invalid_host_leaves_aura_but_equipment_enters_unattached(self):
        spell, (host_card, aura_card, sword_card) = self.spell_and_cards()
        item = self.resolve_targets(spell, [host_card, aura_card, sword_card, None],
                                    lambda: self.game.move_card(host_card, self.a.graveyard, self.a.exile))
        self.assertTrue(item.resolved)
        self.assertIn(aura_card, self.a.graveyard)
        sword = next(p for p in self.a.battlefield if p.card.name == "Sword")
        self.assertIsNone(sword.attached_to)

    def test_an_illegal_attachment_does_not_stop_other_targets(self):
        spell, (host_card, aura_card, sword_card) = self.spell_and_cards()
        self.resolve_targets(spell, [host_card, aura_card, sword_card, None],
                             lambda: self.game.move_card(aura_card, self.a.graveyard, self.a.exile))
        host = next(p for p in self.a.battlefield if p.card.name == "Host")
        sword = next(p for p in self.a.battlefield if p.card.name == "Sword")
        self.assertIs(sword.attached_to, host)

    def test_attachment_slots_must_be_distinct(self):
        spell, (host_card, aura_card, _) = self.spell_and_cards()
        self.assertFalse(self.game.valid_action_targets(self.a, spell.spell_effects,
                                                       [host_card, aura_card, aura_card, None]))
