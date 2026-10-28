"""Counter-filtered graft abilities: costs, target legality, timing and identity."""
import random
import unittest
from unittest.mock import patch

from mtgsim.cards import Effect
from mtgsim.engine import Game, Player, ability_worth, can_block
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, card

SPIDER = card('Aquastrand Spider', '{1}{G}', 'Creature — Spider Mutant',
              'Graft 2\n{G}: Target creature with a +1/+1 counter on it gains reach until end of turn.', 0, 0)
SQUIRTER = card('Helium Squirter', '{4}{U}', 'Creature — Beast Mutant',
                'Graft 3\n{1}: Target creature with a +1/+1 counter on it gains flying until end of turn.', 0, 0)
FROGLING = card('Plaxcaster Frogling', '{1}{G}{U}', 'Creature — Frog Mutant',
                'Graft 3\n{2}: Target creature with a +1/+1 counter on it gains shroud until end of turn.', 0, 0)
TROLL = card('Sporeback Troll', '{3}{G}', 'Creature — Troll Mutant',
             'Graft 2\n{1}{G}: Regenerate target creature with a +1/+1 counter on it.', 0, 0)
GRAFTMAGE = card('Vigean Graftmage', '{2}{U}', 'Creature — Vedalken Wizard Mutant',
                 'Graft 2\n{1}{U}: Untap target creature with a +1/+1 counter on it.', 0, 0)
MANIPULATOR = card('Cytoplast Manipulator', '{2}{U}{U}', 'Creature — Human Wizard Mutant',
                   'Graft 2\n{U}, {T}: Gain control of target creature with a +1/+1 counter on it for as long as '
                   'Cytoplast Manipulator remains on the battlefield.', 0, 0)
ROOTKIN = card('Cytoplast Root-Kin', '{2}{G}{G}', 'Creature — Elemental Mutant',
               'Graft 4\nWhen Cytoplast Root-Kin enters, put a +1/+1 counter on each other creature you control '
               'with a +1/+1 counter on it.\n{2}: Move a +1/+1 counter from target creature you control onto '
               'Cytoplast Root-Kin.', 0, 0)
BASILISK = card('Simic Basilisk', '{4}{G}{G}', 'Creature — Basilisk Mutant',
                'Graft 3\n{1}{G}: Until end of turn, target creature with a +1/+1 counter on it gains '
                '"Whenever this creature deals combat damage to a creature, destroy that creature at end of combat."', 0, 0)
HYDROPON = card('Vigean Hydropon', '{1}{G}{U}', 'Creature — Plant Mutant',
                "Graft 5\nVigean Hydropon can't attack or block.", 0, 0)
RESOLVE = card("Warrior's Resolve", '{1}{G}', 'Enchantment',
               'Creatures you control have training.\nAt the beginning of your end step, if you control a '
               'creature with a +1/+1 counter on it that attacked this turn, draw a card.')
CARDS = (SPIDER, SQUIRTER, FROGLING, TROLL, GRAFTMAGE, MANIPULATOR, ROOTKIN, BASILISK, HYDROPON, RESOLVE)


