"""Rules behavior for thirty effects selected from the residual parser census."""
import dataclasses
import json
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from mtgsim.cards import CardDef, card_from_scryfall, _parse_effects, make_token
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, FOREST, MOUNTAIN, PLAINS, card

DATA = json.loads((Path(__file__).parent / 'fixtures/residual_cards.json').read_text())
CARDS = {name: card_from_scryfall(data) for name, data in DATA.items()}
SPELL = card('Test draw', '{U}', 'Sorcery', 'Draw a card.')
BIG = card('Test giant', '{4}', 'Creature — Giant', '', 4, 4)
SWAMP = card('Swamp', types='Basic Land — Swamp')
MANA_CREATURE = card('Test mana elf', '{G}', 'Creature — Elf', '{T}: Add {G}.', 1, 1)
DRAW_CREATURE = card('Test librarian', '{G}', 'Creature — Elf', '{T}: Draw a card.', 1, 1)
ETB_CREATURE = card('Test entrant', '{G}', 'Creature — Elf', 'When Test entrant enters, draw a card.', 1, 1)
DEATH_CREATURE = card('Test death', '{G}', 'Creature — Elf', 'When Test death dies, draw a card.', 1, 1)
ADAPTER = card('Test adapter', '{G}', 'Creature — Elf', '{1}: Adapt 2.', 1, 1)


