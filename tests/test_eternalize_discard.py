"""#646 slice 11: Embalm / Eternalize with an extra discard (CR 702.128a / 702.129a; alt_casts.graveyard_actions)."""
import unittest

from mtgsim.alt_casts import graveyard_actions
from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
CHAMPION = card("Test Champion", "{2}{W}", "Creature — Human Wizard",
                "Eternalize—{2}{W}{W}, Discard a card.", 2, 1)


class Parsing(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(CHAMPION.unsupported, [])
        (alt,) = CHAMPION.alt_costs
        self.assertEqual((alt.kind, alt.zone, alt.discard, alt.cost.get("W")), ("eternalize", "graveyard", 1, 2))

    def test_refusals(self):
        for text in ("Eternalize—{2}{W}{W}, Discard two cards.", "Eternalize—{2}{W}{W}, Sacrifice a creature.",
                     "Embalm—Discard a card."):
            c = card("X", "{2}", "Creature — Human", text, 1, 1)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def setUp(self):
        super().setUp()
        self.game.step = "main2"
        self.a.graveyard = [CHAMPION]
        self.a.battlefield = [Permanent(PLAINS, self.a) for _ in range(4)]

    def test_eternalize_pays_mana_and_a_discard(self):
        """CR 702.129a: [cost], exile this card from your graveyard: create a token copy, a 4/4 black Zombie."""
        self.a.hand = [BEAR, BEAR]
        graveyard_actions(self.game, self.a)
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual((token.power, token.toughness), (4, 4))
        self.assertIn("Zombie", token.card.subtypes)
        self.assertIn(CHAMPION, self.a.exile)
        self.assertEqual(len(self.a.hand), 1)
        self.assertTrue(all(x.tapped for x in self.a.battlefield if x.card.is_land))

    def test_no_card_to_discard(self):
        self.a.hand = []
        graveyard_actions(self.game, self.a)
        self.assertIn(CHAMPION, self.a.graveyard)
        self.assertFalse(any(x.tapped for x in self.a.battlefield))       # the mana wasn't spent either


class HeuristicUse(Base):
    def test_ai_keeps_its_last_card(self):
        """The default AI eternalizes only with a spare card (it keeps its last card in hand)."""
        self.a.graveyard = [CHAMPION]
        self.a.battlefield = [Permanent(PLAINS, self.a) for _ in range(4)]
        self.a.hand = [BEAR]
        graveyard_actions(self.game, self.a)
        self.assertIn(CHAMPION, self.a.graveyard)
        self.assertEqual(self.a.hand, [BEAR])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Sinuous Striker", "Sunscourge Champion"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()
