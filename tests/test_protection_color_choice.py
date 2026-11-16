"""#627: "gains protection from the color of your choice" on any subject, and "Choose a color. ... gain protection
from the chosen color" (mtgsim.cx_grammar_choice)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Alseid of Life's Bounty", "Borg Incursion", "Sygg, River Guide", "Akroma's Blessing", "Brave the Elements",
        "Prismatic Boon")
BLESSING = card("Test Blessing", "{2}{W}", "Instant", "Choose a color. Creatures you control gain protection from the "
                                                      "chosen color until end of turn.")


class Parse(unittest.TestCase):
    def test_group_and_target(self):
        self.assertEqual(BLESSING.unsupported, [])
        group = BLESSING.spell_effects[0]
        self.assertEqual([e.data["keyword"] for e in group.data["effects"]], ["protection_choice"])
        c = card("Test Sygg", "{W}", "Instant", "Target Merfolk you control gains protection from the color of your "
                                                "choice until end of turn.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.spell_effects[0].data["selector"]["controller"], "mine")

    def test_refusals(self):
        for text in (
            # everyone's creatures: the AI's pick would protect the opponent's creatures from their own colour
            "Choose a color. All creatures gain protection from the chosen color until end of turn.",
            # no duration
            "Target creature you control gains protection from the color of your choice.",
            # a choice between protections
            "Target creature you control gains protection from artifacts or from the color of your choice until end "
            "of turn.",
        ):
            self.assertTrue(card("Test Odd", "{W}", "Instant", text).unsupported, text)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full_and_akroma_protects_from_the_opponents_red(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        mine = g.enter_battlefield(a, card("Bear", "{1}", "Creature — Bear", "", 2, 2))
        theirs = g.enter_battlefield(b, db.get("Goblin Piker"))           # a red creature
        spell = db.get("Akroma's Blessing")
        effects = list(spell.spell_effects)
        g.stack.append(StackItem(a, effects, [None] * len(effects), card=spell, name=spell.name))
        g.resolve_top()
        self.assertTrue(mine.has("protection from red"))
        self.assertFalse(theirs.has("protection from red"))


if __name__ == "__main__":
    unittest.main()