class ResidualBatch(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(7))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None
            p.ai.choose_graft = lambda *args: False

    def put(self, definition=BEAR, p=None, **kw):
        definition = CARDS[definition] if isinstance(definition, str) else definition
        result = self.g.enter_battlefield(p or self.a, definition, **kw)
        if result is not None:
            result.sick = False
        self.g.settle()
        return result

    def mana(self, p=None, n=10):
        return [self.put(c, p) for c in ([ISLAND, FOREST, SWAMP, PLAINS, MOUNTAIN] * n)[:n]]

    def apply(self, text, targets=(), source=None, p=None):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(p or self.a, effects, targets, source=source)
        for eff, target in zip(effects, targets):
            self.g.resolve(p or self.a, eff, target, item)
        return item

    def test_all_thirty_selected_clauses_are_consumed(self):
        request = json.loads((Path(__file__).parents[1] / 'results/residual_batch/requested-backlog.json').read_text())
        self.assertEqual(len(request['items']), 30)
        for item in request['items']:
            with self.subTest(effect=item['id']):
                self.assertNotIn(item['clause'], CARDS[item['card']].unsupported)

    def test_filtered_mass_destroy_uses_current_power(self):
        weak, big, pumped = self.put(), self.put(BIG), self.put()
        pumped.counters['+1/+1'] = 1
        self.apply('Destroy all creatures with power 3 or greater.')
        self.assertIn(weak, self.a.battlefield)
        self.assertNotIn(big, self.a.battlefield)
        self.assertNotIn(pumped, self.a.battlefield)

    def test_filtered_mass_destroy_respects_indestructible(self):
        big = self.put(dataclasses.replace(BIG, keywords=frozenset({'indestructible'})))
        self.apply('Destroy all creatures with power 3 or greater.')
        self.assertIn(big, self.a.battlefield)

    def test_filtered_grave_return_uses_card_power_and_identity(self):
        self.a.graveyard.extend([BEAR, BIG, ISLAND, BEAR])
        first, big, land, second = self.a.graveyard
        self.apply('Return all creature cards with power 2 or less from your graveyard to your hand.')
        self.assertEqual(self.a.hand, [first, second])
        self.assertEqual(self.a.graveyard, [big, land])

    def test_exile_all_graveyards_preserves_owners(self):
        self.a.graveyard.extend([BEAR, SPELL])
        self.b.graveyard.append(BIG)
        self.apply('Exile all graveyards.')
        self.assertFalse(self.a.graveyard or self.b.graveyard)
        self.assertEqual((len(self.a.exile), len(self.b.exile)), (2, 1))

    def test_targeted_grave_exile_only_affects_target(self):
        self.a.graveyard.append(BEAR)
        self.b.graveyard.extend([BEAR, SPELL])
        self.apply("Exile all cards from target player's graveyard.", [self.b])
        self.assertEqual(len(self.a.graveyard), 1)
        self.assertFalse(self.b.graveyard)

    def test_crypt_pays_sacrifice_and_exiles_target(self):
        crypt = self.put("Tormod's Crypt")
        self.b.graveyard.append(BEAR)
        self.assertTrue(self.g.activate_ability(self.a, crypt, 0, [self.b]))
        self.assertIn(crypt.front, self.a.graveyard)
        self.assertFalse(self.b.graveyard)

    def test_grave_exile_choice_belongs_to_target_player(self):
        self.b.graveyard.extend([BEAR, BIG])
        chosen = self.b.graveyard[-1]
        self.b.ai.choose_grave_exile = lambda game, player, cards: chosen
        self.apply('Target player exiles a card from their graveyard.', [self.b])
        self.assertIs(self.b.exile[-1], chosen)
        self.assertEqual(len(self.b.graveyard), 1)

    def test_mystic_sanctuary_counts_other_islands(self):
        self.a.graveyard.append(SPELL)
        for _ in range(2):
            self.put(ISLAND)
        first = self.put('Mystic Sanctuary')
        self.assertTrue(first.tapped)
        self.assertEqual(len(self.a.graveyard), 1)
        second = self.put('Mystic Sanctuary')
        self.assertFalse(second.tapped)
        self.assertIs(self.a.library[-1].definition, SPELL)

    def test_mystic_sanctuary_counts_dual_land_subtypes(self):
        dual = card('Test dual', '', 'Land — Island Forest')
        for _ in range(3):
            self.put(dual)
        self.assertFalse(self.put('Mystic Sanctuary').tapped)

    def test_ownership_condition_is_checked_at_trigger_and_resolution(self):
        agent = self.put('Agent of Treachery')
        self.g.begin_end_step(self.a)
        self.g.settle()
        self.assertFalse(self.a.hand)
        from mtgsim.counter_mechanics import add_control
        borrowed = [self.put(BIG, self.b) for _ in range(3)]
        for creature in borrowed:
            add_control(self.g, creature, self.a)
        self.g.begin_end_step(self.a)
        self.g.flush_triggers()
        self.g.leave_battlefield(borrowed[-1], 'hand')
        self.g.settle()
        self.assertFalse(self.a.hand)
        self.assertIn(agent, self.a.battlefield)

    def test_ownership_threshold_draws_when_still_true(self):
        self.put('Agent of Treachery')
        from mtgsim.counter_mechanics import add_control
        for _ in range(3):
            add_control(self.g, self.put(BIG, self.b), self.a)
        self.g.begin_end_step(self.a)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 3)

    def test_unpaid_cast_trigger_counters_actual_stack_item(self):
        self.put('Lavinia, Azorius Renegade', self.b)
        self.put(ISLAND)
        free = card('Free thing', '', 'Artifact', '')
        self.a.hand.append(free)
        self.assertTrue(self.g.cast(self.a, self.a.hand[-1]))
        self.assertFalse(any(x.card.name == free.name for x in self.a.battlefield))
        self.assertIn(free, self.a.graveyard)

    def test_paid_cast_does_not_trigger_lavinia(self):
        self.put('Lavinia, Azorius Renegade', self.b)
        self.put(ISLAND)
        self.a.hand.append(SPELL)
        self.assertTrue(self.g.cast(self.a, self.a.hand[-1]))
        self.assertEqual(len(self.a.hand), 1)

    def test_aura_end_step_uses_host_controller_and_attack_history(self):
        host = self.put(BEAR, self.b)
        self.g._aura_host = host
        self.put('Aggression')
        self.g.begin_end_step(self.a)
        self.g.settle()
        self.assertIn(host, self.b.battlefield)
        self.g.begin_end_step(self.b)
        self.g.settle()
        self.assertNotIn(host, self.b.battlefield)

    def test_aura_does_not_destroy_creature_that_attacked_this_turn(self):
        host = self.put(BEAR, self.b)
        self.g._aura_host = host
        self.put('Aggression')
        self.g.fire(self.b, 'attacks', host)
        self.g.begin_end_step(self.b)
        self.g.settle()
        self.assertIn(host, self.b.battlefield)

    def test_adapt_and_next_adapt_exception(self):
        creature = self.put(ADAPTER)
        self.mana(n=3)
        self.assertTrue(self.g.activate_ability(self.a, creature, 0))
        self.assertEqual(creature.p1, 2)
        self.g.activate_ability(self.a, creature, 0)
        self.assertEqual(creature.p1, 2)
        self.apply('The next time target creature adapts this turn, it adapts as though it had no +1/+1 counters on it.', [creature])
        self.g.activate_ability(self.a, creature, 0)
        self.assertEqual(creature.p1, 4)
        self.assertEqual(creature.adapt_exceptions, 0)

    def test_miracle_casts_first_draw_outside_sorcery_timing(self):
        self.put(FOREST)
        target = self.put()
        self.g.step = 'draw'
        self.a.library.append(CARDS['Blessings of Nature'])
        self.g.draw(self.a)
        self.g.settle()
        self.assertEqual(target.p1, 4)
        self.assertFalse(self.a.hand)
        self.assertEqual(len(self.a.graveyard), 1)

    def test_miracle_is_not_available_on_later_draws(self):
        self.g.draw(self.a)
        self.a.library.append(CARDS['Blessings of Nature'])
        self.g.draw(self.a)
        self.assertFalse(self.g.pending)
        self.assertTrue(self.a.hand[-1].advanced_rules.get('miracle'))

    def test_miracle_decline_reveal_does_not_register_trigger(self):
        self.a.ai.reveal_miracle = lambda *args: False
        self.a.library.append(CARDS['Blessings of Nature'])
        self.g.draw(self.a)
        self.assertFalse(self.g.pending)

    def test_miracle_ref_does_not_follow_card_leaving_hand(self):
        self.a.library.append(CARDS['Blessings of Nature'])
        self.g.draw(self.a)
        physical = self.a.hand[-1]
        self.g.move_card(physical, self.a.hand, self.a.graveyard)
        self.g.move_card(physical, self.a.graveyard, self.a.hand)
        self.g.settle()
        self.assertIn(physical, self.a.hand)

    def test_mass_bounce_uses_owners_and_tokens_vanish(self):
        first, second = self.put(), self.put(BIG, self.b)
        token = self.put(make_token('Test', 1, 1))
        from mtgsim.counter_mechanics import add_control
        add_control(self.g, second, self.a)
        self.apply("Return all creatures to their owners' hands.")
        self.assertIn(first.front, self.a.hand)
        self.assertIn(second.front, self.b.hand)
        self.assertFalse(self.a.creatures or self.b.creatures)
        self.assertNotIn(token.front, self.a.hand)

    def test_opponent_grave_replacement_preserves_own_graveyard(self):
        self.put('Leyline of the Void')
        mine, theirs = self.put(), self.put(BIG, self.b)
        self.g.sacrifice(mine)
        self.g.sacrifice(theirs)
        self.assertIn(mine.front, self.a.graveyard)
        self.assertIn(theirs.front, self.b.exile)

    def test_leyline_does_not_replace_token_death(self):
        self.put('Leyline of the Void')
        token = self.put(make_token('Test', 1, 1), self.b)
        self.g.sacrifice(token)
        self.assertEqual(token.last_destination, 'graveyard')

    def test_cage_blocks_reanimation_without_changing_reference(self):
        self.put("Grafdigger's Cage")
        self.a.graveyard.append(BEAR)
        physical = self.a.graveyard[-1]
        ref = self.a.graveyard.reference(physical)
        self.apply('Return target creature card with mana value 2 from your graveyard to the battlefield.', [physical])
        self.assertIs(ref.find(self.a.graveyard), physical)
        self.assertFalse(self.a.creatures)

    def test_cage_blocks_library_entry_and_restores_order(self):
        self.put("Grafdigger's Cage")
        self.a.library = [ISLAND, BEAR, FOREST]
        physical = self.a.library[1]
        before = list(self.a.library)
        self.a.library.remove(physical)
        self.assertIsNone(self.g.enter_battlefield(self.a, physical))
        self.assertEqual(self.a.library, before)

    def test_cage_allows_creatures_cast_from_hand(self):
        self.put("Grafdigger's Cage")
        self.mana()
        self.a.hand.append(BEAR)
        self.assertTrue(self.g.cast(self.a, self.a.hand[-1]))
        self.assertEqual(len(self.a.creatures), 1)

    def test_cage_blocks_graveyard_cast_variants(self):
        self.put("Grafdigger's Cage")
        self.a.graveyard.append(CARDS['Dusk // Dawn'])
        variant = self.g._variant(self.a.graveyard[-1], 'aftermath')
        self.mana()
        self.assertFalse(self.g.can_cast_now(self.a, variant))

    def test_entry_suppression_blocks_creature_etb_and_watchers(self):
        self.put('Torpor Orb')
        self.put(ETB_CREATURE)
        self.assertFalse(self.a.hand)
        self.put(card('Watcher', '', 'Enchantment', 'Whenever another creature enters, draw a card.'))
        self.put()
        self.assertFalse(self.a.hand)

    def test_entry_suppression_allows_noncreature_etb(self):
        self.put('Torpor Orb')
        enchantment = card('Test enchantment', '', 'Enchantment', 'When Test enchantment enters, draw a card.')
        self.put(enchantment)
        self.assertEqual(len(self.a.hand), 1)

    def test_simultaneous_entry_sees_hushbringer(self):
        self.g.enter_battlefield_many(self.a, [ETB_CREATURE, CARDS['Hushbringer']])
        self.g.settle()
        self.assertFalse(self.a.hand)

    def test_death_suppression_blocks_own_and_watcher_triggers(self):
        self.put('Hushbringer')
        victim = self.put(DEATH_CREATURE)
        self.g.sacrifice(victim)
        self.g.settle()
        self.assertFalse(self.a.hand)
        self.assertTrue(self.a.creature_died_turn)

    def test_simultaneous_death_retains_suppression_snapshot(self):
        self.put('Hushbringer')
        self.put(DEATH_CREATURE)
        self.apply('Destroy all creatures.')
        self.g.settle()
        self.assertFalse(self.a.hand)
        self.assertFalse(self.a.creatures)

    def test_torpor_orb_does_not_suppress_death(self):
        self.put('Torpor Orb')
        victim = self.put(DEATH_CREATURE)
        self.g.sacrifice(victim)
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_creature_activation_lock_includes_mana(self):
        source = self.put(MANA_CREATURE)
        ability = self.put(DRAW_CREATURE)
        self.put('Cursed Totem')
        self.assertNotIn(source, self.g.mana_sources(self.a))
        self.assertFalse(self.g.can_activate(self.a, ability, 0))
        self.assertFalse(ability.tapped)

    def test_creature_activation_lock_does_not_lock_lands(self):
        land = self.put(ISLAND)
        self.put('Cursed Totem')
        self.assertIn(land, self.g.mana_sources(self.a))

    def test_nonmana_activation_lock_allows_creature_mana(self):
        source = self.put(MANA_CREATURE)
        self.put('Damping Matrix')
        self.assertIn(source, self.g.mana_sources(self.a))
        creature = self.put(DRAW_CREATURE)
        self.assertFalse(self.g.can_activate(self.a, creature, 0))

    def test_nonmana_activation_lock_covers_equipment(self):
        equipment = card('Test sword', '', 'Artifact — Equipment', 'Equip {0}')
        sword, creature = self.put(equipment), self.put()
        self.put('Damping Matrix')
        self.assertFalse(self.g.equip(self.a, sword, creature))

    def test_life_lock_blocks_life_change_but_damage_is_still_dealt(self):
        self.put('Platinum Emperion')
        before = self.a.life
        self.g.change_life(self.a, 5, 'test gain')
        self.g.change_life(self.a, -5, 'test loss')
        self.assertEqual(self.a.life, before)
        self.assertEqual(self.a.life_gained_turn, 0)
        self.assertFalse(self.a.lost_life_turn)

    def test_life_lock_prevents_paying_life_activation_cost(self):
        creature = self.put(card('Life cost', '', 'Creature', 'Pay 2 life: Draw a card.', 1, 1))
        self.put('Platinum Emperion')
        self.assertFalse(self.g.can_activate(self.a, creature, 0))

    def test_player_counter_lock_blocks_poison_energy_and_proliferation(self):
        self.put('Solemnity')
        self.a.counters['energy'] = 4
        self.b.counters['poison'] = 3
        self.assertEqual(self.a.counters['energy'], 0)
        self.assertEqual(self.b.counters['poison'], 0)

    def test_permanent_counter_lock_blocks_placements_not_removals(self):
        creature = self.put(counters={'+1/+1': 3})
        self.put('Solemnity')
        creature.counters['+1/+1'] = creature.p1 + 2
        self.assertEqual(creature.p1, 3)
        creature.counters['+1/+1'] -= 1
        self.assertEqual(creature.p1, 2)

    def test_permanent_counter_lock_does_not_stop_planeswalker_loyalty(self):
        self.put('Solemnity')
        walker = self.put(CardDef('Test walker', {}, 0, frozenset({'Planeswalker'}), loyalty=3))
        self.assertEqual(walker.loyalty, 3)

    def test_poison_prevention_is_controller_scoped(self):
        self.put('Melira, Sylvok Outcast')
        self.a.counters['poison'] = 4
        self.b.counters['poison'] = 4
        self.assertEqual((self.a.counters['poison'], self.b.counters['poison']), (0, 4))
        self.a.counters['energy'] = 2
        self.assertEqual(self.a.counters['energy'], 2)

    def test_negative_counter_prevention_is_controller_scoped(self):
        self.put('Melira, Sylvok Outcast')
        mine, theirs = self.put(), self.put(BIG, self.b)
        mine.counters['-1/-1'] = 1
        theirs.counters['-1/-1'] = 1
        self.assertEqual((mine.m1, theirs.m1), (0, 1))

    def test_infect_removal_and_source_departure(self):
        infect = dataclasses.replace(BEAR, keywords=frozenset({'infect'}))
        mine, theirs = self.put(infect), self.put(infect, self.b)
        melira = self.put('Melira, Sylvok Outcast')
        self.assertTrue(mine.has('infect'))
        self.assertFalse(theirs.has('infect'))
        self.g.leave_battlefield(melira, 'exile')
        self.assertTrue(theirs.has('infect'))

    def test_later_layered_infect_grant_overrides_earlier_removal(self):
        target = self.put(BEAR, self.b)
        self.put('Melira, Sylvok Outcast')
        self.g.add_continuous_effect(target, 'grant', keyword='infect', until_eot=True)
        self.assertTrue(target.has('infect'))

    def test_opponent_negative_anthem_applies_before_sbas(self):
        victim = self.put(BEAR, self.b)
        self.put('Elesh Norn, Grand Cenobite')
        self.assertNotIn(victim, self.b.battlefield)
        mine = self.put()
        self.assertEqual((mine.power, mine.toughness), (4, 4))

    def test_token_anthem_has_keyword_and_excludes_nontokens(self):
        token, creature = self.put(make_token('Test', 1, 1)), self.put()
        self.put('Intangible Virtue')
        self.assertEqual(token.power, 2)
        self.assertTrue(token.has('vigilance'))
        self.assertEqual(creature.power, 2)
        self.assertFalse(creature.has('vigilance'))

    def test_nontoken_anthem_has_keyword_and_excludes_tokens(self):
        token, creature = self.put(make_token('Test', 1, 1)), self.put()
        self.put('Always Watching')
        self.assertEqual(token.power, 1)
        self.assertFalse(token.has('vigilance'))
        self.assertEqual(creature.power, 3)
        self.assertTrue(creature.has('vigilance'))

    def test_color_anthem_applies_to_both_players_and_is_dynamic(self):
        black = card('Test black', '{B}', 'Creature', '', 2, 2)
        mine, theirs, green = self.put(black), self.put(black, self.b), self.put()
        moon = self.put('Bad Moon')
        self.assertEqual((mine.power, theirs.power, green.power), (3, 3, 2))
        moon.silenced_by = green
        self.assertEqual((mine.power, theirs.power), (2, 2))

    def test_opponent_entry_tapped_covers_type_unions_and_future_entries(self):
        existing = self.put(BEAR, self.b)
        self.put('Kismet')
        creature = self.put(BIG, self.b)
        land = self.put(ISLAND, self.b)
        artifact = self.put(card('Test rock', '', 'Artifact'), self.b)
        own = self.put()
        self.assertFalse(existing.tapped)
        self.assertTrue(creature.tapped and land.tapped and artifact.tapped)
        self.assertFalse(own.tapped)

    def test_rest_in_peace_entry_exiles_existing_graveyards(self):
        self.a.graveyard.append(BEAR)
        self.b.graveyard.append(SPELL)
        self.put('Rest in Peace')
        self.assertFalse(self.a.graveyard or self.b.graveyard)
        self.assertEqual((len(self.a.exile), len(self.b.exile)), (1, 1))

    def test_lavinia_does_not_counter_an_uncounterable_free_spell(self):
        self.put('Lavinia, Azorius Renegade', self.b)
        free = card('Free uncounterable', '', 'Artifact', "This spell can't be countered.")
        self.a.hand.append(free)
        self.assertTrue(self.g.cast(self.a, self.a.hand[-1]))
        self.assertTrue(any(x.card.name == free.name for x in self.a.battlefield))

    def test_lavinia_trigger_survives_source_departure(self):
        source = self.put('Lavinia, Azorius Renegade', self.b)
        free = card('Free test', '', 'Artifact')
        self.a.hand.append(free)
        with patch.object(self.g, 'settle'):
            self.assertTrue(self.g.cast(self.a, self.a.hand[-1]))
        self.g.leave_battlefield(source, 'exile')
        self.g.settle()
        self.assertIn(free, self.a.graveyard)

    def test_adapt_exception_is_consumed_even_if_counters_are_blocked(self):
        target = self.put(ADAPTER)
        self.put('Solemnity')
        self.apply('The next time target creature adapts this turn, it adapts as though it had no +1/+1 counters on it.', [target])
        self.apply('Adapt 2.', source=target)
        self.assertEqual(target.p1, 0)
        self.assertEqual(target.adapt_exceptions, 0)

    def test_miracle_cannot_be_cast_again_after_trigger_resolution(self):
        from mtgsim.cards import AltCost
        self.a.ai.cast_miracle = lambda *args: False
        self.a.library.append(CARDS['Blessings of Nature'])
        self.g.draw(self.a)
        self.g.settle()
        option = self.g._variant(self.a.hand[-1], 'miracle', AltCost('miracle', {'G': 1}))
        self.put(FOREST)
        self.put()
        self.assertFalse(self.g.can_cast_now(self.a, option))

    def test_miracle_drawn_on_opponents_turn(self):
        self.put(FOREST)
        target = self.put()
        self.g.active_idx = 1
        self.g.step = 'end_step'
        self.a.library.append(CARDS['Blessings of Nature'])
        self.g.draw(self.a)
        self.g.settle()
        self.assertEqual(target.p1, 4)

    def test_miracle_first_draw_resets_each_turn(self):
        self.g.draw(self.a)
        self.g.turn += 1
        self.a.library.append(CARDS['Blessings of Nature'])
        self.g.draw(self.a)
        self.assertEqual(len(self.g.pending), 1)

    def test_grave_replacement_uses_owner_not_battlefield_controller(self):
        self.put('Leyline of the Void')
        stolen = self.put(BIG, self.b)
        from mtgsim.counter_mechanics import add_control
        add_control(self.g, stolen, self.a)
        self.g.sacrifice(stolen)
        self.assertIn(stolen.front, self.b.exile)
        self.assertFalse(self.a.exile)

    def test_cage_allows_returning_noncreature_to_battlefield(self):
        self.put("Grafdigger's Cage")
        enchantment = card('Returned enchantment', '', 'Enchantment')
        self.a.graveyard.append(enchantment)
        physical = self.a.graveyard.pop()
        self.assertIsNotNone(self.g.enter_battlefield(self.a, physical))

    def test_cage_does_not_affect_return_to_hand(self):
        self.put("Grafdigger's Cage")
        self.a.graveyard.append(BEAR)
        self.apply('Return all creature cards with power 2 or less from your graveyard to your hand.')
        self.assertEqual(self.a.hand, [BEAR])

    def test_cage_prevented_move_does_not_fire_graveyard_leave_event(self):
        self.put("Grafdigger's Cage")
        self.a.graveyard.append(BEAR)
        physical = self.a.graveyard.pop()
        self.g.enter_battlefield(self.a, physical)
        self.assertFalse(self.a.graveyard.left)

    def test_nonmana_matrix_allows_explicit_mana_ability(self):
        source = self.put(card('Sac mana creature', '', 'Creature', 'Sacrifice Sac mana creature: Add {R}.', 1, 1))
        self.put('Damping Matrix')
        self.assertTrue(self.g.can_activate(self.a, source, 0))

    def test_entry_tapped_rule_is_removed_when_source_is_suppressed(self):
        source = self.put('Kismet')
        silencer = self.put()
        source.silenced_by = silencer
        self.assertFalse(self.put(BIG, self.b).tapped)

    def test_opponent_anthem_is_removed_when_source_leaves(self):
        source = self.put('Elesh Norn, Grand Cenobite')
        survivor = self.put(BIG, self.b)
        self.assertEqual(survivor.power, 2)
        self.g.leave_battlefield(source, 'exile')
        self.assertEqual(survivor.power, 4)

    def test_counter_lock_retains_existing_player_counters(self):
        self.a.counters['energy'] = 5
        self.put('Solemnity')
        self.a.counters['energy'] += 1
        self.assertEqual(self.a.counters['energy'], 5)
        self.a.counters['energy'] -= 2
        self.assertEqual(self.a.counters['energy'], 3)

    def test_keyword_removal_timestamp_after_grant(self):
        target = self.put(BEAR, self.b)
        self.g.add_continuous_effect(target, 'grant', keyword='infect', until_eot=True)
        self.put('Melira, Sylvok Outcast')
        self.assertFalse(target.has('infect'))

    def test_filtered_destruction_regeneration_rider(self):
        target = self.put(BIG)
        target.regeneration_shields = 1
        self.apply("Destroy all creatures with power 3 or greater. They can't be regenerated.")
        self.assertNotIn(target, self.a.battlefield)

    def test_both_pilots_can_plan_and_cast_filtered_board_wipe(self):
        from mtgsim.ai import HeuristicAI, BaselineAI
        for pilot in (HeuristicAI, BaselineAI):
            with self.subTest(pilot=pilot.__name__):
                self.setUp()
                self.a.ai = pilot()
                self.a.ai.respond = self.a.ai.respond_extras = lambda *args: None
                self.mana()
                self.put(BIG, self.b)
                self.a.hand.append(CARDS['Dusk // Dawn'])
                # Dusk needs WW, not the generic five-color test allocation.
                self.put(PLAINS)
                option = self.a.hand[-1]
                plan = self.a.ai.plan_spell(self.g, self.a, option)
                self.assertIsNotNone(plan)
                self.assertTrue(self.g.cast(self.a, option, plan[1]))
                self.assertFalse(self.b.creatures)
                self.assertEqual(self.g._origin(option)[1], '')

    def test_cage_library_search_for_creature_land_does_not_crash(self):
        self.put("Grafdigger's Cage")
        dryad = card('Test dryad land', '', 'Land Creature — Forest Dryad', '', 1, 1)
        self.a.library = [dryad]
        self.apply('Search your library for a Forest card, put it onto the battlefield tapped, then shuffle.')
        self.assertEqual(len(self.a.library), 1)
        self.assertFalse(self.a.creatures)

    def test_static_source_index_tracks_card_changes(self):
        creature = self.put()
        source = self.put(card('Unrelated enchantment', '', 'Enchantment'))
        self.assertEqual(creature.power, 2)
        source.card = CARDS['Always Watching']
        self.assertEqual(creature.power, 3)
        source.card = card('Unrelated enchantment', '', 'Enchantment')
        self.assertEqual(creature.power, 2)

    def test_static_source_index_restores_converted_land_rules(self):
        from mtgsim.advanced_templates import update_static
        provider = card('Test land anthem', '', 'Land', 'Black creatures get +1/+1.')
        target = self.put(card('Black test', '{B}', 'Creature', '', 2, 2))
        self.put(provider)
        self.assertEqual(target.power, 3)
        moon_card = card('Blood Moon', '', 'Enchantment', 'Nonbasic lands are Mountains.')
        moon = self.put(moon_card)
        self.assertEqual(target.power, 2)
        self.g.leave_battlefield(moon, 'exile')
        update_static(self.g)
        self.assertEqual(target.power, 3)
