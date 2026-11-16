"""#632: a card from a graveyard on top of / on the bottom of its owner's library (mtgsim.cx_grammar_gylib): "you may
put a <noun> card from your graveyard on top of your library" (a choice on resolution), "Then you may put ...", and
"... from an opponent's graveyard on the bottom of their library" (their library = the card's owner's)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Glowspore Shaman", "Halo-Charged Skaab", "Landscaper Colos", "Sequestered Stash")
TOP = card("Test Shaman", "{1}{G}", "Sorcery", "You may put a land card from your graveyard on top of your library.")
THEN = card("Test Stash", "{1}", "Sorcery", "Mill two cards. Then you may put an artifact card from your graveyard on "
                                            "top of your library.")
THEIR = card("Test Colos", "{1}{W}", "Sorcery",
             "Put target card from an opponent's graveyard on the bottom of their library.")
BEAR = card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
FOREST = card("Forest", "", "Basic Land — Forest", "")
OGRE = card("Ogre", "{4}{R}", "Creature — Ogre", "", 5, 5)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 10, [ISLAND] * 10
    return g, a, b


def cast(g, p, c):
    effects = list(c.spell_effects)
    targets = g.auto_targets(p, effects, None)
    g.stack.append(StackItem(p, effects, targets, card=c, name=c.name))
    g.resolve_top()
    g.settle()
    return targets


class Parse(unittest.TestCase):
    def test_shapes(self):
        for c in (TOP, THEN, THEIR):
            self.assertEqual(c.unsupported, [], c.name)
        inner = TOP.spell_effects[-1].data["effects"][0]
        self.assertEqual((inner.kind, inner.data["to"], inner.data["cx_card"]),
                         ("cx_card_choose", "library_top", {"types": ["land"]}))
        self.assertEqual([e.kind for e in THEN.spell_effects], ["mill", "pay_gate", "cx_players"])
        self.assertEqual(THEIR.spell_effects[0].data["to"], "library_bottom")

    def test_refusals(self):
        for text in ("You may put a land card from your graveyard on the bottom of your library.",
                     "Put up to three target cards from an opponent's graveyard on top of their library in any order.",
                     "You may put a land card from target player's graveyard on top of your library.",
                     "Then you may put a land card from your graveyard on top of your library until end of turn."):
            self.assertTrue(card("Test Odd", "{G}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def test_the_best_matching_card_goes_on_top(self):
        g, a, b = game()
        a.graveyard = [BEAR, FOREST, OGRE]
        cast(g, a, TOP)
        self.assertEqual(a.library[-1].name, "Forest")       # the library's end is its top
        self.assertEqual([c.name for c in a.graveyard], ["Bear", "Ogre", "Test Shaman"])

    def test_nothing_matching_does_nothing(self):
        g, a, b = game()
        a.graveyard = [BEAR]
        cast(g, a, TOP)
        self.assertEqual(len(a.library), 10)

    def test_opponents_card_goes_to_the_bottom_of_their_library(self):
        g, a, b = game()
        b.graveyard = [OGRE]
        a.graveyard = [BEAR]
        targets = cast(g, a, THEIR)
        self.assertEqual(targets[0].name, "Ogre")
        self.assertEqual(b.library[0].name, "Ogre")          # the library's start is its bottom
        self.assertEqual(b.graveyard, [])
        self.assertEqual(len(a.library), 10)


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
