"""Residual multi-recipient damage forms (#320), using actual offline Oracle cards."""
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cards import parse as P
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, BEAR, DB_FILE, card


class MultiDamage(Base):
    def test_one_or_two_has_required_then_optional_target(self):
        effects = parse_sentence('~ deals 2 damage to each of one or two targets.')
        self.assertEqual([e.target for e in effects], ['any', 'any'])
        self.assertEqual([bool(e.data.get('optional_target')) for e in effects], [False, True])
        self.assertTrue(all(e.data.get('distinct') for e in effects))
        c = self.spell('~ deals 2 damage to each of one or two targets.')
        self.cast(c, [self.b, None])
        self.assertEqual(self.b.life, 18)
        with self.game.targeting(c):
            self.assertFalse(self.game.legal_target(self.a, effects[0], None))
            self.assertTrue(self.game.legal_target(self.a, effects[1], None))

    def test_one_or_two_can_hit_two_different_targets(self):
        bear = self.perm(BEAR, self.b)
        self.cast(self.spell('~ deals 2 damage to each of one or two targets.'), [self.b, bear])
        self.assertEqual((self.b.life, bear.damage), (18, 2))

    def test_auto_targets_repick_is_player_safe(self):
        # "any target" includes players; re-picking a distinct second target must not read .controller on them
        c = self.spell('~ deals 2 damage to each of one or two targets.')
        bear = self.perm(BEAR, self.b)
        game, hook = self.game, self.game.hook
        game.hook = lambda p, name: (lambda *a, **k: bear) if name == "choose_target" else hook(p, name)
        try:
            out = game.auto_targets(self.a, c.spell_effects, source=c)
        finally:
            game.hook = hook
        self.assertEqual(out[0], bear)
        self.assertIsNot(out[1], bear)
        self.assertIn(out[1], (self.a, self.b, bear))

    def test_omitted_slot_does_not_keep_an_illegal_target_spell_resolving(self):
        c = self.spell('~ deals 2 damage to each of one or two targets.')
        bear = self.perm(BEAR, self.b)
        item = StackItem(self.a, c.spell_effects, [bear, None], card=c)
        self.b.battlefield.remove(bear)
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertFalse(item.resolved)

    def test_omitted_damage_does_not_fire_a_damage_event(self):
        c = card('Test Pinger', '{R}', 'Creature — Wizard',
                 'Whenever ~ deals damage, draw a card.\n'
                 '{T}: ~ deals 2 damage to each of one or two targets.', 1, 4)
        self.assertEqual(c.unsupported, [])
        src = self.perm(c, self.a)
        self.game.stack.append(StackItem(self.a, c.activated[0].effects, [self.b, None], source=src, kind='ability'))
        self.game.resolve_top()
        self.assertEqual(len(self.game.pending), 1)

    def test_any_other_target_excludes_the_source(self):
        c = card('Test Pinger', '{R}', 'Creature — Wizard', '{T}: ~ deals 2 damage to any other target.', 2, 4)
        self.assertEqual(c.unsupported, [])
        src = self.perm(c, self.a)
        bear = self.perm(BEAR, self.b)
        effect = c.activated[0].effects[0]
        with self.game.targeting(src):
            self.assertNotIn(src, self.game.legal_targets(self.a, effect))
            self.assertIn(bear, self.game.legal_targets(self.a, effect))
            self.assertIn(self.a, self.game.legal_targets(self.a, effect))
            self.assertIn(self.b, self.game.legal_targets(self.a, effect))
        self.game.stack.append(StackItem(self.a, [effect], [src], source=src, kind='ability'))
        self.game.resolve_top()
        self.assertEqual(src.damage, 0)
        self.game.stack.append(StackItem(self.a, [effect], [bear], source=src, kind='ability'))
        self.game.resolve_top()
        self.assertEqual(bear.damage, 2)

    def test_other_after_a_separate_target_is_left_unmatched(self):
        _, bad = P._parse_effects('Gain control of target creature until end of turn. '
                                  '~ deals 2 damage to any other target.')
        self.assertTrue(bad)     # "other" excludes the earlier target here, not the spell itself

    def test_split_self_damage_is_preventable_and_has_lifelink(self):
        c = card('Test Artillery', '{R}', 'Creature — Goblin',
                 'Lifelink\n{T}: ~ deals 2 damage to any target and 3 damage to you.', 1, 4)
        self.assertEqual(c.unsupported, [])
        src = self.perm(c, self.a)
        effects = c.activated[0].effects
        self.a.prevent_next = 2
        self.game.stack.append(StackItem(self.a, effects, [self.b, None], source=src, kind='ability'))
        self.game.resolve_top()
        # Two damage to the opponent gains two life; one unprevented to us loses and regains one.
        self.assertEqual((self.a.life, self.b.life, self.a.prevent_next), (22, 18, 0))

    def test_split_damage_to_itself_is_from_the_same_source(self):
        c = card('Test Pinger', '{R}', 'Creature — Wizard',
                 'Lifelink\n{T}: ~ deals 2 damage to any target and 3 damage to itself.', 1, 5)
        self.assertEqual(c.unsupported, [])
        src = self.perm(c, self.a)
        src.prevent_next = 1
        self.game.stack.append(StackItem(self.a, c.activated[0].effects, [self.b, None], source=src, kind='ability'))
        self.game.resolve_top()
        self.assertEqual((self.a.life, self.b.life, src.damage), (24, 18, 2))

    @unittest.skipUnless(DB_FILE.exists(), 'card database not built')
    def test_real_cards(self):
        db = CardDB(offline=True)
        storm = db.get('Storm of Steel')
        self.assertEqual(storm.unsupported, [])
        self.assertEqual(len(storm.spell_effects), 2)
        charm = db.get('Prismari Charm')
        self.assertEqual(charm.unsupported, [])
        self.assertEqual(len(charm.modes[1]), 2)
        self.assertTrue(charm.modes[1][1].data.get('optional_target'))
        self.assertTrue(all(e.data.get('distinct') for e in charm.modes[1]))
        arzakon = db.get('Arzakon')
        self.assertTrue(arzakon.loyalty_abilities[0][1][0].data.get('other'))
        char = db.get('Char')
        self.assertEqual([e.kind for e in char.spell_effects], ['damage', 'cx_damage'])
        self.a.prevent_next = 2
        self.cast(char, [self.b, None])
        self.assertEqual((self.a.life, self.b.life), (20, 16))


if __name__ == '__main__':
    unittest.main()
