"""#874: "If that spell would be put into your graveyard, exile it instead" after a graveyard cast. The rider used to
be a trigger queued above the cast spell, so it resolved first and the spell still went to the graveyard (only a
direct Game.resolve, which settles the cast at once, hid it). It now travels with the card into the spell's own
move after resolving."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Rider(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0
        self.a.my_turn, self.b.my_turn = True, False
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_dreadhorde_arcanist_exiles_the_spell(self):
        arcanist = self.game.enter_battlefield(self.a, db("Dreadhorde Arcanist"))
        arcanist.sick = False
        self.a.graveyard = [db("Lightning Bolt")]
        self.a.ai.choose_attackers = lambda *_: [arcanist]
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 16)                                  # Bolt for 3, Arcanist for 1
        self.assertEqual([c.name for c in self.a.exile], ["Lightning Bolt"])
        self.assertEqual(self.a.graveyard, [])                             # not back for the next attack

    def test_no_rider_still_goes_to_the_graveyard(self):
        from mtgsim.cards import _parse_effects
        from mtgsim.engine import StackItem
        effects, _ = _parse_effects("You may cast target instant card from your graveyard without paying its mana cost.")
        self.a.graveyard = [db("Lightning Bolt")]
        self.game.stack.append(StackItem(self.a, effects, [None], name="test"))
        self.game.resolve_top()
        self.game.settle()
        self.assertEqual([c.name for c in self.a.graveyard], ["Lightning Bolt"])
        self.assertEqual(self.game.__dict__.get("gy_cast_riders", {}), {})


if __name__ == "__main__":
    unittest.main()
