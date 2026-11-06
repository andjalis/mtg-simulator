"""One damage sentence in general (cx_abil_damage): selectors, relations to the source, quantities, damage to itself."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.cards.tokens import make_token
from mtgsim.engine.policy import choose_ability
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card


def arena(ai=Scripted):
    a, b = Player("a", [], ai()), Player("b", [], ai())
    game = Game(a, b, random.Random(0), log=True)
    game.turn, game.step = 2, "main2"
    for p in (a, b):
        p.library = [ISLAND] * 10
    return game, a, b


def source(text, power=2, toughness=3, **kw):
    return card("Test Pinger", "{1}", "Creature — Goblin", text, power, toughness, **kw)


FLYER = card("Test Flyer", "{2}", "Creature — Bird", "Flying", 2, 2)
GROUND = card("Test Ground", "{2}", "Creature — Bear", "", 2, 2)
BIG = card("Test Big Flyer", "{4}", "Creature — Dragon", "Flying", 4, 4)


class Parse(unittest.TestCase):
    def test_wordings(self):
        for text in ("{T}: ~ deals 1 damage to target creature with flying.",
                     "{T}: ~ deals 2 damage to target attacking creature without flying.",
                     "{T}: ~ deals 1 damage to target red creature.",
                     "{T}: ~ deals 1 damage to target creature that was dealt damage this turn.",
                     "{T}: ~ deals 2 damage to target creature blocking it.",
                     "{T}: ~ deals 2 damage to target creature it's blocking.",
                     "{T}: ~ deals 2 damage to another target creature.",
                     "{T}: ~ deals 1 damage to target creature or planeswalker.",
                     "{T}: ~ deals 1 damage to target attacking or blocking creature.",
                     "{1}: ~ deals 3 damage to each creature without flying.",
                     "{1}: ~ deals 2 damage to any target and 2 damage to itself.",
                     "{T}: ~ deals damage equal to its power to target creature with flying.",
                     "{T}: ~ deals damage equal to the number of charge counters on it to any target.",
                     "{X}, {T}: ~ deals X damage to target attacking or blocking creature."):
            with self.subTest(text=text):
                self.assertEqual(source(text).unsupported, [], text)


class Resolve(unittest.TestCase):
    def test_flying_only(self):
        game, a, b = arena()
        pinger = game.enter_battlefield(a, source("{T}: ~ deals 2 damage to target creature with flying."))
        pinger.sick = False
        ground, flyer = game.enter_battlefield(b, GROUND), game.enter_battlefield(b, FLYER)
        with game.targeting(pinger):
            self.assertEqual(game.legal_targets(a, pinger.activated[0].effects[0]), [flyer])
        self.assertTrue(game.activate_ability(a, pinger, 0))
        game.settle()
        self.assertNotIn(flyer, b.battlefield)
        self.assertIn(ground, b.battlefield)

    def test_each_creature_token(self):
        game, a, b = arena()
        pinger = game.enter_battlefield(a, source("{1}: ~ deals 2 damage to each creature token.", 1, 5))
        pinger.sick = False
        game.enter_battlefield(a, ISLAND).sick = False
        token, real = game.enter_battlefield(b, make_token("Goblin", 1, 1)), game.enter_battlefield(b, GROUND)
        self.assertTrue(game.activate_ability(a, pinger, 0))
        game.settle()
        self.assertNotIn(token, b.battlefield)
        self.assertIn(real, b.battlefield)

    def test_damage_to_itself(self):
        game, a, b = arena()
        pinger = game.enter_battlefield(a, source("{1}: ~ deals 2 damage to any target and 2 damage to itself."))
        game.enter_battlefield(a, ISLAND).sick = False
        self.assertTrue(game.activate_ability(a, pinger, 0))
        game.settle()
        self.assertEqual((b.life, pinger.damage), (18, 2))

    def test_relation_to_the_source(self):
        game, a, b = arena()
        pinger = game.enter_battlefield(a, source("{T}: ~ deals 2 damage to target creature blocking it."))
        pinger.sick = False
        blocker = game.enter_battlefield(b, GROUND)
        game.enter_battlefield(b, GROUND)                      # not blocking: not a legal target
        game.attackers = [pinger]
        game.blocks = {pinger: [blocker]}
        with game.targeting(pinger):
            self.assertEqual(game.legal_targets(a, pinger.activated[0].effects[0]), [blocker])
            game.blocks = {}
            self.assertEqual(game.legal_targets(a, pinger.activated[0].effects[0]), [])

    def test_quantity_is_its_power(self):
        game, a, b = arena()
        pinger = game.enter_battlefield(a, source("{T}: ~ deals damage equal to its power to target creature with flying.",
                                                  4, 4))
        pinger.sick = False
        flyer = game.enter_battlefield(b, BIG)
        self.assertTrue(game.activate_ability(a, pinger, 0))
        game.settle()
        self.assertNotIn(flyer, b.battlefield)

    def test_dealt_damage_this_turn(self):
        game, a, b = arena()
        pinger = game.enter_battlefield(a, source("{T}: ~ deals 2 damage to target creature that was dealt damage this turn."))
        pinger.sick = False
        hurt = game.enter_battlefield(b, GROUND)
        game.enter_battlefield(b, GROUND)                      # undamaged: not a legal target
        hurt.damage = 1
        with game.targeting(pinger):
            self.assertEqual(game.legal_targets(a, pinger.activated[0].effects[0]), [hurt])


class AI(unittest.TestCase):
    """HeuristicAI activates these and aims them at the opponent's creatures, not its own."""

    def test_aims_at_the_opponents_flyer(self):
        game, a, b = arena(HeuristicAI)
        pinger = game.enter_battlefield(a, source("{T}: ~ deals 2 damage to target creature with flying."))
        pinger.sick = False
        mine, theirs = game.enter_battlefield(a, FLYER), game.enter_battlefield(b, FLYER)
        ability = choose_ability(game, a, instant=False)
        self.assertIsNotNone(ability)
        self.assertTrue(game.do_action(a, ability))
        game.settle()
        self.assertNotIn(theirs, b.battlefield)
        self.assertIn(mine, a.battlefield)

    def test_sweep_only_when_it_hits_their_side(self):
        game, a, b = arena(HeuristicAI)
        pinger = game.enter_battlefield(a, source("{1}: ~ deals 2 damage to each creature token.", 1, 5))
        pinger.sick = False
        game.enter_battlefield(a, ISLAND).sick = False
        game.enter_battlefield(a, make_token("Goblin", 1, 1))            # its own token would die too
        self.assertIsNone(choose_ability(game, a, instant=False))        # nothing of theirs is hit
        game.enter_battlefield(b, make_token("Goblin", 1, 1))
        game.enter_battlefield(b, make_token("Goblin", 1, 1))
        ability = choose_ability(game, a, instant=False)
        self.assertIsNotNone(ability)
        self.assertTrue(game.do_action(a, ability))
        game.settle()
        self.assertEqual(len(b.creatures), 0)

    def test_power_damage_is_aimed_at_what_it_kills(self):
        game, a, b = arena(HeuristicAI)
        pinger = game.enter_battlefield(a, source("{T}: ~ deals damage equal to its power to target creature with flying.",
                                                  4, 4))
        pinger.sick = False
        game.enter_battlefield(b, FLYER)
        big = game.enter_battlefield(b, BIG)
        ability = choose_ability(game, a, instant=False)
        self.assertIsNotNone(ability)
        self.assertTrue(game.do_action(a, ability))
        game.settle()
        self.assertNotIn(big, b.battlefield)

if __name__ == "__main__":
    unittest.main()
