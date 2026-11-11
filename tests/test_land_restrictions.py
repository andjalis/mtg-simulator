"""Behavior for the remaining land-play and cast restrictions, using offline Oracle text."""
import random
import unittest
from pathlib import Path

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card


@unittest.skipUnless(Path('mtgsim/data/cards.sqlite3').exists(), 'offline card database required')
class LandRestrictions(unittest.TestCase):
    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, 'main1'

    def put(self, name, player=None):
        return self.game.enter_battlefield(player or self.a, self.db.get(name))

    def test_limited_resources_counts_every_land_and_releases(self):
        source = self.put('Limited Resources')
        for _ in range(5):
            self.put('Island', self.a)
        for _ in range(4):
            self.put('Island', self.b)
        self.assertFalse(self.a.land_played)
        self.assertFalse(self.b.land_played)
        tenth = self.put('Island', self.b)
        self.assertTrue(self.a.land_played)
        self.assertTrue(self.b.land_played)
        self.game.leave_battlefield(tenth, 'hand')
        self.assertFalse(self.a.land_played)
        self.put('Island', self.b)
        self.game.leave_battlefield(source, 'exile')
        self.assertFalse(self.b.land_played)

    def test_ward_of_bones_compares_current_controllers(self):
        source = self.put('Ward of Bones')
        self.put('Island', self.a)
        self.put('Island', self.b)
        self.assertFalse(self.b.land_played)
        self.put('Island', self.b)
        self.assertTrue(self.b.land_played)
        self.assertFalse(self.a.land_played)
        self.put('Island', self.a)
        self.assertFalse(self.b.land_played)
        self.game.leave_battlefield(source, 'exile')
        self.put('Island', self.b)
        self.assertFalse(self.b.land_played)

    def test_worms_prevents_land_entry_and_preserves_library_identity(self):
        source = self.put('Worms of the Earth')
        self.assertTrue(self.a.land_played)
        self.a.library = [ISLAND]
        physical = self.a.library[0]
        generation = physical.generation
        fetch = card('Test Fetch', '{G}', 'Sorcery',
                     'Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.')
        self.assertEqual(fetch.unsupported, [])
        for effect in fetch.spell_effects:
            self.game.resolve(self.a, effect, None)
        self.assertEqual(len(self.a.library), 1)
        self.assertIs(self.a.library[0], physical)
        self.assertEqual(physical.generation, generation)
        self.assertFalse(any(x.card.is_land for x in self.a.battlefield))
        self.game.leave_battlefield(source, 'exile')
        self.assertIsNotNone(self.put('Island'))

    def test_worms_restores_land_put_from_hand_but_allows_other_permanents(self):
        self.put('Worms of the Earth')
        self.a.hand = [ISLAND]
        physical = self.a.hand[0]
        self.a.hand.remove(physical)
        self.assertIsNone(self.game.enter_battlefield(self.a, physical))
        self.assertIs(self.a.hand[0], physical)
        self.assertIsNotNone(self.game.enter_battlefield(self.a, BEAR))

    def test_rock_jockey_restrictions_use_actual_cast_and_land_history(self):
        jockey = self.db.get('Rock Jockey')
        self.assertEqual(jockey.unsupported, [])
        self.a.hand = [jockey]
        for name in ('Mountain', 'Island', 'Island'):
            self.put(name)
        self.assertTrue(self.game.can_cast_now(self.a, self.a.hand[0]))
        self.a.lands_played = 1
        self.assertFalse(self.game.can_cast_now(self.a, self.a.hand[0]))
        self.a.lands_played = 0
        self.assertTrue(self.game.cast(self.a, self.a.hand[0], []))
        self.assertTrue(self.a.land_played)
        self.game.turn += 1
        self.assertFalse(self.a.land_played)
        # Putting it onto the battlefield does not count as casting it.
        self.put('Rock Jockey')
        self.assertFalse(self.a.land_played)

    def test_ward_of_bones_cast_lock_compares_type_counts(self):
        source = self.put('Ward of Bones')
        self.assertEqual(source.card.unsupported, [])
        bears = [self.game.enter_battlefield(self.b, BEAR) for _ in range(2)]
        # Two artifacts and two enchantments on b's side so each type count also exceeds a's
        # (a's Ward of Bones is itself an artifact).
        for _ in range(2):
            self.game.enter_battlefield(self.b, card('Test Artifact Perm', '', 'Artifact', '', 0, 0))
        for _ in range(2):
            self.game.enter_battlefield(self.b, card('Test Enchantment Perm', '', 'Enchantment', '', 0, 0))
        creature = card('Test Creature Spell', '', 'Creature', '', 1, 1)
        artifact = card('Test Artifact Spell', '', 'Artifact', '', 0, 0)
        enchantment = card('Test Enchantment Spell', '', 'Enchantment', '', 0, 0)
        instant = card('Test Instant Spell', '', 'Instant')
        self.b.hand = [creature, artifact, enchantment, instant]
        # The controller's own spells are unaffected.
        self.a.hand = [card('Test Own Creature', '', 'Creature', '', 1, 1)]
        self.assertTrue(self.game.can_cast_now(self.a, self.a.hand[0]))
        self.game.active_idx = 1
        for c in (creature, artifact, enchantment):
            self.assertFalse(self.game.can_cast_now(self.b, c))
        self.assertTrue(self.game.can_cast_now(self.b, instant))
        # One creature each: no longer "more creatures", so creature spells are castable again.
        self.game.enter_battlefield(self.a, BEAR)
        self.b.battlefield.remove(bears[0])
        self.assertTrue(self.game.can_cast_now(self.b, creature))
        self.game.leave_battlefield(source, 'exile')
        self.assertTrue(self.game.can_cast_now(self.b, artifact))

    def test_damping_engine_locks_the_player_with_most_permanents(self):
        source = self.put('Damping Engine')
        self.assertEqual(source.card.unsupported, [])
        for _ in range(2):
            self.game.enter_battlefield(self.b, BEAR)
        self.assertTrue(self.b.land_played)
        self.assertFalse(self.a.land_played)
        creature = card('Test Creature Spell', '', 'Creature', '', 1, 1)
        artifact = card('Test Artifact Spell', '', 'Artifact', '', 0, 0)
        enchantment = card('Test Enchantment Spell', '', 'Enchantment', '', 0, 0)
        sorcery = card('Test Sorcery Spell', '', 'Sorcery')
        planeswalker = card('Test Planeswalker Spell', '', 'Planeswalker')
        self.b.hand = [creature, artifact, enchantment, sorcery, planeswalker]
        self.game.active_idx = 1
        for c in (creature, artifact, enchantment):
            self.assertFalse(self.game.can_cast_now(self.b, c))
        for c in (sorcery, planeswalker):
            self.assertTrue(self.game.can_cast_now(self.b, c))
        # A tie locks nobody; the lock also stops when the source leaves.
        self.game.enter_battlefield(self.a, BEAR)
        self.assertFalse(self.b.land_played)
        self.assertTrue(self.game.can_cast_now(self.b, creature))
        self.game.leave_battlefield(source, 'exile')
        self.game.enter_battlefield(self.b, BEAR)
        self.assertFalse(self.b.land_played)

    def test_moonhold_color_branches_share_one_target_and_expire(self):
        for lands, land_lock, creature_lock in ((('Mountain', 'Island', 'Island'), True, False),
                (('Plains', 'Island', 'Island'), False, True), (('Mountain', 'Plains', 'Island'), True, True)):
            with self.subTest(lands=lands):
                self.setUp()
                for name in lands:
                    self.put(name)
                moonhold = self.db.get('Moonhold')
                self.assertEqual(moonhold.unsupported, [])
                self.a.hand = [moonhold]
                options = [c for c in self.game.spell_options(self.a) if self.game.can_cast_now(self.a, c)]
                self.assertTrue(options)
                self.assertTrue(self.game.cast(self.a, options[0], [self.b, None]))
                self.assertEqual(self.b.land_played, land_lock)
                self.assertFalse(self.a.land_played)
                self.b.hand = [card('Test Free Creature', '', 'Creature', '', 1, 1)]
                self.game.active_idx = 1
                self.assertEqual(self.game.can_cast_now(self.b, self.b.hand[0]), not creature_lock)
                self.game.turn += 1
                self.assertFalse(self.b.land_played)
                self.assertTrue(self.game.can_cast_now(self.b, self.b.hand[0]))
