"""#631: "reveals their hand and discards all <X> cards" and "chooses a card in their hand and discards the rest"
(mtgsim.cx_hand_hits, discard_choice with data["all"])."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Amnesia", "Shatter Assumptions", "Trapfinder's Trick", "Monomania")
AMNESIA = card("Test Amnesia", "{3}{U}{U}{U}", "Sorcery", "Target player reveals their hand and discards all nonland "
                                                         "cards.")
MULTI = card("Test Shatter", "{1}{B}", "Sorcery", "Target opponent reveals their hand and discards all multicolored "
                                                  "cards.")
MONO = card("Test Monomania", "{3}{B}{B}", "Sorcery", "Target player chooses a card in their hand and discards the "
                                                      "rest.")
BOLT = card("Bolt", "{R}", "Instant", "Bolt deals 3 damage to any target.")
GOLD = card("Gold", "{W}{U}", "Instant", "Draw a card.")
DRAGON = card("Dragon", "{5}{R}", "Creature — Dragon", "Flying", 5, 5)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


def cast(g, p, c, targets=None):
    effects = list(c.spell_effects)
    targets = g.auto_targets(p, effects, None) if targets is None else targets
    g.stack.append(StackItem(p, effects, targets, card=c, name=c.name))
    g.resolve_top()
    return targets


class Parse(unittest.TestCase):
    def test_shapes(self):
        for c in (AMNESIA, MULTI, MONO):
            self.assertEqual(c.unsupported, [], c.name)
        e = AMNESIA.spell_effects[0]
        self.assertEqual((e.kind, e.filter, e.data), ("discard_choice", "nonland", {"all": True}))
        self.assertEqual(MONO.spell_effects[0].data, {"all": True, "keep": 1})

    def test_refusals(self):
        for text in ("Target player reveals their hand and discards all cards with flash.",
                     "Target player reveals their hand and discards all nonland cards unless they pay 3 life and "
                     "sacrifice a land."):
            self.assertTrue(card("Test Odd", "{B}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def test_amnesia_discards_every_nonland_card_and_ai_aims_at_the_opponent(self):
        g, a, b = game()
        b.hand = [BOLT, ISLAND, DRAGON]
        a.hand = [BOLT]
        targets = cast(g, a, AMNESIA)
        self.assertIs(targets[0], b)
        self.assertEqual([c.name for c in b.hand], ["Island"])
        self.assertEqual(len(a.hand), 1)

    def test_multicolored_only(self):
        g, a, b = game()
        b.hand = [BOLT, GOLD]
        cast(g, a, MULTI, [b])
        self.assertEqual([c.name for c in b.hand], ["Bolt"])

    def test_monomania_keeps_their_best_card(self):
        g, a, b = game()
        b.hand = [BOLT, DRAGON, ISLAND]
        cast(g, a, MONO, [b])
        self.assertEqual([c.name for c in b.hand], ["Dragon"])


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
