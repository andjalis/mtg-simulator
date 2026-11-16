"""#646 slice 7: Echo and Buyback with non-mana costs (CR 702.30, 702.27; mtgsim.keyword_costs)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.creature_keywords import upkeep as echo_upkeep
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

IMP = card("Test Imp", "{2}{B}", "Creature — Imp", "Flying, haste\nEcho—Discard a card.", 4, 3)
SURGER = card("Test Surger", "{2}{R}", "Creature — Elemental", "Haste\nEcho—Sacrifice two lands.", 7, 2)
SLAUGHTER = card("Test Slaughter", "{2}{B}", "Instant",
                 "Buyback—Pay 4 life.\nDestroy target nonblack creature. It can't be regenerated.")


class Parsing(unittest.TestCase):
    def test_positives(self):
        self.assertEqual(IMP.unsupported, [])
        self.assertEqual(IMP.advanced_rules["echo_cost"], ("discard", 1, 1))
        self.assertEqual(SURGER.advanced_rules["echo_cost"], ("sac", "land", 2))
        self.assertEqual(SLAUGHTER.unsupported, [])
        (alt,) = [a for a in SLAUGHTER.alt_costs if a.kind == "buyback"]
        self.assertEqual(alt.life, 4)

    def test_refusals(self):
        for text in ("Echo—Discard two cards.", "Echo—Sacrifice two land.", "Echo—Pay {E}.",
                     "Buyback—Pay 3 life, Discard a card at random.", "Buyback—Sacrifice three Islands."):
            c = card("X", "{2}", "Creature — Imp", text, 1, 1)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def echo(self):
        echo_upkeep(self.game, self.a)
        self.game.settle()

    def test_echo_discard(self):
        """CR 702.30a: at your upkeep, sacrifice it unless you pay its echo cost (a discard)."""
        imp = self.perm(IMP, self.a)
        self.a.hand = [BEAR, BEAR]
        self.echo()
        self.assertIn(imp, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 1)
        self.echo()                                         # only once: paid since the last upkeep
        self.assertEqual(len(self.a.hand), 1)

    def test_echo_unpaid_sacrifices(self):
        imp = self.perm(IMP, self.a)
        self.a.hand = []
        self.echo()
        self.assertNotIn(imp, self.a.battlefield)
        self.assertIn(IMP, self.a.graveyard)

    def test_echo_two_lands(self):
        surger = self.perm(SURGER, self.a)
        self.a.battlefield += [Permanent(MOUNTAIN, self.a) for _ in range(6)]
        self.echo()
        self.assertIn(surger, self.a.battlefield)
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), 4)

    def test_buyback_pays_life_and_returns(self):
        """CR 702.27a: with buyback paid (4 life), the spell goes to its owner's hand as it resolves."""
        bear = self.perm(BEAR, self.b)
        self.a.hand = [SLAUGHTER]
        self.a.battlefield = [Permanent(card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)"), self.a)
                              for _ in range(3)]
        (variant,) = [o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "buyback"]
        self.assertTrue(self.game.cast(self.a, variant, [bear]))
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.a.life, 16)
        self.assertEqual([c.name for c in self.a.hand], ["Test Slaughter"])


class HeuristicUse(Base):
    def test_ai_lets_the_surger_go_when_short_of_lands(self):
        surger = self.perm(SURGER, self.a)
        self.a.battlefield += [Permanent(ISLAND, self.a) for _ in range(4)]
        echo_upkeep(self.game, self.a)
        self.game.settle()
        self.assertNotIn(surger, self.a.battlefield)
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), 4)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Deepcavern Imp", "Rakdos Headliner", "Skizzik Surger", "Slaughter"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))
        for name in ("Flowstone Flood", "Walk the Aeons"):
            self.assertEqual(card_coverage(db.get(name)).status, "partial", name)


if __name__ == "__main__":
    unittest.main()
