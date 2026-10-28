"""Oracle fixtures and timing/identity tests for the ten requested card changes."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim.cards import Effect, make_token
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, PLAINS, SWAMP, FOREST, card


SAGES = card('Novijen Sages', '{4}{U}{U}', 'Creature — Human Mutant',
             'Graft 4\n{1}, Remove two +1/+1 counters from among creatures you control: Draw a card.', 0, 0)
TAYAM = card('Tayam, Luminous Enigma', '{1}{W}{B}{G}', 'Legendary Creature — Nightmare Beast',
             'Each other creature you control enters with an additional vigilance counter on it.\n'
             '{3}, Remove three counters from among creatures you control: Mill three cards, then return a permanent '
             'card with mana value 3 or less from your graveyard to the battlefield.', 3, 3)
RETRIBUTION = card('Retribution of the Ancients', '{B}', 'Enchantment',
                   '{B}, Remove X +1/+1 counters from among creatures you control: Target creature gets -X/-X until end of turn.')
FLUX = card('Ooze Flux', '{2}{G}{G}', 'Enchantment',
            '{1}{G}, Remove one or more +1/+1 counters from among creatures you control: Create an X/X green Ooze '
            'creature token, where X is the number of +1/+1 counters removed this way.')
TRAINEE = card('Parish-Blade Trainee', '{1}{W}', 'Creature — Human Soldier',
               'Training\nWhen Parish-Blade Trainee dies, put its counters on target creature you control.', 1, 2)
SAVIOR = card('Savior of Ollenbock', '{1}{W}{W}', 'Creature — Human Soldier',
              'Training\nWhenever Savior of Ollenbock trains, exile up to one other target creature from the battlefield '
              'or creature card from a graveyard.\nWhen Savior of Ollenbock leaves the battlefield, put the exiled cards '
              "onto the battlefield under their owners' control.", 1, 2)
MARCHESA = card('Marchesa, the Black Rose', '{1}{U}{B}{R}', 'Legendary Creature — Human Wizard',
                'Dethrone\nOther creatures you control have dethrone.\nWhenever a creature you control with a +1/+1 '
                'counter on it dies, return that card to the battlefield under your control at the beginning of the next end step.', 3, 3)
SCOURGE = card('Scourge of the Throne', '{4}{R}{R}', 'Creature — Dragon',
               "Flying\nDethrone\nWhenever Scourge of the Throne attacks for the first time each turn, if it's attacking "
               'the player with the most life or tied for most life, untap all attacking creatures. After this phase, '
               'there is an additional combat phase.', 5, 5)
CAVALRY = card('Gryffwing Cavalry', '{3}{W}', 'Creature — Human Knight',
               'Flying\nTraining\nWhenever Gryffwing Cavalry attacks, you may pay {1}{W}. If you do, another target '
               'attacking creature without flying gains flying until end of turn.', 2, 2)


class CounterCardBatch(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(7), log=True)
        self.g.turn, self.g.step = 2, 'main1'
        for player in (self.a, self.b):
            player.library = [ISLAND] * 50
            player.ai.attack, player.ai.block = (), {}

    def put(self, definition=BEAR, who=None, counters=None, settle=True):
        result = self.g.enter_battlefield(who or self.a, definition, counters=counters)
        result.sick = False
        if settle:
            self.g.settle()
        return result

    def lands(self, *definitions):
        return [self.put(c) for c in definitions]

    def fight(self, attackers):
        self.a.ai.attack = attackers
        self.g.combat(self.a, self.b)
        self.g.settle()

    def declare(self, attackers, defender=None):
        self.g.attackers = list(attackers)
        self.g.attack_targets = {a: defender or self.b for a in attackers}
        for attacker in attackers:
            attacker.tapped = True
            self.g.fire(self.a, 'attacks', attacker)
        self.g.flush_triggers()

    def end_step(self, player=None):
        self.g.begin_end_step(player or self.a)
        self.g.settle()

    def test_all_nine_oracle_fixtures_are_fully_template_matched(self):
        for definition in (SAGES, TAYAM, RETRIBUTION, FLUX, TRAINEE, SAVIOR, MARCHESA, SCOURGE, CAVALRY):
            with self.subTest(card=definition.name):
                self.assertEqual(definition.unsupported, [])
                self.assertEqual(definition.approximations, [])

    def test_graft_enters_with_counters_and_moves_one(self):
        source = self.put(SAGES)
        self.assertEqual(source.p1, 4)
        self.assertIn(source, self.a.battlefield)
        recipient = self.put()
        self.assertEqual((source.p1, recipient.p1), (3, 1))

    def test_graft_is_optional_and_can_move_to_an_opponent(self):
        source = self.put(SAGES)
        self.a.ai.choose_graft = lambda *args: False
        ally = self.put()
        self.assertEqual((source.p1, ally.p1), (4, 0))
        self.a.ai.choose_graft = lambda *args: True
        enemy = self.put(who=self.b)
        self.assertEqual((source.p1, enemy.p1), (3, 1))

    def test_multiple_graft_instances_add_entry_counters_and_separate_triggers(self):
        source = self.put(card('Double Graft', types='Creature', text='Graft 2\nGraft 3', power=0, toughness=0))
        self.assertEqual(source.p1, 5)
        recipient = self.put()
        self.assertEqual((source.p1, recipient.p1), (3, 2))

    def test_graft_defaults_to_declining_opponent_transfer(self):
        source = self.put(SAGES)
        enemy = self.put(who=self.b)
        self.assertEqual((source.p1, enemy.p1), (4, 0))

    def test_graft_last_counter_can_kill_source(self):
        definition = dataclasses.replace(SAGES, name='Small Graft', graft=1)
        source = self.put(definition)
        recipient = self.put()
        self.assertNotIn(source, self.a.battlefield)
        self.assertEqual(recipient.p1, 1)

    def test_graft_source_or_recipient_leaving_stops_the_move(self):
        source = self.put(SAGES)
        recipient = self.put(settle=False)
        self.g.leave_battlefield(recipient, 'hand')
        self.g.settle()
        self.assertEqual(source.p1, 4)
        recipient = self.put(settle=False)
        self.g.leave_battlefield(source, 'graveyard')
        self.g.settle()
        self.assertEqual(recipient.p1, 0)

    def test_graft_no_counter_left_does_nothing(self):
        source = self.put(dataclasses.replace(SAGES, power=1, toughness=1))
        recipient = self.put(settle=False)
        source.counters['+1/+1'] = 0
        self.g.settle()
        self.assertEqual(recipient.p1, 0)

    def mute(self, source):
        aura = dataclasses.replace(card('Mute Aura', types='Enchantment — Aura'), aura='creature',
                                   aura_flags=frozenset({'loses_abilities'}))
        self.g._aura_host = source
        return self.put(aura)

    def test_losing_abilities_stops_new_graft_triggers(self):
        source = self.put(SAGES)
        self.mute(source)
        recipient = self.put()
        self.assertEqual((source.p1, recipient.p1), (4, 0))

    def test_silenced_death_trigger_uses_last_known_abilities(self):
        source = self.put(TRAINEE, counters={'+1/+1': 2})
        target = self.put()
        self.mute(source)
        self.g.dies(source)
        self.g.settle()
        self.assertEqual(target.p1, 0)

    def test_training_trigger_survives_silence_but_does_not_trigger_lost_trains_ability(self):
        source, enemy = self.put(SAVIOR), self.put(who=self.b)
        ally = self.put()
        self.declare([source, ally])
        self.mute(source)
        self.g.settle()
        self.assertEqual(source.p1, 1)
        self.assertIn(enemy, self.b.battlefield)

    def test_novijen_sages_can_draw_using_graft_counters(self):
        source = self.put(SAGES)
        self.lands(ISLAND)
        before = len(self.a.hand)
        self.assertTrue(self.g.activate_ability(self.a, source, 0))
        self.assertEqual(source.p1, 2)
        self.assertEqual(len(self.a.hand), before + 1)

    def test_tayam_entry_counters_and_mixed_counter_payment(self):
        source = self.put(TAYAM)
        donor = self.put(counters={'charge': 2, '+1/+1': 1})
        self.assertEqual(donor.counters['vigilance'], 1)
        self.assertTrue(donor.has('vigilance'))
        self.assertEqual(source.counters.get('vigilance', 0), 0)
        self.lands(PLAINS, PLAINS, PLAINS)
        self.a.library = [ISLAND, card('Fresh Artifact', '{2}', 'Artifact'), ISLAND]
        self.assertTrue(self.g.activate_ability(self.a, source, 0,
                                               counter_choices=[(donor, 'charge', 2), (donor, 'vigilance', 1)]))
        self.assertEqual(donor.p1, 1)
        self.assertEqual(donor.counters['charge'], 0)
        self.assertEqual(donor.counters['vigilance'], 0)
        self.assertTrue(any(x.card.name == 'Fresh Artifact' for x in self.a.battlefield))
        self.assertEqual(len(self.a.graveyard), 2)

    def test_tayam_cannot_use_opponents_or_missing_counters(self):
        source = self.put(TAYAM)
        enemy = self.put(who=self.b, counters={'charge': 3})
        mana = self.lands(PLAINS, PLAINS, PLAINS)
        self.assertFalse(self.g.activate_ability(self.a, source, 0, counter_choices=[(enemy, 'charge', 3)]))
        self.assertFalse(self.g.activate_ability(self.a, source, 0))
        self.assertTrue(all(not p.tapped for p in mana))
        self.assertEqual(enemy.counters['charge'], 3)

    def test_explicit_counter_choices_cannot_double_spend(self):
        source = self.put(TAYAM)
        donor = self.put(counters={'charge': 2})
        mana = self.lands(PLAINS, PLAINS, PLAINS)
        self.assertFalse(self.g.activate_ability(self.a, source, 0,
                                                counter_choices=[(donor, 'charge', 2), (donor, 'charge', 1)]))
        self.assertEqual(donor.counters['charge'], 2)
        self.assertTrue(all(not p.tapped for p in mana))

    def storage_creature(self, count):
        definition = dataclasses.replace(card('Storage Creature Land', types='Land', text='{T}: Add {C}.'),
                                         storage={'colors': frozenset({'C'})})
        donor = self.put(definition, counters={'storage': count})
        self.g.add_continuous_effect(donor, 'add_types', types={'Creature'})
        self.g.add_continuous_effect(donor, 'set_base', power=1, toughness=2)
        donor.sick = False
        return donor

    def test_storage_counter_cannot_pay_both_mana_and_counter_cost(self):
        source = self.put(TAYAM)
        donor = self.storage_creature(4)
        land = self.lands(PLAINS)[0]
        self.assertFalse(self.g.can_activate(self.a, source, 0))
        self.assertFalse(self.g.activate_ability(self.a, source, 0))
        self.assertEqual(donor.counters['storage'], 4)
        self.assertFalse(donor.tapped or land.tapped)

    def test_unreserved_storage_counter_can_pay_mana(self):
        source = self.put(TAYAM)
        donor = self.storage_creature(4)
        self.lands(PLAINS, PLAINS)
        self.assertTrue(self.g.activate_ability(self.a, source, 0,
                                               counter_choices=[(donor, 'storage', 3)]))
        self.assertEqual(donor.counters['storage'], 0)  # one spent for mana, three for Tayam

    def test_reserving_all_storage_counters_still_allows_the_lands_regular_mana(self):
        source = self.put(TAYAM)
        donor = self.storage_creature(3)
        self.lands(PLAINS, PLAINS)
        self.assertTrue(self.g.activate_ability(self.a, source, 0))
        self.assertEqual(donor.counters['storage'], 0)
        self.assertTrue(donor.tapped)

    def test_retribution_x_is_counter_payment_not_mana(self):
        source = self.put(RETRIBUTION)
        donor = self.put(counters={'+1/+1': 3})
        target = self.put(card('Big Body', types='Creature', power=5, toughness=5), self.b)
        self.lands(SWAMP)
        self.assertTrue(self.g.activate_ability(self.a, source, 0, [target], x=2))
        self.assertEqual(donor.p1, 1)
        self.assertEqual((target.power, target.toughness), (3, 3))

    def test_retribution_default_pilot_and_automatic_targets_use_counter_x(self):
        from mtgsim.engine.policy import choose_ability
        source = self.put(RETRIBUTION)
        donor = self.put(counters={'+1/+1': 2})
        target = self.put(who=self.b)
        self.lands(SWAMP)
        action = choose_ability(self.g, self.a, False)
        self.assertIsNotNone(action)
        self.assertIs(action[1], source)
        self.assertTrue(self.g.can_perform(self.a, action))
        self.assertEqual(donor.p1, 2)
        self.assertTrue(self.g.do_action(self.a, action))
        self.assertEqual(donor.p1, 0)
        self.assertNotIn(target, self.b.battlefield)

    def test_retribution_allows_zero_but_rejects_excess_or_negative_x(self):
        source = self.put(RETRIBUTION)
        target = self.put(who=self.b)
        land = self.lands(SWAMP)[0]
        for value in (-1, 1, True):
            self.assertFalse(self.g.activate_ability(self.a, source, 0, [target], x=value))
            self.assertFalse(land.tapped)
        self.assertTrue(self.g.activate_ability(self.a, source, 0, [target], x=0))
        self.assertEqual(target.toughness, 2)

    def test_ooze_flux_positive_cost_and_size_snapshot(self):
        source = self.put(FLUX)
        donor = self.put(counters={'+1/+1': 4})
        self.lands(FOREST, FOREST)
        self.assertFalse(self.g.activate_ability(self.a, source, 0, x=0))
        self.g._priority_depth = 1
        self.assertTrue(self.g.activate_ability(self.a, source, 0, x=3))
        self.assertEqual(donor.p1, 1)
        donor.counters['+1/+1'] += 5
        self.g._priority_depth = 0
        self.g.settle()
        token = next(x for x in self.a.creatures if x.card.is_token)
        self.assertEqual((token.power, token.toughness), (3, 3))
        self.assertEqual(token.card.colors, frozenset({'G'}))
        self.assertIn('Ooze', token.card.subtypes)

    def test_variable_cost_can_be_selected_by_explicit_donors(self):
        source = self.put(FLUX)
        a, b = self.put(counters={'+1/+1': 1}), self.put(counters={'+1/+1': 2})
        self.lands(FOREST, FOREST)
        self.assertTrue(self.g.activate_ability(self.a, source, 0,
                                               counter_choices=[(a, '+1/+1', 1), (b, '+1/+1', 1)]))
        token = next(x for x in self.a.creatures if x.card.is_token)
        self.assertEqual((a.p1, b.p1, token.power), (0, 1, 2))

    def test_parish_blade_transfers_all_counter_types_using_last_known_values(self):
        source = self.put(TRAINEE, counters={'+1/+1': 2, 'vigilance': 1, 'charge': 3})
        target = self.put()
        self.g.dies(source)
        source.counters['+1/+1'] = 99  # a later mutation cannot alter the queued LKI snapshot
        self.g.settle()
        self.assertEqual(target.p1, 2)
        self.assertEqual(target.counters['charge'], 3)
        self.assertTrue(target.has('vigilance'))

    def test_counter_transfer_does_not_find_reentered_target(self):
        source, target = self.put(TRAINEE, counters={'+1/+1': 2}), self.put()
        self.g.dies(source)
        self.g.flush_triggers()
        self.g.leave_battlefield(target, 'hand')
        physical = self.a.hand.pop()
        replacement = self.put(physical)
        self.g.settle()
        self.assertEqual(replacement.p1, 0)

    def test_training_event_only_comes_from_training(self):
        source = self.put(SAVIOR)
        enemy = self.put(who=self.b)
        source.counters['+1/+1'] = 1
        self.g.settle()
        self.assertIn(enemy, self.b.battlefield)
        source.counters['+1/+1'] = 0
        self.fight([source, self.put()])
        self.assertEqual(source.p1, 1)
        self.assertNotIn(enemy, self.b.battlefield)

    def test_savior_returns_exiled_permanent_through_leave_trigger(self):
        source, enemy = self.put(SAVIOR), self.put(who=self.b)
        self.g.fire(self.a, 'trains', source)
        self.g.settle()
        self.assertIn(enemy.front, self.b.exile)
        self.g.leave_battlefield(source, 'hand')
        self.assertIn(enemy.front, self.b.exile)  # leave ability must resolve first
        self.g.settle()
        self.assertTrue(any(x.front is enemy.front for x in self.b.battlefield))

    def test_savior_can_exile_creature_card_from_either_graveyard(self):
        source = self.put(SAVIOR)
        self.b.graveyard.append(BEAR)
        target = self.b.graveyard[-1]
        self.a.ai.choose_target = lambda game, me, eff: target if eff.kind == 'linked_exile' else None
        self.g.fire(self.a, 'trains', source)
        self.g.settle()
        self.assertIn(target, self.b.exile)
        self.g.leave_battlefield(source, 'hand')
        self.g.settle()
        self.assertTrue(any(x.front is target for x in self.b.battlefield))

    def test_savior_graveyard_target_generation_is_checked(self):
        source = self.put(SAVIOR)
        self.b.graveyard.append(BEAR)
        target = self.b.graveyard[-1]
        self.a.ai.choose_target = lambda *args: target
        self.g.fire(self.a, 'trains', source)
        self.g.flush_triggers()
        self.g.move_card(target, self.b.graveyard, self.b.hand)
        self.g.move_card(target, self.b.hand, self.b.graveyard)
        self.g.settle()
        self.assertIn(target, self.b.graveyard)
        self.assertNotIn(target, self.b.exile)

    def test_savior_return_does_not_follow_card_that_left_and_reentered_exile(self):
        source, enemy = self.put(SAVIOR), self.put(who=self.b)
        self.g.fire(self.a, 'trains', source)
        self.g.settle()
        self.g.move_card(enemy.front, self.b.exile, self.b.hand)
        self.g.move_card(enemy.front, self.b.hand, self.b.exile)
        self.g.leave_battlefield(source, 'hand')
        self.g.settle()
        self.assertIn(enemy.front, self.b.exile)

    def test_savior_leaving_before_exile_resolves_does_not_return_later_exile(self):
        source, enemy = self.put(SAVIOR), self.put(who=self.b)
        self.g.fire(self.a, 'trains', source)
        self.g.flush_triggers()
        self.g.leave_battlefield(source, 'hand')
        self.g.settle()
        self.assertIn(enemy.front, self.b.exile)

    def test_savior_optional_zero_targets_is_legal(self):
        source, enemy = self.put(SAVIOR), self.put(who=self.b)
        effects = next(t.effects for t in source.card.triggers if t.event == 'trains')
        self.g.queue_trigger(self.a, effects, source, targets=[None])
        self.g.settle()
        self.assertIn(enemy, self.b.battlefield)

    def test_marchesa_grant_stacks_with_native_dethrone_but_excludes_self(self):
        source = self.put(MARCHESA)
        ally = self.put(card('Native Dethrone', types='Creature', text='Dethrone', power=2, toughness=3))
        self.fight([source, ally])
        self.assertEqual((source.p1, ally.p1), (1, 2))

    def test_marchesa_grant_ends_when_source_leaves(self):
        source, ally = self.put(MARCHESA), self.put()
        self.assertTrue(ally.has('dethrone'))
        self.g.leave_battlefield(source, 'hand')
        self.assertFalse(ally.has('dethrone'))
        self.fight([ally])
        self.assertEqual(ally.p1, 0)

    def test_marchesa_returns_at_next_end_step_after_source_leaves(self):
        source, ally = self.put(MARCHESA), self.put(counters={'+1/+1': 1})
        self.g.dies(ally)
        self.g.settle()
        self.g.leave_battlefield(source, 'hand')
        self.end_step(self.b)
        returned = next(x for x in self.a.battlefield if x.front is ally.front)
        self.assertEqual(returned.p1, 0)
        self.assertFalse(self.g.delayed_end_step)

    def test_marchesa_returns_stolen_creature_to_trigger_controller(self):
        self.put(MARCHESA)
        ally = self.put(who=self.b, counters={'+1/+1': 1})
        self.b.battlefield.remove(ally)
        ally.controller = self.a
        self.a.battlefield.append(ally)
        self.g.dies(ally)
        self.g.settle()
        self.end_step()
        returned = next(x for x in self.a.battlefield if x.front is ally.front)
        self.assertIs(returned.owner, self.b)

    def test_marchesa_sees_own_and_other_simultaneous_wrath_deaths(self):
        source = self.put(MARCHESA, counters={'+1/+1': 1})
        ally = self.put(counters={'+1/+1': 1})
        self.g.resolve(self.a, Effect('wrath'), None)
        self.g.settle()
        self.assertNotIn(source, self.a.battlefield)
        self.end_step()
        self.assertTrue(any(x.front is source.front for x in self.a.battlefield))
        self.assertTrue(any(x.front is ally.front for x in self.a.battlefield))

    def test_marchesa_sees_simultaneous_state_based_deaths(self):
        source = self.put(MARCHESA, counters={'+1/+1': 1})
        ally = self.put(counters={'+1/+1': 1})
        source.damage = ally.damage = 99
        self.g.state_based_actions()
        self.g.settle()
        self.end_step()
        self.assertTrue(any(x.front is source.front for x in self.a.battlefield))
        self.assertTrue(any(x.front is ally.front for x in self.a.battlefield))

    def test_marchesa_does_not_see_later_death_caused_by_losing_its_anthem(self):
        source = self.put(dataclasses.replace(MARCHESA, anthem=(1, 1)))
        ally = self.put(card('Dependent Body', types='Creature', power=0, toughness=0), counters={'+1/+1': 1})
        source.damage, ally.damage = 99, 1
        self.g.state_based_actions()
        self.g.settle()
        self.end_step()
        self.assertIn(ally.front, self.a.graveyard)

    def test_marchesa_sees_simultaneous_sacrifice_cost(self):
        source = self.put(MARCHESA, counters={'+1/+1': 1})
        ally = self.put(card('Large Ally', '{8}', 'Creature', power=7, toughness=7), counters={'+1/+1': 1})
        altar = self.put(card('Two Sacrifices', '{1}', 'Artifact', '{0}, Sacrifice two creatures: Draw a card.'))
        self.assertTrue(self.g.activate_ability(self.a, altar, 0))
        self.end_step()
        self.assertTrue(any(x.front is source.front for x in self.a.battlefield))
        self.assertTrue(any(x.front is ally.front for x in self.a.battlefield))

    def test_marchesa_does_not_follow_graveyard_reentry_or_return_tokens(self):
        self.put(MARCHESA)
        ally = self.put(counters={'+1/+1': 1})
        token = self.put(make_token('Soldier', 1, 1), counters={'+1/+1': 1})
        self.g.dies(ally)
        self.g.dies(token)
        self.g.settle()
        self.g.move_card(ally.front, self.a.graveyard, self.a.hand)
        self.g.move_card(ally.front, self.a.hand, self.a.graveyard)
        self.end_step()
        self.assertIn(ally.front, self.a.graveyard)
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))

    def test_marchesa_death_during_end_step_waits_for_following_end_step(self):
        self.put(MARCHESA)
        ally = self.put(counters={'+1/+1': 1})
        self.end_step()
        self.g.dies(ally)
        self.g.settle()
        self.assertIn(ally.front, self.a.graveyard)
        self.assertEqual(len(self.g.delayed_end_step), 1)
        self.end_step(self.b)
        self.assertTrue(any(x.front is ally.front for x in self.a.battlefield))

    def test_marchesa_ignores_death_without_positive_counter(self):
        self.put(MARCHESA)
        ally = self.put()
        self.g.dies(ally)
        self.g.settle()
        self.end_step()
        self.assertIn(ally.front, self.a.graveyard)

    def test_scourge_adds_one_combat_after_first_attack(self):
        source = self.put(SCOURGE)
        self.fight([source])
        self.assertEqual(source.attack_count, (self.g.turn, 2))
        self.assertEqual(source.p1, 1)
        self.assertEqual(self.b.life, 8)  # 6 damage in each combat
        self.assertEqual(self.g.extra_combats, 0)
        self.assertTrue(source.tapped)

    def test_scourge_does_not_trigger_on_second_attack_if_first_failed_condition(self):
        source = self.put(SCOURGE)
        self.b.life = 10
        self.fight([source])
        self.assertEqual(source.attack_count[1], 1)
        source.tapped = False
        self.b.life = 30
        self.fight([source])
        self.assertEqual(source.attack_count[1], 2)
        self.assertEqual(self.b.life, 24)

    def test_scourge_intervening_if_rechecks_life_and_source_presence(self):
        source, ally = self.put(SCOURGE), self.put()
        self.declare([source, ally])
        self.b.life = 10
        self.g.settle()
        self.assertEqual(self.g.extra_combats, 0)
        self.assertTrue(ally.tapped)
        self.g.turn += 1
        self.b.life = 20
        self.declare([source, ally])
        self.g.leave_battlefield(source, 'hand')
        self.g.settle()
        self.assertEqual(self.g.extra_combats, 0)

    def test_scourge_does_not_trigger_when_attacking_planeswalker(self):
        source = self.put(SCOURGE)
        walker = self.put(dataclasses.replace(card('Test Walker', types='Planeswalker'), loyalty=10), self.b)
        self.a.ai.choose_attack_targets = lambda *args: {source: walker}
        self.fight([source])
        self.assertEqual(source.attack_count[1], 1)
        self.assertEqual(source.p1, 0)

    def test_scourge_condition_fails_if_control_or_creature_type_changes(self):
        source = self.put(SCOURGE)
        self.declare([source])
        self.g.add_continuous_effect(source, 'set_types', types={'Artifact'})
        self.g.settle()
        self.assertEqual(self.g.extra_combats, 0)
        source = self.put(SCOURGE)
        self.declare([source])
        self.a.battlefield.remove(source)
        source.controller = self.b
        self.b.battlefield.append(source)
        self.g.settle()
        self.assertEqual(self.g.extra_combats, 0)

    def test_multiple_extra_combats_are_phases_not_extra_main_phases(self):
        a, b = self.put(SCOURGE), self.put(SCOURGE)
        self.b.life = 100
        with patch.object(self.g, '_combat', wraps=self.g._combat) as run:
            self.fight([a, b])
        self.assertEqual(run.call_count, 3)
        self.assertEqual((a.attack_count[1], b.attack_count[1]), (2, 2))

    def test_extra_combat_runs_before_second_main_in_real_turn(self):
        source = self.put(SCOURGE)
        self.a.ai.attack = [source]
        phases = []
        combat = self.g._combat

        def run_combat(*args):
            phases.append('combat')
            return combat(*args)

        with patch.object(self.g, 'main_phase', side_effect=lambda p: phases.append(self.g.step)), \
                patch.object(self.g, '_combat', side_effect=run_combat):
            self.g.take_turn(self.a)
        self.assertEqual(phases, ['main1', 'combat', 'combat', 'main2'])

    def test_scourge_can_trigger_again_in_a_new_turn(self):
        source = self.put(SCOURGE)
        self.b.life = 100
        self.fight([source])
        self.g.turn += 1
        source.tapped = False
        self.fight([source])
        self.assertEqual(source.attack_count, (self.g.turn, 2))

    def test_variable_cost_default_selects_largest_payable_counter_amount(self):
        source = self.put(FLUX)
        donor = self.put(counters={'+1/+1': 3})
        self.lands(FOREST, FOREST)
        self.assertTrue(self.g.activate_ability(self.a, source, 0))
        self.assertEqual(donor.p1, 0)
        token = next(x for x in self.a.creatures if x.card.is_token)
        self.assertEqual(token.power, 3)

    def test_gryffwing_payment_gives_other_attacker_flying_until_cleanup(self):
        source, ally = self.put(CAVALRY), self.put()
        mana = self.lands(PLAINS, PLAINS)
        self.fight([source, ally])
        self.assertTrue(ally.has('flying'))
        self.assertTrue(all(p.tapped for p in mana))
        self.g.take_turn(self.b)
        self.assertFalse(ally.has('flying'))

    def test_gryffwing_can_decline_payment_or_lack_mana(self):
        source, ally = self.put(CAVALRY), self.put()
        self.fight([source, ally])
        self.assertFalse(ally.has('flying'))
        source.tapped = ally.tapped = False
        mana = self.lands(PLAINS, PLAINS)
        self.a.ai.pay_optional = lambda *args: False
        self.fight([source, ally])
        self.assertFalse(ally.has('flying'))
        self.assertTrue(all(not p.tapped for p in mana))

    def test_gryffwing_invalid_target_does_not_pay(self):
        source, ally = self.put(CAVALRY), self.put()
        mana = self.lands(PLAINS, PLAINS)
        self.declare([source, ally])
        ally.temp_kw.add('flying')
        self.g.settle()
        self.assertTrue(all(not p.tapped for p in mana))

    def test_gryffwing_cannot_target_itself_or_nonattacking_creatures(self):
        source, ally = self.put(CAVALRY), self.put()
        mana = self.lands(PLAINS, PLAINS)
        self.fight([source])
        self.assertFalse(ally.has('flying'))
        self.assertTrue(all(not p.tapped for p in mana))


if __name__ == '__main__':
    unittest.main()
