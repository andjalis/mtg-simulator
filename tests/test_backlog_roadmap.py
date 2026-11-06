"""Behavior evidence for all ten residual capability tasks in the saved backlog."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.cards import Effect, _parse_effects, make_token
from mtgsim.engine import Game, Player, StackItem, TARGETED
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, FOREST, MOUNTAIN, card

HARVESTER = card('Harvester of Souls', '{4}{B}{B}', 'Creature — Demon',
                 'Deathtouch\nWhenever another nontoken creature dies, you may draw a card.', 5, 5)
VAMPIRE = card('Welcoming Vampire', '{2}{W}', 'Creature — Vampire',
               'Flying\nWhenever one or more other creatures you control with power 2 or less enter, '
               'draw a card. This ability triggers only once each turn.', 2, 3)
MENTOR = card('Mentor of the Meek', '{2}{W}', 'Creature — Human Soldier',
              'Whenever another creature you control with power 2 or less enters, you may pay {1}. '
              'If you do, draw a card.', 2, 2)
GROWTH = card('Abundant Growth', '{G}', 'Enchantment — Aura',
              'Enchant land\nWhen Abundant Growth enters, draw a card.\n'
              'Enchanted land has "{T}: Add one mana of any color."')
SLIVER = card('Acidic Sliver', '{B}{R}', 'Creature — Sliver',
              'All Slivers have "{2}, Sacrifice this creature: This creature deals 2 damage to any target."', 2, 2)
MUTATION = card('Accelerated Mutation', '{3}{G}{G}', 'Instant',
                'Target creature gets +X/+X until end of turn, where X is the highest mana value among permanents you control.')
ELITE = card('Academy Elite', '{3}{U}', 'Creature — Human Wizard',
             'Academy Elite enters with X +1/+1 counters on it, where X is the number of instant and sorcery cards '
             'in all graveyards.\n{2}{U}, Remove a +1/+1 counter from Academy Elite: Draw a card, then discard a card.', 0, 0)
BIOSHIFT = card('Bioshift', '{G/U}', 'Instant',
                'Move any number of +1/+1 counters from target creature onto another target creature with the same controller.')
GUILD = card('Simic Guildmage', '{G/U}{G/U}', 'Creature — Elf Wizard',
             '{1}{G}: Move a +1/+1 counter from target creature onto another target creature with the same controller.\n'
             '{1}{U}: Attach target Aura attached to a permanent to another permanent with the same controller.', 2, 2)
ABUELO = card('Abuelo, Ancestral Echo', '{1}{W}{U}', 'Legendary Creature — Spirit',
              'Flying\nWard {2}\n{1}{W}{U}: Exile another target creature or artifact you control. Return it to the '
              "battlefield under its owner's control at the beginning of the next end step.", 2, 2)
GRACE = card('Abiding Grace', '{2}{W}', 'Enchantment',
             'At the beginning of your end step, choose one —\n• You gain 1 life.\n'
             '• Return target creature card with mana value 1 from your graveyard to the battlefield.')
DEALER = card('Arms Dealer', '{2}{R}', 'Creature — Goblin Rogue',
              '{1}{R}, Sacrifice a Goblin: Arms Dealer deals 4 damage to target creature.', 1, 1)
AJANI = card('Ajani Resolute', '{4}{W}{W}', 'Legendary Planeswalker — Ajani',
             '+2: You gain 2 life.\n−4: Create a 2/2 white Cat Soldier creature token named Ajani\'s Pridemate '
             'with "Whenever you gain life, put a +1/+1 counter on this creature."')
SPINNERS = card('Glamer Spinners', '{4}{W/U}', 'Creature — Faerie Wizard',
                'Flash\nFlying\nWhen Glamer Spinners enters, attach all Auras enchanting target permanent to '
                'another permanent with the same controller.', 2, 4)
ARBITER = card('Silent Arbiter', '{4}', 'Artifact Creature — Construct',
               'No more than one creature can attack each combat.\nNo more than one creature can block each combat.', 1, 5)
ABEYANCE = card('Abeyance', '{1}{W}', 'Instant',
                "Until end of turn, target player can't cast instant or sorcery spells, and that player can't "
                "activate abilities that aren't mana abilities.\nDraw a card.")
AURA = card('Test Blessing', '{W}', 'Enchantment — Aura', 'Enchant creature\nEnchanted creature gets +1/+1.')
ONE = card('One drop', '{W}', 'Creature — Human', '', 1, 1)


class Roadmap(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(7))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 50
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None
            p.ai.choose_graft = lambda *args: False

    def put(self, definition=BEAR, who=None, counters=None, settle=True):
        result = self.g.enter_battlefield(who or self.a, definition, counters=counters)
        result.sick = False
        if settle:
            self.g.settle()
        return result

    def lands(self, who=None):
        return [self.put(c, who) for c in (ISLAND, FOREST, MOUNTAIN, ISLAND)]

    def attach(self, host, definition=AURA, who=None):
        self.g._aura_host = host
        return self.put(definition, who)

    def apply(self, text, targets=(), source=None, settle=True):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad)
        self.assertTrue(effects)
        targets = iter(targets)
        chosen = [next(targets, None) if e.target in TARGETED else None for e in effects]
        item = StackItem(self.a, effects, chosen, source=source, kind='ability')
        self.g.stack.append(item)
        self.g.check_ward(item)
        if settle:
            self.g.settle()
        return item

    def activate(self, source, index, targets, settle=True):
        if not settle:
            with patch.object(self.g, 'settle'):
                return self.g.activate_ability(source.controller, source, index, targets)
        return self.g.activate_ability(source.controller, source, index, targets)

    def endstep(self):
        self.g.begin_end_step(self.a)
        self.g.settle()

    def cleanup(self):
        with patch.object(self.g, 'main_phase'), patch.object(self.g, 'combat'):
            self.g.take_turn(self.b)

    def test_all_recorded_fixture_clauses_match(self):
        for definition in (HARVESTER, VAMPIRE, MENTOR, GROWTH, SLIVER, MUTATION, ELITE, BIOSHIFT, GUILD,
                           ABUELO, GRACE, DEALER, AJANI, SPINNERS, ARBITER, ABEYANCE):
            with self.subTest(card=definition.name):
                self.assertEqual(definition.unsupported, [])
                self.assertEqual(definition.approximations, [])

    def test_death_filter_sees_enemy_nontoken_but_not_tokens(self):
        self.put(HARVESTER)
        creature = self.put(who=self.b)
        token = self.put(make_token('Soldier', 1, 1), self.b)
        self.g.destroy(token)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 0)
        self.g.destroy(creature)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_death_filter_does_not_see_itself(self):
        source = self.put(HARVESTER)
        self.g.destroy(source)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 0)

    def test_simultaneous_wrath_preserves_dead_watcher(self):
        self.put(HARVESTER)
        self.put()
        self.put(who=self.b)
        self.g.resolve(self.a, Effect('wrath'), None)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 2)

    def test_simultaneous_death_filter_uses_pre_wrath_power(self):
        self.put(card('Watcher', '', 'Enchantment', 'Whenever another creature with power 2 or less dies, draw a card.'))
        self.put(card('Anthem Creature', '', 'Creature', 'Creatures you control get +1/+1.', 1, 1))
        self.put()
        self.g.resolve(self.a, Effect('wrath'), None)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_filtered_death_once_per_turn_keeps_stable_trigger_identity(self):
        self.put(card('Watcher', '', 'Enchantment', 'Whenever another creature with power 2 or less dies, draw a card. This ability triggers only once each turn.'))
        self.put()
        self.put()
        self.g.resolve(self.a, Effect('wrath'), None)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.g.turn += 1
        victim = self.put()
        self.g.destroy(victim)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 2)

    def test_suppressed_death_watcher_does_not_trigger(self):
        source = self.put(HARVESTER)
        source.silenced_by = self.put()
        victim = self.put(who=self.b)
        self.g.destroy(victim)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 0)

    def test_exile_does_not_trigger_death(self):
        self.put(HARVESTER)
        victim = self.put(who=self.b)
        self.g.leave_battlefield(victim, 'exile')
        self.g.settle()
        self.assertEqual(len(self.a.hand), 0)

    def test_entry_filter_uses_current_power_including_counters(self):
        self.put(VAMPIRE)
        self.put(counters={'+1/+1': 1})
        self.assertEqual(len(self.a.hand), 0)
        self.put()
        self.assertEqual(len(self.a.hand), 1)

    def test_entry_once_per_turn_allows_only_one_even_for_tokens(self):
        self.put(VAMPIRE)
        self.g.resolve(self.a, Effect('token', 3, data={'name': 'Soldier', 'power': 1, 'toughness': 1}), None)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.g.turn += 1
        self.put()
        self.assertEqual(len(self.a.hand), 2)

    def test_grouped_entry_is_once_per_batch_without_once_per_turn(self):
        self.put(card('Group watcher', '', 'Enchantment', 'Whenever one or more other creatures you control enter, draw a card.'))
        token = Effect('token', 3, data={'name': 'Soldier', 'power': 1, 'toughness': 1})
        self.g.resolve(self.a, token, None)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.g.resolve(self.a, token, None)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 2)

    def test_grouped_entry_batch_observers_entering_together_see_the_batch(self):
        definition = card('Batch watcher', '', 'Creature', 'Whenever one or more other creatures you control enter, draw a card.', 1, 1)
        self.g.enter_battlefield_many(self.a, [definition, BEAR, BEAR])
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_grouped_entry_sees_mass_reanimation_as_one_batch(self):
        self.put(card('Group watcher', '', 'Enchantment', 'Whenever one or more other creatures you control enter, draw a card.'))
        self.a.graveyard.extend([BEAR, BEAR])
        self.apply('Return all creature cards from your graveyard to the battlefield.')
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(len(self.a.creatures), 2)

    def test_grouped_entry_sees_multiple_copies_as_one_batch(self):
        self.put(card('Group watcher', '', 'Enchantment', 'Whenever one or more other creatures you control enter, draw a card.'))
        self.put()
        self.a.hand.clear()
        self.apply('Create two tokens that are copies of target creature you control.')
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(len(self.a.creatures), 3)

    def test_grouped_death_is_once_per_destruction_batch(self):
        self.put(card('Group watcher', '', 'Enchantment', 'Whenever one or more other creatures die, draw a card.'))
        self.put()
        self.put()
        self.g.resolve(self.a, Effect('wrath'), None)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)
        victim = self.put()
        self.g.destroy(victim)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 2)

    def test_filtered_artifact_death_uses_same_generic_subject_path(self):
        self.put(card('Artifact watcher', '', 'Enchantment', 'Whenever another artifact dies, draw a card.'))
        artifact = self.put(card('Artifact victim', '', 'Artifact', ''))
        self.g.destroy(artifact)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_entry_filter_excludes_enemy_and_itself(self):
        self.put(VAMPIRE)
        self.put(who=self.b)
        self.assertEqual(len(self.a.hand), 0)

    def test_mentor_payments_are_optional_and_for_each_entry(self):
        self.put(MENTOR)
        self.put()
        self.assertEqual(len(self.a.hand), 0)
        self.put(ISLAND)
        self.put()
        self.assertEqual(len(self.a.hand), 1)
        self.put()
        self.assertEqual(len(self.a.hand), 1)

    def test_filtered_entry_intervening_condition_checked_at_both_times(self):
        self.put(card('Watcher', '', 'Enchantment', 'Whenever another creature you control with power 2 or less enters, if you control an artifact, draw a card.'))
        self.put(settle=False)
        rock = self.put(card('Rock', '', 'Artifact', ''), settle=False)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 0)
        self.put(settle=False)
        self.g.destroy(rock)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 0)

    def test_entry_filter_is_not_rechecked_after_trigger(self):
        self.put(VAMPIRE)
        obj = self.put(settle=False)
        obj.counters['+1/+1'] = 3
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_growth_grants_host_mana_and_ends_on_source_departure(self):
        host = self.put(FOREST)
        aura = self.attach(host, GROWTH)
        self.assertTrue(self.g.can_pay(self.a, {'W': 1}))
        self.assertIsNotNone(self.g.pay(self.a, {'W': 1}))
        self.assertTrue(host.tapped)
        host.tapped = False
        self.g.destroy(aura)
        self.assertFalse(self.g.can_pay(self.a, {'W': 1}))
        self.assertTrue(self.g.can_pay(self.a, {'G': 1}))

    def test_suppressed_growth_source_does_not_grant_mana(self):
        host = self.put(FOREST)
        aura = self.attach(host, GROWTH)
        aura.silenced_by = self.put()
        self.assertFalse(self.g.can_pay(self.a, {'W': 1}))

    def test_team_ability_grant_affects_both_players_and_not_other_types(self):
        source = self.put(SLIVER)
        enemy = self.put(card('Sliver fixture', '', 'Creature — Sliver', '', 2, 2), self.b)
        other = self.put()
        self.assertEqual((len(source.activated), len(enemy.activated), len(other.activated)), (1, 1, 0))
        self.lands(self.b)
        self.assertTrue(self.activate(enemy, 0, [self.a]))
        self.assertEqual(self.a.life, 18)
        self.assertNotIn(enemy, self.b.battlefield)

    def test_granted_ability_uses_recipient_as_sacrificed_source(self):
        source = self.put(SLIVER)
        other = self.put(card('Sliver fixture', '', 'Creature — Sliver', '', 2, 2))
        self.lands()
        self.assertTrue(self.activate(other, 0, [self.b]))
        self.assertEqual(self.b.life, 18)
        self.assertIn(source, self.a.battlefield)
        self.assertNotIn(other, self.a.battlefield)

    def test_grant_removed_with_source_but_stacked_ability_survives(self):
        source = self.put(SLIVER)
        other = self.put(card('Sliver fixture', '', 'Creature — Sliver', '', 2, 2))
        self.lands()
        self.assertTrue(self.activate(other, 0, [self.b], settle=False))
        self.g.destroy(source)
        self.g.settle()
        self.assertEqual(self.b.life, 18)

    def test_losing_abilities_suppresses_recipient_grants(self):
        self.put(SLIVER)
        other = self.put(card('Sliver fixture', '', 'Creature — Sliver', '', 2, 2))
        other.silenced_by = self.put()
        self.assertEqual(other.activated, [])

    def test_temporary_granted_activated_ability_expires(self):
        obj = self.put()
        self.apply('Target creature gains "{T}: Draw a card." until end of turn.', [obj])
        self.assertTrue(self.activate(obj, 0, None))
        self.assertEqual(len(self.a.hand), 1)
        self.cleanup()
        self.assertEqual(obj.activated, [])

    def test_unknown_granted_ability_body_stays_unsupported(self):
        definition = card('Bad grant', '', 'Enchantment', 'Creatures you control have "{T}: Do something unknown."')
        self.assertTrue(definition.unsupported)

    def test_quantity_pump_evaluates_board_at_resolution(self):
        target = self.put()
        biggest = self.put(card('Big Rock', '{7}', 'Artifact', ''))
        self.apply(MUTATION.oracle, [target], settle=False)
        self.g.destroy(biggest)
        self.put(card('Small Rock', '{4}', 'Artifact', ''), settle=False)
        self.g.settle()
        self.assertEqual((target.power, target.toughness), (6, 6))

    def test_quantity_pump_empty_board_or_scope(self):
        enemy = self.put(who=self.b)
        self.apply(MUTATION.oracle, [enemy])
        self.assertEqual(enemy.power, 2)

    def test_quantity_pump_expires_in_cleanup(self):
        target = self.put()
        self.put(card('Rock', '{4}', 'Artifact', ''))
        self.apply(MUTATION.oracle, [target])
        self.cleanup()
        self.assertEqual(target.power, 2)

    def test_entry_quantity_counts_both_graveyards_once_per_card(self):
        self.a.graveyard.append(card('Instant', '', 'Instant', ''))
        self.b.graveyard.append(card('Sorcery', '', 'Sorcery', ''))
        self.b.graveyard.append(BEAR)
        obj = self.put(ELITE)
        self.assertEqual(obj.p1, 2)
        self.a.graveyard.append(card('Another', '', 'Instant', ''))
        self.assertEqual(obj.p1, 2)

    def test_entry_quantity_zero_dies_as_state_based_action(self):
        obj = self.put(ELITE)
        self.assertNotIn(obj, self.a.battlefield)

    def test_unknown_quantity_is_not_assumed_to_be_mana_x(self):
        definition = card('Bad X', '', 'Instant', 'Target creature gets +X/+X until end of turn, where X is the number of mysteries.')
        self.assertTrue(definition.unsupported)

    def test_counter_transfer_moves_selected_quantity_and_allows_zero(self):
        first = self.put(counters={'+1/+1': 3})
        second = self.put()
        self.a.ai.choose_counter_transfer = lambda *args: 2
        self.apply(BIOSHIFT.oracle, [first, second])
        self.assertEqual((first.p1, second.p1), (1, 2))
        self.a.ai.choose_counter_transfer = lambda *args: 0
        self.apply(BIOSHIFT.oracle, [first, second])
        self.assertEqual((first.p1, second.p1), (1, 2))

    def test_counter_transfer_rejects_same_target_and_different_controllers(self):
        first = self.put(counters={'+1/+1': 3})
        enemy = self.put(who=self.b)
        effects, bad = _parse_effects(BIOSHIFT.oracle)
        self.assertFalse(bad)
        self.assertFalse(self.g.valid_action_targets(self.a, effects, [first, first]))
        self.assertFalse(self.g.valid_action_targets(self.a, effects, [first, enemy]))

    def test_spell_partial_target_choices_preserve_anchor_relationship(self):
        first = self.put(counters={'+1/+1': 2})
        second = self.put()
        self.a.hand.append(BIOSHIFT)
        self.lands()
        self.assertTrue(self.g.cast(self.a, BIOSHIFT, [first, None]))
        self.g.settle()
        self.assertEqual(first.p1 + second.p1, 2)
        self.assertEqual(first.p1, 0)

    def test_pilots_can_cast_relationship_spell_automatically(self):
        for pilot in (HeuristicAI, BaselineAI):
            with self.subTest(pilot=pilot.__name__):
                self.setUp()
                self.a.ai = pilot()
                first = self.put(counters={'+1/+1': 2})
                second = self.put()
                self.a.hand.append(BIOSHIFT)
                self.lands()
                self.g.main_phase(self.a)
                self.assertNotIn(BIOSHIFT, self.a.hand)
                self.assertEqual((first.p1, second.p1), (0, 2))

    def test_relationship_ability_valuation_keeps_earlier_choices(self):
        from mtgsim.engine.policy import ability_worth
        source = self.put(GUILD)
        self.put(counters={'+1/+1': 1})
        self.put()
        self.lands()
        self.assertTrue(ability_worth(self.g, self.a, source, 0))
        self.assertEqual(getattr(self.g, '_choosing_targets', []), [])

    def test_counter_transfer_rechecks_controller_relationship(self):
        first = self.put(counters={'+1/+1': 3})
        second = self.put()
        self.apply(BIOSHIFT.oracle, [first, second], settle=False)
        from mtgsim.counter_mechanics import change_control
        change_control(self.g, second, self.b)
        self.g.settle()
        self.assertEqual((first.p1, second.p1), (3, 0))

    def test_counter_transfer_does_not_remove_if_recipient_left(self):
        first = self.put(counters={'+1/+1': 3})
        second = self.put()
        self.apply(BIOSHIFT.oracle, [first, second], settle=False)
        self.g.leave_battlefield(second, 'hand')
        self.g.settle()
        self.assertEqual(first.p1, 3)

    def test_counter_transfer_does_not_add_if_donor_illegal(self):
        first = self.put(counters={'+1/+1': 3})
        second = self.put()
        self.apply(BIOSHIFT.oracle, [first, second], settle=False)
        first.temp_kw.add('shroud')
        self.g.settle()
        self.assertEqual((first.p1, second.p1), (3, 0))

    def test_guildmage_fixed_transfer_no_counter_is_legal_noop(self):
        source = self.put(GUILD)
        first, second = self.put(), self.put()
        self.lands()
        self.assertTrue(self.activate(source, 0, [first, second]))
        self.assertEqual((first.p1, second.p1), (0, 0))

    def test_counter_transfer_finishes_before_donor_dies(self):
        first = self.put(card('Counter creature', '', 'Creature', '', 0, 0), counters={'+1/+1': 2})
        second = self.put()
        self.apply(BIOSHIFT.oracle, [first, second])
        self.assertNotIn(first, self.a.battlefield)
        self.assertEqual(second.p1, 2)

    def test_blink_returns_exact_card_at_next_end_step_under_owner(self):
        obj = self.put(who=self.b, counters={'+1/+1': 2})
        from mtgsim.counter_mechanics import change_control
        change_control(self.g, obj, self.a)
        self.apply("Exile another target creature or artifact you control. Return it to the battlefield under its owner's control at the beginning of the next end step.", [obj], source=self.put())
        self.assertIn(obj.front, self.b.exile)
        self.endstep()
        new = next(x for x in self.b.creatures if x.front is obj.front)
        self.assertIsNot(new, obj)
        self.assertEqual(new.p1, 0)

    def test_blink_return_does_not_follow_card_reentering_exile(self):
        obj = self.put()
        self.apply("Exile target creature. Return it to the battlefield under its owner's control at the beginning of the next end step.", [obj])
        self.g.move_card(obj.front, self.a.exile, self.a.hand)
        self.g.move_card(obj.front, self.a.hand, self.a.exile)
        self.endstep()
        self.assertFalse(self.a.creatures)

    def test_blink_token_does_not_return(self):
        obj = self.put(make_token('Soldier', 1, 1))
        self.apply("Exile target creature. Return it to the battlefield under its owner's control at the beginning of the next end step.", [obj])
        self.endstep()
        self.assertFalse(self.a.creatures)

    def test_blink_during_end_step_waits_for_next_end_step(self):
        self.endstep()
        obj = self.put()
        self.apply("Exile target creature. Return it to the battlefield under its owner's control at the beginning of the next end step.", [obj])
        self.g.settle()
        self.assertFalse(self.a.creatures)
        self.g.begin_end_step(self.b)
        self.g.settle()
        self.assertEqual(len(self.a.creatures), 1)

    def test_blink_can_target_artifact_and_survive_source_departure(self):
        source = self.put(ABUELO)
        target = self.put(card('Rock', '', 'Artifact', ''))
        self.lands()
        # Replace one land with a Plains to pay the white portion.
        self.put(card('Plains', '', 'Basic Land — Plains', ''))
        self.assertTrue(self.activate(source, 0, [target]))
        self.g.destroy(source)
        self.endstep()
        self.assertTrue(any(x.front is target.front for x in self.a.battlefield))

    def test_graveyard_exact_filter_selects_only_one_mana_creatures(self):
        self.a.graveyard.extend([ONE, BEAR, ISLAND])
        effects, bad = _parse_effects('Return target creature card with mana value 1 from your graveyard to the battlefield.')
        self.assertFalse(bad)
        legal = self.g.legal_targets(self.a, effects[0])
        self.assertEqual(len(legal), 1)
        self.assertEqual(legal[0].name, ONE.name)

    def test_graveyard_target_resolves_and_does_not_follow_generation(self):
        self.a.graveyard.append(ONE)
        target = self.a.graveyard[0]
        self.apply('Return target creature card with mana value 1 from your graveyard to the battlefield.', [target], settle=False)
        self.g.move_card(target, self.a.graveyard, self.a.hand)
        self.g.move_card(target, self.a.hand, self.a.graveyard)
        self.g.settle()
        self.assertFalse(self.a.creatures)
        self.apply('Return target creature card with mana value 1 from your graveyard to the battlefield.', [target])
        self.assertEqual(len(self.a.creatures), 1)

    def test_graveyard_target_to_hand_preserves_identity(self):
        self.a.graveyard.append(ONE)
        target = self.a.graveyard[0]
        self.apply('Return target creature card with mana value 1 from your graveyard to your hand.', [target])
        self.assertIs(self.a.hand[0], target)

    def test_subtype_sacrifice_selects_correct_creature_and_pays_jointly(self):
        dealer = self.put(DEALER)
        other = self.put()
        victim = self.put(card('Goblin fixture', '', 'Creature — Goblin', '', 1, 1))
        target = self.put(who=self.b)
        self.lands()
        self.assertTrue(self.activate(dealer, 0, [target]))
        self.assertEqual(sum(x in self.a.battlefield for x in (dealer, victim)), 1)
        self.assertIn(other, self.a.battlefield)
        self.assertNotIn(target, self.b.battlefield)

    def test_subtype_sacrifice_accepts_changeling_and_kindred(self):
        source = self.put(DEALER)
        changeling = self.put(dataclasses.replace(BEAR, changeling=True))
        kindred = self.put(card('Goblin enchantment', '', 'Kindred Enchantment — Goblin', ''))
        ordinary = self.put()
        candidates = self.g.sacrifice_candidates(self.a, source, 'Goblin')
        self.assertIn(changeling, candidates)
        self.assertIn(kindred, candidates)
        self.assertNotIn(ordinary, candidates)

    def test_subtype_sacrifice_excludes_opponents(self):
        source = self.put(card('Elf device', '', 'Artifact', '{1}, Sacrifice an Elf: Draw a card.'))
        self.put(card('Elf fixture', '', 'Creature — Elf', '', 1, 1), self.b)
        self.lands()
        self.assertFalse(self.activate(source, 0, []))

    def test_failed_subtype_activation_does_not_sacrifice_or_spend(self):
        source = self.put(DEALER)
        self.assertFalse(self.activate(source, 0, [self.put(who=self.b)]))
        self.assertIn(source, self.a.battlefield)

    def test_subtype_sacrifice_cannot_spend_same_permanent_as_mana(self):
        source = self.put(card('Device', '', 'Artifact', '{1}, Sacrifice a Goblin: Draw a card.'))
        donor = self.put(dataclasses.replace(make_token('Goblin', 1, 1), produces=frozenset({'C'}), mana_sac_only=True))
        self.assertFalse(self.activate(source, 0, None))
        self.assertIn(donor, self.a.battlefield)
        self.put(ISLAND)
        self.assertTrue(self.activate(source, 0, None))
        self.assertNotIn(donor, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 1)

    def test_named_token_keeps_literal_name_and_trigger_binds_to_each_token(self):
        self.apply('Create two 2/2 white Cat Soldier creature tokens named Ajani\'s Pridemate with "Whenever you gain life, put a +1/+1 counter on ~."')
        self.assertEqual(len(self.a.creatures), 2)
        self.assertTrue(all(x.card.name == "Ajani's Pridemate" for x in self.a.creatures))
        self.g.change_life(self.a, 3, 'test')
        self.g.settle()
        self.assertEqual([x.p1 for x in self.a.creatures], [1, 1])

    def test_named_token_creator_leaving_does_not_remove_token_trigger(self):
        source = self.put(card('Maker', '', 'Creature', '', 2, 2))
        self.apply('Create a 2/2 white Cat Soldier creature token named Cat Friend with "Whenever you gain life, put a +1/+1 counter on ~."', source=source)
        self.g.destroy(source)
        self.g.change_life(self.a, 1, 'test')
        self.g.settle()
        self.assertEqual(self.a.creatures[0].p1, 1)

    def test_planeswalker_token_name_not_replaced_with_creator_full_name(self):
        effect = AJANI.loyalty_abilities[1][1][0]
        self.assertEqual(effect.data['token_name'], "Ajani's Pridemate")

    def test_unknown_token_trigger_does_not_silently_become_plain_token(self):
        definition = card('Maker', '', 'Instant', 'Create a 2/2 white Cat creature token named Cat Friend with "Whenever you gain life, do something unknown."')
        self.assertTrue(definition.unsupported)

    def test_move_aura_preserves_owner_and_does_not_retrigger_entry(self):
        first, second = self.put(), self.put()
        aura = self.attach(first)
        self.apply('Attach target Aura attached to a permanent to another permanent with the same controller.', [aura, second])
        self.assertIs(aura.aura_host, second)
        self.assertNotIn(aura, first.auras)
        self.assertEqual((first.power, second.power), (2, 3))
        self.assertIs(aura.owner, self.a)

    def test_move_aura_rejects_same_host_and_different_controller(self):
        first = self.put()
        enemy = self.put(who=self.b)
        aura = self.attach(first)
        effects, bad = _parse_effects('Attach target Aura attached to a permanent to another permanent with the same controller.')
        self.assertFalse(bad)
        self.assertFalse(self.g.valid_action_targets(self.a, effects, [aura, first]))
        self.assertFalse(self.g.valid_action_targets(self.a, effects, [aura, enemy]))

    def test_moving_all_auras_only_moves_legal_attachments(self):
        first, second = self.put(), self.put()
        good = self.attach(first)
        controlled = self.attach(first, card('Mine Aura', '', 'Enchantment — Aura', 'Enchant creature you control'), self.b)
        self.apply('Attach all Auras enchanting target permanent to another permanent with the same controller.', [first, second])
        self.assertIs(good.aura_host, second)
        self.assertIs(controlled.aura_host, first)

    def test_aura_cannot_move_to_wrong_type_or_protection(self):
        first = self.put()
        land = self.put(ISLAND)
        second = self.put()
        aura = self.attach(first)
        self.apply('Attach target Aura attached to a permanent to another permanent with the same controller.', [aura, land])
        self.assertIs(aura.aura_host, first)
        second.temp_kw.add('protection from white')
        self.apply('Attach target Aura attached to a permanent to another permanent with the same controller.', [aura, second])
        self.assertIs(aura.aura_host, first)

    def test_aura_move_does_not_follow_departed_target(self):
        first, second = self.put(), self.put()
        aura = self.attach(first)
        self.apply('Attach all Auras enchanting target permanent to another permanent with the same controller.', [first, second], settle=False)
        self.g.leave_battlefield(second, 'hand')
        self.g.settle()
        self.assertIs(aura.aura_host, first)

    def test_target_relationship_choice_does_not_leak_to_other_actions(self):
        first, second = self.put(counters={'+1/+1': 1}), self.put()
        effects, bad = _parse_effects(BIOSHIFT.oracle)
        self.assertFalse(bad)
        chosen = self.g.auto_targets(self.a, effects)
        self.assertEqual(chosen, [first, second])
        self.assertEqual(getattr(self.g, '_choosing_targets', []), [])

    def test_silent_arbiter_limits_declared_attackers(self):
        self.put(ARBITER, self.b)
        creatures = [self.put() for _ in range(3)]
        self.a.ai.attack = creatures
        self.g.combat(self.a, self.b)
        self.assertEqual(len(self.g.attackers), 1)

    def test_silent_arbiter_limits_blockers_across_all_attackers(self):
        source = self.put(ARBITER, self.b)
        # Leave the block limit while suppressing its attack limit for this scenario.
        source.card = dataclasses.replace(source.card, attack_limit=-1)
        attackers = [self.put(card('Attacker', '', 'Creature', '', 0, 3)) for _ in range(2)]
        blockers = [self.put(card('Blocker', '', 'Creature', '', 0, 5), self.b) for _ in range(2)]
        self.a.ai.attack = attackers
        self.b.ai.block = dict(zip(attackers, ([b] for b in blockers)))
        self.g.combat(self.a, self.b)
        self.assertEqual(len({b for group in self.g.blocks.values() for b in group}), 1)

    def test_combat_limit_ends_when_source_suppressed_or_leaves(self):
        source = self.put(ARBITER, self.b)
        source.silenced_by = self.put()
        creatures = [self.put() for _ in range(3)]
        self.a.ai.attack = creatures
        self.g.combat(self.a, self.b)
        self.assertEqual(len(self.g.attackers), 3)

    def test_zero_attack_limit_prevents_all_declarations(self):
        self.put(card('Peace', '', 'Creature', "Creatures can't attack.", 1, 1))
        self.a.ai.attack = [self.put()]
        self.g.combat(self.a, self.b)
        self.assertEqual(self.g.attackers, [])

    def test_abeyance_blocks_both_cast_legality_and_actual_cast(self):
        self.apply(ABEYANCE.oracle, [self.b])
        spell = card('Spell', '', 'Instant', 'Draw a card.')
        self.b.hand.append(spell)
        self.assertFalse(self.g.can_cast_now(self.b, spell))
        self.assertFalse(self.g.cast(self.b, spell))
        self.assertEqual(len(self.a.hand), 1)

    def test_abeyance_blocks_nonmana_activation_without_paying(self):
        source = self.put(card('Device', '', 'Artifact', '{1}, {T}: Draw a card.'), self.b)
        lands = self.lands(self.b)
        self.apply(ABEYANCE.oracle, [self.b])
        self.assertFalse(self.g.activate_ability(self.b, source, 0))
        self.assertFalse(source.tapped)
        self.assertTrue(all(not p.tapped for p in lands))

    def test_abeyance_leaves_mana_abilities_and_triggered_abilities_working(self):
        self.lands(self.b)
        source = self.put(card('Trigger', '', 'Creature', 'Whenever another creature you control enters, draw a card.', 1, 1), self.b)
        self.apply(ABEYANCE.oracle, [self.b])
        self.assertIsNotNone(self.g.pay(self.b, {'U': 1}))
        self.put(who=self.b)
        self.assertEqual(len(self.b.hand), 1)
        self.assertIn(source, self.b.battlefield)

    def test_abeyance_expires_at_cleanup(self):
        self.apply(ABEYANCE.oracle, [self.a])
        source = self.put(card('Device', '', 'Artifact', '{T}: Draw a card.'))
        self.assertFalse(self.activate(source, 0, []))
        self.cleanup()
        self.assertTrue(self.activate(source, 0, []))

    def test_abeyance_blocks_cycling_until_cleanup(self):
        definition = card('Cycler', '{8}', 'Creature', 'Cycling {1}', 2, 2)
        self.assertTrue(definition.cycling)
        self.a.hand.append(definition)
        self.put(ISLAND)
        self.apply(ABEYANCE.oracle, [self.a])
        self.g.cycle_spare(self.a)
        self.assertIn(definition, self.a.hand)
        self.cleanup()
        self.g.cycle_spare(self.a)
        self.assertNotIn(definition, self.a.hand)
        self.assertIn(definition, self.a.graveyard)

    def test_abeyance_blocks_legacy_graveyard_activation(self):
        definition = card('Recurring card', '', 'Creature', '{1}: Return this card from your graveyard to your hand.', 1, 1)
        self.assertTrue(definition.gy_return)
        self.a.graveyard.append(definition)
        self.put(ISLAND)
        self.apply(ABEYANCE.oracle, [self.a])
        self.g.graveyard_abilities(self.a)
        self.assertIn(definition, self.a.graveyard)
        self.cleanup()
        self.g.graveyard_abilities(self.a)
        self.assertIn(definition, self.a.hand)

    def test_abeyance_does_not_restrict_creature_spells_or_other_player(self):
        self.apply(ABEYANCE.oracle, [self.b])
        creature = card('Free creature', '', 'Creature', '', 2, 2)
        self.b.hand.append(creature)
        self.assertTrue(self.g.cast(self.b, creature))
        spell = card('My Spell', '', 'Instant', 'Draw a card.')
        self.a.hand.append(spell)
        self.assertTrue(self.g.cast(self.a, spell))


if __name__ == '__main__':
    unittest.main()
