"""#564: 'destroy / exile another target ...' keeps 'another' (a parser rewrite used to drop it), so blinks and
O-Ring style exiles can't target their own source (Eldrazi Displacer, Hostage Taker, Angel of Condemnation)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card


def other(eff):
    sel = eff.data.get("selector")
    return bool(eff.data.get("other") or (isinstance(sel, dict) and sel.get("other")))


class AnotherKept(unittest.TestCase):
    def test_wordings_keep_other(self):
        for text in ("Exile another target creature, then return it to the battlefield tapped under its owner's "
                     "control.",
                     "Exile another target creature. Return that card to the battlefield under its owner's control "
                     "at the beginning of the next end step.",
                     "Destroy another target creature."):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [], text)
            targeted = [e for e in effects if e.target != "none"]
            self.assertTrue(targeted and all(other(e) for e in targeted), text)

    @unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Eldrazi Displacer", "Soulherder", "Hostage Taker", "Angel of Condemnation", "Galepowder Mage",
                     "Distinguished Conjurer", "Emiel the Blessed", "Wispweaver Angel", "Nephalia Smuggler",
                     "Roon of the Hidden Realm", "Lilysplash Mentor"):
            c = db.get(name)
            self.assertEqual(c.unsupported, [], name)
            effs = [e for t in c.triggers for e in t.effects] + [e for a in c.activated for e in a.effects]
            hits = [e for e in effs if e.kind in ("blink", "blink_next_end", "oring", "blink_link_exile")]
            self.assertTrue(hits and all(other(e) for e in hits), name)

    @unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
    def test_displacer_cannot_blink_itself(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 1, "main1"
        a.library = b.library = [ISLAND] * 10
        displacer = g.enter_battlefield(a, db.get("Eldrazi Displacer"))
        bear = g.enter_battlefield(b, card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        eff = next(e for e in displacer.activated[0].effects if e.kind == "blink")
        with g.targeting(StackItem(a, [eff], [None], source=displacer, kind="ability")):
            legal = g.legal_targets(a, eff)
        self.assertNotIn(displacer, legal)
        self.assertIn(bear, legal)
        taker = db.get("Hostage Taker")
        eff = next(e for e in taker.triggers[0].effects if e.kind == "oring")
        host = g.enter_battlefield(a, taker)
        g.settle()
        with g.targeting(StackItem(a, [eff], [None], source=host, kind="trigger")):
            self.assertNotIn(host, g.legal_targets(a, eff))


if __name__ == "__main__":
    unittest.main()
