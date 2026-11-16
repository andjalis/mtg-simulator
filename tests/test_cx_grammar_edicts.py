"""#631: edicts with the greatest / least stat, lists of kinds and counts above five (mtgsim.cx_grammar_edicts)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Break Under Pressure", "Catch // Release", "Consecrate // Consume", "Consumed by Greed", "Crackling Doom",
        "Extract a Confession", "Flare of Malice", "Necrotic Hex", "Perilous Predicament", "Soul Shatter",
        "Structural Collapse", "To the Slaughter", "Witch-king, Bringer of Ruin", "Zodiark, Umbral God",
        "Legate Lanius, Caesar's Ace", "Vona's Hunger")
GREED = card("Test Greed", "{3}{B}", "Instant", "Target opponent sacrifices a creature with the greatest power among "
                                                "creatures they control.")
LEAST = card("Test Least", "{B}", "Instant", "Target opponent sacrifices a creature with the least power among "
                                             "creatures they control.")
COLLAPSE = card("Test Collapse", "{3}{R}", "Sorcery", "Target player sacrifices an artifact and a land.")
HEX = card("Test Hex", "{B}{B}{B}", "Sorcery", "Each player sacrifices six creatures.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


def creature(g, who, name, p, t):
    return g.enter_battlefield(who, card(name, "{%d}" % p, "Creature — Beast", "", p, t))


def cast(g, p, c, targets=None):
    effects = list(c.spell_effects)
    targets = g.auto_targets(p, effects, None) if targets is None else targets
    g.stack.append(StackItem(p, effects, targets, card=c, name=c.name))
    g.resolve_top()
    g.settle()
    return targets


class Parse(unittest.TestCase):
    def test_shapes(self):
        for c in (GREED, LEAST, COLLAPSE, HEX):
            self.assertEqual(c.unsupported, [], c.name)
        inner = GREED.spell_effects[0].data["effects"][0]
        self.assertEqual((inner.kind, inner.data["extreme"]), ("cx_edict", ["power", "max"]))
        self.assertEqual([e.kind for e in COLLAPSE.spell_effects[0].data["effects"]], ["cx_edict", "cx_edict"])
        self.assertEqual(HEX.spell_effects[0].data["effects"][0].amount, 6)

    def test_refusals(self):
        for text in (
            # the stat is read over another set than the one sacrificed
            "Target player sacrifices a creature with the greatest power among artifacts they control.",
            # a qualifier the edict can't check
            "Target opponent sacrifices a creature that attacked this turn and a land.",
            "Each player sacrifices an artifact and two lands.",
        ):
            self.assertTrue(card("Test Odd", "{B}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def test_greatest_power_goes_and_ai_targets_the_opponent(self):
        g, a, b = game()
        small, big = creature(g, b, "Elf", 1, 1), creature(g, b, "Giant", 6, 6)
        mine = creature(g, a, "Bear", 2, 2)
        targets = cast(g, a, GREED)
        self.assertIs(targets[0], b)
        self.assertIn(small, b.battlefield)
        self.assertNotIn(big, b.battlefield)
        self.assertIn(mine, a.battlefield)

    def test_least_power(self):
        g, a, b = game()
        small, big = creature(g, b, "Elf", 1, 1), creature(g, b, "Giant", 6, 6)
        cast(g, a, LEAST, [b])
        self.assertNotIn(small, b.battlefield)
        self.assertIn(big, b.battlefield)

    def test_ties_are_the_sacrificers_pick(self):
        g, a, b = game()
        token_like, real = creature(g, b, "Wolf", 4, 4), creature(g, b, "Bigger Value", 4, 6)
        cast(g, a, GREED, [b])
        self.assertEqual(len([x for x in (token_like, real) if x in b.battlefield]), 1)

    def test_artifact_and_land(self):
        g, a, b = game()
        rock = g.enter_battlefield(b, card("Rock", "{1}", "Artifact", ""))
        land = g.enter_battlefield(b, card("Wastes", "", "Land", ""))
        elf = creature(g, b, "Elf", 1, 1)
        cast(g, a, COLLAPSE, [b])
        self.assertEqual(b.battlefield, [elf])
        self.assertNotIn(rock, b.battlefield)
        self.assertNotIn(land, b.battlefield)

    def test_six_each(self):
        g, a, b = game()
        theirs = [creature(g, b, f"E{i}", 1, 1) for i in range(7)]
        mine = [creature(g, a, f"M{i}", 1, 1) for i in range(3)]
        cast(g, a, HEX, [None])
        self.assertEqual(len([x for x in theirs if x in b.battlefield]), 1)
        self.assertEqual([x for x in mine if x in a.battlefield], [])


class Fractions(unittest.TestCase):
    def test_half_rounded_up_and_down_is_each_players_own_count(self):
        for way, left in (("up", 2), ("down", 3)):
            g, a, b = game()
            for i in range(5):
                creature(g, b, f"E{i}", 1, 1)
            mine = [creature(g, a, f"M{i}", 1, 1) for i in range(2)]
            c = card("Test Half", "{B}", "Sorcery", f"Each opponent sacrifices half the creatures they control, "
                                                   f"rounded {way}.")
            self.assertEqual(c.unsupported, [])
            cast(g, a, c, [None])
            self.assertEqual(len(b.creatures), left, way)
            self.assertEqual(len([x for x in mine if x in a.battlefield]), 2)

    def test_x_is_not_read(self):
        self.assertTrue(card("Test Break", "{X}{R}{R}", "Sorcery", "Each player sacrifices X lands.").unsupported)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()
