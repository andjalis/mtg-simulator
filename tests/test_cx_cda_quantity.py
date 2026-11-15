"""cx_cda_quantity: characteristic-defining P/T from a quantity (#401) — "~'s power and toughness are each equal
to Q", "~'s power is equal to Q" and the two-clause "... and its toughness is equal to that number plus N"."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, PLAINS, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


def cda(text, power=0, toughness=0, types="Creature — Beast"):
    return card("Test Goyf", "{1}{G}", types, text, power, toughness)


class Parsing(unittest.TestCase):
    def full(self, text, **kw):
        c = cda(text, **kw)
        self.assertEqual(c.unsupported, [], text)
        return c.advanced_rules.get("cda_pt", ())

    def ignored(self, text, **kw):
        c = cda(text, **kw)
        self.assertEqual(len(c.unsupported), 1, text)
        self.assertNotIn("cda_pt", c.advanced_rules, text)

    def test_reads_each_shape(self):
        rows = self.full("~'s power and toughness are each equal to the number of cards in all graveyards.")
        self.assertEqual(rows[0][0], rows[0][1])
        rows = self.full("~'s power is equal to your devotion to red.")
        self.assertEqual(rows[0][1], None)
        self.assertEqual(rows[0][0][0], "devotion")
        rows = self.full("~'s toughness is equal to 1 plus the number of green creatures on the battlefield.")
        self.assertEqual(rows[0][0], None)
        self.assertEqual(rows[0][1][0], "arith")
        rows = self.full("~'s power is equal to the number of creature cards in all graveyards and its toughness is "
                         "equal to that number plus 1.")
        self.assertEqual(rows[0][1], ("arith", rows[0][0], "+", 1))
        rows = self.full("~'s power and toughness are each equal to twice the number of oil counters on it.")
        self.assertEqual(rows[0][0][1], "twice")
        self.full("Top of the Food Chain — ~'s power is equal to the greatest mana value among permanents you "
                  "control.")                                    # an ability-word label is stripped
        self.full("~'s power and toughness are each equal to the number of Forests on the battlefield.")

    def test_refuses_what_it_cannot_play_correctly(self):
        for text in (
                "~'s power and toughness are each equal to the greatest power among creatures you control.",  # reads P/T
                "~'s power is equal to ~'s toughness.",                # reads P/T (dependency loop)
                "~'s power and toughness are each equal to the number of untapped artifacts, creatures, and lands "
                "you control.",                                        # unknown quantity
                "~'s power and toughness are each equal to the number of creatures of the chosen type on the "
                "battlefield.",                                        # a choice
                "~'s power is equal to that number plus 1.",               # "that number" with no first clause
                "During your turn, ~'s power and toughness are each equal to the number of cards in your hand.",  # a gate
                "~'s power is equal to the exiled card's mana value.",     # no fixed referent
                "~'s power and toughness are each equal to the number of cards in your graveyard plus ~'s power.",
        ):
            self.ignored(text)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.my_turn = True
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x


class Playing(Base):
    def test_both_stats_count_all_graveyards(self):
        lord = self.perm(cda("~'s power and toughness are each equal to the number of cards in all graveyards."),
                         self.a)
        self.assertEqual((lord.power, lord.toughness), (0, 0))
        self.a.graveyard = [ISLAND, ISLAND, MOUNTAIN]
        self.b.graveyard = [PLAINS]
        self.assertEqual((lord.power, lord.toughness), (4, 4))

    def test_power_and_toughness_from_their_own_quantities(self):
        goyf = self.perm(cda("~'s power is equal to the number of creature cards in all graveyards and its "
                             "toughness is equal to that number plus 1."), self.a)
        self.assertEqual((goyf.power, goyf.toughness), (0, 1))
        self.a.graveyard = [BEAR, ISLAND]
        self.b.graveyard = [BEAR]
        self.assertEqual((goyf.power, goyf.toughness), (2, 3))

    def test_single_stat_leaves_the_other_printed(self):
        constable = self.perm(cda("~'s toughness is equal to 1 plus the number of red creatures on the "
                                  "battlefield.", power=2, toughness=2), self.a)
        self.assertEqual((constable.power, constable.toughness), (2, 1))
        self.perm(card("Imp", "{R}", "Creature — Imp", "", 1, 1), self.a)
        self.assertEqual((constable.power, constable.toughness), (2, 2))

    def test_devotion_and_counters_on_it(self):
        anax = self.perm(cda("~'s power is equal to your devotion to red.", power=1, toughness=1), self.a)
        self.assertEqual(anax.power, 0)
        self.perm(card("Rock", "{2}{R}", "Artifact", "", cmc=3), self.a)
        self.assertEqual(anax.power, 1)
        self.perm(card("Anvil", "{R}{R}", "Artifact", "", cmc=2), self.a)
        self.assertEqual(anax.power, 3)
        hydra = self.perm(cda("~'s power and toughness are each equal to twice the number of oil counters on it."),
                          self.a)
        hydra.counters["oil"] = 3
        self.assertEqual((hydra.power, hydra.toughness), (6, 6))

    def test_cda_applies_before_other_modifiers(self):
        lord = self.perm(cda("~'s power and toughness are each equal to the number of cards in all graveyards."),
                         self.a)
        self.a.graveyard = [ISLAND] * 3
        lord.counters["+1/+1"] = 2
        self.assertEqual((lord.power, lord.toughness), (5, 5))     # 7a CDA, then the 7c counter
        self.perm(card("Anthem", "{1}{W}", "Enchantment", "Creatures you control get +1/+1."), self.a)
        self.assertEqual((lord.power, lord.toughness), (6, 6))     # and the anthem on top


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB(offline=True)
        for name in ("Lhurgoyf", "Lord of Extinction", "Necrogoyf", "Masumaro, First to Live", "Allosaurus Rider",
                     "Gaea's Avenger", "Lost Order of Jarkeld", "Coiling Woodworm", "Aven Trailblazer",
                     "Captain Pike, Fullness of Time", "Mwonvuli Ooze", "An-Havva Constable", "Dodgy Jalopy"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))

    def test_maraxus_quantity_stays_ignored(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        row = card_coverage(db.get("Maraxus of Keld"))
        self.assertIn("the number of untapped artifacts, creatures, and lands you control", row.ignored[0])


if __name__ == "__main__":
    unittest.main()
