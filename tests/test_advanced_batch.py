"""Behavior checks for the thirty shared capability implementations."""
import dataclasses
import json
import random
import unittest
from pathlib import Path

from mtgsim.cards import Effect, card_from_scryfall, _parse_effects, make_token
from mtgsim.engine import Game, Player, StackItem
from mtgsim import advanced_templates as advanced, auras, permanent_templates as pt
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, FOREST, MOUNTAIN, PLAINS, card
SWAMP = card("Swamp", types="Basic Land — Swamp")

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/advanced_cards.json').read_text())
CARDS = {n: card_from_scryfall(d) for n, d in FIXTURES.items()}
SPELL = card('Test draw', '{U}', 'Sorcery', 'Draw a card.')
ELF = card('Test Elf', '{G}', 'Creature — Elf', '', 1, 1)
WALL = card('Test Wall', '{1}', 'Creature — Wall', '', 0, 4)


class AdvancedBatch(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(7))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None
            p.ai.choose_graft = lambda *args: False

    def put(self, c=BEAR, p=None, **kw):
        c = CARDS[c] if isinstance(c, str) else c
        perm = self.g.enter_battlefield(p or self.a, c, **kw)
        perm.sick = False
        self.g.settle()
        return perm

    def apply(self, text, targets=(), source=None, context=None):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets, source=source, context=context)
        for eff, target in zip(effects, targets):
            self.g.resolve(self.a, eff, target, item)
        return item

    def cast(self, name, targets=None, p=None):
        p = p or self.a
        p.hand.append(CARDS[name] if name in CARDS else name)
        c = p.hand[-1]
        self.assertTrue(self.g.cast(p, c, targets))
        return c

    def mana(self, p=None, n=8):
        return [self.put(c, p) for c in ([ISLAND, FOREST, MOUNTAIN, SWAMP, PLAINS, SWAMP] * n)[:n]]

    def test_every_proposed_clause_is_consumed(self):
        backlog = json.loads((Path(__file__).parents[1] / 'results/roadmap_batch/backlog.json').read_text())
        for task in backlog['items']:
            for example in task['examples']:
                with self.subTest(task=task['id'], card=example['card']):
                    ignored = CARDS[example['card']].unsupported
                    self.assertNotIn(example['remaining_ignored_text'], ignored)

    def test_base_stats_ignore_counters_and_pumps(self):
        bess = self.put('Bess, Soul Nourisher')
        elf = self.put(ELF, counters={'+1/+1': 4})
        self.assertEqual(bess.p1, 1)
        self.assertEqual(elf.power, 5)
        spec = pt.selector('creature with base power and toughness 1/1')
        self.assertTrue(pt.matches(self.g, elf, spec, self.a))
        self.g.add_continuous_effect(elf, 'set_base', power=2, toughness=2)
        self.assertFalse(pt.matches(self.g, elf, spec, self.a))

    def test_equipment_ability_follows_attachment(self):
        first, second = self.put(), self.put()
        bow = self.put('Viridian Longbow')
        bow.attached_to = first
        self.assertEqual(len(first.activated), 1)
        self.assertTrue(self.g.activate_ability(self.a, first, 0, [self.b]))
        self.assertEqual(self.b.life, 19)
        bow.attached_to = second
        self.assertFalse(first.activated)
        self.assertEqual(len(second.activated), 1)
        bow.silenced_by = second
        self.assertFalse(second.activated)

    def test_event_amount_uses_triggering_spell(self):
        wurm = self.put('Aberrant Manawurm')
        original = wurm.power
        self.mana()
        self.cast(SPELL)
        self.assertEqual(wurm.power, original + 1)

    def test_allocations_are_fixed_and_grouped_for_replacements(self):
        first, second = self.put(), self.put()
        self.put('Hardened Scales')
        self.apply('Distribute four +1/+1 counters among any number of target creatures.', [first, first, first, second])
        self.assertEqual((first.p1, second.p1), (4, 2))

    def test_allocation_lost_target_does_not_redistribute(self):
        first, second = self.put(), self.put()
        effects, _ = _parse_effects('Distribute four +1/+1 counters among any number of target creatures.')
        self.g.leave_battlefield(first, 'exile')
        self.g.stack.append(StackItem(self.a, effects, [first, first, second, second]))
        self.g.settle()
        self.assertEqual(second.p1, 2)

    def test_next_turn_modifier_survives_cleanup(self):
        target = self.put(BEAR, self.b)
        self.a.graveyard.extend([ISLAND, SPELL])
        self.apply('Target creature an opponent controls gets -X/-0 until your next turn, where X is the number of different mana values among cards in your graveyard.', [target])
        self.assertEqual(target.power, 0)
        self.g.expire_continuous_effects()
        advanced.begin_turn(self.g, self.b)
        self.assertEqual(target.power, 0)
        advanced.begin_turn(self.g, self.a)
        self.assertEqual(target.power, 2)

    def test_grave_targets_share_type_and_are_distinct(self):
        self.a.graveyard.extend([ELF, ELF, BEAR])
        effects = CARDS['Aphetto Dredging'].spell_effects
        first, second, bear = self.a.graveyard
        self.g._choosing_targets = [first]
        legal = self.g.legal_targets(self.a, effects[1])
        self.assertIn(second, legal)
        self.assertNotIn(first, legal)
        self.assertNotIn(bear, legal)
        self.g._choosing_targets = []
        self.mana()
        self.cast('Aphetto Dredging', [first, second, None])
        self.assertEqual(len(self.a.graveyard), 2)  # bear and resolved spell
        self.assertIn(first, self.a.hand)
        self.assertIn(second, self.a.hand)

    def test_opponent_cannot_force_sacrifice_but_costs_work(self):
        self.put('Sigarda, Host of Herons')
        victim = self.put()
        self.g.resolving_item = StackItem(self.b, [], [])
        self.g.sacrifice(victim)
        self.assertIn(victim, self.a.battlefield)
        self.g.resolving_item = None
        self.g.sacrifice(victim)
        self.assertNotIn(victim, self.a.battlefield)

    def test_token_receives_and_can_activate_quoted_ability(self):
        source = self.put('Triskelavus')
        self.mana(n=1)
        self.assertTrue(self.g.activate_ability(self.a, source, 0))
        token = next(x for x in self.a.creatures if x.card.is_token)
        self.assertTrue(token.has('flying'))
        self.assertTrue(self.g.activate_ability(self.a, token, 0, [self.b]))
        self.assertEqual(self.b.life, 19)
        self.assertNotIn(token, self.a.battlefield)

    def test_non_wall_aura_excludes_changelings(self):
        aura = CARDS['Aggression']
        bear, wall = self.put(), self.put(WALL)
        change = self.put(dataclasses.replace(ELF, changeling=True))
        self.assertTrue(auras.can_attach(self.g, self.a, aura, bear))
        self.assertFalse(auras.can_attach(self.g, self.a, aura, wall))
        self.assertFalse(auras.can_attach(self.g, self.a, aura, change))

    def test_activation_discount_preserves_one_mana_floor(self):
        self.put("Biomancer's Familiar")
        creature = self.put()
        self.assertEqual(advanced.activation_cost(self.g, self.a, creature, {'generic': 2}), {'generic': 1})
        self.assertEqual(advanced.activation_cost(self.g, self.a, creature, {'generic': 2, 'U': 1}), {'generic': 0, 'U': 1})
        artifact = self.put('Viridian Longbow')
        self.assertEqual(advanced.activation_cost(self.g, self.a, artifact, {'generic': 2}), {'generic': 2})

    def test_attack_tax_rejects_unpaid_attackers(self):
        self.put('Ghostly Prison', self.b)
        first, second = self.put(), self.put()
        self.mana(n=2)
        self.a.ai.attack = [first, second]
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 18)
        self.assertTrue(first.tapped)
        self.assertFalse(second.tapped)

    def test_aura_control_ends_on_detachment(self):
        target = self.put(BEAR, self.b)
        aura = self.put('Control Magic')
        auras.attach(self.g, aura, target)
        self.g.state_based_actions()
        self.assertIs(target.controller, self.a)
        auras.detach(aura)
        self.assertIs(target.controller, self.b)

    def test_source_control_expires_on_source_departure(self):
        target = self.put(BEAR, self.b)
        source = self.put('Sower of Temptation')
        self.assertIs(target.controller, self.a)
        self.g.leave_battlefield(source, 'graveyard')
        self.assertIs(target.controller, self.b)

    def test_indefinite_control_survives_source_departure(self):
        target = self.put(ISLAND, self.b)
        source = self.put('Agent of Treachery')
        self.assertIs(target.controller, self.a)
        self.g.leave_battlefield(source, 'exile')
        self.assertIs(target.controller, self.a)
        self.assertIs(target.owner, self.b)

    def test_graveyard_to_library_top_preserves_identity(self):
        for _ in range(3):
            self.put(ISLAND)
        self.a.graveyard.append(SPELL)
        source = self.a.graveyard[-1]
        self.put('Mystic Sanctuary')
        self.assertIs(self.a.library[-1], source)

    def test_tapped_entry_does_not_trigger_sanctuary(self):
        self.a.graveyard.append(SPELL)
        self.put('Mystic Sanctuary', tapped=True)
        self.assertEqual(len(self.a.graveyard), 1)

    def test_opponent_payment_gate_declined(self):
        before = len(self.a.hand)
        self.apply('You may draw a card unless that player pays {1}.', context=self.b)
        self.assertEqual(len(self.a.hand), before + 1)

    def test_opponent_payment_gate_paid(self):
        self.mana(self.b, 1)
        self.b.ai.pay_optional = lambda *args: True
        before = len(self.a.hand)
        self.apply('You may draw a card unless that player pays {1}.', context=self.b)
        self.assertEqual(len(self.a.hand), before)

    def test_populate_copies_token_characteristics_not_counters(self):
        token = self.put(make_token('Bird', 1, 1, {'flying'}), counters={'+1/+1': 3})
        self.apply('Populate.')
        copies = [x for x in self.a.creatures if x.card.is_token and x is not token]
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].power, 1)
        self.assertTrue(copies[0].has('flying'))

    def test_counter_replacements_stack_and_exclude_opponents(self):
        self.put('Hardened Scales')
        self.put('Hardened Scales')
        mine, theirs = self.put(), self.put(BEAR, self.b)
        mine.counters['+1/+1'] = 1
        theirs.counters['+1/+1'] = 1
        self.assertEqual((mine.p1, theirs.p1), (3, 1))
        mine.counters['+1/+1'] -= 1
        self.assertEqual(mine.p1, 2)

    def test_manufactor_replacement_and_multiple_sources(self):
        self.put('Academy Manufactor')
        self.put('Academy Manufactor')
        self.g.create_token(self.a, Effect('token', 1, data={'kind': 'treasure'}))
        self.assertEqual({k: sum(x.card.token_kind == k for x in self.a.battlefield) for k in ('food', 'clue', 'treasure')}, {'food': 3, 'clue': 3, 'treasure': 3})

    def test_sunburst_counts_colors_not_total_mana(self):
        self.mana(n=2)
        prism = self.cast('Pentad Prism')
        perm = next(x for x in self.a.battlefield if x.front is prism)
        self.assertEqual(perm.counters.get('charge'), 2)

    def test_sunburst_without_casting_has_no_counters(self):
        prism = self.put('Pentad Prism')
        self.assertEqual(prism.counters.get('charge', 0), 0)

    def test_energy_trigger_and_cost_are_shared_player_resource(self):
        tower = self.put('Dynavolt Tower')
        self.mana(n=3)
        self.cast(SPELL)
        self.assertEqual(self.a.counters.get('energy'), 2)
        self.a.counters['energy'] = 4
        self.assertFalse(self.g.activate_ability(self.a, tower, 0, [self.b]))
        self.assertFalse(tower.tapped)
        self.a.counters['energy'] = 5
        self.assertTrue(self.g.activate_ability(self.a, tower, 0, [self.b]))
        self.assertEqual(self.a.counters['energy'], 0)
        self.assertEqual(self.b.life, 17)

    def test_draw_replacement_exempts_first_draw_step_draw(self):
        self.put('Notion Thief', self.b)
        self.g.step = 'draw'
        self.g.draw(self.a, 2)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 1))

    def test_two_draw_replacements_apply_once_each(self):
        self.put('Notion Thief')
        self.put('Notion Thief', self.b)
        self.g.draw(self.a)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 0))

    def test_draw_limit_resets_on_turn_change(self):
        self.put('Narset, Parter of Veils', self.b)
        self.g.draw(self.a, 3)
        self.assertEqual(len(self.a.hand), 1)
        self.g.turn += 1
        self.g.draw(self.a, 2)
        self.assertEqual(len(self.a.hand), 2)

    def test_graveyard_replacement_covers_discard_death_and_mill(self):
        self.put('Rest in Peace')
        self.a.hand.append(SPELL)
        self.g.discard_card(self.a, self.a.hand[-1])
        victim = self.put()
        self.g.sacrifice(victim)
        self.g.move_card(self.a.library[-1], self.a.library, self.a.graveyard)
        self.assertEqual(len(self.a.graveyard), 0)
        self.assertEqual(len(self.a.exile), 3)
        self.assertEqual(victim.last_destination, 'exile')

    def test_grave_permission_once_each_turn_and_exile(self):
        self.put('Kess, Dissident Mage')
        self.mana()
        self.a.graveyard.extend([SPELL, SPELL])
        options = [x for x in self.g.spell_options(self.a) if self.g._origin(x)[1] == 'grave_permission']
        self.assertEqual(len(options), 2)
        self.assertTrue(self.g.cast(self.a, options[0]))
        self.assertFalse(self.g.can_cast_now(self.a, options[1]))
        self.assertEqual(len(self.a.exile), 1)
        self.g.turn += 2
        self.assertEqual(len([x for x in self.g.spell_options(self.a) if self.g._origin(x)[1] == 'grave_permission']), 1)

    def test_grave_permission_stops_on_opponent_turn(self):
        self.put('Kess, Dissident Mage')
        self.a.graveyard.append(SPELL)
        self.g.active_idx = 1
        self.assertFalse([x for x in self.g.spell_options(self.a) if self.g._origin(x)[1] == 'grave_permission'])

    def test_cipher_encodes_and_casts_copy_on_damage(self):
        host = self.put()
        victim = self.put(BEAR, self.b)
        self.mana(n=2)
        spell = self.cast('Hands of Binding', [victim])
        self.assertIn(spell, self.a.exile)
        self.assertTrue(host.encoded)
        advanced.cipher_damage(self.g, host)
        self.g.settle()
        self.assertEqual(len(self.a.exile), 1)
        self.assertEqual(len(self.a.graveyard), 0)
        self.assertEqual(self.g.spells_cast_turn(self.a), 2)

    def test_cipher_stale_reference_stops_trigger(self):
        host = self.put()
        victim = self.put(BEAR, self.b)
        self.mana(n=2)
        spell = self.cast('Hands of Binding', [victim])
        self.g.move_card(spell, self.a.exile, self.a.hand)
        self.g.move_card(spell, self.a.hand, self.a.exile)
        advanced.cipher_damage(self.g, host)
        self.assertFalse(self.g.pending)

    def test_aftermath_only_available_from_graveyard(self):
        c = CARDS['Dusk // Dawn']
        self.a.hand.append(c)
        self.assertFalse(any(self.g._origin(x)[1] == 'aftermath' for x in self.g.spell_options(self.a)))
        self.g.move_card(self.a.hand[-1], self.a.hand, self.a.graveyard)
        self.mana()
        self.a.pool = []
        # Dawn costs WW: add two Plains.
        from tests.test_templates import PLAINS
        self.put(PLAINS)
        self.put(PLAINS)
        option = next(x for x in self.g.spell_options(self.a) if self.g._origin(x)[1] == 'aftermath')
        self.assertTrue(self.g.cast(self.a, option))
        self.assertEqual(len(self.a.exile), 1)

    def test_foreign_permission_uses_any_mana_and_owner_destination(self):
        self.b.library = [SPELL] * 4
        source = self.put('Gonti, Lord of Luxury')
        self.assertEqual(len(self.a.foreign_permissions), 1)
        self.g.leave_battlefield(source, 'exile')
        self.put(FOREST)
        option = next(x for x in self.g.spell_options(self.a) if self.g._origin(x)[1].startswith('foreign_'))
        self.assertTrue(self.g.cast(self.a, option))
        self.assertEqual(len(self.b.graveyard), 1)
        self.assertEqual(len(self.a.graveyard), 0)

    def test_foreign_permission_expires_when_card_changes_zones(self):
        self.b.library = [SPELL] * 4
        self.put('Gonti, Lord of Luxury')
        zone, ref = self.a.foreign_permissions[0]
        spell = ref.find(zone)
        self.g.move_card(spell, zone, self.b.hand)
        self.g.move_card(spell, self.b.hand, zone)
        self.assertFalse(any(self.g._origin(x)[1].startswith('foreign_') for x in self.g.spell_options(self.a)))

    def test_conditional_cast_limit_uses_actual_land_count(self):
        self.put('Lavinia, Azorius Renegade', self.b)
        self.a.hand.append(SPELL)
        self.assertFalse(self.g.can_cast_now(self.a, self.a.hand[-1]))
        self.put(ISLAND)
        self.assertTrue(self.g.can_cast_now(self.a, self.a.hand[-1]))

    def test_blood_moon_converts_and_restores_nonbasic_lands(self):
        land = self.put(CARDS['Mystic Sanctuary'])
        basic = self.put(ISLAND)
        moon = self.put('Blood Moon')
        self.assertEqual(land.card.subtypes, frozenset({'Mountain'}))
        self.assertEqual(land.card.produces, frozenset({'R'}))
        self.assertEqual(basic.card.produces, frozenset({'U'}))
        self.assertFalse(land.triggers)
        self.g.leave_battlefield(moon, 'graveyard')
        self.g.state_based_actions()
        self.assertEqual(land.card.subtypes, frozenset({'Island'}))
        self.assertEqual(land.card.produces, frozenset({'U'}))

    def test_blood_moon_removes_entry_abilities_before_entry(self):
        self.put('Blood Moon')
        tapland = card('Test tapland', '', 'Land', 'Test tapland enters tapped.\n{T}: Add {U}.')
        land = self.put(tapland)
        self.assertFalse(land.tapped)
        self.assertEqual(land.card.produces, frozenset({'R'}))

    def test_base_stats_grouped_entry_triggers_once(self):
        bess = self.put('Bess, Soul Nourisher')
        self.g.enter_battlefield_many(self.a, [ELF, ELF])
        self.g.settle()
        self.assertEqual(bess.p1, 1)

    def test_multiple_grave_targets_reject_stale_identity(self):
        self.a.graveyard.append(ELF)
        victim = self.a.graveyard[-1]
        effects = CARDS['Aphetto Dredging'].spell_effects
        item = StackItem(self.a, effects, [victim, None, None])
        self.g.check_ward(item)
        self.g.move_card(victim, self.a.graveyard, self.a.hand)
        self.g.move_card(victim, self.a.hand, self.a.graveyard)
        self.g.stack.append(item)
        self.g.settle()
        self.assertIn(victim, self.a.graveyard)

    def test_graveyard_common_type_cannot_be_bridged_by_changeling(self):
        change = dataclasses.replace(ELF, changeling=True)
        self.a.graveyard.extend([change, ELF, BEAR])
        first, elf, bear = self.a.graveyard
        self.g._choosing_targets = [first, elf]
        self.assertNotIn(bear, self.g.legal_targets(self.a, CARDS['Aphetto Dredging'].spell_effects[2]))

    def test_allocation_only_triggers_ward_once_per_creature(self):
        target = self.put(dataclasses.replace(BEAR, ward=1), self.b)
        effects, _ = _parse_effects('Distribute four +1/+1 counters among any number of target creatures.')
        item = StackItem(self.a, effects, [target] * 4, card=SPELL)
        self.g.check_ward(item)
        self.assertEqual(len(self.g.pending), 1)

    def test_source_bound_control_does_not_start_after_source_dies(self):
        target = self.put(BEAR, self.b)
        source = self.put()
        self.g.leave_battlefield(source, 'graveyard')
        self.apply('Gain control of target creature for as long as ~ remains on the battlefield.', [target], source)
        self.assertIs(target.controller, self.b)

    def test_aura_control_tracks_aura_controller_changes(self):
        target = self.put(BEAR, self.b)
        aura = self.put('Control Magic')
        auras.attach(self.g, aura, target)
        self.g.state_based_actions()
        from mtgsim.counter_mechanics import add_control
        add_control(self.g, aura, self.b)
        self.g.state_based_actions()
        self.assertIs(target.controller, self.b)
        self.assertIs(target.owner, self.b)

    def test_aura_control_ends_when_ability_is_lost(self):
        target = self.put(BEAR, self.b)
        aura = self.put('Control Magic')
        auras.attach(self.g, aura, target)
        silencer = self.put()
        aura.silenced_by = silencer
        self.g.state_based_actions()
        self.assertIs(target.controller, self.b)

    def test_entry_grave_trigger_still_resolves_if_land_is_tapped_later(self):
        for _ in range(3):
            self.put(ISLAND)
        from unittest.mock import patch
        self.a.graveyard.append(SPELL)
        victim = self.a.graveyard[-1]
        with patch.object(self.g, 'settle'):
            source = self.g.enter_battlefield(self.a, CARDS['Mystic Sanctuary'])
        source.tapped = True
        self.g.settle()
        self.assertIs(self.a.library[-1], victim)

    def test_counter_replacement_applies_to_entry_counters(self):
        self.put('Hardened Scales')
        trisk = self.put('Triskelavus')
        self.assertEqual(trisk.p1, 4)

    def test_manufactor_and_token_doublers_compose(self):
        self.put('Academy Manufactor')
        doubler = card('Token doubler', '', 'Enchantment', 'If one or more tokens would be created under your control, twice that many of those tokens are created instead.')
        self.put(doubler)
        self.g.create_token(self.a, Effect('token', 2, data={'kind': 'food'}))
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), 12)

    def test_populate_has_no_effect_without_a_creature_token(self):
        self.put()
        self.g.create_token(self.a, Effect('token', 1, data={'kind': 'treasure'}))
        before = len(self.a.battlefield)
        self.apply('Populate.')
        self.assertEqual(len(self.a.battlefield), before)

    def test_sunburst_does_not_count_colorless_mana(self):
        wastes = card('Wastes', types='Basic Land', text='{T}: Add {C}.')
        self.put(wastes)
        self.put(ISLAND)
        physical = self.cast('Pentad Prism')
        perm = next(x for x in self.a.battlefield if x.front is physical)
        self.assertEqual(perm.counters['charge'], 1)

    def test_draw_replacement_respects_redirected_players_draw_limit(self):
        self.put('Notion Thief', self.b)
        self.put('Narset, Parter of Veils')
        self.g.draw(self.a, 3)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, 1))

    def test_grave_replacement_does_not_trigger_creature_death(self):
        self.put('Rest in Peace')
        watcher = card('Death watcher', '', 'Creature', 'Whenever another creature dies, draw a card.', 1, 1)
        self.put(watcher)
        victim = self.put()
        before = len(self.a.hand)
        self.g.sacrifice(victim)
        self.g.settle()
        self.assertEqual(len(self.a.hand), before)
        self.assertEqual(self.a.graveyard.descents, 0)

    def test_grave_replacement_covers_tokens_and_itself(self):
        source = self.put('Rest in Peace')
        token = self.put(make_token('Test', 1, 1))
        self.g.sacrifice(token)
        self.assertEqual(token.last_destination, 'exile')
        self.g.sacrifice(source)
        self.assertIn(source.front, self.a.exile)
        self.assertFalse(self.a.graveyard)

    def test_grave_replacement_covers_zone_slice_insertions(self):
        self.put('Rest in Peace')
        self.a.graveyard[:] = [BEAR, SPELL]
        self.assertFalse(self.a.graveyard)
        self.assertEqual(len(self.a.exile), 2)

    def test_grave_permission_revoked_before_cast_if_provider_leaves(self):
        source = self.put('Kess, Dissident Mage')
        self.a.graveyard.append(SPELL)
        self.mana()
        option = next(x for x in self.g.spell_options(self.a) if self.g._origin(x)[1] == 'grave_permission')
        self.g.leave_battlefield(source, 'exile')
        self.assertFalse(self.g.cast(self.a, option))
        self.assertEqual(len(self.a.graveyard), 1)

    def test_foreign_exile_is_face_down_until_card_leaves(self):
        self.b.library = [SPELL] * 4
        self.put('Gonti, Lord of Luxury')
        zone, ref = self.a.foreign_permissions[0]
        spell = ref.find(zone)
        self.assertTrue(spell.face_down_exile)
        self.g.move_card(spell, zone, self.b.hand)
        self.assertFalse(spell.face_down_exile)

    def test_blood_moon_preserves_supertype_and_restores_activated_abilities(self):
        land = card('Legendary test land', '', 'Legendary Land', '{T}: Add {U}.\n{1}, {T}: Draw a card.')
        permanent = self.put(land)
        self.assertTrue(permanent.activated)
        moon = self.put('Blood Moon')
        self.assertTrue(permanent.card.legendary)
        self.assertFalse(permanent.activated)
        self.g.leave_battlefield(moon, 'exile')
        self.g.state_based_actions()
        self.assertTrue(permanent.activated)

    def test_planner_can_use_allocation_spell(self):
        from mtgsim.ai import HeuristicAI
        self.a.ai = HeuristicAI()
        self.put()
        self.mana()
        plan = self.a.ai.plan_spell(self.g, self.a, CARDS['Blessings of Nature'])
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan[1]), 4)

    def test_kess_countered_spell_goes_to_exile(self):
        from unittest.mock import patch
        self.put('Kess, Dissident Mage')
        self.a.graveyard.append(SPELL)
        self.mana()
        option = next(x for x in self.g.spell_options(self.a) if self.g._origin(x)[1] == 'grave_permission')
        with patch.object(self.g, 'settle'):
            self.assertTrue(self.g.cast(self.a, option))
        item = self.g.stack[-1]
        self.g.counter(self.b, Effect('counter', target='spell'), item)
        self.assertEqual(len(self.a.exile), 1)
        self.assertFalse(self.a.graveyard)

    def test_aftermath_bounced_spell_is_exiled(self):
        self.a.graveyard.append(CARDS['Dusk // Dawn'])
        base = self.a.graveyard.pop()
        variant = self.g._variant(base, 'aftermath')
        item = StackItem(self.a, [], [], card=variant)
        self.g.stack.append(item)
        self.g.counter(self.b, Effect('bounce_spell', target='spell'), item)
        self.assertIn(base, self.a.exile)
        self.assertNotIn(base, self.a.hand)

    def test_aura_control_resumes_after_suppression_ends(self):
        target = self.put(BEAR, self.b)
        aura = self.put('Control Magic')
        auras.attach(self.g, aura, target)
        silencer = self.put()
        aura.silenced_by = silencer
        self.g.state_based_actions()
        self.assertIs(target.controller, self.b)
        self.g.leave_battlefield(silencer, 'exile')
        self.g.state_based_actions()
        self.assertIs(target.controller, self.a)

    def test_event_amount_includes_x_payment(self):
        source = self.put('Aberrant Manawurm')
        before = source.power
        context = StackItem(self.a, [], [], card=SPELL)
        context.mana_spent, context.x = 1, 4
        self.apply('~ gets +X/+0 until end of turn, where X is the amount of mana spent to cast that spell.', source=source, context=context)
        self.assertEqual(source.power, before + 5)

    def test_unknown_variable_allocation_stays_visible(self):
        _, ignored = _parse_effects('Distribute X +1/+1 counters among any number of target creatures.')
        self.assertTrue(ignored)

    def test_each_draw_replacement_source_applies_once(self):
        self.put('Notion Thief')
        self.put('Notion Thief', self.b)
        self.put('Notion Thief', self.b)
        self.g.draw(self.a)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, 1))

    def test_cipher_trigger_is_removed_when_host_loses_abilities(self):
        host = self.put()
        victim = self.put(BEAR, self.b)
        self.mana(n=2)
        self.cast('Hands of Binding', [victim])
        host.silenced_by = victim
        advanced.cipher_damage(self.g, host)
        self.assertFalse(self.g.pending)
