import unittest

from mtgsim.build_carddb import forge_card, forge_cost
from mtgsim.carddb import ALL_CARDS, CardDB

FIRE_ICE = """Name:Fire
ManaCost:1 R
Types:Instant
AlternateMode:Split
Oracle:Fire deals 2 damage divided as you choose among one or two targets.

ALTERNATE

Name:Ice
ManaCost:1 U
Types:Instant
Oracle:Tap target permanent.\\nDraw a card.
"""


class TestForgeConversion(unittest.TestCase):
    def test_costs(self):
        self.assertEqual(forge_cost("1 BP BP"), ("{1}{B/P}{B/P}", 3))
        self.assertEqual(forge_cost("RW RW 2R"), ("{R/W}{R/W}{2/R}", 4))
        self.assertEqual(forge_cost("X X R"), ("{X}{X}{R}", 1))
        self.assertEqual(forge_cost("no cost"), ("", 0))

    def test_split_card(self):
        card = forge_card(FIRE_ICE)
        self.assertEqual(card["name"], "Fire // Ice")
        self.assertEqual(card["layout"], "split")
        self.assertEqual(card["mana_cost"], "{1}{R} // {1}{U}")
        self.assertEqual(card["card_faces"][1]["oracle_text"], "Tap target permanent.\nDraw a card.")

    def test_planeswalker_text(self):
        card = forge_card("Name:Pw\nManaCost:2 U\nTypes:Legendary Planeswalker Jace\nLoyalty:3\n"
                          "Oracle:[+1]: Draw a card.\\n[-2]: Scry 2.\n")
        self.assertEqual(card["oracle_text"], "+1: Draw a card.\n−2: Scry 2.")
        self.assertEqual(card["type_line"], "Legendary Planeswalker — Jace")


@unittest.skipUnless(ALL_CARDS.exists(), "card database not built")
class TestAllCards(unittest.TestCase):
    db = CardDB(offline=True)

    def test_lookup_any_card(self):
        self.assertEqual(self.db.get("Sheoldred, the Apocalypse").power, 4)
        self.assertEqual(self.db.get("lim-dul the necromancer").name, "Lim-Dûl the Necromancer")

    def test_face_names(self):
        self.assertEqual(self.db.lookup("Stomp")["name"], "Bonecrusher Giant // Stomp")
        self.assertEqual(self.db.get("Fable of the Mirror-Breaker").name, "Fable of the Mirror-Breaker")

    def test_unknown(self):
        with self.assertRaises(KeyError):
            self.db.ensure(["Not A Real Card Name"])
