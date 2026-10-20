"""Source-aware DEBT rules and evasion, including offline real-card regressions."""
import random
import unittest

from mtgsim import auras, kw_evasion
from mtgsim.cards import Effect
from mtgsim.carddb import CardDB, ALL_CARDS
from mtgsim.engine import Game, Permanent, Player, StackItem, can_block
from tests.test_templates import card, BEAR, DRAGON, ISLAND, MOUNTAIN, SHOCK
from mtgsim.ai import HeuristicAI


class EvasionTests(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(1))
        self.game.turn = 1
        self.a.library = self.b.library = [ISLAND] * 50

    def perm(self, text='', owner=None, cost='{W}', types='Creature — Human', p=2, t=4):
        c = card('Test', cost, types, text, p, t)
        result = Permanent(c, owner or self.a)
        result.sick = result.tapped = False
        result.controller.battlefield.append(result)
        return result

    def test_protection_lists(self):
        for text in ('Flying, first strike, and haste', 'Flying, protection from red', 'Protection from black and from red',
                     'First strike; protection from artifacts', 'Protection from all colors',
                     'Protection from creatures', 'Protection from everything', 'Protection from monocolored',
                     'Protection from multicolored', 'Protection from instants'):
            with self.subTest(text=text):
                self.assertFalse(self.perm(text).card.unsupported)
        self.assertTrue(self.perm('Protection from red as long as you control a Goblin.').card.unsupported)

    def test_shroud_stops_both_players_but_not_nontargeted_effects(self):
        obj = self.perm('Shroud')
        self.assertFalse(self.game.targetable(obj, self.a))
        self.assertFalse(self.game.targetable(obj, self.b))
        self.game.resolve(self.b, Effect('damage', 1, target='each_creature'), None,
                          StackItem(self.b, [], [], card=SHOCK))
        self.assertEqual(obj.damage, 1)

    def test_color_targeting_at_announcement_and_resolution(self):
        obj = self.perm('Protection from red')
        self.assertFalse(self.game.legal_target(self.b, SHOCK.spell_effects[0], obj, SHOCK))
        self.b.hand = [SHOCK]
        self.perm(owner=self.b, types='Basic Land — Mountain', cost='')
        # Explicit forbidden choices fail before spending mana or moving the card.
        self.assertFalse(self.game.cast(self.b, SHOCK, [obj]))
        self.assertIn(SHOCK, self.b.hand)
        obj.temp_kw.clear()
        self.game.stack = [StackItem(self.b, SHOCK.spell_effects, [obj], card=SHOCK)]
        self.game.resolve_top()
        self.assertEqual(obj.damage, 0)

    def test_protection_gained_in_response(self):
        obj = self.perm()
        self.game.stack = [StackItem(self.b, SHOCK.spell_effects, [obj], card=SHOCK)]
        obj.temp_kw.add('protection from red')
        self.game.resolve_top()
        self.assertEqual(obj.damage, 0)

    def test_damage_and_blocking_by_color_and_type(self):
        obj = self.perm('Protection from red')
        red = self.perm(owner=self.b, cost='{R}')
        self.assertFalse(can_block(red, obj))
        self.game.deal_damage(obj, 3, by=self.b, source=red)
        self.assertEqual(obj.damage, 0)
        self.game.deal_damage(obj, 1, by=self.b, source=BEAR)
        self.assertEqual(obj.damage, 1)
        obj.temp_kw.add('protection from creatures')
        self.assertFalse(can_block(self.perm(owner=self.b), obj))
        self.assertFalse(self.game.targetable(obj, self.b, SHOCK))

    def test_protection_does_not_prevent_destroy_or_life_loss(self):
        obj = self.perm('Protection from everything')
        self.game.destroy(obj)
        self.assertNotIn(obj, self.a.battlefield)

    def test_all_colors_excludes_colorless(self):
        obj = self.perm('Protection from all colors')
        self.assertTrue(kw_evasion.protected(obj, SHOCK))
        self.assertFalse(kw_evasion.protected(obj, self.perm(cost='{3}')))

    def test_mono_and_multicolor_use_actual_colors(self):
        mono = self.perm('Protection from monocolored')
        multi = self.perm('Protection from multicolored')
        two = self.perm(cost='{W}{U}')
        self.assertFalse(kw_evasion.protected(mono, two))
        self.assertTrue(kw_evasion.protected(multi, two))
        devoid = card('Devoid test', '{R}', 'Creature', 'Devoid', 2, 2)
        self.assertFalse(kw_evasion.protected(mono, devoid))
        hybrid = card('Hybrid test', '{W/U}', 'Creature', '', 2, 2)
        self.assertTrue(kw_evasion.protected(multi, hybrid))

    def test_protection_combat_prevents_lifelink_and_deathtouch(self):
        obj = self.perm('Protection from red')
        red = self.perm('Deathtouch, lifelink', owner=self.b, cost='{R}')
        self.game.combat_damage(self.a, self.b, [obj], {obj: [red]}, lambda p: p is red)
        self.assertEqual(obj.damage, 0)
        self.assertFalse(obj.deathtouched)
        self.assertEqual(self.b.life, 20)

    def test_fight_uses_creature_instead_of_spell_color(self):
        obj = self.perm('Protection from green')
        green = self.perm(owner=self.b, cost='{G}')
        item = StackItem(self.b, [], [green, obj], card=SHOCK)
        self.game.resolve(self.b, Effect('fight', target='creature'), obj, item)
        self.assertEqual(obj.damage, 0)
        self.assertEqual(green.damage, obj.power)

    def test_aura_and_equipment_fall_off_as_sba(self):
        obj = self.perm()
        aura = self.perm('Enchant creature\nEnchanted creature gets +1/+1.', types='Enchantment — Aura', cost='{R}')
        auras.attach(self.game, aura, obj)
        eq = self.perm('Equip {1}', types='Artifact — Equipment', cost='{1}')
        eq.attached_to = obj
        obj.temp_kw.update({'protection from red', 'protection from artifacts'})
        self.game.state_based_actions()
        self.assertNotIn(aura, self.a.battlefield)
        self.assertIn(aura.card, self.a.graveyard)
        self.assertIsNone(eq.attached_to)
        self.assertIn(eq, self.a.battlefield)

    def test_equipment_grants_both_protection_qualities(self):
        obj = self.perm()
        eq = self.perm('Equipped creature gets +2/+2 and has protection from red and from blue.\nEquip {1}',
                       types='Artifact — Equipment', cost='{1}')
        self.assertFalse(eq.card.unsupported)
        eq.attached_to = obj
        self.assertTrue(obj.has('protection from red'))
        self.assertTrue(obj.has('protection from blue'))
        self.assertFalse(self.game.targetable(obj, self.b, SHOCK))
        self.assertEqual(obj.power, 4)

    def test_shroud_does_not_remove_existing_attachments(self):
        obj = self.perm()
        aura = self.perm('Enchant creature', types='Enchantment — Aura')
        auras.attach(self.game, aura, obj)
        obj.temp_kw.add('shroud')
        self.game.state_based_actions()
        self.assertIs(aura.aura_host, obj)

    def test_aura_cast_cannot_enchant_protected_creature(self):
        obj = self.perm('Protection from red')
        aura = card('Red aura', '{R}', 'Enchantment — Aura', 'Enchant creature\nEnchanted creature gets +1/+1.')
        self.assertFalse(self.game.aura_host_legal(self.a, aura, obj))

    def test_shadow_blocks_only_shadow(self):
        shadow = self.perm('Shadow')
        normal = self.perm(owner=self.b)
        other = self.perm('Shadow', owner=self.b)
        self.assertFalse(can_block(normal, shadow))
        self.assertFalse(can_block(shadow, normal))
        self.assertTrue(can_block(other, shadow))

    def test_horsemanship_is_independent_of_flying(self):
        horse = self.perm('Horsemanship')
        fly = self.perm('Flying', owner=self.b)
        other = self.perm('Horsemanship', owner=self.b)
        self.assertFalse(can_block(fly, horse))
        self.assertTrue(can_block(other, horse))
        self.assertTrue(can_block(horse, self.perm(owner=self.b)))

    def test_can_block_only_flying_requires_flying_not_reach(self):
        tern = self.perm('Flying\nThis creature can block only creatures with flying.')
        self.assertFalse(can_block(tern, self.perm('Reach', owner=self.b)))
        self.assertTrue(can_block(tern, self.perm('Flying', owner=self.b)))

    def test_basic_landwalk_looks_at_land_type_not_mana_produced(self):
        for keyword, subtype in [('plainswalk','Plains'), ('islandwalk','Island'), ('swampwalk','Swamp'),
                                 ('mountainwalk','Mountain'), ('forestwalk','Forest')]:
            with self.subTest(keyword=keyword):
                self.b.battlefield.clear()
                attacker = self.perm(keyword)
                blocker = self.perm(owner=self.b)
                self.assertTrue(can_block(blocker, attacker))
                self.perm(owner=self.b, types='Basic Land — '+subtype, cost='')
                self.assertFalse(can_block(blocker, attacker))
                self.b.battlefield.pop()
                self.perm('{T}: Add {G}.', owner=self.b, types='Land', cost='')
                self.assertTrue(can_block(blocker, attacker))

    def test_nonbasic_legendary_snow_landwalk(self):
        for keyword, types in [('Nonbasic landwalk', 'Land — Island'), ('Legendary landwalk', 'Legendary Land'),
                               ('Snow landwalk','Snow Land'), ('Snow forestwalk','Snow Land — Forest')]:
            with self.subTest(keyword=keyword):
                self.b.battlefield.clear()
                obj = self.perm(keyword)
                blocker = self.perm(owner=self.b)
                self.perm(owner=self.b, types='Basic Land — Island', cost='')
                self.assertTrue(can_block(blocker, obj))
                self.perm(owner=self.b, types=types, cost='')
                self.assertFalse(can_block(blocker, obj))

    def test_except_by_flying_and_reach(self):
        obj = self.perm("This creature can't be blocked except by creatures with flying or reach.")
        self.assertFalse(can_block(self.perm(owner=self.b), obj))
        self.assertTrue(can_block(self.perm('Reach', owner=self.b), obj))
        obj = self.perm("This creature can't be blocked except by creatures with flying.")
        self.assertFalse(can_block(self.perm('Reach', owner=self.b), obj))

    def test_fear_intimidate_and_skulk(self):
        fear = self.perm('Fear')
        self.assertFalse(can_block(self.perm(owner=self.b), fear))
        self.assertTrue(can_block(self.perm(cost='{B}', owner=self.b), fear))
        self.assertTrue(can_block(self.perm(types='Artifact Creature', owner=self.b), fear))
        intimidate = self.perm('Intimidate', cost='{R}{G}')
        self.assertTrue(can_block(self.perm(cost='{G}', owner=self.b), intimidate))
        self.assertFalse(can_block(self.perm(cost='{B}', owner=self.b), intimidate))
        skulk = self.perm('Skulk', p=1)
        self.assertFalse(can_block(self.perm(owner=self.b, p=2), skulk))

    def test_blocker_count_is_enforced_by_combat(self):
        for count in (2, 3):
            with self.subTest(count=count):
                self.a.battlefield.clear()
                self.b.battlefield.clear()
                self.b.life = 20
                obj = self.perm("This creature can't be blocked except by three or more creatures.", p=4, t=8)
                blockers = [self.perm(owner=self.b, p=1, t=8) for _ in range(count)]
                self.a.ai.choose_attackers = lambda *args: [obj]
                self.b.ai.choose_blocks = lambda *args: {obj: blockers}
                self.game.combat(self.a, self.b)
                self.assertEqual(self.b.life, 16 if count == 2 else 20)

    def test_minimum_blocker_counts(self):
        obj = self.perm("This creature can't be blocked except by three or more creatures.")
        self.assertEqual(kw_evasion.minimum_blockers(obj), 3)
        obj.temp_kw.add('menace')
        self.assertEqual(kw_evasion.minimum_blockers(obj), 3)

    def test_granted_protection_color_choice(self):
        obj = self.perm()
        self.perm(owner=self.b, cost='{R}')
        c = card('Bless', '{W}', 'Instant', 'Target creature you control gains protection from the color of your choice until end of turn.')
        self.assertFalse(c.unsupported)
        self.game.resolve(self.a, c.spell_effects[0], obj, StackItem(self.a, c.spell_effects, [obj], card=c))
        self.assertTrue(obj.has('protection from red'))

    def test_subtype_protection_and_comma_lists(self):
        obj = self.perm('Protection from Vampires, from Werewolves, and from Zombies')
        self.assertFalse(obj.card.unsupported)
        zombie = self.perm(owner=self.b, types='Creature — Zombie')
        self.assertFalse(can_block(zombie, obj))
        self.assertTrue(can_block(self.perm(owner=self.b), obj))

    def test_quoted_flying_only_token_restriction(self):
        c = card('Maker', '{U}', 'Sorcery', 'Create a 1/1 blue Faerie creature token with flying and "This token can block only creatures with flying."')
        self.assertFalse(c.unsupported)
        self.game.create_token(self.a, c.spell_effects[0])
        token = self.a.creatures[0]
        self.assertFalse(can_block(token, self.perm(owner=self.b)))
        self.assertTrue(can_block(token, self.perm('Flying', owner=self.b)))

    def test_self_grants_keep_both_protection_qualities(self):
        obj = self.perm('{0}: This creature gains protection from blue and from red until end of turn.')
        self.assertFalse(obj.card.unsupported)
        self.assertTrue(self.game.activate_ability(self.a, obj, 0))
        self.assertTrue(obj.has('protection from blue'))
        self.assertTrue(obj.has('protection from red'))

    def test_colored_token_protection(self):
        c = card('Maker', '{W}', 'Sorcery', 'Create a 1/1 red Goblin creature token.')
        self.game.create_token(self.b, c.spell_effects[0])
        obj = self.perm('Protection from red')
        self.assertFalse(can_block(self.b.creatures[0], obj))


