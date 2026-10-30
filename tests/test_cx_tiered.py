"""Tiered spells and the Ring-bearer conditions."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from mtgsim.turn_conditions import check, parse

from tests.test_templates import BEAR, ISLAND, card

FIRE = card("Test Fire Magic", "{R}", "Sorcery", "Tiered (Choose one additional cost.)\n"
            "• Fire — {0} — Test Fire Magic deals 1 damage to each creature.\n"
            "• Fira — {2} — Test Fire Magic deals 2 damage to each creature.\n"
            "• Firaga — {5} — Test Fire Magic deals 3 damage to each creature.")


class Tiered(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_one_mode_per_cast(self):
        self.assertEqual(FIRE.unsupported, [])
        self.a.hand = [FIRE]
        options = self.game._hand_options(self.a, FIRE)
        self.assertEqual(sorted(sum(o.origin[2].cost.values()) for o in options), [1, 3, 6])

    def test_ring_conditions(self):
        self.assertEqual(parse("you don't control a Ring-bearer"), "no_ring_bearer")
        self.assertEqual(parse("you chose a creature other than ~ as your Ring-bearer"), "ring_other")
        bear = Permanent(BEAR, self.a)
        self.a.battlefield.append(bear)
        self.assertTrue(check(self.game, self.a, "no_ring_bearer", None))
        self.a.ring_bearer = bear
        self.assertFalse(check(self.game, self.a, "no_ring_bearer", None))
        self.assertTrue(check(self.game, self.a, "ring_other", None))


SQUIRE = card("Test Squire", "{2}", "Artifact Creature — Construct", "{T}: Attach target Equipment you control to "
              "target creature you control.", 1, 1)
SWORD = card("Test Sword", "{2}", "Artifact — Equipment", "Equipped creature gets +2/+2.\nEquip {2}")


class AttachEquipment(unittest.TestCase):
    def test_moves_equipment_to_the_target(self):
        self.assertEqual(SQUIRE.unsupported, [])
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        sword, bear, other = (Permanent(c, a) for c in (SWORD, BEAR, BEAR))
        a.battlefield += [sword, bear, other]
        sword.attached_to = other
        from mtgsim.engine import StackItem
        game.stack.append(StackItem(a, list(SQUIRE.activated[0].effects), [bear], name="squire", kind="ability"))
        game.resolve_top()
        self.assertIs(sword.attached_to, bear)


STIFLE = card("Test Stifle", "{U}", "Instant", "Counter target activated or triggered ability.")
SQUELCH = card("Test Squelch", "{1}{U}{U}", "Instant", "Counter target activated ability.\nDraw a card.")


class CounterAbilities(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_counters_only_matching_kind(self):
        from mtgsim.engine import StackItem
        self.assertEqual(STIFLE.unsupported + SQUELCH.unsupported, [])
        trig = StackItem(self.b, [], [], name="trigger", kind="trigger")
        act = StackItem(self.b, [], [], name="activated", kind="ability")
        self.game.stack += [act, trig]
        self.game.stack.append(StackItem(self.a, list(SQUELCH.spell_effects), [None, None], card=SQUELCH,
                                         name=SQUELCH.name))
        self.game.resolve_top()
        self.assertEqual([i.name for i in self.game.stack], ["trigger"])
        self.game.stack.append(StackItem(self.a, list(STIFLE.spell_effects), [None], card=STIFLE, name=STIFLE.name))
        self.game.resolve_top()
        self.assertEqual(self.game.stack, [])


if __name__ == "__main__":
    unittest.main()
