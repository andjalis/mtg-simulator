"""Real-card regression tests for regeneration, prevention, upkeep and mana grants."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cards import Effect
from mtgsim.engine import Game, Permanent, Player, StackItem, ability_worth
from mtgsim.ai import HeuristicAI
from tests.test_templates import BEAR, FOREST, MOUNTAIN, card


class RegenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player('a', [FOREST] * 30, HeuristicAI())
        self.b = Player('b', [FOREST] * 30, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(7))
        self.g.turn, self.g.step = 1, 'main1'

    def perm(self, name, player=None):
        c = self.db.get(name) if isinstance(name, str) else name
        x = Permanent(c, player or self.a)
        x.sick = x.tapped = False
        x.controller.battlefield.append(x)
        return x

    def apply(self, name, target=None, source=None, player=None):
        c = self.db.get(name)
        effects = c.spell_effects
        if source is not None:
            effects = c.activated[0].effects
        item = StackItem(player or self.a, effects, [target] * len(effects), source=source)
        for e in effects:
            self.g.resolve(player or self.a, e, target, item)

    def shield(self, x):
        self.g.resolve(self.a, Effect('regenerate'), x)

    def test_real_templates(self):
        for name in ('Drudge Skeletons', 'Restless Dead', 'Regenerate', 'Stone Rain', 'Sinkhole', 'Rain of Tears',
                     'Fog', 'Darkness', 'Holy Day', 'Bandage', 'Samite Healer', 'Darba',
                     "Karametra's Favor", 'Abundant Growth', 'Multani\'s Harmony'):
            with self.subTest(name=name):
                c = self.db.get(name)
                self.assertEqual(c.unsupported, [])
                self.assertEqual(c.approximations, [])

    def test_destroy_consumes_one_shield_taps_clears_damage_and_combat(self):
        x, b = self.perm('Drudge Skeletons'), self.perm(BEAR, self.b)
        self.g.attackers = [x]
        self.g.blocks = {x: [b]}
        self.shield(x)
        self.shield(x)
        x.damage = 1
        x.deathtouched = True
        self.g.destroy(x)
        self.assertIn(x, self.a.battlefield)
        self.assertTrue(x.tapped)
        self.assertEqual((x.damage, x.deathtouched, x.regen_shields), (0, False, 1))
        self.assertNotIn(x, self.g.attackers)
        self.assertNotIn(x, self.g.blocks)
        self.g.destroy(x)
        self.g.destroy(x)
        self.assertNotIn(x, self.a.battlefield)

    def test_lethal_damage_and_deathtouch_regenerate(self):
        for deathtouch in (False, True):
            x = self.perm(BEAR)
            self.shield(x)
            x.damage = 1 if deathtouch else 2
            x.deathtouched = deathtouch
            self.g.state_based_actions()
            self.assertIn(x, self.a.battlefield)
            self.assertEqual(x.damage, 0)

    def test_sacrifice_zero_toughness_and_expiry(self):
        x = self.perm(BEAR)
        self.shield(x)
        self.g.sacrifice(x)
        self.assertNotIn(x, self.a.battlefield)
        x = self.perm(BEAR)
        self.shield(x)
        x.pump_t = -2
        self.g.state_based_actions()
        self.assertNotIn(x, self.a.battlefield)
        x = self.perm(BEAR)
        self.shield(x)
        self.g.turn += 1
        self.g.destroy(x)
        self.assertNotIn(x, self.a.battlefield)

    def test_wrath_and_targeted_no_regeneration(self):
        for name in ('Terror', 'Wrath of God'):
            x = self.perm(BEAR)
            self.shield(x)
            self.apply(name, x)
            self.assertNotIn(x, self.a.battlefield)

    def test_regenerated_blocker_leaves_attacker_blocked(self):
        a, b = self.perm(BEAR), self.perm('Drudge Skeletons', self.b)
        self.g.attackers, self.g.blocks = [a], {a: [b]}
        self.shield(b)
        self.g.destroy(b)
        self.g.combat_damage(self.a, self.b, self.g.attackers, self.g.blocks, lambda x: True)
        self.assertEqual(self.b.life, 20)
        self.assertEqual(a.damage, 0)

    def test_next_damage_consumption_and_life_loss(self):
        self.apply('Bandage', self.a)
        self.g.deal_damage(self.a, 1)
        self.assertEqual(self.a.life, 20)
        self.g.deal_damage(self.a, 3)
        self.assertEqual(self.a.life, 17)
        self.g.resolve(self.a, Effect('prevent_damage', 3), self.a)
        self.g.change_life(self.a, -2, 'loss of life')
        self.assertEqual(self.a.life, 15)
        self.g.deal_damage(self.a, 4)
        self.assertEqual(self.a.life, 14)

    def test_fog_prevents_combat_triggers_lifelink_and_deathtouch(self):
        a = self.perm(card('Vampire', '{B}', 'Creature', 'Lifelink\nDeathtouch', 3, 3))
        b = self.perm(BEAR, self.b)
        self.apply('Fog')
        self.g.combat_damage(self.a, self.b, [a], {a: [b]}, lambda x: True)
        self.assertEqual((self.a.life, b.damage, b.deathtouched), (20, 0, False))
        self.g.deal_damage(b, 1)
        self.assertEqual(b.damage, 1)
        self.g.turn += 1
        self.g.combat_damage(self.a, self.b, [a], {}, lambda x: True)
        self.assertEqual(self.b.life, 17)

    def test_prevent_all_damage_and_no_prevention(self):
        x = self.perm(BEAR)
        self.g.resolve(self.a, Effect('prevent_damage', -1, target='creature'), x)
        self.g.deal_damage(x, 20)
        self.assertEqual(x.damage, 0)
        self.g.resolve(self.a, Effect('no_prevention'), None)
        self.g.deal_damage(x, 2)
        self.g.state_based_actions()
        self.assertNotIn(x, self.a.battlefield)

    def test_nonbasic_land_and_resolution_revalidation(self):
        forest = self.perm(FOREST, self.b)
        land = self.perm('Llanowar Wastes', self.b)
        creature = self.perm(BEAR, self.b)
        e = card('Ruin', '{B}', 'Sorcery', 'Destroy target nonbasic land an opponent controls.').spell_effects[0]
        self.assertEqual(self.g.legal_targets(self.a, e), [land])
        self.assertFalse(self.g.legal_target(self.a, e, forest))
        self.assertFalse(self.g.legal_target(self.a, e, creature))
        self.apply('Stone Rain', forest)
        self.assertNotIn(forest, self.b.battlefield)

    def test_upkeep_payment_and_failure(self):
        x = self.perm('Darba')
        for _ in range(2):
            self.perm(FOREST)
        self.g.fire(self.a, 'upkeep')
        self.g.settle()
        self.assertIn(x, self.a.battlefield)
        self.assertEqual(sum(p.tapped for p in self.a.battlefield), 2)
        self.g.fire(self.a, 'upkeep')
        self.g.settle()
        self.assertNotIn(x, self.a.battlefield)
        x = self.perm('Darba')
        self.g.fire(self.a, 'upkeep')
        self.a.battlefield.remove(x)
        x.controller = self.b
        self.b.battlefield.append(x)
        self.g.settle()
        self.assertIn(x, self.b.battlefield)  # the old controller cannot sacrifice it

    def test_opponents_aura_grants_mana_and_detach_removes_it(self):
        x = self.perm(BEAR)
        aura = self.perm("Karametra's Favor", self.b)
        aura.aura_host = x
        x.auras.append(aura)
        self.assertEqual(x.granted_mana(), frozenset('WUBRG'))
        x.sick = True
        self.assertFalse(x.can_tap_for_mana())
        x.sick = False
        self.assertTrue(self.g.can_pay(self.a, {'U': 1}))
        self.g.leave_battlefield(aura, 'graveyard')
        self.assertFalse(x.granted_mana())

    def test_ability_responds_once_to_destroy(self):
        x = self.perm('Drudge Skeletons')
        self.perm('Swamp')
        self.g.stack.append(StackItem(self.b, [Effect('destroy', target='creature')], [x]))
        self.assertTrue(ability_worth(self.g, self.a, x, 0))
        self.g.activate_ability(self.a, x, 0)
        self.assertIn(x, self.a.battlefield)
        self.assertFalse(ability_worth(self.g, self.a, x, 0))

    def test_actual_priority_regeneration_response(self):
        x = self.perm('Drudge Skeletons')
        self.perm('Swamp')
        self.g.stack.append(StackItem(self.b, [Effect('destroy', target='creature')], [x]))
        self.g.settle()
        self.assertIn(x, self.a.battlefield)
        self.assertTrue(x.tapped)
        self.assertEqual(x.regen_shields, 0)

    def test_prevention_applies_to_planeswalkers_and_damage_to_each_player(self):
        pw = self.perm('Jace, the Mind Sculptor')
        pw.counters['loyalty'] = 3
        self.g.resolve(self.a, Effect('prevent_damage', 2, target='any'), pw)
        self.g.deal_damage(pw, 3)
        self.assertEqual(pw.loyalty, 2)
        self.g.resolve(self.a, Effect('prevent_damage', 2), self.a)
        self.g.resolve(self.a, Effect('damage_each_player', 3), None)
        self.assertEqual((self.a.life, self.b.life), (19, 17))

    def test_quoted_equipment_mana_grant(self):
        x, eq = self.perm(BEAR), self.perm('Paradise Mantle')
        eq.attached_to = x
        self.assertFalse(eq.card.unsupported)
        self.assertEqual(x.granted_mana(), frozenset('WUBRG'))
        eq.attached_to = None
        self.assertFalse(x.granted_mana())

    def test_land_ai_fallback_picks_land(self):
        land = self.perm(FOREST, self.b)
        e = self.db.get('Stone Rain').spell_effects[0]
        self.assertEqual(self.g.auto_targets(self.a, [e]), [land])

    def test_temporary_and_permanent_quoted_grants(self):
        x = self.perm(BEAR)
        temporary = card('Mana Gift', '{G}', 'Instant',
                         'Target creature gains "{T}: Add one mana of any color." until end of turn.')
        permanent = card('Mana Gift Two', '{G}', 'Instant',
                         'Target creature gains "{T}: Add {C}."')
        self.assertFalse(temporary.unsupported)
        self.assertFalse(permanent.unsupported)
        self.g.resolve(self.a, temporary.spell_effects[0], x)
        self.g.resolve(self.a, permanent.spell_effects[0], x)
        self.assertEqual(x.granted_mana(), frozenset('WUBRGC'))
        self.a.battlefield.remove(x)
        x.controller = self.b
        self.b.battlefield.append(x)
        self.assertEqual(x.granted_mana(), frozenset('WUBRGC'))
        self.g.turn += 1
        self.assertEqual(x.granted_mana(), frozenset('C'))

    def test_damage_cannot_be_regenerated_rider_before_lethal_damage(self):
        x = self.perm(BEAR)
        self.shield(x)
        burn = card('Scorch', '{R}', 'Instant',
                    "Scorch deals 2 damage to target creature. It can't be regenerated this turn.")
        self.assertFalse(burn.unsupported)
        self.g.stack.append(StackItem(self.b, burn.spell_effects, [x, None]))
        self.g.resolve_top()
        self.assertNotIn(x, self.a.battlefield)


if __name__ == '__main__':
    unittest.main()
