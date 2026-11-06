"""Self-referential combat riders: untap and remove from combat, and "you may have it deal N damage"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.kinds.cx_night_combat import remove_from_combat
from tests.test_templates import BEAR, card

DODGER = card("Test Dodger", "{1}{G}", "Creature — Bear", "Whenever Test Dodger becomes blocked, you may untap it and remove it from combat.",
              power="2", toughness="2")
PINGER = card("Test Pinger", "{R}", "Creature — Goblin", "Whenever Test Pinger becomes blocked, you may have it deal 1 damage to any target.",
              power="1", toughness="1")


class CombatRiders(unittest.TestCase):
    def test_parse(self):
        self.assertEqual((DODGER.unsupported, DODGER.triggers[0].event, DODGER.triggers[0].effects[0].kind),
                         ([], "becomes_blocked", "remove_from_combat"))
        self.assertEqual((PINGER.unsupported, PINGER.triggers[0].effects[0].kind, PINGER.triggers[0].effects[0].amount),
                         ([], "damage", 1))

    def test_attacker_is_untapped_and_taken_out_of_combat_but_stays_blocked(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        atk, blk = Permanent(DODGER, a), Permanent(BEAR, b)
        a.battlefield.append(atk)
        b.battlefield.append(blk)
        atk.tapped = True
        game.attackers, game.blocks, game.attack_targets = [atk], {atk: [blk]}, {atk: b}
        item = StackItem(card=DODGER, controller=a, effects=[], targets=[], source=atk)
        remove_from_combat(game, a, item=item)
        self.assertFalse(atk.tapped)
        self.assertEqual((game.attackers, game.blocks), ([], {atk: []}))

    def test_a_blocker_is_removed_from_its_attackers_blockers(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        atk, blk = Permanent(BEAR, a), Permanent(DODGER, b)
        a.battlefield.append(atk)
        b.battlefield.append(blk)
        game.attackers, game.blocks, game.attack_targets = [atk], {atk: [blk]}, {atk: b}
        remove_from_combat(game, b, item=StackItem(card=DODGER, controller=b, effects=[], targets=[], source=blk))
        self.assertEqual(game.blocks, {atk: []})
        self.assertEqual(game.attackers, [atk])

    def test_a_watcher_removes_the_blocked_creature_not_itself(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        watcher, atk, blk = Permanent(BEAR, a), Permanent(BEAR, a), Permanent(BEAR, b)
        a.battlefield.extend([watcher, atk])
        b.battlefield.append(blk)
        watcher.tapped = atk.tapped = True
        game.attackers, game.blocks, game.attack_targets = [atk], {atk: [blk]}, {atk: b}
        remove_from_combat(game, a, item=StackItem(card=BEAR, controller=a, effects=[], targets=[],
                                                   source=watcher, context=atk))
        self.assertEqual((atk.tapped, watcher.tapped, game.attackers), (False, True, []))

    def test_nivea_parses_its_blocked_creature_trigger(self):
        from mtgsim.carddb import CardDB
        nivea = CardDB().get("Nivea, Beloved Battlemage")
        self.assertEqual([t.effects[0].kind for t in nivea.triggers], ["remove_from_combat"])


if __name__ == "__main__":
    unittest.main()
