"""Damage replacement amounts read the replacement permanent's current characteristics (#315)."""
import unittest

from mtgsim.carddb import CardDB
from tests.test_cx_grammar import Base, BEAR, DB_FILE, card


@unittest.skipUnless(DB_FILE.exists(), 'card database not built')
class ReplacementAmounts(Base):
    def setUp(self):
        super().setUp()
        self.db = CardDB(offline=True)

    def holder(self, name):
        c = self.db.get(name)
        self.assertEqual(c.unsupported, [], name)
        return self.perm(c, self.a)

    def test_fire_counters_are_read_for_each_damage_event(self):
        holder = self.holder('Fated Firepower')
        src = self.perm(BEAR, self.a)
        holder.counters['fire'] = 4
        self.game.deal_damage(self.b, 2, by=self.a, source=src)
        self.assertEqual(self.b.life, 14)
        holder.counters['fire'] = 1
        self.game.deal_damage(self.b, 2, by=self.a, source=src)
        self.assertEqual(self.b.life, 11)
        holder.counters['fire'] = 0
        self.game.deal_damage(self.b, 2, by=self.a, source=src)
        self.assertEqual(self.b.life, 9)

    def test_hawkeye_uses_its_own_current_power(self):
        holder = self.holder('Hawkeye, Young Avenger')
        src = self.perm(BEAR, self.a)
        self.game.deal_damage(self.b, 1, by=self.a, source=src)
        self.assertEqual(self.b.life, 19 - holder.power)
        holder.counters['+1/+1'] = 2
        before = self.b.life
        self.game.deal_damage(self.b, 1, by=self.a, source=src)
        self.assertEqual(self.b.life, before - 1 - holder.power)

    def test_hawkeye_filters_combat_sources_and_recipients(self):
        self.holder('Hawkeye, Young Avenger')
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.game.deal_damage(self.b, 1, by=self.a, source=mine, combat=True)
        self.game.deal_damage(self.a, 1, by=self.a, source=mine)
        self.game.deal_damage(self.b, 1, by=self.b, source=theirs)
        self.assertEqual((self.a.life, self.b.life), (19, 18))

    def test_dynamic_addition_participates_in_replacement_order(self):
        holder = self.holder('Fated Firepower')
        holder.counters['fire'] = 4
        self.holder('Furnace of Rath')
        src = self.perm(BEAR, self.a)
        self.game.deal_damage(self.b, 2, by=self.a, source=src)
        self.assertEqual(self.b.life, 12)   # opponent chooses double first, then +4

    def test_negative_power_does_not_reduce_damage(self):
        holder = self.holder('Hawkeye, Young Avenger')
        holder.counters['-1/-1'] = holder.power + 1
        src = self.perm(BEAR, self.a)
        self.game.deal_damage(self.b, 2, by=self.a, source=src)
        self.assertEqual(self.b.life, 18)

    def test_unbound_dynamic_and_temporary_replacements_stay_unmatched(self):
        for body in ('it deals that much damage plus X instead.',
                     'it deals that much damage plus an amount of damage equal to that creature\'s power instead.'):
            c = card('Test Modifier', '{R}', 'Enchantment',
                     'If a source you control would deal damage to a permanent or player, ' + body)
            self.assertTrue(c.unsupported, body)
        c = card('Test Modifier', '{R}', 'Enchantment',
                 'If a source you control would deal damage to a permanent or player this turn, '
                 'it deals that much damage plus 2 instead.')
        self.assertTrue(c.unsupported)

    def test_that_much_to_any_other_target_preserves_amount_and_source(self):
        c = card('Test Reckoner', '{R}', 'Creature — Minotaur',
                 'Lifelink\nWhenever ~ is dealt damage, it deals that much damage to any other target.', 1, 8)
        self.assertEqual(c.unsupported, [])
        src = self.perm(c, self.a)
        self.b.prevent_next = 1
        self.game.deal_damage(src, 3, by=self.b, source=self.perm(BEAR, self.b))
        self.assertEqual(len(self.game.pending), 1)
        self.game.flush_triggers()
        item = self.game.stack[-1]
        effect = item.effects[0]
        self.assertEqual(effect.amount, 3)
        with self.game.targeting(item):
            self.assertFalse(self.game.legal_target(self.a, effect, src))
        item.targets = [self.b]
        self.game.resolve_top()
        self.assertEqual((self.a.life, self.b.life), (22, 18))

    def test_actual_damage_backreference_card(self):
        c = self.db.get('Black Panther, Most Dangerous')
        self.assertFalse(any('that much damage' in s for s in c.unsupported), c.unsupported)
        self.assertTrue(c.triggers[0].effects[0].data.get('other'))
        self.assertTrue(c.triggers[0].effects[0].data.get('that_much'))


if __name__ == '__main__':
    unittest.main()
