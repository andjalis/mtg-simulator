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

class Dealer(unittest.TestCase):
    """"It" / "that creature" is the creature an earlier effect targeted (or that triggered the ability), not the card."""

    DEADSHOT = "Tap target creature. It deals damage equal to its power to another target creature."

    def test_parse_marks_the_dealer(self):
        spell = card("Test Deadshot", "{2}{R}", "Sorcery", self.DEADSHOT)
        self.assertEqual(spell.unsupported, [])
        damage = spell.spell_effects[-1]
        self.assertTrue(damage.data.get("src_prev"))
        self.assertTrue(damage.data.get("source_power"))

    def test_deadshot_the_tapped_creature_deals_the_damage(self):
        game, a, b = arena(HeuristicAI)
        game.step = "main1"
        for _ in range(3):
            game.enter_battlefield(a, card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")).sick = False
        spell = card("Test Deadshot", "{2}{R}", "Sorcery", self.DEADSHOT)
        big = game.enter_battlefield(b, card("Test Colossus", "{6}", "Creature — Giant", "", 6, 6))
        small = game.enter_battlefield(b, card("Test Elf", "{1}", "Creature — Elf", "", 1, 2))     # power 1: its own damage can't kill it
        a.hand = [spell]
        a.ai.main_phase(game, a)
        game.settle()
        self.assertTrue(big.tapped)                                      # the first target
        self.assertNotIn(small, b.battlefield)                           # killed by the tapped creature's 6 power
        self.assertEqual(big.damage, 0)                                  # "another target": not itself
        self.assertIn(spell, a.graveyard)

    def test_trigger_subject_deals_the_damage(self):
        game, a, b = arena()
        watcher = card("Test Watcher", "{2}", "Enchantment",
                       "Whenever a creature you control enters, that creature deals damage equal to its power to any target.")
        self.assertEqual(watcher.unsupported, [])
        game.enter_battlefield(a, watcher)
        game.enter_battlefield(a, card("Test Ogre", "{4}", "Creature — Ogre", "", 5, 5))
        game.settle()
        self.assertEqual(b.life, 15)                           # 5 power from the entering creature, not 0 from the card

    def test_real_cards_parse(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Deadshot", "Electropotence", "Halana, Kessig Ranger", "Brokers Charm"):
            with self.subTest(name=name):
                self.assertEqual(db.get(name).unsupported, [])

    def test_gated_trigger_halana(self):
        """Halana: the entering creature (power 4), not Halana (power 3) and not the target, deals the damage."""
        from mtgsim.carddb import CardDB
        game, a, b = arena(HeuristicAI)
        game.enter_battlefield(a, CardDB(offline=True).get("Halana, Kessig Ranger"))
        for _ in range(2):
            game.enter_battlefield(a, ISLAND).sick = False
        victim = game.enter_battlefield(b, card("Test Victim", "{4}", "Creature — Giant", "", 1, 4))
        game.enter_battlefield(a, card("Test Ogre", "{4}", "Creature — Ogre", "", 4, 4))
        game.settle()
        self.assertNotIn(victim, b.battlefield)                # 4 damage from the Ogre; Halana's 3 would not kill it

    def test_it_in_a_trigger_about_the_card_is_the_card(self):
        """Goblin Javelineer: when it becomes blocked, *it* (Javelineer) deals the damage, not the blocker."""
        game, a, b = arena()
        game.step = "declare_blockers"
        jav = game.enter_battlefield(a, card("Test Javelineer", "{1}", "Creature — Goblin",
                                             "Whenever this creature becomes blocked, it deals 1 damage to target creature "
                                             "blocking it.", 1, 3))
        elf = game.enter_battlefield(b, card("Test Elves", "{1}", "Creature — Elf", "", 1, 1))
        self.assertEqual(jav.card.unsupported, [])
        seen = []
        real = game.deal_damage
        game.deal_damage = lambda tgt, amount, **kw: (seen.append((tgt, amount, kw.get("source"))), real(tgt, amount, **kw))[1]
        game.attackers = [jav]
        game.blocks = {jav: [elf]}
        game.fire(a, "becomes_blocked", jav, context=elf)
        game.settle()
        self.assertEqual([(t, n, s) for t, n, s in seen if n == 1], [(elf, 1, jav)])

    def test_mandatory_damage_trigger_targets_even_when_nothing_dies(self):
        """#295: Javelineer blocked by a 1/2 still has to deal its 1 damage to it."""
        game, a, b = arena()
        game.step = "declare_blockers"
        jav = game.enter_battlefield(a, card("Test Javelineer", "{1}", "Creature — Goblin",
                                             "Whenever this creature becomes blocked, it deals 1 damage to target creature "
                                             "blocking it.", 1, 3))
        wall = game.enter_battlefield(b, card("Test Wall", "{1}", "Creature — Wall", "", 1, 2))
        game.attackers = [jav]
        game.blocks = {jav: [wall]}
        game.fire(a, "becomes_blocked", jav, context=wall)
        game.settle()
        self.assertEqual(wall.damage, 1)


if __name__ == "__main__":
    unittest.main()