@unittest.skipUnless(ALL_CARDS.exists(), 'offline card DB required')
class RealCardTests(unittest.TestCase):
    setUp = EvasionTests.setUp

    def test_real_cards_parse_fully(self):
        db = CardDB(offline=True)
        for name in ('White Knight', 'Akroma, Angel of Wrath', 'True-Name Nemesis', 'Zodiac Horse',
                     'Elite Cat Warrior', 'Willow Dryad', 'Rime Dryad', 'Dryad Sophisticate',
                     'Ayumi, the Last Visitor', 'Welkin Tern', 'Dauthi Slayer', 'Spire Tracer',
                     'Amrou Seekers', 'Shelter', 'Deft Duelist'):
            with self.subTest(card=name):
                c = db.get(name)
                self.assertEqual(c.unsupported, [])
                self.assertEqual(c.approximations, [])

    def test_true_name_tracks_chosen_player_across_control_change(self):
        obj = self.game.enter_battlefield(self.a, CardDB(True).get('True-Name Nemesis'))
        self.assertIs(obj.protection_player, self.b)
        self.assertTrue(kw_evasion.protected(obj, SHOCK, self.b))
        self.a.battlefield.remove(obj)
        self.b.battlefield.append(obj)
        obj.controller = self.b
        self.assertTrue(kw_evasion.protected(obj, SHOCK, self.b))
        self.assertFalse(kw_evasion.protected(obj, SHOCK, self.a))

    def test_actual_db_color_indicator_and_characteristic_colors(self):
        db = CardDB(True)
        self.assertEqual(kw_evasion.colors(db.get('Dryad Arbor')), {'G'})
        self.assertEqual(kw_evasion.colors(db.get('Ghostfire')), set())
        self.assertEqual(kw_evasion.colors(db.get('Transguild Courier')), set('WUBRG'))
