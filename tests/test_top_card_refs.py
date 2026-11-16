"""#628: the looked-at top card when the first move didn't happen: "If you don't put the card into your hand, [you may]
put it ...", "Otherwise, ..." after a reveal-to-hand, and a reveal gated by "You may pay ... If you do, ..."
(mtgsim.cx_links)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Archghoul of Thraben", "Cabaretti Ascendancy", "Sarinth Steelseeker", "Territory Culler", "Traveling Botanist",
        "Risen Reef", "Wickerfolk Thresher", "N'Yami-Class Mother Ship", "Bucolic Ranch", "Vivien's Grizzly",
        "Lantern of Revealing", "Nylea, Keen-Eyed", "Skirk Drill Sergeant")

BEAR = card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
BOLT = card("Bolt", "{R}", "Instant", "Bolt deals 3 damage to any target.")
GOBLIN = card("Goblin", "{R}", "Creature — Goblin", "", 1, 1)

HAND_ELSE_BOTTOM = ("Look at the top card of your library. If it's a creature card, you may reveal it and put it into "
                    "your hand. If you don't put the card into your hand, you may put it on the bottom of your library.")
LAND_ELSE_HAND = ("Look at the top card of your library. If it's a land card, you may put it onto the battlefield tapped. "
                  "If you don't put the card onto the battlefield, put it into your hand.")


class Parse(unittest.TestCase):
    def test_positive(self):
        c = card("Test Look", "{G}", "Sorcery", HAND_ELSE_BOTTOM)
        self.assertEqual(c.unsupported, [])
        self.assertEqual([(e.kind, e.data.get("to")) for e in c.spell_effects],
                         [("peek_top", None), ("ref_move", "hand"), ("ref_move", "bottom")])
        self.assertTrue(c.spell_effects[2].cond.startswith('lib:["and","!'))

    def test_refusals(self):
        for text in (
            # the "if you don't" names a different move than the one before it
            "Look at the top card of your library. If it's a land card, you may put it into your hand. If you don't "
            "put the card onto the battlefield, put it into your graveyard.",
            # no looked-at card before it
            "Draw a card. If you don't put the card into your hand, put it into your graveyard.",
            # the reveal is gated by something else than a payment
            "Draw a card. If you do, reveal the top card of your library. If it's a land card, put it into your hand.",
        ):
            self.assertTrue(card("Test Odd", "{G}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.b.library = [ISLAND] * 10

    def resolve(self, text, top):
        c = card("Test Look", "{G}", "Sorcery", text)
        self.assertEqual(c.unsupported, [])
        self.a.library = [ISLAND, ISLAND, top]
        effects = list(c.spell_effects)
        self.g.stack.append(StackItem(self.a, effects, [None] * len(effects), card=c, name=c.name))
        self.g.resolve_top()

    def test_hit_goes_to_hand(self):
        self.resolve(HAND_ELSE_BOTTOM, BEAR)
        self.assertIn(BEAR, self.a.hand)
        self.assertNotIn(BEAR, self.a.library)

    def test_miss_goes_to_the_bottom(self):
        self.resolve(HAND_ELSE_BOTTOM, BOLT)
        self.assertEqual(self.a.library[0].name, "Bolt")
        self.assertNotIn(BOLT, self.a.hand)

    def test_land_enters_tapped_else_hand(self):
        self.resolve(LAND_ELSE_HAND, ISLAND)
        self.assertTrue(any(x.card.name == ISLAND.name and x.tapped for x in self.a.battlefield))
        self.resolve(LAND_ELSE_HAND, BOLT)
        self.assertIn(BOLT, self.a.hand)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.b.library = [ISLAND] * 10

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in FULL:
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_nylea_otherwise_graveyard(self):
        nylea = self.db.get("Nylea, Keen-Eyed")
        effects = list(nylea.activated[-1].effects)
        self.a.library = [ISLAND, BOLT]
        self.g.stack.append(StackItem(self.a, effects, [None] * len(effects), name="Nylea"))
        self.g.resolve_top()
        self.assertIn(BOLT, self.a.graveyard)
        self.a.library = [ISLAND, BEAR]
        self.g.stack.append(StackItem(self.a, effects, [None] * len(effects), name="Nylea"))
        self.g.resolve_top()
        self.assertIn(BEAR, self.a.hand)

    def test_skirk_unpaid_reveals_nothing(self):
        skirk = self.db.get("Skirk Drill Sergeant")
        effects = list(skirk.triggers[0].effects)
        self.a.library = [ISLAND, BOLT]          # no lands on the battlefield: {2}{R} can't be paid
        self.g.stack.append(StackItem(self.a, effects, [None] * len(effects), name="Skirk"))
        self.g.resolve_top()
        self.assertEqual(self.a.library, [ISLAND, BOLT])
        self.assertEqual(self.a.graveyard, [])
