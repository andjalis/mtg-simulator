"""Blocking restrictions and shroud share legality checks with the combat AI and stack."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI, search_blocks
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player, StackItem, can_block, choose_equip_target
from tests.test_templates import BEAR, ISLAND, card


class BlockingLandwalkShroud(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, 'main1'
        self.a.library = [ISLAND] * 20
        self.b.library = [ISLAND] * 20

    def creature(self, who=None, text='', power=2, toughness=2):
        c = card('Test creature', text=text, power=power, toughness=toughness)
        self.assertFalse(c.unsupported)
        perm = self.game.enter_battlefield(who or self.a, c)
        perm.sick = False
        return perm

    def cast(self, text, targets=(), who=None):
        p = who or self.a
        c = card('Test spell', types='Instant', text=text)
        self.assertFalse(c.unsupported)
        p.hand.append(c)
        self.assertTrue(self.game.cast(p, c, list(targets)))
        self.game.settle()

    def test_flying_only_blocker_cannot_block_ground_creature(self):
        a = self.creature()
        b = self.creature(self.b, 'This creature can block only creatures with flying.')
        self.assertFalse(can_block(b, a))
        self.assertEqual(search_blocks([a], [b], self.a, self.b), {})
        a.temp_kw.add('flying')
        self.assertFalse(can_block(b, a))  # the restriction does not grant flying or reach
        b.temp_kw.add('reach')
        self.assertTrue(can_block(b, a))

    def test_flying_blocker_still_has_flying_only_restriction(self):
        a = self.creature()
        b = self.creature(self.b, 'Flying\nThis creature can block only creatures with flying.')
        self.assertFalse(can_block(b, a))
        a.temp_kw.add('flying')
        self.assertTrue(can_block(b, a))
        b.tapped = True
        self.assertFalse(can_block(b, a))

    def test_ground_creature_connects_despite_illegal_ai_block(self):
        a = self.creature()
        b = self.creature(self.b, 'Flying\nThis creature can block only creatures with flying.', 5, 5)
        with patch.object(self.a.ai, 'choose_attackers', return_value=[a]), \
             patch.object(self.b.ai, 'choose_blocks', return_value={a: [b]}):
            self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 18)
        self.assertIn(a, self.a.battlefield)

    def test_losing_flying_changes_blocking_legality(self):
        a = self.creature(text='Flying')
        b = self.creature(self.b, 'Flying\nThis creature can block only creatures with flying.')
        self.assertTrue(can_block(b, a))
        a.card = BEAR
        self.assertFalse(can_block(b, a))

    def test_restricted_blocking_variants_remain_visible(self):
        c = card('Unsupported', text='This creature can block only creatures with shadow.')
        self.assertTrue(c.unsupported)

    def test_landwalk_checks_defenders_land_subtypes(self):
        for kw, subtype in [('forestwalk', 'Forest'), ('mountainwalk', 'Mountain')]:
            with self.subTest(keyword=kw):
                a = self.creature(text=kw.capitalize())
                b = self.creature(self.b)
                land = card('Test dual', types='Land — Island ' + subtype)
                mine = self.game.enter_battlefield(self.a, land)
                self.assertTrue(can_block(b, a))
                theirs = self.game.enter_battlefield(self.b, land)
                theirs.tapped = True
                self.assertFalse(can_block(b, a))
                self.game.destroy(theirs)
                self.assertTrue(can_block(b, a))
                self.game.leave_battlefield(mine, 'hand')

    def test_landwalk_name_and_mana_are_insufficient(self):
        for kw, subtype, color in [('forestwalk', 'Forest', 'G'), ('mountainwalk', 'Mountain', 'R')]:
            with self.subTest(keyword=kw):
                a = self.creature(text=kw.capitalize())
                b = self.creature(self.b)
                self.game.enter_battlefield(self.b, card(subtype + ' named land', types='Land', text='{T}: Add {' + color + '}.'))
                self.assertTrue(can_block(b, a))

    def test_landwalk_snow_lands_and_granted_keywords(self):
        a = self.creature()
        b = self.creature(self.b, 'Flying')
        a.temp_kw.add('forestwalk')
        land = self.game.enter_battlefield(self.b, card('Snow Forest', types='Basic Snow Land — Forest'))
        self.assertFalse(can_block(b, a))
        self.game.leave_battlefield(land, 'hand')
        self.assertTrue(can_block(b, a))

    def test_both_landwalk_keywords_and_real_combat(self):
        a = self.creature(text='Forestwalk, mountainwalk')
        b = self.creature(self.b, power=5, toughness=5)
        self.game.enter_battlefield(self.b, card('Mountain', types='Basic Land — Mountain'))
        self.assertFalse(can_block(b, a))
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 18)
        self.assertIn(a, self.a.battlefield)
        self.assertIn(b, self.b.battlefield)

    def test_other_landwalk_stays_unsupported(self):
        self.assertTrue(card('Desertwalker', text='Desertwalk').unsupported)

    def test_shroud_rejects_both_controllers_targets(self):
        a = self.creature(text='Shroud')
        for by in (self.a, self.b):
            self.assertFalse(self.game.targetable(a, by))
            for eff in (Effect('damage', 2, target='any'), Effect('destroy', target='creature'),
                        Effect('pump', 2, 2, target='creature_mine')):
                self.assertNotIn(a, self.game.legal_targets(by, eff))
                self.assertFalse(self.game.legal_target(by, eff, a))

    def test_hexproof_still_allows_friendly_targeting(self):
        a = self.creature(text='Hexproof')
        self.assertTrue(self.game.targetable(a, self.a))
        self.assertFalse(self.game.targetable(a, self.b))

    def test_shroud_on_noncreature_permanent(self):
        c = card('Shrouded land', types='Land', text='Shroud')
        self.assertFalse(c.unsupported)
        land = self.game.enter_battlefield(self.b, c)
        eff = Effect('destroy', target='land')
        self.assertNotIn(land, self.game.legal_targets(self.a, eff))
        self.assertFalse(self.game.targetable(land, self.b))

    def test_gaining_shroud_in_response_fizzles_spell_including_draw(self):
        a = self.creature(self.b)
        with patch.object(self.game, 'settle'):
            self.cast('Destroy target creature. Draw a card.', [a])
        a.temp_kw.add('shroud')
        self.game.settle()
        self.assertIn(a, self.b.battlefield)
        self.assertEqual(self.a.hand, [])

    def test_losing_shroud_restores_targeting(self):
        a = self.creature(self.b)
        a.temp_kw.add('shroud')
        self.assertFalse(self.game.targetable(a, self.a))
        a.temp_kw.clear()
        self.cast('Destroy target creature.', [a])
        self.assertNotIn(a, self.b.battlefield)

    def test_shroud_does_not_prevent_untargeted_wrath(self):
        a = self.creature(self.b, 'Shroud')
        self.cast('Destroy all creatures.')
        self.assertNotIn(a, self.b.battlefield)

    def test_shroud_does_not_prevent_team_pumps(self):
        a = self.creature(text='Shroud')
        self.cast('Creatures you control get +1/+1 until end of turn.')
        self.assertEqual((a.power, a.toughness), (3, 3))

    def test_shroud_does_not_prevent_self_abilities(self):
        a = self.creature(text='Shroud')
        item = StackItem(self.a, [], [], source=a)
        self.game.resolve(self.a, Effect('pump', 2, 2, target='self'), None, item)
        self.assertEqual(a.power, 4)

    def test_shroud_does_not_prevent_normal_combat_damage(self):
        a = self.creature(text='Shroud')
        self.creature(self.b, power=3, toughness=3)
        with patch.object(self.a.ai, 'choose_attackers', return_value=[a]):
            self.game.combat(self.a, self.b)
        self.assertNotIn(a, self.a.battlefield)

    def test_equip_cannot_target_shroud_and_ai_chooses_legal_host(self):
        hidden = self.creature(text='Shroud', power=5, toughness=5)
        legal = self.creature()
        c = card('Test sword', types='Artifact — Equipment', text='Equipped creature gets +1/+1.\nEquip {0}')
        self.assertFalse(c.unsupported)
        sword = self.game.enter_battlefield(self.a, c)
        self.assertFalse(self.game.equip(self.a, sword, hidden))
        self.assertIs(choose_equip_target(self.game, self.a, sword), legal)
        self.assertTrue(self.game.equip(self.a, sword, legal))
        legal.temp_kw.add('shroud')
        self.assertIs(sword.attached_to, legal)
        self.assertEqual(legal.power, 3)

    def test_equipment_grants_shroud_without_detaching_itself(self):
        a = self.creature()
        c = card('Shroud cloak', types='Artifact — Equipment', text='Equipped creature has shroud.\nEquip {0}')
        self.assertFalse(c.unsupported)
        cloak = self.game.enter_battlefield(self.a, c)
        self.assertTrue(self.game.equip(self.a, cloak, a))
        self.assertFalse(self.game.targetable(a, self.a))
        self.assertIs(cloak.attached_to, a)
        self.game.leave_battlefield(cloak, 'graveyard')
        self.assertTrue(self.game.targetable(a, self.a))
