"""#346: looking at and reordering the top of a target player's library, mill choices from it, the optional
shuffle afterwards, and "put one into your hand and exile the rest" (Browse)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

LAND = card("Test Land", "", "Land", "")
SPELL = card("Test Spell", "{4}", "Sorcery", "Draw a card.")


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    return g, a, b


def run(g, p, effects, targets):
    g.stack.append(StackItem(p, list(effects), list(targets), kind="ability"))
    g.resolve_top()


class Parse(unittest.TestCase):
    def kinds(self, text):
        effects, bad = _parse_effects(text)
        return None if bad else [(e.kind, e.amount, e.amount2, e.target, e.filter) for e in effects]

    def test_shapes(self):
        self.assertEqual(self.kinds("Look at the top three cards of target player's library, then put them back in "
                                    "any order."), [("reorder_top", 3, 0, "player", "")])
        self.assertEqual(self.kinds("Look at the top five cards of target opponent's library, then put them back in "
                                    "any order."), [("reorder_top", 5, 0, "player", "opp")])
        self.assertEqual(self.kinds("Look at the top two cards of target player's library. Put one of them into their "
                                    "graveyard."), [("peek_mill", 2, 1, "player", "")])
        self.assertEqual(self.kinds("Look at the top three cards of target player's library. Put one back and the "
                                    "rest into that player's graveyard."), [("peek_mill", 3, 1, "player", "")])
        self.assertEqual(self.kinds("Look at the top five cards of your library, put one of them into your hand, and "
                                    "exile the rest."), [("dig_gy", 5, 1, "none", "")])

    def test_near_misses(self):
        for text in ("Look at the top three cards of target player's library, then put them on the bottom.",
                     "Look at the top three cards of target player's library. Put two of them into your hand.",
                     "Look at the top five cards of your library, put one of them into your hand, and exile the "
                     "rest face down."):
            self.assertIsNone(self.kinds(text), text)


class Engine(unittest.TestCase):
    def test_own_library_friendly_opponents_hostile(self):
        g, a, b = game()
        effects, _ = _parse_effects("Look at the top three cards of target player's library, then put them back in "
                                    "any order.")
        a.library = [ISLAND] * 5 + [SPELL, SPELL, LAND]           # a has no lands: it wants a land on top
        run(g, a, effects, [a])
        self.assertEqual(a.library[-1].name, LAND.name)
        b.library = [ISLAND] * 5 + [SPELL, LAND, SPELL]           # b wants a land too: it goes to the bottom
        run(g, a, effects, [b])
        self.assertNotEqual(b.library[-1].name, LAND.name)
        self.assertEqual(b.library[-3].name, LAND.name)
        self.assertEqual(len(b.library), 8)

    def test_that_player_orders_your_library(self):
        g, a, b = game()
        effects, bad = _parse_effects("That player looks at the top three cards of your library, then puts them back "
                                      "in any order.")
        self.assertEqual(bad, [])
        a.library = [ISLAND] * 5 + [SPELL, LAND, SPELL]
        run(g, a, effects, [None])
        self.assertEqual(a.library[-3].name, LAND.name)                        # ordered against a: the wanted land at the bottom

    def test_peek_mill_takes_their_best(self):
        g, a, b = game()
        effects, _ = _parse_effects("Look at the top two cards of target player's library. Put one of them into their "
                                    "graveyard.")
        b.library = [ISLAND] * 5 + [SPELL, LAND]
        run(g, a, effects, [b])
        self.assertEqual([c.name for c in b.graveyard], [LAND.name])                     # the land b wanted is milled
        self.assertEqual(b.library[-1].name, SPELL.name)
        self.assertEqual(len(b.library), 6)

    def test_peek_mill_short_library(self):
        g, a, b = game()
        effects, _ = _parse_effects("Look at the top three cards of target player's library. Put one back and the "
                                    "rest into that player's graveyard.")
        b.library = [SPELL]
        run(g, a, effects, [b])
        self.assertEqual(([c.name for c in b.library], b.graveyard), ([SPELL.name], []))

    def test_browse_exiles_the_rest(self):
        g, a, b = game()
        effects, _ = _parse_effects("Look at the top five cards of your library, put one of them into your hand, and "
                                    "exile the rest.")
        a.library = [ISLAND] * 3 + [LAND, LAND, SPELL, LAND, LAND]
        a.hand = []
        run(g, a, effects, [None])
        self.assertEqual(len(a.hand), 1)
        self.assertEqual(len(a.exile), 4)
        self.assertEqual(len(a.library), 3)
        self.assertEqual(a.graveyard, [])

    def test_shuffle_only_when_the_top_helps_them(self):
        g, a, b = game()
        effects, _ = _parse_effects("Look at the top five cards of target player's library. You may then have that "
                                    "player shuffle that library.")
        b.library = [SPELL] * 5 + [LAND] * 5                      # b wants lands: the top is good for b
        before = list(b.library)
        run(g, a, effects, [b, None, None])
        self.assertNotEqual(b.library, before)                    # shuffled
        b.library = [LAND] * 5 + [SPELL] * 5
        before = list(b.library)
        run(g, a, effects, [b, None, None])
        self.assertEqual(b.library, before)                       # left alone

    def test_ai_sides(self):
        g, a, b = game()
        for text, who in (("Look at the top three cards of target player's library, then put them back in any "
                           "order.", a),
                          ("Look at the top two cards of target player's library. Put one of them into their "
                           "graveyard.", b),
                          ("Look at the top five cards of target player's library.", b)):
            effects, _ = _parse_effects(text)
            self.assertIs(g.auto_targets(a, effects)[0], who, text)


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Architects of Will", "Elemental Augury", "Natural Selection", "Portent", "Second Sight",
                     "Tahngarth's Glare", "Browse", "Wu Spy", "Dimir Charm", "Cruel Fate", "Visions", "Orcish Spy"):
            self.assertEqual(db.get(name).unsupported, [], name)

    def test_architects_trigger_in_game(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        g, a, b = game()
        a.library = [ISLAND] * 5 + [SPELL, SPELL, LAND]
        g.enter_battlefield(a, db.get("Architects of Will"))
        g.settle()
        self.assertEqual(a.library[-1].name, LAND.name)


if __name__ == "__main__":
    unittest.main()
