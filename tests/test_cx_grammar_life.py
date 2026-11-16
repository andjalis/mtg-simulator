"""#629: life totals set to a number, read by #760's mtgsim.life_total (kind life_total), extended here with "each
player's life total becomes the lowest / highest life total among all players" and "double its controller's life
total"."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Arbiter of Knollridge", "The Darkhold", "Beacon of Immortality", "Blessed Wind", "Celestial Mantle", "Form of the Dinosaur",
        "Live Long and Prosper", "Magister Sphinx", "Repay in Kind", "Revival // Revenge", "Vraska, Relic Seeker")
DOUBLE = card("Test Beacon", "{3}{W}", "Instant", "Double target player's life total.")
SET10 = card("Test Sphinx", "{3}{U}", "Sorcery", "Target player's life total becomes 10.")
SET20 = card("Test Wind", "{7}{W}", "Sorcery", "Target player's life total becomes 20.")
LOWEST = card("Test Repay", "{5}{B}{B}", "Sorcery", "Each player's life total becomes the lowest life total among "
                                                    "all players.")
HIGHEST = card("Test Arbiter", "{5}{W}", "Sorcery", "Each player's life total becomes the highest life total among "
                                                     "all players.")
MANTLE = card("Test Mantle", "{3}{W}", "Enchantment — Aura", "Enchant creature\nWhenever enchanted creature deals "
              "combat damage to a player, double its controller's life total.")
LIFELINK_FAN = card("Test Fan", "{1}", "Creature — Human", "Whenever you gain life, put a +1/+1 counter on ~.", 1, 1)


def game(mine=20, theirs=20):
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    a.life, b.life = mine, theirs
    return g, a, b


def cast(g, p, c, targets=None):
    effects = list(c.spell_effects)
    targets = g.auto_targets(p, effects, None) if targets is None else targets
    g.stack.append(StackItem(p, effects, targets, card=c, name=c.name))
    g.resolve_top()
    g.settle()
    return targets


class Parse(unittest.TestCase):
    def test_shapes(self):
        for c in (DOUBLE, SET10, SET20, LOWEST, MANTLE):
            self.assertEqual(c.unsupported, [], c.name)
        e = SET10.spell_effects[0]
        self.assertEqual((e.kind, e.amount, e.data["op"]), ("life_total", 10, "set"))
        self.assertEqual(LOWEST.spell_effects[0].data, {"op": "lowest", "who": "each"})
        self.assertEqual(HIGHEST.spell_effects[0].data, {"op": "highest", "who": "each"})
        self.assertEqual(DOUBLE.spell_effects[0].data["op"], "double")

    def test_refusals(self):
        for text in ("Target player's life total becomes 10 until end of turn.",
                     "Each player's life total becomes the number of creatures they control.",
                     "Triple target player's life total.",
                     "Each opponent's life total becomes the lowest life total among all players."):
            self.assertTrue(card("Test Odd", "{W}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def test_double_targets_ourselves(self):
        g, a, b = game(12, 20)
        targets = cast(g, a, DOUBLE)
        self.assertIs(targets[0], a)
        self.assertEqual((a.life, b.life), (24, 20))

    def test_becomes_ten_targets_the_opponent(self):
        g, a, b = game(20, 20)
        targets = cast(g, a, SET10)
        self.assertIs(targets[0], b)
        self.assertEqual((a.life, b.life), (20, 10))

    def test_becomes_twenty_from_seven_targets_ourselves(self):
        g, a, b = game(7, 20)
        targets = cast(g, a, SET20)
        self.assertIs(targets[0], a)
        self.assertEqual(a.life, 20)

    def test_lowest(self):
        g, a, b = game(20, 5)
        cast(g, a, LOWEST, [None])
        self.assertEqual((a.life, b.life), (5, 5))

    def test_highest(self):
        g, a, b = game(5, 14)
        cast(g, a, HIGHEST, [None])
        self.assertEqual((a.life, b.life), (14, 14))

    def test_setting_life_is_gaining_it(self):
        g, a, b = game(7, 20)
        fan = g.enter_battlefield(a, LIFELINK_FAN)
        g.settle()
        cast(g, a, SET20, [a])
        self.assertEqual(a.life, 20)
        self.assertEqual(fan.p1, 1)                  # "whenever you gain life" saw the gain (CR 119.5)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)

    def test_celestial_mantle_doubles_the_enchanted_creatures_controller(self):
        from tests.test_combat_triggers import Scripted
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        a.life = 12
        bear = g.enter_battlefield(a, card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        bear.sick = False
        for _ in range(4):
            g.enter_battlefield(a, card("Test Plains", "", "Land", "{T}: Add {W}."))
        g.settle()
        a.hand = [MANTLE]
        self.assertTrue(g.cast(a, MANTLE, [bear]))
        g.settle()
        a.ai.attack, b.ai.block = [bear], {}
        g.combat(a, b)
        g.settle()
        self.assertEqual((a.life, b.life), (24, 18))

    def test_magister_sphinx_etb(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        g, a, b = game(20, 20)
        g.enter_battlefield(a, db.get("Magister Sphinx"))
        g.settle()
        self.assertEqual((a.life, b.life), (20, 10))


if __name__ == "__main__":
    unittest.main()
