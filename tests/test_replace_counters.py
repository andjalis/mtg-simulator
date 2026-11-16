"""#407 slice 1: counter-amount replacements ("twice that many", "that many plus one", "minus one")."""
import unittest

from mtgsim.cx_replace_amounts import parse_mod
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
ROCK = card("Test Rock", "{2}", "Artifact", "")


class Parsing(unittest.TestCase):
    def test_wordings(self):
        cases = {
            "If one or more +1/+1 counters would be put on a creature you control, twice that many +1/+1 counters "
            "are put on it instead.": ("+1/+1", "mul", 2, ""),
            "If one or more counters would be put on an artifact or creature you control, that many plus one of each "
            "of those kinds of counters are put on that permanent instead.": ("", "add", 1, ""),
            "If one or more -1/-1 counters would be put on a creature you control, that many -1/-1 counters minus one "
            "are put on it instead.": ("-1/-1", "add", -1, ""),
            "If one or more +1/+1 counters would be put on ~, that many plus one +1/+1 counters are put on it "
            "instead.": ("+1/+1", "add", 1, ""),
            "If you would put one or more counters on a permanent you control, put twice that many of each of those "
            "kinds of counters on that permanent instead.": ("", "mul", 2, "who puts the counters is not checked"),
            "If an effect would put one or more counters on a permanent you control, it puts twice that many of "
            "those counters on that permanent instead.": ("", "mul", 2, "counters put as a cost are changed too"),
        }
        for line, (kind, op, n, note) in cases.items():
            with self.subTest(line):
                mod, got_note = parse_mod(line)
                self.assertEqual((mod["counter"], mod["op"], mod["n"], got_note), (kind, op, n, note))

    def test_objects(self):
        mod, _ = parse_mod("If one or more +1/+1 counters would be put on an Army, Goblin, or Orc you control, that "
                           "many plus one +1/+1 counters are put on it instead.")
        self.assertEqual([s.get("sub") for s in mod["obj"]], [["Army"], ["Goblin"], ["Orc"]])
        self.assertTrue(mod["mine"])
        mod, _ = parse_mod("If one or more +1/+1 counters would be put on another creature you control, that many "
                           "plus one +1/+1 counters are put on it instead.")
        self.assertTrue(mod["other"])

    def test_refusals(self):
        for line in (
                # counters on players are not modelled
                "If you would put one or more counters on a permanent or player, put twice that many of each of "
                "those kinds of counters on that permanent or player instead.",
                # a duration
                "Until end of turn, if one or more counters would be put on a permanent you control, that many plus "
                "one of each of those kinds of counters are put on that permanent instead.",
                # another kind than the one replaced
                "If one or more +1/+1 counters would be put on a creature you control, twice that many -1/-1 "
                "counters are put on it instead.",
                # a qualifier the filter can't read
                "If one or more +1/+1 counters would be put on a creature with flying you control, twice that many "
                "+1/+1 counters are put on it instead.",
                # whose ability puts them
                "If a modular triggered ability would put one or more +1/+1 counters on a creature you control, that "
                "many plus one +1/+1 counters are put on it instead."):
            with self.subTest(line):
                self.assertIsNone(parse_mod(line))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Engine(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)

    def get(self, name):
        c = self.db.get(name)
        self.assertEqual(c.unsupported, [], name)
        return c

    def test_doubler_only_on_your_creatures(self):
        self.perm(self.get("Corpsejack Menace"), self.a)
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        mine.counters["+1/+1"] = 2
        theirs.counters["+1/+1"] = 2
        self.assertEqual((mine.counters["+1/+1"], theirs.counters["+1/+1"]), (4, 2))
        mine.counters["-1/-1"] = 1          # another kind
        self.assertEqual(mine.counters["-1/-1"], 1)

    def test_plus_one_then_double(self):
        # additions first, then doubling: (1 + 1) * 2, the controller's best order
        self.perm(self.get("Corpsejack Menace"), self.a)
        self.perm(self.get("Conclave Mentor"), self.a)
        bear = self.perm(BEAR, self.a)
        bear.counters["+1/+1"] = 1
        self.assertEqual(bear.counters["+1/+1"], 4)

    def test_minus_one_can_remove_the_whole_put(self):
        self.perm(self.get("Vizier of Remedies"), self.a)
        bear = self.perm(BEAR, self.a)
        bear.counters["-1/-1"] = 1
        self.assertEqual(bear.counters.get("-1/-1", 0), 0)
        bear.counters["-1/-1"] = 3
        self.assertEqual(bear.counters["-1/-1"], 2)

    def test_any_kind_and_object_types(self):
        self.perm(self.get("Ozolith, the Shattered Spire"), self.a)       # +1/+1 on an artifact or creature
        rock = self.perm(ROCK, self.a)
        rock.counters["+1/+1"] = 1
        self.assertEqual(rock.counters["+1/+1"], 2)
        rock.counters["charge"] = 1                                       # +1/+1 only
        self.assertEqual(rock.counters["charge"], 1)
        self.perm(self.get("Optimization Annex"), self.a)                 # charge counters on an artifact
        rock.counters["charge"] = 2
        self.assertEqual(rock.counters["charge"], 3)

    def test_subtype_list_and_self(self):
        self.perm(self.get("Mauhúr, Uruk-hai Captain"), self.a)
        goblin, bear = self.perm(GOBLIN, self.a), self.perm(BEAR, self.a)
        goblin.counters["+1/+1"] = 1
        bear.counters["+1/+1"] = 1
        self.assertEqual((goblin.counters["+1/+1"], bear.counters["+1/+1"]), (2, 1))
        mowu = self.perm(self.get("Mowu, Loyal Companion"), self.a)
        mowu.counters["+1/+1"] = 1
        bear.counters["+1/+1"] = 2
        self.assertEqual((mowu.counters["+1/+1"], bear.counters["+1/+1"]), (2, 2))

    def test_another_excludes_itself(self):
        hydra = self.perm(self.get("Benevolent Hydra"), self.a)
        before = hydra.counters.get("+1/+1", 0)
        hydra.counters["+1/+1"] = before + 1
        bear = self.perm(BEAR, self.a)
        bear.counters["+1/+1"] = 1
        self.assertEqual((hydra.counters["+1/+1"] - before, bear.counters["+1/+1"]), (1, 2))

    def test_enters_with_counters_and_effects_are_doubled(self):
        self.perm(self.get("Branching Evolution"), self.a)
        from mtgsim.engine import StackItem
        c = card("Test Grower", "{G}", "Sorcery", "Put two +1/+1 counters on target creature.")
        bear = self.perm(BEAR, self.a)
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [bear], card=c))
        self.game.resolve_top()
        self.assertEqual(bear.counters["+1/+1"], 4)
        hatchling = card("Test Hatchling", "{1}{G}", "Creature — Elf", "~ enters with two +1/+1 counters on it.", 0, 0)
        self.game.enter_battlefield(self.a, hatchling)
        entered = next(x for x in self.a.battlefield if x.card.name == "Test Hatchling")
        self.assertEqual(entered.counters["+1/+1"], 4)

    def test_player_counters(self):
        self.perm(self.get("Winding Constrictor"), self.a)
        self.a.counters["energy"] = 2
        self.b.counters["energy"] = 2
        self.assertEqual((self.a.counters["energy"], self.b.counters["energy"]), (3, 2))
        self.a.counters["poison"] = 1          # any counters you get, poison too
        self.assertEqual(self.a.counters["poison"], 2)
        bear = self.perm(BEAR, self.a)
        bear.counters["+1/+1"] = 1             # and the permanent line
        self.assertEqual(bear.counters["+1/+1"], 2)

    def test_simplified_wordings(self):
        for name in ("Doubling Season", "Dr. Joseph M'Benga"):
            with self.subTest(name):
                c = self.db.get(name)
                self.assertEqual(c.unsupported, [])
                self.assertTrue(c.approximations)

    def test_suppressed_abilities_stop_the_replacement(self):
        menace = self.perm(self.get("Corpsejack Menace"), self.a)
        menace.silenced_by = self.perm(ROCK, self.b)       # a silencer still on the battlefield
        self.assertTrue(menace.abilities_suppressed)
        bear = self.perm(BEAR, self.a)
        bear.counters["+1/+1"] = 1
        self.assertEqual(bear.counters["+1/+1"], 1)


if __name__ == "__main__":
    unittest.main()
