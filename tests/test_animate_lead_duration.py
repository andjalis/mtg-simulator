"""#645: "Until end of turn, target land becomes a 3/3 creature. It's still a land." (leading duration)."""
import random
import re
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

SPELL = card("Test Animate", "{1}{U}", "Instant", "Until end of turn, target land becomes a 3/3 Elemental creature. "
             "It's still a land.")


class LeadDuration(unittest.TestCase):
    def test_parses_temporary(self):
        self.assertEqual(SPELL.unsupported, [])
        eff = SPELL.spell_effects[0]
        self.assertEqual(eff.kind, "animate_land")
        self.assertFalse(eff.data["permanent"])

    def test_wears_off(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        land = g.enter_battlefield(a, ISLAND)
        g.enter_battlefield(a, ISLAND)
        g.enter_battlefield(a, ISLAND)
        g.settle()
        a.hand = [SPELL]
        self.assertTrue(g.cast(a, SPELL, [land]))
        g.settle()
        self.assertTrue(land.is_creature)
        self.assertEqual((land.power, land.toughness), (3, 3))


DB_FILE = Path(__file__).resolve().parent.parent / "mtgsim" / "data" / "cards.sqlite3"
FIXED = ("Animate Land", "Disturbed Slumber", "Rampaging Growth", "Blizzard Strix", "Skybind", "Mistmeadow Vanisher",
         "Decree of Justice", "Rise of the Hobgoblins")


class NoMarkerLeaks(unittest.TestCase):
    """Guard for the cards fixed under #645: no internal rewrite marker (CXANIM, DELAYEDBLINK, XTOKEN ...) may
    show in their ignored text again."""

    @unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
    def test_fixed_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in FIXED:
            leaked = [w for u in db.get(name).unsupported for w in re.findall(r"\b[A-Z]{5,}\b", u)]
            self.assertEqual(leaked, [], name)


if __name__ == "__main__":
    unittest.main()
