"""Regeneration replaces destruction, rather than death, and removes the creature from combat."""
import random
import unittest
from unittest.mock import patch
from mtgsim.ai import HeuristicAI, fight_group
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player, ability_worth
from tests.test_templates import ISLAND, card


class Regeneration(unittest.TestCase):
    def setUp(self):
        self.a,self.b=Player('a',[],HeuristicAI()),Player('b',[],HeuristicAI())
        self.game=Game(self.a,self.b,random.Random(0),log=True)
        self.game.turn,self.game.step=2,'main1'
        self.a.library,self.b.library=[ISLAND]*30,[ISLAND]*30

    def creature(self,text='',who=None,p=2,t=2):
        c=card('Fixture',types='Creature',text=text,power=p,toughness=t)
        self.assertFalse(c.unsupported)
        return self.game.enter_battlefield(who or self.a,c)

    def spell(self,text,targets=(),who=None):
        p=who or self.a
        c=card('Fixture spell',types='Instant',text=text)
        self.assertFalse(c.unsupported)
        p.hand.append(c)
        self.assertTrue(self.game.cast(p,c,list(targets)))
        self.game.settle()
        return c

    def shield(self,a,n=1):
        self.game.resolve(a.controller,Effect('regenerate',n,target='creature'),a)

    def test_one_shield_consumed_per_destruction(self):
        a=self.creature()
        self.shield(a,2)
        self.game.destroy(a)
        self.assertIn(a,self.a.battlefield)
        self.assertTrue(a.tapped)
        self.assertEqual(a.regeneration_shields,1)
        self.game.destroy(a)
        self.game.destroy(a)
        self.assertNotIn(a,self.a.battlefield)

    def test_lethal_damage_and_deathtouch_are_cleared(self):
        a=self.creature()
        self.shield(a)
        a.damage=1
        a.deathtouched=True
        self.game.state_based_actions()
        self.assertIn(a,self.a.battlefield)
        self.assertEqual((a.damage,a.deathtouched,a.regeneration_shields),(0,False,0))

    def test_sacrifice_zero_toughness_and_zero_loyalty_ignore_shield(self):
        a=self.creature()
        self.shield(a)
        self.game.sacrifice(a)
        self.assertNotIn(a,self.a.battlefield)
        b=self.creature()
        self.shield(b)
        b.counters['-1/-1']=2
        self.game.state_based_actions()
        self.assertNotIn(b,self.a.battlefield)

    def test_indestructible_does_not_consume_shield(self):
        a=self.creature('Indestructible')
        self.shield(a)
        self.game.destroy(a,no_regen=True)
        self.assertIn(a,self.a.battlefield)
        self.assertEqual(a.regeneration_shields,1)

    def test_shield_prevents_dying_even_with_finality(self):
        a=self.creature()
        a.counters['finality']=1
        self.shield(a)
        self.game.destroy(a)
        self.assertIn(a,self.a.battlefield)
        self.assertEqual(self.a.exile,[])

    def test_regeneration_does_not_fire_death_or_entry_triggers(self):
        a=self.creature('When this creature enters, draw a card.\nWhen this creature dies, draw a card.')
        self.game.settle()
        self.shield(a)
        self.game.destroy(a)
        self.game.settle()
        self.assertEqual(len(self.a.hand),1)

    def test_destroy_cant_be_regenerated_rider(self):
        a=self.creature()
        self.shield(a)
        self.spell("Destroy target creature. It can't be regenerated.",[a],self.b)
        self.assertNotIn(a,self.a.battlefield)

    def test_wrath_cant_be_regenerated_rider(self):
        a=self.creature()
        self.shield(a)
        self.spell("Destroy all creatures. They can't be regenerated.",who=self.b)
        self.assertNotIn(a,self.a.battlefield)

    def test_damage_rider_blocks_regeneration_for_turn(self):
        a=self.creature(t=4)
        self.shield(a)
        self.spell("Fixture spell deals 1 damage to any target. A creature dealt damage this way can't be regenerated this turn.",[a],self.b)
        self.assertTrue(a.regeneration_blocked)
        self.game.destroy(a)
        self.assertNotIn(a,self.a.battlefield)

    def test_unknown_rider_base_not_hidden(self):
        c=card('Unknown',types='Instant',text="Dance with target creature. It can't be regenerated.")
        self.assertTrue(c.unsupported)

    def test_regeneration_removes_attacker_and_blocker_from_combat(self):
        a,b=self.creature(),self.creature(who=self.b)
        self.game.attackers=[a]
        self.game.attack_targets={a:self.b}
        self.game.blocks={a:[b]}
        self.shield(b)
        self.game.destroy(b)
        self.assertEqual(self.game.blocks[a],[])
        self.shield(a)
        self.game.destroy(a)
        self.assertEqual(self.game.attackers,[])
        self.assertEqual(self.game.blocks,{})

    def test_first_strike_regeneration_matches_ai(self):
        a=self.creature('First strike',p=3,t=3)
        b=self.creature(who=self.b)
        self.shield(b)
        self.assertEqual(fight_group(a,[b])[0],set())
        self.game.attackers=[a]
        blocks={a:[b]}
        self.game.blocks=blocks
        self.game.combat_damage(self.a,self.b,[a],blocks,lambda c:c.has('first strike'))
        self.game.combat_damage(self.a,self.b,[a],blocks,lambda c:not c.has('first strike'))
        self.assertEqual(a.damage,0)
        self.assertIn(b,self.b.battlefield)
        self.assertEqual(b.damage,0)

    def test_cleanup_expires_shields_and_regeneration_prohibition(self):
        a=self.creature()
        a.regeneration_blocked=True
        self.shield(a)
        with patch.object(self.game,'main_phase'),patch.object(self.game,'combat'):
            self.game.take_turn(self.a)
        self.assertEqual((a.regeneration_shields,a.regeneration_blocked),(0,False))

    def test_ai_activates_self_regeneration_in_response(self):
        a=self.creature('{1}: Regenerate this creature.')
        self.game.enter_battlefield(self.a,ISLAND)
        self.spell('Destroy target creature.',[a],self.b)
        self.assertIn(a,self.a.battlefield)
        self.assertTrue(a.tapped)
        self.assertEqual(a.regeneration_shields,0)

    def test_ai_does_not_spend_against_regeneration_prevention(self):
        a=self.creature('{1}: Regenerate this creature.')
        land=self.game.enter_battlefield(self.a,ISLAND)
        self.spell("Destroy target creature. It can't be regenerated.",[a],self.b)
        self.assertNotIn(a,self.a.battlefield)
        self.assertFalse(land.tapped)

    def test_regeneration_spell_targets_and_shroud(self):
        a=self.creature('Shroud')
        c=card('Regrowth shield',types='Instant',text='Regenerate target creature.')
        self.assertNotIn(a,self.game.legal_targets(self.a,c.spell_effects[0]))
        self.shield(a)
        self.game.destroy(a)
        self.assertIn(a,self.a.battlefield)

    def test_ai_regenerates_intended_target_with_artifact_ability(self):
        weak=self.creature(p=1,t=1)
        strong=self.creature(p=4,t=4)
        item=card('Healer',types='Artifact',text='{1}: Regenerate target creature.')
        self.assertFalse(item.unsupported)
        self.game.enter_battlefield(self.a,item)
        self.game.enter_battlefield(self.a,ISLAND)
        self.spell('Destroy target creature.',[weak],self.b)
        self.assertIn(weak,self.a.battlefield)
        self.assertEqual(strong.regeneration_shields,0)

    def test_regenerate_all_friendly_creatures(self):
        a,b=self.creature(),self.creature()
        self.spell('Regenerate each creature you control.')
        self.game.destroy(a)
        self.game.destroy(b)
        self.assertEqual(len(self.a.creatures),2)

    def test_pure_regeneration_ability_is_not_used_without_threat(self):
        a=self.creature('{1}: Regenerate this creature.')
        land=self.game.enter_battlefield(self.a,ISLAND)
        self.assertFalse(ability_worth(self.game,self.a,a,0))
        self.game.hook(self.a,'use_abilities')(self.game,self.a)
        self.assertEqual(a.regeneration_shields,0)
        self.assertFalse(land.tapped)
