"""#546: "Return X target cards" / "another target ... card" / "all cards" from a graveyard: the count word or
"another" must not end up as the card description (which matched no card, so the cards returned nothing)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class GraveyardReturns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def game(self, land, n, graveyard):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [self.db.get("Island")] * 10
        for _ in range(n):
            g.enter_battlefield(a, self.db.get(land)).sick = False
        a.graveyard = [self.db.get(x) for x in graveyard]
        g.settle()
        return g, a, b

    def test_parse(self):
        for name in ("Wildest Dreams", "Junk Diver", "Myr Retriever", "Elderfang Ritualist", "Praetor's Counsel",
                     "Restock", "Eerie Soultender", "Spectral Steel"):
            self.assertEqual(self.db.get(name).unsupported, [], name)
        moves = [e for e in self.db.get("Wildest Dreams").spell_effects if e.kind == "gy_move"]
        self.assertEqual(len(moves), 1)
        self.assertTrue(moves[0].data["x_n"])
        self.assertEqual(moves[0].data["what"], "")
        for name in ("Junk Diver", "Restock"):
            c = self.db.get(name)
            effs = list(c.spell_effects) + [e for t in c.triggers for e in t.effects]
            self.assertFalse(any(e.kind == "gy_move" for e in effs), name)      # targeted: cx_card_move
            self.assertTrue(any(e.kind == "cx_card_move" for e in effs), name)

    def test_near_misses(self):
        effs, bad = _parse_effects("Return target card from your graveyard to your hand.")
        self.assertFalse(any(e.kind == "gy_move" and e.data.get("what") == "target" for e in effs))
        effs, bad = _parse_effects("Return a card from your graveyard to your hand.")
        self.assertFalse(any(e.kind == "gy_move" and not e.data.get("what") for e in effs))   # not widened

    def test_wildest_dreams_returns_x_cards(self):
        g, a, _ = self.game("Forest", 5, ["Grizzly Bears", "Llanowar Elves", "Giant Growth"])
        dreams = self.db.get("Wildest Dreams")
        item = StackItem(a, list(dreams.spell_effects), [None] * len(dreams.spell_effects), card=dreams, name=dreams.name)
        item.x = 2
        g.stack.append(item)
        g.resolve_top()
        g.settle()
        self.assertEqual(sorted(c.name for c in a.hand), ["Grizzly Bears", "Llanowar Elves"])   # X=2: two of three
        self.assertEqual(len(a.graveyard), 1)

    def test_praetors_counsel_returns_all(self):
        g, a, _ = self.game("Forest", 8, ["Grizzly Bears", "Llanowar Elves", "Giant Growth", "Island"])
        counsel = self.db.get("Praetor's Counsel")
        a.hand.append(counsel)
        self.assertTrue(g.cast(a, counsel))
        g.settle()
        self.assertEqual(sorted(c.name for c in a.hand),
                         ["Giant Growth", "Grizzly Bears", "Island", "Llanowar Elves"])
        self.assertEqual(a.graveyard, [])

    def test_junk_diver_returns_another_artifact(self):
        g, a, b = self.game("Island", 0, ["Ornithopter", "Grizzly Bears"])
        diver = g.enter_battlefield(a, self.db.get("Junk Diver"))
        g.settle()
        g.destroy(diver) if hasattr(g, "destroy") else g.leave_battlefield(diver, "graveyard")
        g.settle()
        self.assertIn("Ornithopter", [c.name for c in a.hand])
        self.assertIn("Junk Diver", [c.name for c in a.graveyard])         # not itself

    def test_ai_casts_wildest_dreams(self):
        g, a, _ = self.game("Forest", 5, ["Craw Wurm", "Hill Giant", "Giant Growth"])
        a.hand = [self.db.get("Wildest Dreams")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertIn("Wildest Dreams", [c.name for c in a.exile])
        self.assertIn("Craw Wurm", [c.name for c in a.hand])                # highest mana value first


if __name__ == "__main__":
    unittest.main()
