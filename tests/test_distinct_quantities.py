""""for each different mana value / power / toughness among <things>" and "for each color among <things>" (#337):
cx_grammar_quantity counts distinct values over a battlefield group or a zone's cards."""
import unittest

from mtgsim.cx_grammar_quantity import quantity

from tests.test_cx_grammar import BEAR, DB_FILE, GOBLIN, Base, card

RED_ART = card("Test Red Relic", "{R}", "Artifact", "")
BLUE_ART = card("Test Blue Relic", "{U}", "Artifact", "")
PAINTER = card("Test Painter", "{U}{R}", "Artifact", "")
GIANT = card("Test Giant", "{4}", "Creature — Giant", "", 5, 5)


class Parsing(unittest.TestCase):
    def test_specs(self):
        self.assertEqual(quantity("the number of different powers among creatures you control")[:3],
                         ("cxq", "distinct", "power"))
        self.assertEqual(quantity("the number of different mana values among nonland cards in your graveyard")[:4],
                         ("cxq", "distinct_cards", "mana value", "your_gy"))
        self.assertEqual(quantity("the number of colors among artifacts you control")[:3], ("cxq", "distinct", "colors"))
        for q in ("the number of different names among creatures you control",
                  "the number of different powers among target creatures"):
            self.assertIsNone(quantity(q), q)


class Resolving(Base):
    def draws(self, text):
        hand = len(self.a.hand)
        self.cast(self.spell(text, "Sorcery"))
        return len(self.a.hand) - hand

    def test_distinct_powers_of_yours_only(self):
        self.perm(BEAR, self.a), self.perm(BEAR, self.a), self.perm(GOBLIN, self.a), self.perm(GIANT, self.b)
        self.assertEqual(self.draws("Draw a card for each different power among creatures you control."), 2)

    def test_distinct_mana_values_in_graveyard(self):
        self.a.graveyard = [BEAR, BEAR, GOBLIN, GIANT, card("Test Land", "", "Land", "")]
        self.assertEqual(self.draws("Draw a card for each different mana value among nonland cards in your "
                                    "graveyard."), 3)

    def test_colors_among_other_artifacts(self):
        self.perm(RED_ART, self.a), self.perm(BLUE_ART, self.a), self.perm(PAINTER, self.a), self.perm(BLUE_ART, self.b)
        self.assertEqual(self.draws("Draw a card for each color among artifacts you control."), 2)

    def test_nothing_is_zero(self):
        self.assertEqual(self.draws("Draw a card for each different power among creatures you control."), 0)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class StaticCount(Base):
    def test_sisay_counts_colors_of_other_legends(self):
        from mtgsim.carddb import CardDB
        sisay = self.perm(CardDB().get("Sisay, Weatherlight Captain"), self.a)
        self.assertEqual((sisay.power, sisay.toughness), (2, 2))       # her own white doesn't count ("other")
        self.perm(card("Test Legend", "{R}{G}", "Legendary Creature — Elf", "", 1, 1), self.a)
        self.perm(card("Test Relic", "{U}", "Legendary Artifact", ""), self.a)
        self.perm(card("Test Theirs", "{B}", "Legendary Creature — Elf", "", 1, 1), self.b)
        self.assertEqual((sisay.power, sisay.toughness), (5, 5))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Lunar Insight", "Golden Ratio", "Sudden Insight", "Karn, Gilded Guardian", "Earthen Ally",
                     "Sisay, Weatherlight Captain"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()
