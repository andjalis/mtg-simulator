"""#627: name locks choose from public information only (mtgsim.cx_name_lock), and Disruptor Flute's "Spells with the
chosen name cost {3} more to cast"."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cx_name_lock import lock_name
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, MOUNTAIN, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

BOLT = card("Bolt", "{R}", "Instant", "Bolt deals 3 damage to any target.")
DRAGON = card("Dragon", "{4}{R}{R}", "Creature — Dragon", "Flying", 5, 5)
SECRET = card("Secret Bomb", "{5}{B}{B}", "Sorcery", "Each opponent loses 10 life.")
FLUTE = card("Test Flute", "{3}", "Artifact", "As ~ enters, choose a card name.\nSpells with the chosen name cost {3} "
                                               "more to cast.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class Names(unittest.TestCase):
    def test_public_cards_weighted_by_threat(self):
        g, a, b = game()
        b.graveyard = [BOLT, BOLT]                      # weight 2 x (1 + 1)
        g.enter_battlefield(b, DRAGON)                  # weight 1 + 6 + 5
        g.enter_battlefield(b, MOUNTAIN)                # lands are not named
        self.assertEqual(lock_name(g, a), "Dragon")

    def test_the_opponents_hidden_hand_and_library_do_not_matter(self):
        picks = []
        for hidden in ([], [SECRET] * 7):
            g, a, b = game()
            b.graveyard = [BOLT]
            b.hand = list(hidden)
            b.library = list(hidden) + [ISLAND] * 3
            b.deck = list(hidden) + [BOLT] * 4
            picks.append(lock_name(g, a))
        self.assertEqual(picks, ["Bolt", "Bolt"])

    def test_nothing_public_names_nothing(self):
        g, a, b = game()
        b.hand = [SECRET] * 7
        b.deck = [SECRET] * 20
        self.assertEqual(lock_name(g, a), "")


class Flute(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(FLUTE.unsupported, [])
        self.assertEqual(FLUTE.advanced_rules["named_tax"], 3)
        stray = card("Test Odd", "{1}", "Artifact", "Spells with the chosen name cost {3} more to cast.")
        self.assertTrue(stray.unsupported)              # no name is chosen: nothing to read

    def test_the_named_spell_costs_three_more(self):
        g, a, b = game()
        b.graveyard = [BOLT]
        flute = g.enter_battlefield(a, FLUTE)
        g.settle()
        self.assertEqual(flute.chosen_name, "Bolt")
        self.assertEqual(g.cost_of(b, BOLT).get("generic", 0), 3)
        self.assertEqual(g.cost_of(b, DRAGON).get("generic", 0), 4)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_flute_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        self.assertEqual(card_coverage(db.get("Disruptor Flute")).status, "full")


if __name__ == "__main__":
    unittest.main()
