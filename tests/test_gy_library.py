"""#632: graveyard cards shuffled into their owner's library (mtgsim.cx_gy_library, kind gy_to_library)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Archangel's Light", "Elixir of Immortality", "Feldon's Cane", "Mnemonic Nexus", "Rooting Kavu",
        "Stream of Thought", "Struggle // Survive", "The Mending of Dominaria")
# "up to N / any number of target cards": chosen on resolution, recorded as an approximation
SIMPLIFIED = ("Devious Cover-Up", "Perpetual Timepiece", "Piper's Melody", "Put Away", "Renewing Touch",
              "The Bath Song", "Wand of Vertebrae")
BEAR = card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
OGRE = card("Ogre", "{4}{R}", "Creature — Ogre", "", 5, 5)
BOLT = card("Bolt", "{R}", "Instant", "Bolt deals 3 damage to any target.")
ALL = card("Test Cane", "{1}", "Sorcery", "Shuffle your graveyard into your library.")
EACH = card("Test Nexus", "{3}{U}", "Instant", "Each player shuffles their graveyard into their library.")
CREATURES = card("Test Shaman", "{2}{G}", "Sorcery", "Shuffle all creature cards from your graveyard into your library.")
UPTO = card("Test Cover", "{1}{U}", "Sorcery", "Shuffle up to two target cards from your graveyard into your library.")
ANY = card("Test Touch", "{2}{G}", "Sorcery",
           "Shuffle any number of target creature cards from your graveyard into your library.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 10, [ISLAND] * 10
    a.graveyard, b.graveyard = [BEAR, OGRE, BOLT], [BEAR, BOLT]
    return g, a, b


def cast(g, p, c):
    effects = list(c.spell_effects)
    g.stack.append(StackItem(p, effects, g.auto_targets(p, effects, None), card=c, name=c.name))
    g.resolve_top()
    g.settle()


class Parse(unittest.TestCase):
    def test_shapes(self):
        for c, who, what, n in ((ALL, "you", "", None), (EACH, "each", "", None), (CREATURES, "you", "creature", None),
                                (UPTO, "you", "", 2), (ANY, "you", "creature", None)):
            self.assertEqual(c.unsupported, [], c.name)
            e = c.spell_effects[-1]
            self.assertEqual((e.kind, e.data["who"], e.data["what"], e.data["n"]), ("gy_to_library", who, what, n),
                             c.name)

    def test_refusals(self):
        for text in ("Shuffle all creature cards from target player's graveyard into that player's library.",
                     "Shuffle up to four target cards with mana value 3 or greater from your graveyard into your "
                     "library.",
                     "Shuffle all cards of the chosen type from your graveyard into your library.",
                     "Shuffle ~ and up to three target cards from a single graveyard into their owners' libraries.",
                     "Target player shuffles any number of target cards from their graveyard into their library."):
            self.assertTrue(card("Test Odd", "{U}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def test_moves_go_through_move_card(self):
        g, a, b = game()
        seen = []
        orig = g.move_card
        g.move_card = lambda card, src, dst, **kw: seen.append(kw.get("reason")) or orig(card, src, dst, **kw)
        cast(g, a, ALL)
        self.assertEqual(seen.count("gy_to_library"), 3)

    def test_all(self):
        g, a, b = game()
        cast(g, a, ALL)
        self.assertEqual((len(a.graveyard), len(a.library)), (1, 13))   # the spell itself goes to the graveyard
        self.assertEqual(len(b.graveyard), 2)

    def test_each_player(self):
        g, a, b = game()
        cast(g, a, EACH)
        self.assertEqual((len(a.library), len(b.library)), (13, 12))
        self.assertEqual(b.graveyard, [])

    def test_quality(self):
        g, a, b = game()
        cast(g, a, CREATURES)
        self.assertEqual([c.name for c in a.graveyard], ["Bolt", "Test Shaman"])

    def test_up_to_n_keeps_the_better_cards(self):
        g, a, b = game()
        cast(g, a, UPTO)
        self.assertEqual([c.name for c in a.graveyard], ["Ogre", "Test Cover"])
        self.assertEqual(len(a.library), 12)

    def test_any_number_takes_every_matching_card(self):
        g, a, b = game()
        cast(g, a, ANY)
        self.assertEqual([c.name for c in a.graveyard], ["Bolt", "Test Touch"])


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
        for name in SIMPLIFIED:
            self.assertEqual(card_coverage(self.db.get(name)).status, "simplified", name)

    def test_elixir_of_immortality_goes_back_with_the_graveyard(self):
        g, a, b = game()
        elixir = g.enter_battlefield(a, self.db.get("Elixir of Immortality"))
        for _ in range(2):
            g.enter_battlefield(a, self.db.get("Island"))
        g.settle()
        self.assertTrue(g.activate(a, elixir, "ability:0"))
        g.settle()
        self.assertNotIn(elixir, a.battlefield)
        self.assertEqual(a.graveyard, [])
        self.assertEqual(len(a.library), 14)
        self.assertIn("Elixir of Immortality", [c.name for c in a.library])
        self.assertEqual(a.life, 25)

    def test_feldons_cane_is_kept_until_the_library_runs_low(self):
        from mtgsim.engine.policy import ability_worth
        for library, used in ((30, False), (5, True)):
            g, a, b = game()
            a.library = [ISLAND] * library
            cane = g.enter_battlefield(a, self.db.get("Feldon's Cane"))
            g.settle()
            self.assertEqual(ability_worth(g, a, cane, 0), used, library)


if __name__ == "__main__":
    unittest.main()
