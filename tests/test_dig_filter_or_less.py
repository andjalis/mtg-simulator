"""Audit 2026-11-16 (opus-cast): Game.dig turned "power 2 or less" into "power 2 or a less" (its " or " -> " or a "
rewrite for "artifact or creature card"), so a dig with an "N or less / or greater" filter never found a card
(Living Phone, Militia Bugler, Recruitment Officer, Gavony Dawnguard, Squad Rallier, Water Tribe Rallier)."""
import unittest

from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import ISLAND, card

SMALL = card("Test Small", "{1}{W}", "Creature — Human", "", 2, 2)
BIG = card("Test Big", "{4}{G}", "Creature — Beast", "", 5, 5)
ROCK = card("Test Rock", "{2}", "Artifact", "")


class DigFilter(Base):
    def dig(self, desc, library):
        self.a.library = [ISLAND] * 5 + list(library)
        self.game.dig(self.a, 3, 1, desc)
        return [c.name for c in self.a.hand]

    def test_power_or_less(self):
        self.assertEqual(self.dig("a creature card with power 2 or less", [BIG, SMALL, ISLAND]), ["Test Small"])

    def test_or_greater(self):
        self.assertEqual(self.dig("a creature card with mana value 4 or greater", [SMALL, BIG, ISLAND]), ["Test Big"])

    def test_type_lists_still_read(self):
        """The rewrite's purpose: "artifact or creature card" still matches either."""
        self.assertEqual(self.dig("an artifact or creature card", [ISLAND, ROCK, ISLAND]), ["Test Rock"])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_living_phone(self):
        from mtgsim.carddb import CardDB
        phone = self.game.enter_battlefield(self.a, CardDB(offline=True).get("Living Phone"))
        self.a.library = [ISLAND] * 10 + [BIG, SMALL, ISLAND, ISLAND, ISLAND]
        self.game.destroy(phone)
        self.game.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Test Small"])

    def test_militia_bugler(self):
        from mtgsim.carddb import CardDB
        self.a.library = [ISLAND] * 10 + [BIG, SMALL, ISLAND, ISLAND]
        self.game.enter_battlefield(self.a, CardDB(offline=True).get("Militia Bugler"))
        self.game.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Test Small"])


if __name__ == "__main__":
    unittest.main()
