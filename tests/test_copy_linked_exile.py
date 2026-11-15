"""Linked exile references on copy-granting activated abilities (#527)."""
import dataclasses
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card


class LinkedCopy(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, 'main1'
        for player in self.game.players:
            player.library = [ISLAND] * 20
            player.ai.respond = player.ai.respond_extras = lambda *args: None
        self.db = CardDB(offline=True)
        self.dna = self.game.enter_battlefield(self.a, self.db.get('Dino DNA'))
        for _ in range(8):
            self.game.enter_battlefield(self.a, ISLAND).sick = False

    def imprint(self, source, card_in_graveyard):
        effect = source.card.activated[0].effects[0]
        item = StackItem(self.a, [effect], [card_in_graveyard], source=source, kind='ability')
        self.game.resolve(self.a, effect, card_in_graveyard, item)

    def test_only_this_sources_exact_exiled_cards_are_targets(self):
        self.b.graveyard.extend([BEAR, BEAR])
        first, other = self.b.graveyard
        self.imprint(self.dna, first)
        second_dna = self.game.enter_battlefield(self.a, self.db.get('Dino DNA'))
        self.imprint(second_dna, other)
        effect = self.dna.activated[1].effects[0]
        with self.game.targeting(self.dna):
            self.assertEqual(self.game.legal_targets(self.a, effect), [first])
            self.assertFalse(self.game.legal_target(self.a, effect, other))
        self.assertTrue(self.game.activate_ability(self.a, self.dna, 1, [first]))
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual((token.card.name, token.power, token.toughness, token.card.colors),
                         (BEAR.name, 6, 6, frozenset({'G'})))
        self.assertEqual(token.card.types, frozenset({'Creature'}))
        self.assertEqual(token.card.subtypes, frozenset({'Dinosaur'}))
        self.assertTrue(token.has('trample'))

    def test_imprint_activation_creates_the_link(self):
        self.b.graveyard.append(BEAR)
        target = self.b.graveyard[0]
        self.assertTrue(self.game.activate_ability(self.a, self.dna, 0, [target]))
        self.assertIs(self.b.exile[0], target)
        effect = self.dna.activated[1].effects[0]
        with self.game.targeting(self.dna):
            self.assertEqual(self.game.legal_targets(self.a, effect), [target])

    def test_source_reentry_and_card_leaving_exile_break_links(self):
        self.b.graveyard.append(BEAR)
        first = self.b.graveyard[0]
        self.imprint(self.dna, first)
        effect = self.dna.activated[1].effects[0]
        self.game.move_card(first, self.b.exile, self.b.hand)
        self.game.move_card(first, self.b.hand, self.b.exile)
        with self.game.targeting(self.dna):
            self.assertEqual(self.game.legal_targets(self.a, effect), [])
        self.game.leave_battlefield(self.dna, 'exile')
        new = self.game.enter_battlefield(self.a, self.db.get('Dino DNA'))
        with self.game.targeting(new):
            self.assertEqual(self.game.legal_targets(self.a, new.activated[1].effects[0]), [])

    def test_target_leaves_and_is_reimprinted_before_resolution(self):
        self.b.graveyard.append(BEAR)
        target = self.b.graveyard[0]
        self.imprint(self.dna, target)
        settle = self.game.settle
        self.game.settle = lambda: None
        try:
            self.assertTrue(self.game.activate_ability(self.a, self.dna, 1, [target]))
        finally:
            self.game.settle = settle
        self.game.move_card(target, self.b.exile, self.b.graveyard)
        self.imprint(self.dna, target)
        self.game.settle()
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))

    def test_copy_ability_resolves_after_source_leaves(self):
        self.b.graveyard.append(BEAR)
        target = self.b.graveyard[0]
        self.imprint(self.dna, target)
        settle = self.game.settle
        self.game.settle = lambda: None
        try:
            self.assertTrue(self.game.activate_ability(self.a, self.dna, 1, [target]))
        finally:
            self.game.settle = settle
        self.game.leave_battlefield(self.dna, 'graveyard')
        self.game.settle()
        self.assertTrue(any(x.card.is_token and x.card.name == BEAR.name for x in self.a.battlefield))

    def test_copy_respects_token_doubling(self):
        self.b.graveyard.append(BEAR)
        target = self.b.graveyard[0]
        self.imprint(self.dna, target)
        doubler = dataclasses.replace(card('Doubler', types='Enchantment'), token_double=True)
        self.game.enter_battlefield(self.a, doubler)
        self.assertTrue(self.game.activate_ability(self.a, self.dna, 1, [target]))
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 2)

    def test_unbound_linked_copy_stays_unsupported(self):
        unbound = card('Unbound', '{1}', 'Artifact',
                       '{6}: Create a token that\'s a copy of target creature card exiled with ~, '
                       'except it\'s a 6/6 green Dinosaur creature with trample.')
        self.assertTrue(unbound.unsupported)
        self.assertFalse(unbound.activated)

    def test_saga_later_chapters_copy_the_card_exiled_by_chapter_one(self):
        self.a.graveyard.append(BEAR)
        chosen = self.a.graveyard[0]
        saga = self.game.enter_battlefield(self.a, self.db.get('The Cloning of Shredder'))
        self.game.settle()
        self.assertIs(self.a.exile[0], chosen)
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 1)
        self.game.add_lore(saga)
        self.game.settle()
        self.game.add_lore(saga)
        self.game.settle()
        tokens = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(tokens), 3)
        for token in tokens:
            self.assertEqual(token.card.name, BEAR.name)
            self.assertIn('Mutant', token.card.subtypes)
            self.assertIn('Bear', token.card.subtypes)
            self.assertFalse(token.card.legendary)
        self.assertNotIn(saga, self.a.battlefield)

    def test_saga_does_not_copy_card_moved_out_of_exile(self):
        self.a.graveyard.append(BEAR)
        chosen = self.a.graveyard[0]
        saga = self.game.enter_battlefield(self.a, self.db.get('The Cloning of Shredder'))
        self.game.settle()
        self.game.move_card(chosen, self.a.exile, self.a.hand)
        self.game.move_card(chosen, self.a.hand, self.a.exile)
        self.game.add_lore(saga)
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 1)
