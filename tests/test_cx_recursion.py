"""Non-targeted graveyard choices retain their filters, counts and physical cards."""
import random
import unittest

from mtgsim.ai import HeuristicAI, BaselineAI
from mtgsim.cards import _parse_effects
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, FOREST, ISLAND, SHOCK, card

SORCERY = card('Test sorcery', '{2}', 'Sorcery', 'Draw a card.')


class NonTargetedRecursion(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], HeuristicAI()), Player('b', [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(28))
        self.g.turn, self.g.step = 4, 'main1'
        for p in self.g.players:
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def resolve(self, text, x=0):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        self.assertEqual(len(effects), 1)
        item = StackItem(self.a, effects, [None])
        item.x = x
        self.g.stack.append(item)
        self.g.settle()
        self.assertTrue(item.resolved)
        return effects[0]

    def test_bound_returns_only_creatures_and_at_most_two(self):
        self.a.graveyard.extend([BEAR, BEAR, BEAR, SHOCK, ISLAND])
        self.resolve('Then return up to two creature cards from your graveyard to your hand.')
        self.assertEqual(len(self.a.hand), 2)
        self.assertTrue(all(c.is_creature for c in self.a.hand))
        self.assertEqual(len(self.a.graveyard), 3)

    def test_type_union_is_inclusive_and_excludes_other_types(self):
        self.a.graveyard.extend([BEAR, SHOCK, SORCERY, ISLAND])
        wanted = set(self.a.graveyard[1:3])
        self.resolve('Return up to two instant and/or sorcery cards from your graveyard to your hand.')
        self.assertEqual(set(self.a.hand), wanted)
        self.assertEqual([c.name for c in self.a.graveyard], [BEAR.name, ISLAND.name])

    def test_exact_physical_duplicates_and_versions_are_preserved(self):
        self.a.graveyard.extend([BEAR, BEAR])
        old = list(self.a.graveyard)
        generations = [c.generation for c in old]
        self.resolve('Return up to two creature cards from your graveyard to your hand.')
        self.assertEqual(set(self.a.hand), set(old))
        self.assertEqual(len({id(c) for c in self.a.hand}), 2)
        self.assertTrue(all(c.zone is self.a.hand and c.owner is self.a for c in old))
        self.assertTrue(all(c.generation > v for c, v in zip(old, generations)))

    def test_caster_graveyard_only(self):
        self.a.graveyard.append(BEAR)
        self.b.graveyard.extend([BEAR, SHOCK])
        theirs = list(self.b.graveyard)
        self.resolve('Return up to two creature and/or land cards from your graveyard to your hand.')
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(list(self.b.graveyard), theirs)
        self.assertFalse(self.b.hand)

    def test_subtype_and_type_intersection(self):
        rat = card('Test rat', '{1}', 'Creature — Rat', '', 1, 1)
        kindred = card('Test rat sorcery', '{3}', 'Kindred Sorcery — Rat')
        self.a.graveyard.extend([BEAR, rat, kindred])
        wanted = self.a.graveyard[1]
        self.resolve('Return up to two Rat creature cards from your graveyard to your hand.')
        self.assertEqual(list(self.a.hand), [wanted])

    def test_mana_value_filter_is_applied_at_resolution(self):
        high = card('Test large creature', '{6}', 'Creature', '', 6, 6)
        self.a.graveyard.extend([BEAR, high, BEAR])
        wanted = {self.a.graveyard[0], self.a.graveyard[2]}
        self.resolve('Return up to three creature cards with mana value 2 or less from your graveyard to your hand.')
        self.assertEqual(set(self.a.hand), wanted)
        self.assertEqual([c.name for c in self.a.graveyard], [high.name])

    def test_all_matching_has_no_99_card_limit(self):
        self.a.graveyard.extend([BEAR] * 103 + [SHOCK])
        self.resolve('Return all creature cards from your graveyard to your hand.')
        self.assertEqual(len(self.a.hand), 103)
        self.assertEqual([c.name for c in self.a.graveyard], [SHOCK.name])

    def test_no_available_cards_and_zero_choices_resolve(self):
        self.resolve('Return up to two creature cards from your graveyard to your hand.')
        self.a.graveyard.append(BEAR)
        self.resolve('Return up to 0 creature cards from your graveyard to your hand.')
        self.assertEqual(len(self.a.graveyard), 1)
        self.assertFalse(self.a.hand)

    def test_x_selection_count_and_x_mana_value_limit(self):
        self.a.graveyard.extend([BEAR, BEAR, BEAR, SHOCK, SORCERY])
        self.resolve('Return up to X creature cards from your graveyard to your hand.', x=2)
        self.assertEqual(len(self.a.hand), 2)
        self.a.hand.clear()
        self.resolve('Return up to two instant or sorcery cards with mana value X or less '
                     'from your graveyard to your hand.', x=1)
        self.assertEqual([c.name for c in self.a.hand], [SHOCK.name])
        self.assertTrue(any(c.name == SORCERY.name for c in self.a.graveyard))

    def test_paid_x_spell_uses_real_remaining_mana(self):
        spell = card('Test X return', '{X}{G}', 'Sorcery',
                     'Return up to X creature cards from your graveyard to your hand.', cmc=1)
        self.assertFalse(spell.unsupported)
        for _ in range(5):
            self.g.enter_battlefield(self.a, FOREST)
        self.a.graveyard.extend([BEAR] * 6)
        self.a.hand.append(spell)
        self.assertTrue(self.g.cast(self.a, spell))
        self.assertEqual(len(self.a.hand), 4)
        self.assertEqual(sum(c.is_creature for c in self.a.graveyard), 2)

    def test_target_and_relationship_requirements_are_not_discarded(self):
        cases = ['Return up to two other target creature cards with different names from your graveyard to your hand.',
                 'Return up to two nonlegendary creature cards from your graveyard to your hand.',
                 'Return up to two creature cards of the chosen type from your graveyard to your hand.',
                 "Return up to two creature cards from an opponent's graveyard to their owner's hand."]
        for text in cases:
            with self.subTest(text=text):
                _, ignored = _parse_effects(text)
                self.assertTrue(ignored)

    @unittest.skipUnless(ALL_CARDS.exists(), 'offline database unavailable')
    def test_actual_another_chance_cast_with_both_pilots(self):
        spell = CardDB(offline=True).get('Another Chance')
        self.assertFalse(spell.unsupported)
        for pilot in (HeuristicAI, BaselineAI):
            with self.subTest(pilot=pilot.__name__):
                a, b = Player('a', [], pilot()), Player('b', [], pilot())
                g = Game(a, b, random.Random(16))
                g.turn, g.step = 3, 'main1'
                for p in g.players:
                    p.ai.respond = p.ai.respond_extras = lambda *args: None
                for _ in range(3):
                    g.enter_battlefield(a, card('Test swamp', '', 'Land', '{T}: Add {B}.'))
                a.library.extend([ISLAND] * 8)
                a.graveyard.extend([BEAR, BEAR])
                wanted = set(a.graveyard)
                a.hand.append(spell)
                self.assertTrue(g.cast(a, spell))
                self.assertEqual(set(a.hand), wanted)
