"""#631: "<players> choose N <noun> / an X, a Y, ... they control, then sacrifice the rest" (cx_grammar_edicts,
kind cx_keep): every player keeps its own most valuable permanents."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Covetous Elegy", "Archfiend of Depravity", "Razia's Purification", "Limited Resources",
        "Planetary Annihilation", "Keldon Firebombers", "Cataclysm", "Cataclysmic Gearhulk", "Global Ruin",
        "Liliana, Dreadhorde General")
ELEGY = card("Test Elegy", "{4}{W}{B}", "Sorcery", "Each player chooses up to two creatures they control, then "
                                                   "sacrifices the rest.")
CATA = card("Test Cataclysm", "{2}{W}{W}", "Sorcery", "Each player chooses from among the permanents they control an "
            "artifact, a creature, an enchantment, and a land, then sacrifices the rest.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


def board(g, p):
    out = {f"C{i}": g.enter_battlefield(p, card(f"C{i}", "{%d}" % i, "Creature — Beast", "", i, i)) for i in (1, 3, 5)}
    out["Rock"] = g.enter_battlefield(p, card("Rock", "{2}", "Artifact", ""))
    out["Aura"] = g.enter_battlefield(p, card("Aura", "{1}", "Enchantment", ""))
    out["Land"] = g.enter_battlefield(p, card("Wastes", "", "Land", ""))
    out["Land2"] = g.enter_battlefield(p, card("Wastes", "", "Land", ""))
    return out


def resolve(g, p, c):
    effects = list(c.spell_effects)
    g.stack.append(StackItem(p, effects, [None] * len(effects), card=c, name=c.name))
    g.resolve_top()
    g.settle()


class Parse(unittest.TestCase):
    def test_shapes(self):
        for c in (ELEGY, CATA):
            self.assertEqual(c.unsupported, [], c.name)
        inner = ELEGY.spell_effects[0].data["effects"][0]
        self.assertEqual((inner.kind, [n for _, n in inner.data["keep"]]), ("cx_keep", [2]))
        inner = CATA.spell_effects[0].data["effects"][0]
        self.assertEqual([n for _, n in inner.data["keep"]], [1, 1, 1, 1])

    def test_refusals(self):
        for text in ("Each player chooses up to two creatures they control, then exiles the rest.",
                     "Each player chooses any number of creatures they control with total power 4 or less, then "
                     "sacrifices all other creatures they control.",
                     "Each player chooses two creatures with flying they control named Bob, then sacrifices the rest."):
            self.assertTrue(card("Test Odd", "{B}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def test_each_player_keeps_its_two_best_creatures(self):
        g, a, b = game()
        mine, theirs = board(g, a), board(g, b)
        resolve(g, a, ELEGY)
        for side, p in ((mine, a), (theirs, b)):
            self.assertEqual(sorted(x.card.name for x in p.creatures), ["C3", "C5"])
            self.assertIn(side["Rock"], p.battlefield)            # only creatures are in scope

    def test_cataclysm_keeps_one_of_each(self):
        g, a, b = game()
        theirs = board(g, b)
        resolve(g, a, CATA)
        kept = sorted(x.card.name for x in b.battlefield)
        self.assertEqual(kept, ["Aura", "C5", "Rock", "Wastes"])
        self.assertIn(theirs["C5"], b.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in FULL:
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_global_ruin_keeps_one_land_per_basic_type(self):
        g, a, b = game()
        for n in ("Plains", "Island", "Swamp", "Swamp", "Mountain"):
            g.enter_battlefield(b, self.db.get(n))
        resolve(g, a, self.db.get("Global Ruin"))
        self.assertEqual(sorted(x.card.name for x in b.battlefield), ["Island", "Mountain", "Plains", "Swamp"])

    def test_keldon_firebombers_leaves_three_lands(self):
        g, a, b = game()
        for n in ("Plains", "Island", "Swamp", "Swamp", "Mountain"):
            g.enter_battlefield(b, self.db.get(n))
        g.enter_battlefield(a, self.db.get("Keldon Firebombers"))
        g.settle()
        self.assertEqual(len([x for x in b.battlefield if x.card.is_land]), 3)


if __name__ == "__main__":
    unittest.main()