class GraftAbilities(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 30
            p.ai.attack, p.ai.block = (), {}
            p.ai.choose_graft = lambda *args: False

    def put(self, definition=BEAR, who=None, counters=None):
        obj = self.g.enter_battlefield(who or self.a, definition, counters=counters)
        obj.sick = False
        self.g.settle()
        return obj

    def mana(self, who=None):
        return [self.put(c, who) for c in (ISLAND, ISLAND, FOREST, FOREST)]

    def activate(self, src, tgt, settle=True):
        if not settle:
            with patch.object(self.g, 'settle'):
                return self.g.activate_ability(src.controller, src, 0, [tgt])
        return self.g.activate_ability(src.controller, src, 0, [tgt])

    def cleanup(self):
        with patch.object(self.g, 'main_phase'), patch.object(self.g, 'combat'):
            self.g.take_turn(self.b)

    def mark_attack(self, obj):
        self.g.attackers = [obj]
        self.g.attack_targets[obj] = self.b
        self.g.fire(obj.controller, 'attacks', obj)
        self.g.settle()

    def endstep(self, who=None):
        self.g.begin_end_step(who or self.a)
        self.g.settle()

    def test_all_ten_oracle_fixtures_fully_matched(self):
        for definition in CARDS:
            with self.subTest(card=definition.name):
                self.assertEqual(definition.unsupported, [])
                self.assertEqual(definition.approximations, [])

    def test_each_counter_filtered_ability_rejects_no_counter_and_other_counters(self):
        for definition in CARDS[:6] + (BASILISK,):
            with self.subTest(card=definition.name):
                src = self.put(definition)
                self.mana()
                plain = self.put()
                plain.counters['vigilance'] = 1
                before = [x.tapped for x in self.a.battlefield]
                self.assertFalse(self.activate(src, plain))
                self.assertEqual(before, [x.tapped for x in self.a.battlefield])
                plain.counters['+1/+1'] = 1
                self.assertIn(plain, self.g.legal_targets(self.a, src.card.activated[0].effects[0]))

    def test_grants_reach_flying_shroud_and_expires(self):
        for definition, keyword in ((SPIDER, 'reach'), (SQUIRTER, 'flying'), (FROGLING, 'shroud')):
            with self.subTest(keyword=keyword):
                src = self.put(definition)
                target = self.put(counters={'+1/+1': 1})
                self.mana()
                self.assertTrue(self.activate(src, target))
                self.assertTrue(target.has(keyword))
                self.cleanup()
                self.assertFalse(target.has(keyword))

    def test_filter_rechecked_after_counter_removed_before_resolution(self):
        for definition in (SPIDER, TROLL, GRAFTMAGE, MANIPULATOR, BASILISK):
            with self.subTest(card=definition.name):
                src = self.put(definition)
                self.mana()
                target = self.put(counters={'+1/+1': 1})
                target.tapped = True
                self.assertTrue(self.activate(src, target, settle=False))
                target.counters['+1/+1'] = 0
                self.g.settle()
                self.assertFalse(target.has('reach'))
                self.assertEqual(target.regeneration_shields, 0)
                self.assertEqual(target.temp_triggers, [])
                self.assertTrue(target.tapped)

    def test_counter_can_be_added_in_response_to_make_target_legal_again(self):
        src = self.put(SQUIRTER)
        self.mana()
        target = self.put(counters={'+1/+1': 1})
        self.assertTrue(self.activate(src, target, settle=False))
        target.counters['+1/+1'] = 0
        target.counters['+1/+1'] = 1
        self.g.settle()
        self.assertTrue(target.has('flying'))

    def test_grants_can_target_enemy_and_self(self):
        src = self.put(SPIDER)
        self.mana()
        self.assertTrue(self.activate(src, src))
        enemy = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.assertTrue(self.activate(src, enemy))
        self.assertTrue(enemy.has('reach'))

    def test_reach_allows_blocking_flyer(self):
        spider = self.put(SPIDER)
        flyer = self.put(SQUIRTER, self.b)
        flyer.temp_kw.add('flying')
        # Spider's printed type is not itself reach.
        self.assertFalse(can_block(spider, flyer))
        self.mana()
        self.activate(spider, spider)
        self.assertTrue(can_block(spider, flyer))

    def test_shroud_blocks_later_friendly_and_enemy_targets(self):
        frog = self.put(FROGLING)
        self.mana()
        self.activate(frog, frog)
        self.assertFalse(self.g.targetable(frog, self.a))
        self.assertFalse(self.g.targetable(frog, self.b))

    def test_insufficient_mana_does_not_grant_keyword(self):
        src = self.put(FROGLING)
        self.assertFalse(self.activate(src, src))
        self.assertFalse(src.has('shroud'))

    def test_regenerate_shield_preserves_object_counters_and_removes_combat(self):
        src = self.put(TROLL)
        target = self.put(counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        target.damage = 1
        self.g.attackers = [target]
        self.g.destroy(target)
        self.assertIn(target, self.a.battlefield)
        self.assertEqual((target.damage, target.p1, target.regeneration_shields), (0, 1, 0))
        self.assertTrue(target.tapped)
        self.assertNotIn(target, self.g.attackers)

    def test_regeneration_cannot_prevent_sacrifice(self):
        src = self.put(TROLL)
        target = self.put(counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        self.g.sacrifice(target)
        self.assertNotIn(target, self.a.battlefield)

    def test_graftmage_untaps_own_or_enemy_creature(self):
        src = self.put(GRAFTMAGE)
        for who in (self.a, self.b):
            target = self.put(who=who, counters={'+1/+1': 1})
            target.tapped = True
            self.mana()
            self.assertTrue(self.activate(src, target))
            self.assertFalse(target.tapped)

    def test_graftmage_auto_target_is_tapped_ally(self):
        src = self.put(GRAFTMAGE)
        target = self.put(counters={'+1/+1': 1})
        target.tapped = True
        self.mana()
        self.assertTrue(self.g.activate_ability(self.a, src, 0))
        self.g.settle()
        self.assertFalse(target.tapped)

    def test_manipulator_preserves_owner_counters_tapped_status_and_sets_sick(self):
        src = self.put(MANIPULATOR)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        target.tapped = True
        self.mana()
        self.assertTrue(self.activate(src, target))
        self.assertIs(target.controller, self.a)
        self.assertIs(target.owner, self.b)
        self.assertTrue(target.sick)
        self.assertTrue(target.tapped)
        self.assertEqual(target.p1, 1)
        self.assertTrue(src.tapped)

    def test_manipulator_sickness_prevents_tap_cost(self):
        src = self.put(MANIPULATOR)
        src.sick = True
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.assertFalse(self.activate(src, target))
        self.assertIs(target.controller, self.b)

    def test_source_leaving_before_resolution_prevents_control(self):
        src = self.put(MANIPULATOR)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target, settle=False)
        self.g.leave_battlefield(src, 'hand')
        self.g.settle()
        self.assertIs(target.controller, self.b)

    def test_source_leaves_returns_control_immediately_without_trigger(self):
        src = self.put(MANIPULATOR)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        target.counters['+1/+1'] = 0
        self.g.leave_battlefield(src, 'hand')
        self.assertIs(target.controller, self.b)
        self.assertTrue(target.sick)
        self.assertEqual(self.g.control_effects, [])

    def test_source_leaves_and_reenters_does_not_keep_control(self):
        src = self.put(MANIPULATOR)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        self.g.leave_battlefield(src, 'hand')
        self.a.hand.remove(src.front)
        self.put(src.front)
        self.assertIs(target.controller, self.b)

    def test_control_survives_cleanup_and_source_control_change(self):
        src = self.put(MANIPULATOR)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        self.cleanup()
        self.assertIs(target.controller, self.a)
        from mtgsim.counter_mechanics import change_control
        change_control(self.g, src, self.b)
        self.assertIs(target.controller, self.a)
        self.g.leave_battlefield(src, 'hand')
        self.assertIs(target.controller, self.b)

    def test_control_removes_attacker_from_combat(self):
        src = self.put(MANIPULATOR)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.g.attackers = [target]
        self.g.attack_targets[target] = self.a
        self.mana()
        self.activate(src, target)
        self.assertNotIn(target, self.g.attackers)
        self.assertNotIn(target, self.g.attack_targets)

    def test_competing_manipulators_restore_latest_active_then_original_control(self):
        src = self.put(MANIPULATOR)
        other = self.put(MANIPULATOR, self.b)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        self.mana(self.b)
        self.activate(other, target)
        self.assertIs(target.controller, self.b)
        self.g.leave_battlefield(other, 'hand')
        self.assertIs(target.controller, self.a)
        self.g.leave_battlefield(src, 'hand')
        self.assertIs(target.controller, self.b)

    def test_ending_older_control_does_not_override_newer_effect(self):
        src = self.put(MANIPULATOR)
        other = self.put(MANIPULATOR, self.b)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        self.mana(self.b)
        self.activate(other, target)
        self.g.leave_battlefield(src, 'hand')
        self.assertIs(target.controller, self.b)
        self.g.leave_battlefield(other, 'hand')
        self.assertIs(target.controller, self.b)

    def test_threaten_and_source_control_have_independent_durations(self):
        src = self.put(MANIPULATOR)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        self.g.resolve(self.b, Effect('threaten', target='creature'), target)
        self.assertIs(target.controller, self.b)
        self.cleanup()
        self.assertIs(target.controller, self.a)
        self.g.leave_battlefield(src, 'hand')
        self.assertIs(target.controller, self.b)

    def test_dead_controlled_target_is_not_followed_to_new_battlefield_object(self):
        src = self.put(MANIPULATOR)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        self.g.destroy(target)
        self.b.graveyard.remove(target.front)
        new = self.put(target.front, self.b)
        self.g.leave_battlefield(src, 'hand')
        self.assertIs(new.controller, self.b)
        self.assertIsNot(new, target)

    def test_rootkin_entry_distributes_only_to_other_counter_bearing_allies(self):
        yes = self.put(counters={'+1/+1': 1})
        no = self.put()
        enemy = self.put(who=self.b, counters={'+1/+1': 1})
        root = self.put(ROOTKIN)
        self.assertEqual((yes.p1, no.p1, enemy.p1, root.p1), (2, 0, 1, 4))

    def test_rootkin_automatic_activation_requires_another_counter_donor(self):
        root = self.put(ROOTKIN)
        self.mana()
        self.assertFalse(ability_worth(self.g, self.a, root, 0))
        donor = self.put(counters={'+1/+1': 1})
        self.assertTrue(ability_worth(self.g, self.a, root, 0))
        self.assertTrue(self.g.activate_ability(self.a, root, 0))
        self.assertEqual((root.p1, donor.p1), (5, 0))
        self.assertFalse(ability_worth(self.g, self.a, root, 0))

    def test_rootkin_transfer_can_kill_zero_base_donor(self):
        root = self.put(ROOTKIN)
        donor = self.put(card('Donor', '', 'Creature', '', 0, 0), counters={'+1/+1': 1})
        self.mana()
        self.assertTrue(self.activate(root, donor))
        self.assertEqual(root.p1, 5)
        self.assertNotIn(donor, self.a.battlefield)

    def test_rootkin_transfer_is_not_counter_cost_and_allows_zero_counter_target(self):
        root = self.put(ROOTKIN)
        donor = self.put()
        self.mana()
        self.assertTrue(self.activate(root, donor))
        self.assertEqual((root.p1, donor.p1), (4, 0))

    def test_rootkin_self_transfer_is_noop_and_enemy_target_illegal(self):
        root = self.put(ROOTKIN)
        self.mana()
        self.assertTrue(self.activate(root, root))
        self.assertEqual(root.p1, 4)
        enemy = self.put(who=self.b, counters={'+1/+1': 1})
        self.assertFalse(self.activate(root, enemy))

    def test_rootkin_cannot_move_counter_if_source_left(self):
        root = self.put(ROOTKIN)
        donor = self.put(counters={'+1/+1': 1})
        self.mana()
        self.activate(root, donor, settle=False)
        self.g.leave_battlefield(root, 'hand')
        self.g.settle()
        self.assertEqual(donor.p1, 1)

    def test_basilisk_destroy_delayed_until_end_of_combat(self):
        basilisk = self.put(BASILISK)
        source = self.put(counters={'+1/+1': 1})
        victim = self.put(who=self.b)
        self.mana()
        self.activate(basilisk, source)
        self.g.deal_damage(victim, 1, source=source, by=self.a, combat=True)
        self.g.settle()
        self.assertIn(victim, self.b.battlefield)
        self.g.end_combat(self.a)
        self.g.settle()
        self.assertNotIn(victim, self.b.battlefield)

    def test_basilisk_noncombat_or_prevented_damage_does_not_trigger(self):
        basilisk = self.put(BASILISK)
        source = self.put(counters={'+1/+1': 1})
        victim = self.put(who=self.b)
        self.mana()
        self.activate(basilisk, source)
        self.g.deal_damage(victim, 1, source=source, by=self.a)
        victim.prevent_next = 1
        self.g.deal_damage(victim, 1, source=source, by=self.a, combat=True)
        self.g.settle()
        self.assertEqual(self.g.end_combat_effects, [])

    def test_basilisk_delayed_trigger_survives_granted_creature_death(self):
        basilisk = self.put(BASILISK)
        source = self.put(counters={'+1/+1': 1})
        victim = self.put(who=self.b)
        self.mana()
        self.activate(basilisk, source)
        self.g.deal_damage(victim, 1, source=source, by=self.a, combat=True)
        self.g.destroy(source)
        self.g.settle()
        self.g.end_combat(self.a)
        self.g.settle()
        self.assertNotIn(victim, self.b.battlefield)

    def test_basilisk_does_not_follow_blinked_damaged_creature(self):
        basilisk = self.put(BASILISK)
        source = self.put(counters={'+1/+1': 1})
        victim = self.put(who=self.b)
        self.mana()
        self.activate(basilisk, source)
        self.g.deal_damage(victim, 1, source=source, by=self.a, combat=True)
        self.g.settle()
        self.g.leave_battlefield(victim, 'hand')
        self.b.hand.remove(victim.front)
        new = self.put(victim.front, self.b)
        self.g.end_combat(self.a)
        self.g.settle()
        self.assertIn(new, self.b.battlefield)

    def test_basilisk_granted_trigger_expires_at_cleanup(self):
        basilisk = self.put(BASILISK)
        self.mana()
        self.activate(basilisk, basilisk)
        self.assertEqual(len(basilisk.temp_triggers), 1)
        self.cleanup()
        self.assertEqual(basilisk.temp_triggers, [])

    def test_hydropon_cannot_attack_or_block_but_grafts(self):
        hydropon = self.put(HYDROPON)
        enemy = self.put(who=self.b)
        self.assertFalse(hydropon.can_attack())
        self.assertFalse(can_block(hydropon, enemy))
        self.a.ai.choose_graft = lambda *args: True
        ally = self.put()
        self.assertEqual((hydropon.p1, ally.p1), (4, 1))
        self.a.ai.attack = [hydropon]
        self.g.combat(self.a, self.b)
        self.assertEqual(self.g.attackers, [])

    def test_hydropon_restrictions_are_lost_with_its_abilities(self):
        hydropon = self.put(HYDROPON)
        suppressor = self.put()
        enemy = self.put(who=self.b)
        hydropon.silenced_by = suppressor
        self.assertTrue(hydropon.can_attack())
        self.assertTrue(can_block(hydropon, enemy))
        self.g.destroy(suppressor)
        self.assertFalse(hydropon.can_attack())
        self.assertFalse(can_block(hydropon, enemy))

    def test_source_control_does_not_end_when_source_loses_abilities(self):
        src = self.put(MANIPULATOR)
        target = self.put(who=self.b, counters={'+1/+1': 1})
        self.mana()
        self.activate(src, target)
        src.silenced_by = self.put()
        self.assertIs(target.controller, self.a)
        self.g.leave_battlefield(src, 'hand')
        self.assertIs(target.controller, self.b)

    def test_resolve_draws_only_at_own_end_step_for_counter_bearing_attacker(self):
        self.put(RESOLVE)
        attacker = self.put(counters={'+1/+1': 1})
        self.mark_attack(attacker)
        self.endstep(self.b)
        self.assertEqual(len(self.a.hand), 0)
        self.endstep()
        self.assertEqual(len(self.a.hand), 1)

    def test_resolve_no_draw_for_nonattacker_even_if_another_attacked(self):
        self.put(RESOLVE)
        attacker = self.put()
        self.put(counters={'+1/+1': 1})
        self.mark_attack(attacker)
        self.endstep()
        self.assertEqual(len(self.a.hand), 0)

    def test_resolve_intervening_condition_rechecked_on_resolution(self):
        self.put(RESOLVE)
        attacker = self.put(counters={'+1/+1': 1})
        self.mark_attack(attacker)
        self.g.fire(self.a, 'end_step')
        self.g.flush_triggers()
        attacker.counters['+1/+1'] = 0
        self.g.settle()
        self.assertEqual(len(self.a.hand), 0)

    def test_resolve_condition_must_hold_when_end_step_begins(self):
        self.put(RESOLVE)
        attacker = self.put()
        self.mark_attack(attacker)
        self.g.fire(self.a, 'end_step')
        attacker.counters['+1/+1'] = 1
        self.g.settle()
        self.assertEqual(len(self.a.hand), 0)

    def test_resolve_attack_history_resets_by_turn_and_not_blink(self):
        self.put(RESOLVE)
        attacker = self.put(counters={'+1/+1': 1})
        self.mark_attack(attacker)
        self.g.turn += 1
        self.endstep()
        self.assertEqual(len(self.a.hand), 0)
        self.mark_attack(attacker)
        self.g.leave_battlefield(attacker, 'hand')
        self.a.hand.remove(attacker.front)
        self.put(attacker.front, counters={'+1/+1': 1})
        self.endstep()
        self.assertEqual(len(self.a.hand), 0)

    def test_resolve_training_grant_produces_counter_and_draw(self):
        self.put(RESOLVE)
        small, large = self.put(), self.put(counters={'+1/+1': 2})
        self.a.ai.attack = [small, large]
        self.g.combat(self.a, self.b)
        self.assertEqual(small.p1, 1)
        self.endstep()
        self.assertEqual(len(self.a.hand), 1)


if __name__ == '__main__':
    unittest.main()
