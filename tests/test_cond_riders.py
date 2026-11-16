"""#628: "If C, those creatures [also] ..." after a group or counted targets, in the same paragraph or on its own
ability-word line (mtgsim.cx_group_refs.cond_rider / spell_line_rider)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Break of Day", "Zealous Display", "Kytheon's Tactics", "Icy Blast", "When We Were Young", "Send to Sleep")
TACTICS = card("Test Tactics", "{1}{W}", "Sorcery", "Creatures you control get +2/+1 until end of turn.\nSpell mastery — "
               "If there are two or more instant and/or sorcery cards in your graveyard, those creatures also gain "
               "vigilance until end of turn.")
SLEEP = card("Test Sleep", "{1}{U}", "Instant", "Tap up to two target creatures.\nSpell mastery — If there are two or "
             "more instant and/or sorcery cards in your graveyard, those creatures don't untap during their "
             "controllers' next untap steps.")
BOLT = card("Bolt", "{R}", "Instant", "Bolt deals 3 damage to any target.")


class Parse(unittest.TestCase):
    def test_group_rider_is_a_separate_conditional_group(self):
        self.assertEqual(TACTICS.unsupported, [])
        kinds = [(e.kind, bool(e.cond)) for e in TACTICS.spell_effects]
        self.assertEqual(kinds, [("pump_all", False), ("permanent_group", True)])

    def test_counted_rider_copies_carry_the_condition(self):
        self.assertEqual(SLEEP.unsupported, [])
        self.assertEqual([(e.kind, bool(e.cond)) for e in SLEEP.spell_effects],
                         [("tap", False), ("skip_untap", True)] * 2)

    def test_refusals(self):
        for text in (
            # a condition the parser can't read
            "Creatures you control get +1/+1 until end of turn.\nIf the moon is full, those creatures gain flying "
            "until end of turn.",
            # a group of a target player's creatures: a second group would need that target
            "Creatures target player controls get +1/+1 until end of turn.\nIf you control a Forest, those creatures "
            "gain trample until end of turn.",
            # nothing before it
            "If you control a Forest, those creatures gain trample until end of turn.",
            # a rider that still talks about "their" own things
            "Creatures you control get +1/+1 until end of turn.\nIf you control a Forest, those creatures gain "
            "trample until end of turn and their controllers draw a card.",
        ):
            self.assertTrue(card("Test Odd", "{G}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def creature(self, owner):
        x = self.g.enter_battlefield(owner, card("Bear", "{1}", "Creature — Bear", "", 2, 2))
        x.sick = False
        return x

    def resolve(self, c, targets=None):
        effects = list(c.spell_effects)
        self.g.stack.append(StackItem(self.a, effects, targets or [None] * len(effects), card=c, name=c.name))
        self.g.resolve_top()

    def test_tactics_without_spell_mastery(self):
        x = self.creature(self.a)
        self.resolve(TACTICS)
        self.assertEqual(x.power, 4)
        self.assertFalse(x.has("vigilance"))

    def test_tactics_with_spell_mastery(self):
        x = self.creature(self.a)
        self.a.graveyard = [BOLT, BOLT]
        self.resolve(TACTICS)
        self.assertEqual(x.power, 4)
        self.assertTrue(x.has("vigilance"))

    def test_sleep_locks_only_with_spell_mastery(self):
        x, y = self.creature(self.b), self.creature(self.b)
        self.resolve(SLEEP, [x, None, y, None])
        self.assertTrue(x.tapped and y.tapped)
        self.assertEqual((x.skip_untap, y.skip_untap), (0, 0))
        x2, y2 = self.creature(self.b), self.creature(self.b)
        self.a.graveyard = [BOLT, BOLT]
        self.resolve(SLEEP, [x2, None, y2, None])
        self.assertEqual((x2.skip_untap >= 1, y2.skip_untap >= 1), (True, True))

    def test_x_targets_lock_only_when_ferocious(self):
        blast = card("Test Blast", "{X}{U}", "Instant", "Tap X target creatures.\nFerocious — If you control a "
                     "creature with power 4 or greater, those creatures don't untap during their controllers' next "
                     "untap steps.")
        self.assertEqual(blast.unsupported, [])
        x, y = self.creature(self.b), self.creature(self.b)
        self.resolve(blast, [[x, y]])
        self.assertTrue(x.tapped and y.tapped)
        self.assertEqual((x.skip_untap, y.skip_untap), (0, 0))
        self.g.enter_battlefield(self.a, card("Ogre", "{4}", "Creature — Ogre", "", 4, 4))
        x2, y2 = self.creature(self.b), self.creature(self.b)
        self.resolve(blast, [[x2, y2]])
        self.assertTrue(x2.skip_untap >= 1 and y2.skip_untap >= 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()
