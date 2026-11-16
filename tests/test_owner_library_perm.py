"""#632: a permanent put into its owner's library: "the owner of target X shuffles it into their library", "~'s owner
shuffles it ...", "... puts it into their library second from the top or on the bottom", "Nth from the top", "target
permanent you own on the bottom of your library" (mtgsim.cx_grammar_ownerlib, kind cx_tuck)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Blitz Hellion", "Cerulean Sphinx", "Deem Inferior", "Happy Hogan, Bodyguard", "Lightning Shrieker",
        "Lost Days", "Lost to Legend", "Tel-Jilad Stylus", "Temporal Cleansing", "Trickster's Stratagem")
OWNER_SHUFFLE = card("Test Parting", "{3}{G}", "Sorcery",
                     "The owner of target artifact or creature an opponent controls shuffles it into their library.")
SECOND = card("Test Deem", "{3}{U}", "Instant", "The owner of target nonland permanent puts it into their library "
                                                "second from the top or on the bottom.")
FOURTH = card("Test Legend", "{3}{U}", "Instant", "Put target creature into its owner's library fourth from the top.")
LEGEND = card("Test Lost", "{2}{U}", "Instant",
              "Put target nonland historic permanent into its owner's library fourth from the top.")
BEAR = card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
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
        for c in (OWNER_SHUFFLE, SECOND, FOURTH, LEGEND):
            self.assertEqual(c.unsupported, [], c.name)
        e = OWNER_SHUFFLE.spell_effects[0]
        self.assertEqual((e.kind, e.data["where"], e.data["selector"]["controller"]), ("cx_tuck", "shuffle", "opp"))
        e = LEGEND.spell_effects[0]          # a noun the older tuck wordings don't list: the Nth-from-the-top verb
        self.assertEqual((e.kind, e.data["where"], e.data["side"]), ("cx_tuck", 4, "theirs"))

    def test_refusals(self):
        for text in ("Put enchanted creature into its owner's library third from the top.",
                     "Put all creatures into their owners' libraries third from the top.",
                     "The owner of target nonland permanent shuffles it into their library, then draws two cards.",
                     "Put target spell or nonland permanent into its owner's library second from the top.",
                     "Put target creature into its owner's library twelfth from the top.",
                     "Put target creature into its owner's library third from the top until end of turn."):
            self.assertTrue(card("Test Odd", "{U}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def test_owner_shuffles_the_opponents_creature_away(self):
        g, a, b = game()
        mine = g.enter_battlefield(a, OGRE)
        theirs = g.enter_battlefield(b, BEAR)
        targets = cast(g, a, OWNER_SHUFFLE)
        self.assertIs(targets[0], theirs)
        self.assertIn(mine, a.battlefield)
        self.assertNotIn(theirs, b.battlefield)
        self.assertEqual((len(b.library), b.graveyard), (11, []))

    def test_second_from_the_top_is_the_owners_choice(self):
        g, a, b = game()
        theirs = g.enter_battlefield(b, OGRE)
        targets = cast(g, a, SECOND)
        self.assertIs(targets[0], theirs)
        self.assertEqual(b.library[-2].name, "Ogre")           # the library's end is its top
        self.assertEqual(b.graveyard, [])

    def test_fourth_from_the_top(self):
        g, a, b = game()
        g.enter_battlefield(b, OGRE)
        cast(g, a, FOURTH)
        self.assertEqual(b.library[-4].name, "Ogre")

    def test_nth_verb_on_a_historic_permanent(self):
        g, a, b = game()
        relic = g.enter_battlefield(b, card("Test Relic", "{3}", "Legendary Artifact", "{T}: Draw a card."))
        targets = cast(g, a, LEGEND)
        self.assertIs(targets[0], relic)
        self.assertEqual(b.library[-4].name, "Test Relic")


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

    def test_blitz_hellion_goes_back_at_the_end_step(self):
        g, a, b = game()
        hellion = g.enter_battlefield(a, self.db.get("Blitz Hellion"))
        g.settle()
        g.step = "end"
        g.fire(a, "end_step")
        g.settle()
        self.assertNotIn(hellion, a.battlefield)
        self.assertEqual(len(a.library), 11)
        self.assertEqual(a.graveyard, [])

    def test_tel_jilad_stylus_only_targets_what_we_own(self):
        g, a, b = game()
        stylus = g.enter_battlefield(a, self.db.get("Tel-Jilad Stylus"))
        theirs = g.enter_battlefield(b, OGRE)
        g.settle()
        effects = stylus.activated[0].effects
        with g.targeting(stylus):
            targets = g.auto_targets(a, list(effects), None)
        self.assertIsNot(targets[0], theirs)


if __name__ == "__main__":
    unittest.main()
