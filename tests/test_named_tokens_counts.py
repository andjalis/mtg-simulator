"""Named/quoted tokens and count gates exercise game state, not only recognition."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import BaselineAI
from mtgsim.cards import _parse_effects
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, can_block
from tests.test_templates import BEAR, ISLAND, card


class NamedTokensCounts(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], BaselineAI()), Player('b', [], BaselineAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g._priority_depth = 2, 1

    def real(self, name):
        db = CardDB(offline=True)
        if db._all is None:
            self.skipTest('local card database unavailable')
        try:
            return db.get(name)
        finally:
            db._all.close()

    def drain(self):
        while self.g.pending or self.g.stack:
            self.g.flush_triggers()
            self.g.resolve_top()

    def create(self, text):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        for effect in effects:
            self.g.resolve(self.a, effect, None)

    def watch(self, condition, body='you gain 2 life'):
        definition = card('Count watcher', types='Enchantment',
                          text=f'At the beginning of each upkeep, if {condition}, {body}.')
        self.assertFalse(definition.unsupported)
        return self.g.enter_battlefield(self.a, definition)

    def test_the_hive_preserves_name_type_and_keywords(self):
        definition = self.real('The Hive')
        self.assertFalse(definition.unsupported)
        self.g.resolve(self.a, definition.activated[0].effects[0], None)
        wasp = self.a.creatures[0]
        self.assertEqual((wasp.card.name, wasp.card.subtypes), ('Wasp', {'Insect'}))
        self.assertTrue(wasp.card.is_artifact)
        self.assertTrue(wasp.has('flying'))
        self.assertEqual((wasp.power, wasp.toughness, wasp.card.colors), (1, 1, set()))

    def test_sliversmith_activation_creates_metallic_sliver(self):
        definition = self.real('Sliversmith')
        self.assertFalse(definition.unsupported)
        source = self.g.enter_battlefield(self.a, definition)
        source.sick = False
        self.g.enter_battlefield(self.a, ISLAND)
        self.a.hand = [BEAR]
        self.assertTrue(self.g.activate_ability(self.a, source, 0))
        self.drain()
        token = next(x for x in self.a.creatures if x.card.is_token)
        self.assertEqual((token.card.name, token.card.subtypes), ('Metallic Sliver', {'Sliver'}))
        self.assertTrue(token.card.is_artifact)
        self.assertTrue(source.tapped)
        self.assertEqual(len(self.a.hand), 0)

    def test_prefix_named_legendary_tokens_use_the_real_name(self):
        text = 'Create Marit Lage, a legendary 20/20 black Avatar creature token with flying and indestructible.'
        self.create(text)
        self.create(text)
        self.assertEqual(len(self.a.creatures), 1)
        token = self.a.creatures[0]
        self.assertEqual((token.card.name, token.card.subtypes), ('Marit Lage', {'Avatar'}))
        self.assertTrue(token.card.legendary)
        self.assertTrue(token.has('flying') and token.has('indestructible'))
        self.assertEqual((token.power, token.toughness), (20, 20))

    def test_named_tokens_do_not_replace_subtypes_with_names(self):
        entry_states = []
        emit = self.g.rule_events.emit
        def observe(event):
            if event.kind == 'zone_change' and event.destination == 'battlefield':
                entry_states.append(event.source.tapped)
            return emit(event)
        with patch.object(self.g.rule_events, 'emit', side_effect=observe):
            self.create('Create two tapped 2/2 green Wolf creature tokens named Watcher with vigilance.')
        self.assertEqual(entry_states, [True, True])
        self.assertEqual(len(self.a.creatures), 2)
        self.assertTrue(all(x.card.name == 'Watcher' and x.card.subtypes == {'Wolf'} for x in self.a.creatures))
        self.assertTrue(all(x.has('vigilance') for x in self.a.creatures))

    def test_pest_summoning_tokens_have_their_death_trigger(self):
        definition = self.real('Pest Summoning')
        self.assertFalse(definition.unsupported)
        self.g.resolve(self.a, definition.spell_effects[0], None)
        first, second = self.a.creatures
        self.assertEqual(first.card.colors, {'B', 'G'})
        self.g.sacrifice(first)
        self.drain()
        self.assertEqual(self.a.life, 21)
        self.g.sacrifice(second)
        self.drain()
        self.assertEqual(self.a.life, 22)

    def test_edgewall_pack_rat_cannot_block(self):
        definition = self.real('Edgewall Pack')
        self.assertFalse(definition.unsupported)
        source = self.g.enter_battlefield(self.a, definition)
        self.drain()
        rat = next(x for x in self.a.creatures if x.card.is_token)
        attacker = self.g.enter_battlefield(self.b, BEAR)
        self.assertFalse(can_block(rat, attacker))
        self.assertTrue(can_block(source, attacker))

    def test_mixed_keywords_and_quoted_ability(self):
        self.create('Create a 1/1 white Spirit creature token named Guide with flying and "When this token dies, you gain 2 life."')
        token = self.a.creatures[0]
        self.assertTrue(token.has('flying'))
        self.assertEqual(token.card.name, 'Guide')
        self.g.sacrifice(token)
        self.drain()
        self.assertEqual(self.a.life, 22)

    def test_temporary_haste_expires_and_is_not_copiable(self):
        self.create('Create a 1/1 red Goblin creature token named Runner. It gains haste until end of turn.')
        token = self.a.creatures[0]
        self.assertTrue(token.can_attack())
        self.assertNotIn('haste', token.copiable_card.keywords)
        self.a.library = [ISLAND] * 3
        self.g.take_turn(self.a)
        self.assertEqual(self.g.step, 'cleanup')
        self.assertFalse(token.has('haste'))
        self.assertEqual(token.card.name, 'Runner')

    def test_nest_invader_spawn_pays_while_tapped_or_sick_without_tapping(self):
        definition = self.real('Nest Invader')
        self.assertFalse(definition.unsupported)
        for tapped in (False, True):
            self.g.enter_battlefield(self.a, definition)
            self.drain()
            token = next(x for x in self.a.creatures if x.card.is_token)
            token.tapped = tapped
            self.assertTrue(token.sick)
            self.assertEqual(self.g.pay(self.a, {'C': 1}), [token])
            self.assertNotIn(token, self.a.battlefield)
            self.assertEqual(token.tapped, tapped)

    def test_spawn_cannot_pay_mana_and_an_additional_sacrifice(self):
        token_effect = self.real('Nest Invader').triggers[0].effects[0]
        self.g.resolve(self.a, token_effect, None)
        definition = card('Two resources', '{C}', 'Sorcery')
        definition.extra_sacrifice = 'creature'
        self.a.hand = [definition]
        spell = self.a.hand[0]
        self.assertFalse(self.g.can_perform(self.a, (spell, [])))
        self.assertEqual(len(self.a.creatures), 1)
        self.g.resolve(self.a, token_effect, None)
        self.assertTrue(self.g.cast(self.a, spell))
        self.assertEqual(self.a.sacrificed_turn, 2)

    def test_enchantment_tokens_have_card_types_not_fake_subtypes(self):
        self.create('Create a 2/2 white Nymph enchantment creature token named Muse.')
        token = self.a.creatures[0]
        self.assertEqual(token.card.types, {'Creature', 'Enchantment'})
        self.assertEqual(token.card.subtypes, {'Nymph'})
        self.watch('you control an enchantment')
        self.g.begin_upkeep(self.b)
        self.drain()
        self.assertEqual(self.a.life, 22)

    def test_unknown_quoted_abilities_and_delayed_suffixes_stay_gaps(self):
        for text in ['Create a 1/1 green Insect creature token named Butterfly at the beginning of the next end step.',
                     'Create a 1/1 blue Spirit creature token with "This token phases through moons."',
                     'Create a 1/1 blue Spirit creature token with " ".',
                     'Create a 1/1 blue Spirit creature token. It has "This token phases through moons."',
                     'Create a 1/1 blue Spirit creature token. It has "When this token dies, draw a card. You gain 1 life."',
                     'Create a 1/1 blue Spirit creature token with "Sacrifice this token: Add {C}{C}."']:
            with self.subTest(text=text):
                _, bad = _parse_effects(text)
                self.assertTrue(bad)

    def test_library_gate_uses_own_library_and_is_checked_once(self):
        self.watch('you have two or more cards in your library', 'draw a card and draw a card')
        self.b.library = [ISLAND] * 3
        self.g.begin_upkeep(self.b)
        self.assertFalse(self.g.pending)
        self.a.library = [ISLAND, ISLAND]
        self.g.begin_upkeep(self.b)
        self.drain()
        self.assertEqual((len(self.a.hand), len(self.a.library)), (2, 0))
        self.assertFalse(self.a.lost)

    def test_library_gate_rechecked_after_library_changes(self):
        self.watch('there are two or fewer cards in your library')
        self.a.library = [ISLAND] * 2
        self.g.begin_upkeep(self.b)
        self.a.library.append(ISLAND)
        self.drain()
        self.assertEqual(self.a.life, 20)

    def test_dragonmaster_outcast_checks_lands_at_both_times(self):
        definition = self.real('Dragonmaster Outcast')
        self.assertFalse(definition.unsupported)
        self.g.enter_battlefield(self.a, definition)
        for _ in range(5):
            self.g.enter_battlefield(self.a, ISLAND)
        self.g.begin_upkeep(self.a)
        self.assertFalse(self.g.pending)
        land = self.g.enter_battlefield(self.a, ISLAND)
        self.g.begin_upkeep(self.a)
        self.g.leave_battlefield(land, 'graveyard')
        self.drain()
        self.assertFalse(any(x.card.is_token for x in self.a.creatures))
        self.g.enter_battlefield(self.a, ISLAND)
        self.g.begin_upkeep(self.a)
        self.drain()
        dragon = next(x for x in self.a.creatures if x.card.is_token)
        self.assertEqual((dragon.power, dragon.toughness), (5, 5))
        self.assertTrue(dragon.has('flying'))

    def test_scute_mob_counts_lands_and_puts_four_counters(self):
        definition = self.real('Scute Mob')
        self.assertFalse(definition.unsupported)
        source = self.g.enter_battlefield(self.a, definition)
        for _ in range(5):
            self.g.enter_battlefield(self.a, ISLAND)
        self.g.begin_upkeep(self.a)
        self.drain()
        self.assertEqual((source.p1, source.power, source.toughness), (4, 5, 5))

    def test_other_artifacts_excludes_the_source(self):
        source = self.watch('you control two or more other artifacts')
        self.g.add_continuous_effect(source, 'add_types', types={'Artifact'})
        self.g.enter_battlefield(self.a, card('Rock', types='Artifact'))
        self.g.begin_upkeep(self.b)
        self.assertFalse(self.g.pending)
        self.g.enter_battlefield(self.a, card('Other rock', types='Artifact'))
        self.g.begin_upkeep(self.b)
        self.drain()
        self.assertEqual(self.a.life, 22)

    def test_permanent_types_follow_current_characteristics(self):
        self.watch('you control exactly one artifact creature')
        permanent = self.g.enter_battlefield(self.a, ISLAND)
        self.g.begin_upkeep(self.b)
        self.assertFalse(self.g.pending)
        self.g.add_continuous_effect(permanent, 'add_types', types={'Artifact', 'Creature'})
        self.g.begin_upkeep(self.b)
        self.drain()
        self.assertEqual(self.a.life, 22)

    def test_count_lower_bound_and_opponents_permanents(self):
        self.watch('you control two or fewer lands')
        for _ in range(4):
            self.g.enter_battlefield(self.b, ISLAND)
        self.g.begin_upkeep(self.b)
        self.drain()
        self.assertEqual(self.a.life, 22)
        for _ in range(3):
            self.g.enter_battlefield(self.a, ISLAND)
        self.g.begin_upkeep(self.b)
        self.assertFalse(self.g.pending)

    def test_unsupported_count_predicates_and_winning_remain_gaps(self):
        for condition in ['you control seven or more lands with different names',
                          'you control eight or more artifacts with the same name as one another',
                          'you control three or more creatures with different powers']:
            definition = card('Unknown count', types='Enchantment',
                              text=f'At the beginning of each upkeep, if {condition}, you gain 1 life.')
            self.assertTrue(definition.unsupported)
        self.assertTrue(self.real('Battle of Wits').unsupported)


if __name__ == '__main__':
    unittest.main()
