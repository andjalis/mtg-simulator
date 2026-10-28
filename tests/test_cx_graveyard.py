"""Physical-card and rules behavior for expanded graveyard-library targets."""
import random
import unittest
from unittest.mock import patch

from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, SHOCK, card

ENCHANTMENT = card('Test enchantment', '{W}', 'Enchantment')
ARTIFACT = card('Test artifact', '{1}', 'Artifact')
BATTLE = card('Test battle', '{1}', 'Battle — Siege')
SORCERY = card('Test sorcery', '{1}', 'Sorcery', 'Draw a card.')
SPELL = card('Test reclaim', '{G}', 'Instant', 'Put target card from your graveyard on top of your library.')


class GraveyardLibraryTargets(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(12))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 15
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def effects(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        self.assertEqual(len(effects), 1)
        return effects

    def resolve(self, text, target):
        effects = self.effects(text)
        item = StackItem(self.a, effects, [target])
        self.g.check_ward(item)
        self.g.stack.append(item)
        self.g.settle()
        return item

    def test_any_card_includes_all_normal_card_types(self):
        self.a.graveyard.extend([BEAR, ISLAND, SHOCK, SORCERY, ARTIFACT, ENCHANTMENT, BATTLE])
        effect = self.effects('Put target card from your graveyard on top of your library.')[0]
        self.assertEqual(self.g.legal_targets(self.a, effect), list(self.a.graveyard))

    def test_permanent_excludes_instant_and_sorcery(self):
        self.a.graveyard.extend([BEAR, ISLAND, SHOCK, SORCERY, ARTIFACT])
        effect = self.effects('Put target permanent card from your graveyard on top of your library.')[0]
        self.assertEqual(self.g.legal_targets(self.a, effect), [self.a.graveyard[i] for i in (0, 1, 4)])

    def test_type_union_is_inclusive(self):
        self.a.graveyard.extend([BEAR, SHOCK, ARTIFACT, ISLAND])
        effect = self.effects('Put target artifact or creature card from your graveyard on top of your library.')[0]
        self.assertEqual(self.g.legal_targets(self.a, effect), [self.a.graveyard[0], self.a.graveyard[2]])

    def test_land_target_does_not_include_creatures(self):
        self.a.graveyard.extend([BEAR, ISLAND])
        effect = self.effects('Put up to one target land card from your graveyard on top of your library.')[0]
        self.assertEqual(self.g.legal_targets(self.a, effect), [self.a.graveyard[1]])

    def test_instant_sorcery_union_optional_target(self):
        self.a.graveyard.extend([BEAR, SHOCK, SORCERY])
        effect = self.effects('Put up to one target instant or sorcery card from your graveyard on top of your library.')[0]
        self.assertEqual(self.g.legal_targets(self.a, effect), list(self.a.graveyard[1:]))
        self.assertTrue(self.g.legal_target(self.a, effect, None))

    def test_opponent_graveyard_is_excluded(self):
        self.b.graveyard.append(BEAR)
        effect = self.effects('Put target card from your graveyard on top of your library.')[0]
        self.assertFalse(self.g.legal_target(self.a, effect, self.b.graveyard[-1]))

    def test_returns_exact_physical_duplicate_to_top(self):
        self.a.graveyard.extend([BEAR, BEAR])
        first, second = self.a.graveyard
        before = len(self.a.library)
        self.resolve('Put target card from your graveyard on top of your library.', second)
        self.assertIs(self.a.library[-1], second)
        self.assertIs(self.a.graveyard[-1], first)
        self.assertEqual(len(self.a.library), before + 1)
        self.assertIs(second.owner, self.a)

    def test_return_is_drawn_next(self):
        self.a.graveyard.append(SHOCK)
        target = self.a.graveyard[-1]
        self.resolve('Put target card from your graveyard on top of your library.', target)
        self.g.draw(self.a)
        self.assertIs(self.a.hand[-1], target)

    def test_target_that_leaves_and_returns_is_illegal(self):
        self.a.graveyard.append(BEAR)
        target = self.a.graveyard[-1]
        effects = self.effects('Put target card from your graveyard on top of your library.')
        item = StackItem(self.a, effects, [target])
        self.g.check_ward(item)
        self.g.move_card(target, self.a.graveyard, self.a.hand)
        self.g.move_card(target, self.a.hand, self.a.graveyard)
        self.g.stack.append(item)
        self.g.settle()
        self.assertIn(target, self.a.graveyard)
        self.assertFalse(item.resolved)

    def test_optional_zero_targets_resolves(self):
        item = self.resolve('Put up to one target permanent card from your graveyard on top of your library.', None)
        self.assertTrue(item.resolved)
        self.assertEqual(len(self.a.library), 15)

    def test_required_target_cannot_be_omitted(self):
        effect = self.effects('Put target card from your graveyard on top of your library.')[0]
        self.assertFalse(self.g.legal_target(self.a, effect, None))

    def test_wrong_type_is_illegal_at_resolution(self):
        self.a.graveyard.append(SHOCK)
        item = self.resolve('Put target permanent card from your graveyard on top of your library.', self.a.graveyard[-1])
        self.assertFalse(item.resolved)
        self.assertEqual(len(self.a.graveyard), 1)

    def test_normal_casting_auto_selects_a_legal_card(self):
        from tests.test_templates import FOREST
        self.g.enter_battlefield(self.a, FOREST)
        self.a.graveyard.append(SHOCK)
        target = self.a.graveyard[-1]
        self.a.hand.append(SPELL)
        self.assertTrue(self.g.cast(self.a, self.a.hand[-1]))
        self.assertIs(self.a.library[-1], target)
        self.assertEqual(list(self.a.graveyard), [SPELL])

    def test_explicit_cast_target_stays_fixed(self):
        from tests.test_templates import FOREST
        self.g.enter_battlefield(self.a, FOREST)
        self.a.graveyard.extend([BEAR, SHOCK])
        target = self.a.graveyard[-1]
        self.a.hand.append(SPELL)
        with patch.object(self.g, 'settle'):
            self.assertTrue(self.g.cast(self.a, self.a.hand[-1], [target]))
        self.assertIs(self.g.stack[-1].targets[0], target)
        self.g.settle()
        self.assertIs(self.a.library[-1], target)

    def test_optional_entry_trigger_uses_existing_trigger_path(self):
        creature = card('Test curator', '', 'Creature', 'When Test curator enters, put up to one target instant or sorcery card from your graveyard on top of your library.', 1, 1)
        self.assertFalse(creature.unsupported)
        self.a.graveyard.append(SHOCK)
        target = self.a.graveyard[-1]
        self.g.enter_battlefield(self.a, creature)
        self.g.settle()
        self.assertIs(self.a.library[-1], target)

    def test_non_target_and_unsupported_qualifiers_remain_visible(self):
        for text in [
            'Put a land card from your graveyard on top of your library.',
            'Put target Zombie card from your graveyard on top of your library.',
            'Put any number of target creature cards from your graveyard on top of your library.',
            'Put up to one other target card from your graveyard on top of your library.',
            "Put target card from a graveyard on top of its owner's library.",
            'Put target noncreature, nonland card from your graveyard on top of your library.',
        ]:
            with self.subTest(text=text):
                _, ignored = _parse_effects(text)
                self.assertTrue(ignored)
