"""Symmetric shadow restrictions, shared-color intimidation, and remaining basic landwalk."""
import random
import unittest
from mtgsim.ai import HeuristicAI, search_blocks
from mtgsim.engine import Game, Player, can_block
from tests.test_templates import ISLAND, card


class ShadowIntimidateLandwalk(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], HeuristicAI()), Player('b', [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn = 2
        self.a.library, self.b.library = [ISLAND]*20, [ISLAND]*20

    def creature(self, who=None, text='', cost='', types='Creature'):
        c=card('Fixture', cost, types, text, 2, 2)
        self.assertFalse(c.unsupported)
        p=self.game.enter_battlefield(who or self.a,c)
        p.sick=False
        return p

    def test_shadow_restricts_both_attackers_and_blockers(self):
        for attack,block,legal in [('', '',True),('Shadow','',False),('','Shadow',False),('Shadow','Shadow',True)]:
            with self.subTest(attack=attack,block=block):
                a,b=self.creature(text=attack),self.creature(self.b,block)
                self.assertEqual(can_block(b,a),legal)

    def test_shadow_does_not_override_flying_or_reach(self):
        a=self.creature(text='Shadow, flying')
        b=self.creature(self.b,'Shadow')
        self.assertFalse(can_block(b,a))
        b.temp_kw.add('reach')
        self.assertTrue(can_block(b,a))
        b.card=card('Reach only',types='Creature',text='Reach',power=2,toughness=2)
        self.assertFalse(can_block(b,a))

    def test_shadow_keyword_changes_update_blocking(self):
        a,b=self.creature(),self.creature(self.b)
        a.temp_kw.add('shadow')
        self.assertFalse(can_block(b,a))
        b.temp_kw.add('shadow')
        self.assertTrue(can_block(b,a))
        b.tapped=True
        self.assertFalse(can_block(b,a))

    def test_shadow_ai_and_combat(self):
        a,b=self.creature(text='Shadow'),self.creature(self.b)
        self.assertEqual(search_blocks([a],[b],self.a,self.b),{})
        self.game.combat(self.a,self.b)
        self.assertEqual(self.b.life,18)

    def test_intimidate_shares_any_actual_color(self):
        a=self.creature(text='Intimidate',cost='{R}{G}')
        for cost,legal in [('{R}',True),('{G}{W}',True),('{B}',False),('',False)]:
            with self.subTest(cost=cost):
                self.assertEqual(can_block(self.creature(self.b,cost=cost),a),legal)

    def test_intimidate_allows_artifact_creatures_of_any_color(self):
        a=self.creature(text='Intimidate',cost='{G}')
        b=self.creature(self.b,cost='{B}',types='Artifact Creature')
        self.assertTrue(can_block(b,a))

    def test_colorless_intimidate_requires_artifact_blocker(self):
        a=self.creature(text='Intimidate, devoid',cost='{B}')
        b=self.creature(self.b,text='Devoid',cost='{B}')
        self.assertFalse(can_block(b,a))
        artifact=self.creature(self.b,types='Artifact Creature')
        self.assertTrue(can_block(artifact,a))

    def test_intimidate_does_not_override_flying(self):
        a=self.creature(text='Flying, intimidate',cost='{R}')
        b=self.creature(self.b,cost='{R}')
        self.assertFalse(can_block(b,a))
        b.temp_kw.add('reach')
        self.assertTrue(can_block(b,a))

    def test_fear_and_intimidate_combine(self):
        a=self.creature(text='Fear, intimidate',cost='{W}')
        self.assertFalse(can_block(self.creature(self.b,cost='{W}'),a))
        self.assertFalse(can_block(self.creature(self.b,cost='{B}'),a))
        self.assertTrue(can_block(self.creature(self.b,cost='{W}{B}'),a))

    def test_islandwalk_and_plainswalk_use_opposing_land_subtypes(self):
        for keyword,subtype in [('Islandwalk','Island'),('Plainswalk','Plains')]:
            with self.subTest(keyword=keyword):
                a,b=self.creature(text=keyword),self.creature(self.b)
                land=card('Dual',types='Snow Land — Swamp '+subtype)
                mine=self.game.enter_battlefield(self.a,land)
                self.assertTrue(can_block(b,a))
                theirs=self.game.enter_battlefield(self.b,land)
                self.assertFalse(can_block(b,a))
                self.game.leave_battlefield(theirs,'hand')
                self.assertTrue(can_block(b,a))
                self.game.leave_battlefield(mine,'hand')

    def test_land_name_and_mana_are_not_landwalk_subtypes(self):
        a,b=self.creature(text='Islandwalk, plainswalk'),self.creature(self.b)
        self.game.enter_battlefield(self.b,card('Island Plains',types='Land',text='{T}: Add {U}.'))
        self.assertTrue(can_block(b,a))

    def test_granted_islandwalk(self):
        a,b=self.creature(),self.creature(self.b)
        a.temp_kw.add('islandwalk')
        self.game.enter_battlefield(self.b,ISLAND)
        self.assertFalse(can_block(b,a))

    def test_other_landwalk_and_shadow_exceptions_remain_visible(self):
        self.assertTrue(card('Other',text='Desertwalk').unsupported)
        self.assertTrue(card('Other',text="This creature can block creatures with shadow as though they didn't have shadow.").unsupported)
