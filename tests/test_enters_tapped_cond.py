"""#630: "~ enters tapped unless / if <condition>" and "If <condition>, ~ enters tapped" with any condition the
shared library reads (mtgsim.cx_night_buffs.enters_tapped_late)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.cx_condlib import parse
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import PLAINS, card

ROADS = card("Test Roads", "", "Land", "~ enters tapped unless you control a Mount or Vehicle.\n{T}: Add {G}.")
GRANGE = card("Test Grange", "", "Land — Plains", "~ enters tapped unless you control three or more other Plains.")
CHICANE = card("Test Chicane", "", "Land", "If you were the starting player, ~ enters tapped.\n{T}: Add {C}.")
MOUNT = card("Test Mount", "{1}", "Creature — Horse Mount", "", 2, 2)


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (ROADS, GRANGE, CHICANE):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertTrue(CHICANE.tapped_condition.startswith('lib:["not"'))

    def test_article_carries_over_a_bare_noun(self):
        self.assertEqual(parse("you control a Mount or Vehicle"), parse("you control a Mount or a Vehicle"))

    def test_older_forms_keep_their_codes(self):
        fortress = card("Test Fortress", "", "Land", "~ enters tapped unless you control a Plains or an Island.")
        self.assertEqual(fortress.tapped_condition, "unless_control:Plains|Island")

    def test_refusals(self):
        for text in ("~ enters tapped unless you control a foo bar.",
                     "~ enters tapped unless you control a white, blue, or black permanent."):
            c = card("Test Refused", "", "Land", text)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def enter(self, c):
        self.game.enter_battlefield(self.a, c)
        return [x for x in self.a.battlefield if x.card.name == c.name][-1]

    def test_unless_mount_or_vehicle(self):
        self.assertTrue(self.enter(ROADS).tapped)
        self.perm(MOUNT, self.a)
        self.assertFalse(self.enter(ROADS).tapped)

    def test_other_plains_count(self):
        for _ in range(2):
            self.perm(PLAINS, self.a)
        self.assertTrue(self.enter(GRANGE).tapped)                      # itself is not "other"
        self.perm(PLAINS, self.a)
        self.assertFalse(self.enter(GRANGE).tapped)

    def test_if_starting_player(self):
        self.assertIs(self.game.players[0], self.a)                     # a went first
        self.assertTrue(self.enter(CHICANE).tapped)
        self.game.enter_battlefield(self.b, CHICANE)
        self.assertFalse([x for x in self.b.battlefield if x.card.name == "Test Chicane"][0].tapped)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Country Roads", "Foul Roads", "Reef Roads", "Rocky Roads", "Wild Roads", "Idyllic Grange",
                     "Rising Chicane"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()
