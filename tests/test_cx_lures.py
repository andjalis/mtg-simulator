"""Blocking requirements and limits: "all creatures able to block ... do so", "blocks ~ if able", "can't block"."""
import random
import unittest

from mtgsim.cx_lures import extra_blocks, is_lure, max_blockers
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem, can_block
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")

SCENT = card("Test Scent", "{1}{G}", "Instant", "All creatures able to block target creature this turn do so.")
ELEPHANT = card("Test Elephant", "{3}{W}", "Creature — Elephant",
                "{G}: Target creature blocks ~ this turn if able.", 2, 2)
PATHFINDER = card("Test Pathfinder", "{5}", "Creature — Eldrazi",
                  "{C}: Target creature can't block ~ this turn.", 5, 5)
BEDLAM = card("Test Bedlam", "{2}{R}{R}", "Enchantment", "Creatures can't block.")
SANDS = card("Test Sands", "{1}{W}", "Enchantment",
             "Creatures you control have vigilance.\nEach creature you control can block an additional creature each combat.")
LURE = card("Test Lure", "{1}{G}{G}", "Enchantment — Aura",
            "Enchant creature\nAll creatures able to block enchanted creature do so.")
SCREEN = card("Test Screen", "{2}", "Artifact Creature — Wall", "Defender\n~ blocks each combat if able.", 2, 1)
TROLL = card("Test Troll", "{4}{G}", "Creature — Troll",
             "Each creature you control with power 4 or greater can't be blocked by more than one creature.", 6, 5)
AWE = card("Test Awe", "{3}{R}", "Sorcery", "Monocolored creatures can't block this turn.")


class Lures(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parse(self):
        for c in (SCENT, ELEPHANT, PATHFINDER, BEDLAM, SANDS, LURE, SCREEN, TROLL, AWE):
            self.assertEqual(c.unsupported, [], c.name)

    def test_lure_spell(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        blockers = [self.game.enter_battlefield(self.b, BEAR) for _ in range(2)]
        self.game.resolve(self.a, SCENT.spell_effects[0], bear)
        self.assertTrue(is_lure(bear))
        blocks = self.game.force_blocks(self.b, [bear], {})
        self.assertEqual(sorted(map(id, blocks[bear])), sorted(map(id, blockers)))

    def test_lure_aura(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        aura = self.game.enter_battlefield(self.a, LURE)
        aura.aura_host = bear
        bear.auras.append(aura)
        self.assertTrue(is_lure(bear))

    def test_blocks_source_if_able(self):
        elephant = self.game.enter_battlefield(self.a, ELEPHANT)
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.enter_battlefield(self.a, FOREST)
        self.assertTrue(self.game.activate_ability(self.a, elephant, 0, [bear]))
        self.game.settle()
        blocks = self.game.force_blocks(self.b, [elephant], {})
        self.assertEqual(blocks.get(elephant), [bear])

    def test_cant_block_source(self):
        path = self.game.enter_battlefield(self.a, PATHFINDER)
        other = self.game.enter_battlefield(self.a, BEAR)
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.resolve(self.a, PATHFINDER.activated[0].effects[0], bear,
                          item=StackItem(self.a, [], [], source=path))
        self.assertFalse(can_block(bear, path))
        self.assertTrue(can_block(bear, other))
        self.game.turn += 1
        self.assertTrue(can_block(bear, path))

    def test_static_limits(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, BEAR)
        self.game.enter_battlefield(self.b, SANDS)
        self.assertEqual(extra_blocks(theirs), 1)
        self.assertEqual(extra_blocks(bear), 0)
        troll = self.game.enter_battlefield(self.a, TROLL)
        self.assertEqual(max_blockers(troll), 1)
        self.assertFalse(max_blockers(bear))
        self.assertTrue(self.game.enter_battlefield(self.b, SCREEN).has("must_block_now"))
        self.game.enter_battlefield(self.a, BEDLAM)
        self.assertFalse(can_block(theirs, bear))

    def test_mass_cant_block(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        theirs = self.game.enter_battlefield(self.b, BEAR)
        self.game.resolve(self.a, AWE.spell_effects[0], None)
        self.assertFalse(can_block(theirs, bear))


if __name__ == "__main__":
    unittest.main()
