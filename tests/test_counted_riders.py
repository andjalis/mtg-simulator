"""#628: riders about "them" after counted targets that #649 didn't reach: the "tap up to two target creatures" wording
entry, "one or two target ...", one-sentence "A and put ... on each of them", "their controllers' next untap steps",
and "for each opponent, tap up to one target creature that player controls. ... each of those creatures"."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Succumb to the Cold", "Homesickness", "Rime Chill", "Scroll of Isildur", "Sudden Storm", "Out Cold",
        "Hapatra, the Desert Frost", "Juvenile Mist Dragon")


def kinds(c):
    return [e.kind for e in c.spell_effects]


class Parse(unittest.TestCase):
    def test_legacy_tap_entry_splits_only_with_a_rider(self):
        alone = card("Test Tap", "{U}", "Instant", "Tap up to two target creatures.")
        self.assertEqual([(e.kind, e.amount) for e in alone.spell_effects], [("tap", 2)])     # unchanged
        c = card("Test Stun", "{U}", "Instant", "Tap up to two target creatures. Put a stun counter on each of them.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(kinds(c), ["tap", "stun"] * 2)
        self.assertTrue(all(e.data.get("optional_target") for e in c.spell_effects if e.kind == "tap"))

    def test_their_controllers_untap_steps(self):
        c = card("Test Storm", "{U}", "Instant", "Tap up to two target creatures. Those creatures don't untap during "
                                                 "their controllers' next untap steps.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(kinds(c), ["tap", "skip_untap"] * 2)

    def test_one_or_two(self):
        c = card("Test Cold", "{U}", "Instant", "Tap one or two target creatures an opponent controls. Put a stun "
                                                "counter on each of them.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(kinds(c), ["tap", "stun"] * 2)

    def test_one_sentence(self):
        c = card("Test Out", "{U}", "Instant", "Tap up to two target creatures and put a stun counter on each of "
                                               "them.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(kinds(c), ["tap", "stun"] * 2)

    def test_refusals(self):
        for text in (
            "Tap up to two target creatures. Put a stun counter on each of them unless their controller pays {2}.",
            "Tap up to two target creatures. Those creatures deal damage equal to their power to target player.",
            "Tap target creature. Put a stun counter on each of them.",
        ):
            c = card("Test Odd", "{U}", "Instant", text)
            self.assertTrue(c.unsupported, text)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def creature(self, owner, p=2, t=2):
        x = self.g.enter_battlefield(owner, card("Bear", "{1}", "Creature — Bear", "", p, t))
        x.sick = False
        return x

    def test_each_target_is_tapped_and_stunned(self):
        c = card("Test Stun", "{U}", "Instant", "Tap up to two target creatures. Put a stun counter on each of them.")
        x, y, z = self.creature(self.b), self.creature(self.b), self.creature(self.b)
        targets = [x, None, y, None]
        self.g.stack.append(StackItem(self.a, list(c.spell_effects), targets, card=c, name=c.name))
        self.g.resolve_top()
        self.assertEqual([(v.tapped, v.counters.get("stun", 0)) for v in (x, y, z)], [(True, 1), (True, 1), (False, 0)])

    def test_ai_aims_the_stun_at_opponents(self):
        c = card("Test Stun", "{U}", "Instant", "Tap up to two target creatures. Put a stun counter on each of them.")
        mine = self.creature(self.a, 3, 3)
        theirs = [self.creature(self.b, 3, 3), self.creature(self.b, 2, 2)]
        targets = self.g.auto_targets(self.a, list(c.spell_effects), None)
        chosen = [t for t in targets if t is not None]
        self.assertTrue(chosen)
        self.assertNotIn(mine, chosen)
        self.assertTrue(all(t in theirs for t in chosen))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in FULL:
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_cards_returned_from_a_graveyard_are_refused(self):
        # "it" after a graveyard card target is not the permanent it became: stays partial (Smile at Death)
        from mtgsim.coverage import card_coverage
        row = card_coverage(self.db.get("Smile at Death"))
        self.assertEqual(row.ignored, ["Put a +1/+1 counter on each of those creatures."])

    def test_hapatra_stuns_the_opponents_creature(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        mine = g.enter_battlefield(a, card("Bear", "{1}", "Creature — Bear", "", 2, 2))
        theirs = g.enter_battlefield(b, card("Ogre", "{2}", "Creature — Ogre", "", 3, 3))
        g.enter_battlefield(a, self.db.get("Hapatra, the Desert Frost"))
        g.settle()
        self.assertEqual((theirs.tapped, theirs.counters.get("stun", 0)), (True, 1))
        self.assertEqual((mine.tapped, mine.counters.get("stun", 0)), (False, 0))


if __name__ == "__main__":
    unittest.main()
