"""Owner-cast permissions last for one exile generation, independent of the source."""
import random
import unittest
from pathlib import Path

from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

PAID = ('Exile target nonland permanent. For as long as that card remains exiled, '
        'its owner may cast it.')
FREE = PAID[:-1] + ' without paying its mana cost.'
DB_FILE = Path(__file__).resolve().parents[1] / 'mtgsim/data/cards.sqlite3'


class ExileDurations(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(2))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def put(self, definition=BEAR, player=None):
        return self.g.enter_battlefield(player or self.a, definition)

    def apply(self, text, target, source=None):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [])
        self.g.stack.append(StackItem(self.a, effects, [target] + [None] * (len(effects) - 1),
                                     source=source, kind='ability'))
        self.g.resolve_top()

    def options(self, p):
        return [c for c in self.g.spell_options(p) if self.g._origin(c)[1].startswith('exile_cast_')]

    def test_permission_belongs_to_owner_not_controller_or_exiler(self):
        from mtgsim.counter_mechanics import add_control
        bear = self.put(player=self.b)
        add_control(self.g, bear, self.a)
        self.apply(PAID, bear)
        self.assertEqual(self.options(self.a), [])
        options = self.options(self.b)
        self.assertEqual(len(options), 1)
        self.assertIs(self.g._origin(options[0])[0], bear.front)
        self.assertIn(bear.front, self.b.exile)

    def test_free_cast_survives_source_leaving_and_time_passing(self):
        bear, source = self.put(player=self.b), self.put()
        self.apply(FREE, bear, source)
        self.g.destroy(source)
        self.g.settle()
        self.g.turn += 6
        self.g.active_idx = 1
        option = self.options(self.b)[0]
        self.assertEqual(self.g.cost_of(self.b, option), {'generic': 0})
        self.assertTrue(self.g.cast(self.b, option, []))
        self.assertEqual(len(self.b.creatures), 1)
        self.assertIs(self.b.creatures[0].front, bear.front)
        self.assertEqual(self.options(self.b), [])

    def test_paid_permission_preserves_colored_mana_cost(self):
        bear = self.put(player=self.b)
        self.apply(PAID, bear)
        option = self.options(self.b)[0]
        self.g.active_idx = 1
        self.assertEqual(self.g.cost_of(self.b, option), dict(BEAR.mana_cost))
        self.assertFalse(self.g.cast(self.b, option, []))
        self.assertIn(bear.front, self.b.exile)

    def test_free_permission_does_not_grant_flash(self):
        bear = self.put(player=self.b)
        self.apply(FREE, bear)
        option = self.options(self.b)[0]
        self.g.active_idx = 0
        self.assertFalse(self.g.can_cast_now(self.b, option))
        self.g.active_idx = 1
        self.assertTrue(self.g.can_cast_now(self.b, option))

    def test_stale_variant_cannot_cast_same_card_after_exile_reentry(self):
        bear = self.put(player=self.b)
        self.apply(FREE, bear)
        option = self.options(self.b)[0]
        self.g.move_card(bear.front, self.b.exile, self.b.hand)
        self.g.move_card(bear.front, self.b.hand, self.b.exile)
        self.g.active_idx = 1
        self.assertFalse(self.g.cast(self.b, option, []))
        self.assertEqual(self.options(self.b), [])

    def test_does_not_grant_permission_to_identical_other_copy(self):
        first, second = self.put(player=self.b), self.put(player=self.b)
        self.apply(FREE, first)
        self.g.leave_battlefield(second, 'exile')
        self.g.move_card(first.front, self.b.exile, self.b.hand)
        self.assertEqual(self.options(self.b), [])

    def test_illegal_target_and_token_do_not_grant_permissions(self):
        bear = self.put(player=self.b)
        self.g.leave_battlefield(bear, 'hand')
        self.apply(FREE, bear)
        self.assertEqual(self.options(self.b), [])
        token = self.put(card('Test Token', '', 'Creature', '', 2, 2))
        token.card.is_token = token.front.is_token = True
        self.apply(FREE, token)
        self.assertEqual(self.options(self.a), [])

    def test_free_x_spell_uses_zero_for_x(self):
        thing = card('Test Hydra', '{X}{G}', 'Creature', '', 1, 1)
        permanent = self.put(thing, self.b)
        self.apply(FREE, permanent)
        self.g.active_idx = 1
        option = self.options(self.b)[0]
        self.assertNotIn('X', option.mana_cost)
        self.assertTrue(self.g.cast(self.b, option, []))
        self.assertEqual(self.b.creatures[0].entered_x, 0)

    def test_free_cast_still_pays_additional_costs(self):
        creature = card('Test Offering', '{3}{B}', 'Creature', '', 2, 2)
        creature.extra_discard = 1
        permanent = self.put(creature, self.b)
        self.apply(FREE, permanent)
        self.g.active_idx = 1
        option = self.options(self.b)[0]
        self.assertFalse(self.g.can_cast_now(self.b, option))
        self.b.hand = [ISLAND]
        self.assertTrue(self.g.cast(self.b, option, []))
        self.assertEqual(len(self.b.hand), 0)
        self.assertIn(ISLAND, self.b.graveyard)

    def test_play_taxes_and_untracked_referents_remain_unmatched(self):
        for s in (PAID.split('. ', 1)[1],
                  'Exile target nonland permanent. For as long as that card remains exiled, its owner may play it.',
                  'Exile target nonland permanent. You may cast that card for as long as it remains exiled.'):
            self.assertTrue(_parse_effects(s)[1], s)

    @unittest.skipUnless(DB_FILE.exists(), 'offline card database not built')
    def test_real_oracle(self):
        self.assertEqual(CardDB(offline=True).get('Release to the Wind').unsupported, [])
