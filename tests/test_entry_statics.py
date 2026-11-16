"""#630: statics that change how a group enters: "<group> [your opponents control] enter tapped" and "<group> you
control enter with an additional counter" (mtgsim.entry_statics)."""
import unittest

from mtgsim.coverage import card_coverage
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, FOREST, card

ARCHON = card("Test Archon", "{2}{W}", "Creature — Archon", "Nonbasic lands your opponents control enter tapped.", 2, 3)
THALIA = card("Test Thalia", "{2}{W}", "Legendary Creature — Human Soldier",
              "Creatures and nonbasic lands your opponents control enter tapped.", 3, 2)
MAZE = card("Test Maze", "{G}", "Enchantment", "Artifacts and lands enter tapped.")
RENATA = card("Test Renata", "{2}{G}", "Legendary Creature — Demigod",
              "Each other creature you control enters with an additional +1/+1 counter on it.", 2, 2)
BEASTIE = card("Test Beastie", "{4}{G}", "Creature — Beast",
               "Colorless creatures you control enter with two additional +1/+1 counters on them.", 4, 4)
GLOBE = card("Test Globe", "{3}", "Artifact", "Each Dragon you control enters with an additional +1/+1 counter on it.")
OATH = card("Test Oath", "{1}{W}", "Legendary Enchantment",
            "Each planeswalker you control enters with an additional loyalty counter on it.")
TEMPLE = card("Test Temple", "", "Land", "{T}: Add {C}.")
GOLEM = card("Test Golem", "{3}", "Artifact Creature — Golem", "", 2, 2)
DRAGON = card("Test Dragon", "{4}{R}", "Creature — Dragon", "Flying", 4, 4)


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (ARCHON, THALIA, MAZE, RENATA, BEASTIE, GLOBE, OATH):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(THALIA.advanced_rules["entry_tapped"][0][1], "opp")
        self.assertEqual(MAZE.advanced_rules["entry_tapped"][0][1], "all")
        self.assertEqual(BEASTIE.advanced_rules["entry_counters"][0][1:], ("+1/+1", 2, False))

    def test_refusals(self):
        for text in ("Each creature you control that's a Wolf or a Werewolf enters with an additional +1/+1 counter "
                     "on it.",
                     "Creatures your opponents control with power 2 or less enter tapped.",
                     "Non-Phyrexian creatures enter tapped.",
                     "Each other creature you control enters with an additional +1/+1 counter on it if it's red."):
            c = card("Test Refused", "{3}", "Enchantment", text)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def enter(self, p, c):
        self.game.enter_battlefield(p, c)
        return [x for x in p.battlefield if x.card.name == c.name][-1]

    def test_opponents_nonbasic_lands_only(self):
        self.perm(ARCHON, self.a)
        self.assertTrue(self.enter(self.b, TEMPLE).tapped)
        self.assertFalse(self.enter(self.b, FOREST).tapped)              # basic
        self.assertFalse(self.enter(self.a, TEMPLE).tapped)              # mine

    def test_creatures_and_nonbasic_lands(self):
        self.perm(THALIA, self.a)
        self.assertTrue(self.enter(self.b, BEAR).tapped)
        self.assertTrue(self.enter(self.b, TEMPLE).tapped)
        self.assertFalse(self.enter(self.a, BEAR).tapped)

    def test_everyones_artifacts_and_lands(self):
        self.perm(MAZE, self.b)
        self.assertTrue(self.enter(self.a, FOREST).tapped)
        self.assertTrue(self.enter(self.b, GOLEM).tapped)
        self.assertFalse(self.enter(self.a, BEAR).tapped)

    def test_other_creatures_get_a_counter(self):
        renata = self.perm(RENATA, self.a)
        self.assertEqual(self.enter(self.a, BEAR).p1, 1)
        self.assertEqual(self.enter(self.b, BEAR).p1, 0)                  # theirs
        self.assertEqual(renata.p1, 0)

    def test_two_counters_for_colorless(self):
        self.perm(BEASTIE, self.a)
        self.assertEqual(self.enter(self.a, GOLEM).p1, 2)
        self.assertEqual(self.enter(self.a, BEAR).p1, 0)

    def test_dragons_only(self):
        self.perm(GLOBE, self.a)
        self.assertEqual(self.enter(self.a, DRAGON).p1, 1)
        self.assertEqual(self.enter(self.a, BEAR).p1, 0)

    def test_loyalty(self):
        self.perm(OATH, self.a)
        walker = card("Test Walker", "{3}", "Legendary Planeswalker — Test", "+1: Draw a card.")
        walker.loyalty = 3
        perm = self.enter(self.a, walker)
        self.assertEqual(perm.counters.get("loyalty", 0), 4)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Archon of Emeria", "Thalia, Heretic Cathar", "Root Maze", "Spider-Woman, Stunning Savior",
                     "Renata, Called to the Hunt", "Curator Beastie", "Deanna Troi, Psychic Counsel",
                     "Dragonstorm Globe", "Sage of Fables", "Slinza, the Spiked Stampede", "Bramblewood Paragon",
                     "Oona's Blackguard", "Oath of Gideon"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()
