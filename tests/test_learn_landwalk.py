"""Learn's three options, per-game outside pools, and landwalk based on supertypes."""
import random
import io
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, can_block, is_basic_land
from mtgsim.runner import run_match, MatchResult
from mtgsim.sideboard import Plan, run_bo3
from tests.test_templates import BEAR, ISLAND, card

LESSON=card('Fixture Lesson','{1}','Sorcery — Lesson','Draw a card.')


class LearnLandwalk(unittest.TestCase):
    def setUp(self):
        self.a,self.b=Player('a',[],HeuristicAI()),Player('b',[],HeuristicAI())
        self.game=Game(self.a,self.b,random.Random(0))
        self.game.turn,self.game.step=2,'main1'
        self.a.library,self.b.library=[ISLAND]*20,[ISLAND]*20

    def learn(self):
        c=card('Fixture learn',types='Sorcery',text='Learn.')
        self.assertFalse(c.unsupported)
        self.a.hand.append(c)
        self.assertTrue(self.game.cast(self.a,c))
        self.game.settle()

    def test_lesson_revealed_and_put_into_hand_from_sideboard(self):
        self.a.sideboard=[LESSON,BEAR]
        self.learn()
        self.assertEqual(self.a.hand,[LESSON])
        self.assertEqual(self.a.sideboard,[BEAR])
        self.assertEqual(len(self.a.library),20)

    def test_discard_then_draw_alternative_fires_discard_triggers(self):
        self.a.hand=[BEAR]
        with patch.object(self.a.ai,'choose_learn',create=True,return_value=('discard',BEAR)):
            self.learn()
        self.assertEqual(self.a.hand,[ISLAND])
        self.assertIn(BEAR,self.a.graveyard)
        self.assertEqual(self.a.discarded_cards,[BEAR])

    def test_may_decline_both_options(self):
        self.a.hand=[BEAR]
        self.a.sideboard=[LESSON]
        with patch.object(self.a.ai,'choose_learn',create=True,return_value=None):
            self.learn()
        self.assertEqual(self.a.hand,[BEAR])
        self.assertEqual(self.a.sideboard,[LESSON])

    def test_cannot_draw_without_discarding(self):
        with patch.object(self.a.ai,'choose_learn',create=True,return_value=('discard',BEAR)):
            self.learn()
        self.assertEqual(self.a.hand,[])
        self.assertEqual(len(self.a.library),20)

    def test_lesson_does_not_come_from_exile_or_opponents_sideboard(self):
        self.a.exile=[LESSON]
        self.b.sideboard=[LESSON]
        with patch.object(self.a.ai,'choose_learn',create=True,return_value=('lesson',LESSON)):
            self.learn()
        self.assertEqual(self.a.hand,[])
        self.assertEqual(self.a.exile,[LESSON])

    def test_nonlesson_outside_card_is_rejected(self):
        self.a.sideboard=[BEAR]
        with patch.object(self.a.ai,'choose_learn',create=True,return_value=('lesson',BEAR)):
            self.learn()
        self.assertEqual(self.a.hand,[])
        self.assertEqual(self.a.sideboard,[BEAR])

    def test_repeated_learn_consumes_each_sideboard_copy_once(self):
        self.a.sideboard=[LESSON,LESSON]
        self.learn()
        self.learn()
        self.assertEqual(self.a.hand,[LESSON,LESSON])
        self.assertEqual(self.a.sideboard,[])

    def test_learn_on_etb_trigger(self):
        self.a.sideboard=[LESSON]
        c=card('Student',types='Creature',text='When this creature enters, learn.',power=1,toughness=1)
        self.assertFalse(c.unsupported)
        self.game.enter_battlefield(self.a,c)
        self.game.settle()
        self.assertEqual(self.a.hand,[LESSON])

    def test_discarding_last_card_and_drawing_empty_library_loses(self):
        self.a.hand=[BEAR]
        self.a.library=[]
        with patch.object(self.a.ai,'choose_learn',create=True,return_value=('discard',BEAR)):
            self.learn()
        self.assertTrue(self.a.lost)
        self.assertIn(BEAR,self.a.graveyard)

    def test_player_copies_sideboard_instead_of_mutating_callers_list(self):
        pool=[LESSON]
        p=Player('pool',[],HeuristicAI(),sideboard=pool)
        p.sideboard.pop()
        self.assertEqual(pool,[LESSON])

    def test_runner_resets_outside_pools_for_every_game(self):
        seen=[]
        def play(game):
            for p in game.players:
                if p.name=='a':
                    seen.append(list(p.sideboard))
                    p.sideboard.pop()
            return game.players[0]
        pool=[LESSON]
        with patch('mtgsim.runner.Game.play',play):
            run_match('a',[ISLAND],'b',[ISLAND],games=2,sideboard_a=pool)
        self.assertEqual(seen,[[LESSON],[LESSON]])
        self.assertEqual(pool,[LESSON])

    def test_bo3_outside_pool_changes_after_sideboarding(self):
        lookup={BEAR.name:BEAR,LESSON.name:LESSON}
        db=SimpleNamespace(ensure=lambda names:None,get=lambda name:lookup[name])
        pa=Plan('test',ins={LESSON.name:1},outs={BEAR.name:1},deck={LESSON.name:1})
        pb=Plan('test',deck={BEAR.name:1})
        seen=[]
        def play(game):
            a=next(p for p in game.players if p.name=='a')
            seen.append(([c.name for c in a.deck],[c.name for c in a.sideboard]))
            return a
        with patch('mtgsim.sideboard.plan_sideboard',side_effect=[pa,pb]),patch('mtgsim.sideboard.Game.play',play):
            run_bo3('a',{BEAR.name:1},{LESSON.name:1},'b',{BEAR.name:1},{},db,matches=1)
        self.assertEqual(seen,[([BEAR.name],[LESSON.name]),([LESSON.name],[BEAR.name])])

    def test_ai_values_a_learn_spell_when_lesson_is_available(self):
        c=card('Study',types='Sorcery',text='Learn.')
        self.a.sideboard=[LESSON]
        plan=self.a.ai.plan_spell(self.game,self.a,c)
        self.assertIsNotNone(plan)
        self.assertGreater(plan[0],0)

    def test_cli_passes_lesson_sideboard_to_single_game_runner(self):
        from mtgsim.__main__ import main
        student=card('Student',types='Sorcery',text='Learn.')
        lookup={student.name:student,BEAR.name:BEAR,LESSON.name:LESSON}
        db=SimpleNamespace(ensure=lambda names:None,get=lambda name:lookup[name])
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a.txt',Path(tmp)/'b.txt'
            a.write_text('1 Student\nSideboard\n1 Fixture Lesson\n')
            b.write_text('1 Grizzly Bears\n')
            with patch('mtgsim.__main__.CardDB',return_value=db), \
                 patch('mtgsim.__main__.run_match',return_value=(MatchResult('a','b'),[])) as play, \
                 redirect_stdout(io.StringIO()):
                main([str(a),str(b),'-n','1','--offline'])
            self.assertEqual(play.call_args.kwargs['sideboard_a'],[LESSON])

    def walker(self,keyword):
        c=card('Walker',types='Creature',text=keyword,power=2,toughness=2)
        self.assertFalse(c.unsupported)
        a=self.game.enter_battlefield(self.a,c)
        b=self.game.enter_battlefield(self.b,BEAR)
        return a,b

    def test_nonbasic_landwalk_distinguishes_basic_supertype_and_dual(self):
        a,b=self.walker('Nonbasic landwalk')
        basic=self.game.enter_battlefield(self.b,card('New Basic',types='Basic Land — Forest'))
        self.assertTrue(is_basic_land(basic.card))
        self.assertTrue(can_block(b,a))
        dual=self.game.enter_battlefield(self.b,card('Dual',types='Snow Land — Island Forest'))
        self.assertFalse(is_basic_land(dual.card))
        self.assertFalse(can_block(b,a))
        self.game.destroy(dual)
        self.assertTrue(can_block(b,a))

    def test_nonbasic_landwalk_does_not_use_attackers_lands(self):
        a,b=self.walker('Nonbasic landwalk')
        self.game.enter_battlefield(self.a,card('Dual',types='Land — Island Forest'))
        self.assertTrue(can_block(b,a))

    def test_legendary_landwalk_requires_defending_legendary_land(self):
        a,b=self.walker('Legendary landwalk')
        self.game.enter_battlefield(self.b,card('Legend',types='Legendary Artifact'))
        self.game.enter_battlefield(self.b,card('Normal',types='Land'))
        self.assertTrue(can_block(b,a))
        land=self.game.enter_battlefield(self.b,card('Famous',types='Legendary Land'))
        self.assertFalse(can_block(b,a))
        self.game.leave_battlefield(land,'hand')
        self.assertTrue(can_block(b,a))

    def test_nonbasic_name_alone_does_not_change_supertypes(self):
        self.assertFalse(is_basic_land(card('Snow-Covered Dual',types='Snow Land — Forest Island')))
        self.assertFalse(card('Legendary in name',types='Land').legendary)
        self.assertTrue(card('Actual',types='Legendary Land').legendary)
